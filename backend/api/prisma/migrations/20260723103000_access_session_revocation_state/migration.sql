ALTER TABLE "session_projection"
  ADD COLUMN "providerRoute" VARCHAR(80),
  ADD COLUMN "providerSessionSecretReference" VARCHAR(512),
  ADD COLUMN "observationRevision" BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN "observationObservedAt" TIMESTAMPTZ(6),
  ADD COLUMN "revocationIntentAt" TIMESTAMPTZ(6),
  ADD COLUMN "revocationState" VARCHAR(40) NOT NULL DEFAULT 'none',
  ADD COLUMN "revocationAttempt" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "revocationLastAttemptAt" TIMESTAMPTZ(6),
  ADD COLUMN "revocationNextRetryAt" TIMESTAMPTZ(6),
  ADD COLUMN "revocationLastErrorCode" VARCHAR(80),
  ADD COLUMN "revocationVersion" INTEGER NOT NULL DEFAULT 0;

ALTER TABLE "session_projection"
  ADD CONSTRAINT "session_projection_temporal_check"
    CHECK (
      "authenticatedAt" <= "lastSeenAt"
      AND "authenticatedAt" < "expiresAt"
      AND "lastSeenAt" < "expiresAt"
      AND ("observationObservedAt" IS NULL OR "lastSeenAt" <= "observationObservedAt" + INTERVAL '5 minutes')
      AND ("revokedAt" IS NULL OR "revokedAt" >= "authenticatedAt")
    ),
  ADD CONSTRAINT "session_projection_observation_revision_check"
    CHECK ("observationRevision" >= 0),
  ADD CONSTRAINT "session_projection_revocation_attempt_check"
    CHECK ("revocationAttempt" >= 0),
  ADD CONSTRAINT "session_projection_revocation_state_check"
    CHECK ("revocationState" IN ('none', 'pending', 'confirmed', 'retry_required', 'manual_review_required')),
  ADD CONSTRAINT "session_projection_provider_reference_check"
    CHECK (
      ("providerRoute" IS NULL AND "providerSessionSecretReference" IS NULL)
      OR (
        "providerRoute" = 'customer-ciam'
        AND "providerSessionSecretReference" LIKE 'secret://%'
      )
    );

CREATE INDEX "session_projection_revocationState_revocationNextRetryAt_idx"
  ON "session_projection"("revocationState", "revocationNextRetryAt");
