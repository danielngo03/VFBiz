-- DSAR target registry and append-only execution evidence.

CREATE TYPE "customer_data_request_target_state" AS ENUM (
  'pending',
  'processing',
  'completed',
  'retry_required',
  'legally_retained',
  'permanent_failure'
);

ALTER TABLE "customer_data_request"
  ADD COLUMN "policyRevision" VARCHAR(80) NOT NULL DEFAULT 'dsar-policy-v1',
  ADD COLUMN "targetSetRevision" VARCHAR(80) NOT NULL DEFAULT 'dsar-targets-v1',
  ADD COLUMN "finalizedAt" TIMESTAMPTZ(6),
  ADD COLUMN "nextReconcileAt" TIMESTAMPTZ(6);

CREATE TABLE "customer_data_request_target" (
  "id" UUID NOT NULL,
  "requestId" UUID NOT NULL,
  "targetKey" VARCHAR(80) NOT NULL,
  "targetVersion" VARCHAR(40) NOT NULL,
  "phase" INTEGER NOT NULL,
  "state" "customer_data_request_target_state" NOT NULL DEFAULT 'pending',
  "attemptCount" INTEGER NOT NULL DEFAULT 0,
  "maxAttempts" INTEGER NOT NULL DEFAULT 5,
  "availableAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "claimOwner" VARCHAR(120),
  "leaseExpiresAt" TIMESTAMPTZ(6),
  "fencingToken" BIGINT NOT NULL DEFAULT 0,
  "lastErrorCode" VARCHAR(120),
  "lastAttemptAt" TIMESTAMPTZ(6),
  "evidenceCode" VARCHAR(120),
  "evidenceHash" CHAR(64),
  "artifactObjectRef" VARCHAR(255),
  "completedAt" TIMESTAMPTZ(6),
  "version" INTEGER NOT NULL DEFAULT 1,
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ(6) NOT NULL,
  CONSTRAINT "customer_data_request_target_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "customer_data_request_target_attempt_check"
    CHECK ("attemptCount" >= 0 AND "maxAttempts" > 0),
  CONSTRAINT "customer_data_request_target_phase_check" CHECK ("phase" > 0),
  CONSTRAINT "customer_data_request_target_evidence_hash_check"
    CHECK ("evidenceHash" IS NULL OR "evidenceHash" ~ '^[0-9a-f]{64}$')
);

CREATE TABLE "customer_data_request_event" (
  "id" UUID NOT NULL,
  "requestId" UUID NOT NULL,
  "targetId" UUID,
  "eventType" VARCHAR(100) NOT NULL,
  "outcomeCode" VARCHAR(120) NOT NULL,
  "evidenceHash" CHAR(64),
  "correlationId" UUID NOT NULL,
  "event_sequence" BIGSERIAL NOT NULL,
  "occurredAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "customer_data_request_event_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "customer_data_request_event_evidence_hash_check"
    CHECK ("evidenceHash" IS NULL OR "evidenceHash" ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX "customer_data_request_target_requestId_targetKey_key"
  ON "customer_data_request_target"("requestId", "targetKey");
CREATE INDEX "customer_data_request_target_due_idx"
  ON "customer_data_request_target"("state", "availableAt", "leaseExpiresAt");
CREATE INDEX "customer_data_request_target_request_phase_state_idx"
  ON "customer_data_request_target"("requestId", "phase", "state");
CREATE UNIQUE INDEX "customer_data_request_event_event_sequence_key"
  ON "customer_data_request_event"("event_sequence");
CREATE INDEX "customer_data_request_event_request_sequence_idx"
  ON "customer_data_request_event"("requestId", "event_sequence");
CREATE INDEX "customer_data_request_event_target_sequence_idx"
  ON "customer_data_request_event"("targetId", "event_sequence");

ALTER TABLE "customer_data_request_target"
  ADD CONSTRAINT "customer_data_request_target_requestId_fkey"
  FOREIGN KEY ("requestId") REFERENCES "customer_data_request"("id")
  ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "customer_data_request_event"
  ADD CONSTRAINT "customer_data_request_event_requestId_fkey"
  FOREIGN KEY ("requestId") REFERENCES "customer_data_request"("id")
  ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "customer_data_request_event"
  ADD CONSTRAINT "customer_data_request_event_targetId_fkey"
  FOREIGN KEY ("targetId") REFERENCES "customer_data_request_target"("id")
  ON DELETE SET NULL ON UPDATE CASCADE;
