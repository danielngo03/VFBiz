CREATE TYPE "controlled_apply_reservation_state" AS ENUM ('reserved', 'completed', 'cancelled');

CREATE TABLE "controlled_apply_reservation" (
    "id" UUID NOT NULL,
    "idempotencyKeyHash" CHAR(64) NOT NULL,
    "nonce" CHAR(64) NOT NULL,
    "pairingSha256" CHAR(64) NOT NULL,
    "sourceEnvelopeUri" VARCHAR(256) NOT NULL,
    "sourceEnvelopeSha256" CHAR(64) NOT NULL,
    "sourceEnvelopeGeneration" BIGINT NOT NULL,
    "claimId" VARCHAR(256) NOT NULL,
    "claimFencingToken" BIGINT NOT NULL,
    "requesterSubjectSha256" CHAR(64) NOT NULL,
    "approverSubjectSha256" CHAR(64) NOT NULL,
    "approvalEventId" VARCHAR(256) NOT NULL,
    "approvalEventRevision" BIGINT NOT NULL,
    "approvalEvidenceSha256" CHAR(64) NOT NULL,
    "approvalPolicyRevisionSha256" CHAR(64) NOT NULL,
    "state" "controlled_apply_reservation_state" NOT NULL DEFAULT 'reserved',
    "reservationReceiptSha256" CHAR(64) NOT NULL,
    "completionReceiptSha256" CHAR(64),
    "cancellationReceiptSha256" CHAR(64),
    "cancellationEvidenceSha256" CHAR(64),
    "cancellationActorSubjectSha256" CHAR(64),
    "outcome" VARCHAR(80),
    "expiresAt" TIMESTAMPTZ(6) NOT NULL,
    "reservedAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completedAt" TIMESTAMPTZ(6),
    "cancelledAt" TIMESTAMPTZ(6),
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,
    CONSTRAINT "controlled_apply_reservation_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "controlled_apply_reservation_digest_check" CHECK (
      "idempotencyKeyHash" ~ '^[a-f0-9]{64}$' AND
      "nonce" ~ '^[a-f0-9]{64}$' AND
      "pairingSha256" ~ '^[a-f0-9]{64}$' AND
      "sourceEnvelopeSha256" ~ '^[a-f0-9]{64}$' AND
      "requesterSubjectSha256" ~ '^[a-f0-9]{64}$' AND
      "approverSubjectSha256" ~ '^[a-f0-9]{64}$' AND
      "approvalEvidenceSha256" ~ '^[a-f0-9]{64}$' AND
      "approvalPolicyRevisionSha256" ~ '^[a-f0-9]{64}$' AND
      "reservationReceiptSha256" ~ '^[a-f0-9]{64}$' AND
      ("completionReceiptSha256" IS NULL OR "completionReceiptSha256" ~ '^[a-f0-9]{64}$') AND
      ("cancellationReceiptSha256" IS NULL OR "cancellationReceiptSha256" ~ '^[a-f0-9]{64}$') AND
      ("cancellationEvidenceSha256" IS NULL OR "cancellationEvidenceSha256" ~ '^[a-f0-9]{64}$') AND
      ("cancellationActorSubjectSha256" IS NULL OR "cancellationActorSubjectSha256" ~ '^[a-f0-9]{64}$')
    ),
    CONSTRAINT "controlled_apply_reservation_locator_check" CHECK (
      "sourceEnvelopeUri" ~ ('^gs://vinfast-503003-evidence-dev/controlled-apply/authority-envelopes/v1/' || "sourceEnvelopeSha256" || '[.]json#[1-9][0-9]*$')
      AND "sourceEnvelopeGeneration" > 0
    ),
    CONSTRAINT "controlled_apply_reservation_fence_check" CHECK (
      "claimFencingToken" > 0 AND "approvalEventRevision" > 0 AND "requesterSubjectSha256" <> "approverSubjectSha256"
    ),
    CONSTRAINT "controlled_apply_reservation_terminal_check" CHECK (
      ("state" = 'reserved' AND "completionReceiptSha256" IS NULL AND "cancellationReceiptSha256" IS NULL AND "completedAt" IS NULL AND "cancelledAt" IS NULL)
      OR ("state" = 'completed' AND "completionReceiptSha256" IS NOT NULL AND "completedAt" IS NOT NULL AND "cancellationReceiptSha256" IS NULL AND "cancelledAt" IS NULL)
      OR ("state" = 'cancelled' AND "cancellationReceiptSha256" IS NOT NULL AND "cancelledAt" IS NOT NULL AND "completionReceiptSha256" IS NULL AND "completedAt" IS NULL)
    )
);

CREATE UNIQUE INDEX "controlled_apply_reservation_idempotencyKeyHash_key" ON "controlled_apply_reservation"("idempotencyKeyHash");
CREATE UNIQUE INDEX "controlled_apply_reservation_nonce_key" ON "controlled_apply_reservation"("nonce");
CREATE INDEX "controlled_apply_reservation_pairingSha256_claimId_claimFen_idx" ON "controlled_apply_reservation"("pairingSha256", "claimId", "claimFencingToken");
CREATE INDEX "controlled_apply_reservation_state_expiresAt_idx" ON "controlled_apply_reservation"("state", "expiresAt");

CREATE OR REPLACE FUNCTION "controlled_apply_reservation_set_updated_at"()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW."updatedAt" = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$;
CREATE TRIGGER "controlled_apply_reservation_updated_at"
BEFORE UPDATE ON "controlled_apply_reservation"
FOR EACH ROW EXECUTE FUNCTION "controlled_apply_reservation_set_updated_at"();
