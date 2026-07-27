-- VFBIZ-0018: durable Conversation Runtime.
-- Existing conversation sessions intentionally receive no runtime row because
-- their budget, access and event history cannot be reconstructed safely.

ALTER TABLE "conversation_message"
  ADD COLUMN "contentEnvelope" JSONB,
  ADD COLUMN "contentKeyId" VARCHAR(64);
ALTER TABLE "conversation_message"
  ALTER COLUMN "sequence" TYPE BIGINT;

ALTER TABLE "conversation_session"
  ADD COLUMN "ownerSubjectKeyHash" CHAR(64);

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

UPDATE "conversation_session" session
SET "ownerSubjectKeyHash" = encode(
  digest(
    octet_length(identity."issuer")::TEXT || ':' || identity."issuer" ||
    octet_length(identity."subject")::TEXT || ':' || identity."subject",
    'sha256'
  ),
  'hex'
)
FROM "customer_profile" profile
JOIN "identity_subject" identity
  ON identity."id" = profile."identitySubjectId"
WHERE session."customerProfileId" = profile."id"
  AND session."assistantProfile" = 'authenticated_customer';

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM "conversation_session"
    WHERE "assistantProfile" = 'authenticated_customer'
      AND "ownerSubjectKeyHash" IS NULL
  ) THEN
    RAISE EXCEPTION
      'Authenticated conversation owner hash backfill is incomplete';
  END IF;
END
$$;

CREATE TABLE "conversation_subject_erasure_fence" (
  "subjectKeyHash" CHAR(64) NOT NULL,
  "deletionRequestId" UUID NOT NULL,
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "conversation_subject_erasure_fence_pkey"
    PRIMARY KEY ("subjectKeyHash")
);

CREATE UNIQUE INDEX "conversation_subject_erasure_fence_deletionRequestId_key"
  ON "conversation_subject_erasure_fence"("deletionRequestId");
CREATE INDEX "conversation_session_ownerSubjectKeyHash_retentionUntil_idx"
  ON "conversation_session"("ownerSubjectKeyHash", "retentionUntil");

CREATE TABLE "conversation_runtime" (
  "conversationSessionId" UUID NOT NULL,
  "version" BIGINT NOT NULL DEFAULT 0,
  "runtimeStatus" VARCHAR(24) NOT NULL DEFAULT 'open',
  "remainingModelTokens" BIGINT NOT NULL,
  "remainingCostMicros" BIGINT NOT NULL,
  "lastReceivedSequence" BIGINT NOT NULL DEFAULT 0,
  "lastPublicEventSequence" BIGINT NOT NULL DEFAULT 0,
  "fencingTokenHighWatermark" BIGINT NOT NULL DEFAULT 0,
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ(6) NOT NULL,
  CONSTRAINT "conversation_runtime_pkey" PRIMARY KEY ("conversationSessionId"),
  CONSTRAINT "conversation_runtime_status_check"
    CHECK ("runtimeStatus" IN ('open', 'handoff')),
  CONSTRAINT "conversation_runtime_counters_check"
    CHECK (
      "version" >= 0
      AND "remainingModelTokens" >= 0
      AND "remainingCostMicros" >= 0
      AND "lastReceivedSequence" >= 0
      AND "lastPublicEventSequence" >= 0
      AND "fencingTokenHighWatermark" >= 0
    )
);

CREATE TABLE "conversation_turn" (
  "id" UUID NOT NULL,
  "conversationSessionId" UUID NOT NULL,
  "customerMessageId" UUID NOT NULL,
  "clientMessageId" VARCHAR(160) NOT NULL,
  "requestFingerprintEnvelope" JSONB NOT NULL,
  "requestFingerprintKeyId" VARCHAR(64) NOT NULL,
  "receivedSequence" BIGINT NOT NULL,
  "acceptedVersion" BIGINT NOT NULL,
  "acceptedEventSequence" BIGINT NOT NULL,
  "status" VARCHAR(24) NOT NULL DEFAULT 'accepted',
  "cancellationAuthority" VARCHAR(16),
  "cancellationReason" VARCHAR(40),
  "cancelledAt" TIMESTAMPTZ(6),
  "maxModelTokens" BIGINT NOT NULL,
  "maxCostMicros" BIGINT NOT NULL,
  "usedModelTokens" BIGINT,
  "usedCostMicros" BIGINT,
  "workerId" VARCHAR(160),
  "fencingToken" BIGINT,
  "leaseExpiresAt" TIMESTAMPTZ(6),
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ(6) NOT NULL,
  CONSTRAINT "conversation_turn_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "conversation_turn_status_check"
    CHECK ("status" IN ('accepted', 'claimed', 'completed', 'cancelled', 'handed_off')),
  CONSTRAINT "conversation_turn_budget_check"
    CHECK (
      "receivedSequence" > 0
      AND "acceptedVersion" > 0
      AND "acceptedEventSequence" > 0
      AND "maxModelTokens" > 0
      AND "maxCostMicros" > 0
      AND ("usedModelTokens" IS NULL OR (
        "usedModelTokens" >= 0 AND "usedModelTokens" <= "maxModelTokens"
      ))
      AND ("usedCostMicros" IS NULL OR (
        "usedCostMicros" >= 0 AND "usedCostMicros" <= "maxCostMicros"
      ))
    ),
  CONSTRAINT "conversation_turn_claim_shape_check"
    CHECK (
      (
        "status" = 'claimed'
        AND "workerId" IS NOT NULL
        AND "fencingToken" IS NOT NULL
        AND "fencingToken" > 0
        AND "leaseExpiresAt" IS NOT NULL
      )
      OR
      (
        "status" <> 'claimed'
        AND "workerId" IS NULL
        AND "fencingToken" IS NULL
        AND "leaseExpiresAt" IS NULL
      )
    ),
  CONSTRAINT "conversation_turn_usage_shape_check"
    CHECK (
      (
        "status" IN ('accepted', 'claimed')
        AND "usedModelTokens" IS NULL
        AND "usedCostMicros" IS NULL
      )
      OR
      (
        "status" IN ('completed', 'cancelled', 'handed_off')
        AND "usedModelTokens" IS NOT NULL
        AND "usedCostMicros" IS NOT NULL
        AND "usedModelTokens" >= 0
        AND "usedModelTokens" <= "maxModelTokens"
        AND "usedCostMicros" >= 0
        AND "usedCostMicros" <= "maxCostMicros"
      )
    ),
  CONSTRAINT "conversation_turn_cancellation_shape_check"
    CHECK (
      (
        "status" = 'cancelled'
        AND "cancellationAuthority" IN ('customer', 'system', 'worker')
        AND "cancellationReason" IN (
          'budget_exhausted',
          'system_shutdown',
          'timeout',
          'user_interrupt'
        )
        AND (
          (
            "cancellationAuthority" = 'customer'
            AND "cancellationReason" = 'user_interrupt'
          )
          OR
          (
            "cancellationAuthority" IN ('system', 'worker')
            AND "cancellationReason" IN (
              'budget_exhausted',
              'system_shutdown',
              'timeout'
            )
          )
        )
        AND "cancelledAt" IS NOT NULL
      )
      OR
      (
        "status" <> 'cancelled'
        AND "cancellationAuthority" IS NULL
        AND "cancellationReason" IS NULL
        AND "cancelledAt" IS NULL
      )
    )
);

