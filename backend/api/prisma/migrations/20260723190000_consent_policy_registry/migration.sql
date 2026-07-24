-- Governed consent policy registry and propagation prerequisites.

CREATE TYPE "consent_policy_state" AS ENUM ('draft', 'active', 'retired');

CREATE TABLE "consent_policy" (
  "id" UUID NOT NULL,
  "purpose" VARCHAR(100) NOT NULL,
  "policyVersion" VARCHAR(80) NOT NULL,
  "state" "consent_policy_state" NOT NULL DEFAULT 'draft',
  "contentChecksum" CHAR(64) NOT NULL,
  "approvedByRef" VARCHAR(160),
  "approvalEvidenceRef" VARCHAR(512),
  "approvedAt" TIMESTAMPTZ(6),
  "effectiveAt" TIMESTAMPTZ(6) NOT NULL,
  "expiresAt" TIMESTAMPTZ(6),
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ(6) NOT NULL,
  CONSTRAINT "consent_policy_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "consent_policy_checksum_check"
    CHECK ("contentChecksum" ~ '^[0-9a-f]{64}$'),
  CONSTRAINT "consent_policy_effective_window_check"
    CHECK ("expiresAt" IS NULL OR "expiresAt" > "effectiveAt"),
  CONSTRAINT "consent_policy_active_approval_check"
    CHECK (
      "state" <> 'active'
      OR (
        "approvedByRef" IS NOT NULL
        AND "approvalEvidenceRef" IS NOT NULL
        AND "approvedAt" IS NOT NULL
        AND "approvedAt" <= "effectiveAt"
      )
    )
);

CREATE UNIQUE INDEX "consent_policy_purpose_policyVersion_key"
  ON "consent_policy"("purpose", "policyVersion");
CREATE INDEX "consent_policy_purpose_state_effectiveAt_idx"
  ON "consent_policy"("purpose", "state", "effectiveAt");
CREATE UNIQUE INDEX "consent_policy_one_active_purpose_idx"
  ON "consent_policy"("purpose")
  WHERE "state" = 'active';
