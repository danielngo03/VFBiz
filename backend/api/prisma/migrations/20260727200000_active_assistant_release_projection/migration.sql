CREATE TABLE "active_assistant_release_projection" (
  "assistantProfile" VARCHAR(40) NOT NULL,
  "environment" VARCHAR(24) NOT NULL,
  "activationId" VARCHAR(160) NOT NULL,
  "graphRevision" VARCHAR(160) NOT NULL,
  "policyRevision" VARCHAR(160) NOT NULL,
  "knowledgeRevision" VARCHAR(160) NOT NULL,
  "manifestSha256" CHAR(64) NOT NULL,
  "activationEnvelopeSha256" CHAR(64) NOT NULL,
  "pointerRevision" BIGINT NOT NULL,
  "effectiveAt" TIMESTAMPTZ(6) NOT NULL,
  "expiresAt" TIMESTAMPTZ(6) NOT NULL,
  "status" VARCHAR(24) NOT NULL,
  "signingKeyId" VARCHAR(160) NOT NULL,
  "signedEnvelope" JSONB NOT NULL,
  "signature" TEXT NOT NULL,
  "projectedAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ(6) NOT NULL,
  CONSTRAINT "active_assistant_release_projection_pkey"
    PRIMARY KEY ("assistantProfile", "environment"),
  CONSTRAINT "active_assistant_release_projection_window"
    CHECK ("expiresAt" > "effectiveAt"),
  CONSTRAINT "active_assistant_release_projection_pointer"
    CHECK ("pointerRevision" > 0),
  CONSTRAINT "active_assistant_release_projection_digests"
    CHECK (
      "manifestSha256" ~ '^[a-f0-9]{64}$'
      AND "activationEnvelopeSha256" ~ '^[a-f0-9]{64}$'
    ),
  CONSTRAINT "active_assistant_release_projection_status"
    CHECK ("status" IN ('active', 'revoked'))
);

CREATE INDEX "active_assistant_release_projection_status_effectiveAt_expiresAt_idx"
  ON "active_assistant_release_projection"("status", "effectiveAt", "expiresAt");

ALTER TABLE "conversation_session"
  ADD COLUMN "assistantReleaseActivationId" VARCHAR(160),
  ADD COLUMN "assistantReleaseGraphRevision" VARCHAR(160),
  ADD COLUMN "assistantReleaseKnowledgeRevision" VARCHAR(160),
  ADD COLUMN "assistantReleaseManifestSha256" CHAR(64),
  ADD COLUMN "assistantReleaseEnvelopeSha256" CHAR(64),
  ADD COLUMN "assistantReleasePointerRevision" BIGINT,
  ADD COLUMN "assistantReleaseEffectiveAt" TIMESTAMPTZ(6),
  ADD COLUMN "assistantReleaseExpiresAt" TIMESTAMPTZ(6);

-- Existing sessions predate release authority and stay unreadable by the new
-- dispatcher until they expire. No release identity is fabricated.
ALTER TABLE "conversation_session"
  ADD CONSTRAINT "conversation_session_release_binding_complete"
  CHECK (
    (
      "assistantReleaseActivationId" IS NULL
      AND "assistantReleaseGraphRevision" IS NULL
      AND "assistantReleaseKnowledgeRevision" IS NULL
      AND "assistantReleaseManifestSha256" IS NULL
      AND "assistantReleaseEnvelopeSha256" IS NULL
      AND "assistantReleasePointerRevision" IS NULL
      AND "assistantReleaseEffectiveAt" IS NULL
      AND "assistantReleaseExpiresAt" IS NULL
    )
    OR
    (
      "assistantReleaseActivationId" IS NOT NULL
      AND "assistantReleaseGraphRevision" IS NOT NULL
      AND "assistantReleaseKnowledgeRevision" IS NOT NULL
      AND "assistantReleaseManifestSha256" ~ '^[a-f0-9]{64}$'
      AND "assistantReleaseEnvelopeSha256" ~ '^[a-f0-9]{64}$'
      AND "assistantReleasePointerRevision" > 0
      AND "assistantReleaseExpiresAt" > "assistantReleaseEffectiveAt"
    )
  );
