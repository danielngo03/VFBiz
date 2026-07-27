ALTER TABLE "conversation_turn"
  ADD COLUMN "assistantReleaseCandidateSha256" CHAR(64),
  ADD COLUMN "assistantReleaseEnvelopeSha256" CHAR(64),
  ADD COLUMN "assistantReleasePointerRevision" BIGINT,
  ADD COLUMN "assistantReleaseReceiptIssuedAt" TIMESTAMPTZ(6),
  ADD COLUMN "assistantReleaseReceiptExpiresAt" TIMESTAMPTZ(6),
  ADD COLUMN "assistantReleaseRequestId" VARCHAR(160),
  ADD COLUMN "assistantReleaseConversationVersion" BIGINT,
  ADD COLUMN "assistantReleaseFencingToken" BIGINT,
  ADD COLUMN "assistantReleaseLeaseId" UUID;

ALTER TABLE "conversation_turn"
  ADD CONSTRAINT "conversation_turn_release_receipt_complete"
  CHECK (
    (
      "assistantReleaseRevision" IS NULL
      AND
      "assistantReleaseCandidateSha256" IS NULL
      AND "assistantReleaseEnvelopeSha256" IS NULL
      AND "assistantReleasePointerRevision" IS NULL
      AND "assistantReleaseReceiptIssuedAt" IS NULL
      AND "assistantReleaseReceiptExpiresAt" IS NULL
      AND "assistantReleaseRequestId" IS NULL
      AND "assistantReleaseConversationVersion" IS NULL
      AND "assistantReleaseFencingToken" IS NULL
      AND "assistantReleaseLeaseId" IS NULL
    )
    OR
    (
      "assistantReleaseRevision" IS NOT NULL
      AND "assistantReleaseCandidateSha256" IS NOT NULL
      AND "assistantReleaseEnvelopeSha256" IS NOT NULL
      AND "assistantReleasePointerRevision" IS NOT NULL
      AND "assistantReleaseReceiptIssuedAt" IS NOT NULL
      AND "assistantReleaseReceiptExpiresAt" IS NOT NULL
      AND "assistantReleaseRequestId" IS NOT NULL
      AND "assistantReleaseConversationVersion" IS NOT NULL
      AND "assistantReleaseFencingToken" IS NOT NULL
      AND "assistantReleaseLeaseId" IS NOT NULL
      AND "assistantReleaseCandidateSha256" ~ '^[a-f0-9]{64}$'
      AND "assistantReleaseEnvelopeSha256" ~ '^[a-f0-9]{64}$'
      AND "assistantReleasePointerRevision" > 0
      AND "assistantReleaseConversationVersion" >= 0
      AND "assistantReleaseFencingToken" > 0
      AND "assistantReleaseReceiptExpiresAt" > "assistantReleaseReceiptIssuedAt"
      AND "assistantReleaseReceiptExpiresAt"
        <= "assistantReleaseReceiptIssuedAt" + INTERVAL '30 seconds'
    )
  );