CREATE TABLE "conversation_public_event" (
  "id" UUID NOT NULL,
  "conversationSessionId" UUID NOT NULL,
  "conversationTurnId" UUID NOT NULL,
  "sequence" BIGINT NOT NULL,
  "schemaVersion" INTEGER NOT NULL,
  "type" VARCHAR(64) NOT NULL,
  "payloadEnvelope" JSONB NOT NULL,
  "payloadKeyId" VARCHAR(64) NOT NULL,
  "occurredAt" TIMESTAMPTZ(6) NOT NULL,
  "retentionUntil" TIMESTAMPTZ(6) NOT NULL,
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "conversation_public_event_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "conversation_public_event_sequence_check"
    CHECK ("sequence" > 0 AND "schemaVersion" = 1),
  CONSTRAINT "conversation_public_event_retention_check"
    CHECK ("retentionUntil" >= "occurredAt")
);

CREATE UNIQUE INDEX
  "conversation_turn_conversationSessionId_clientMessageId_key"
  ON "conversation_turn"("conversationSessionId", "clientMessageId");
CREATE UNIQUE INDEX
  "conversation_turn_conversationSessionId_receivedSequence_key"
  ON "conversation_turn"("conversationSessionId", "receivedSequence");
CREATE UNIQUE INDEX
  "conversation_turn_customerMessageId_key"
  ON "conversation_turn"("customerMessageId");
CREATE INDEX
  "conversation_turn_conversationSessionId_status_receivedSequ_idx"
  ON "conversation_turn"("conversationSessionId", "status", "receivedSequence");
CREATE UNIQUE INDEX
  "conversation_turn_one_claimed_per_session_key"
  ON "conversation_turn"("conversationSessionId")
  WHERE "status" = 'claimed';

CREATE UNIQUE INDEX
  "conversation_public_event_conversationSessionId_sequence_key"
  ON "conversation_public_event"("conversationSessionId", "sequence");
CREATE INDEX
  "conversation_public_event_conversationSessionId_occurredAt_idx"
  ON "conversation_public_event"("conversationSessionId", "occurredAt");
CREATE INDEX
  "conversation_public_event_payloadKeyId_idx"
  ON "conversation_public_event"("payloadKeyId");
ALTER TABLE "conversation_runtime"
  ADD CONSTRAINT "conversation_runtime_conversationSessionId_fkey"
  FOREIGN KEY ("conversationSessionId")
  REFERENCES "conversation_session"("id")
  ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "conversation_turn"
  ADD CONSTRAINT "conversation_turn_conversationSessionId_fkey"
  FOREIGN KEY ("conversationSessionId")
  REFERENCES "conversation_session"("id")
  ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "conversation_turn"
  ADD CONSTRAINT "conversation_turn_customerMessageId_fkey"
  FOREIGN KEY ("customerMessageId")
  REFERENCES "conversation_message"("id")
  ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "conversation_public_event"
  ADD CONSTRAINT "conversation_public_event_conversationSessionId_fkey"
  FOREIGN KEY ("conversationSessionId")
  REFERENCES "conversation_session"("id")
  ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "conversation_public_event"
  ADD CONSTRAINT "conversation_public_event_conversationTurnId_fkey"
  FOREIGN KEY ("conversationTurnId")
  REFERENCES "conversation_turn"("id")
  ON DELETE CASCADE ON UPDATE CASCADE;
