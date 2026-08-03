DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM "controlled_apply_reservation"
    WHERE "state" = 'cancelled'
  ) THEN
    RAISE EXCEPTION
      'controlled_apply_reservation contains legacy cancelled rows without cancellation event lineage; operator backfill is required before 20260802110000';
  END IF;
END
$$;

ALTER TABLE "controlled_apply_reservation"
  ADD COLUMN "cancellationEventId" VARCHAR(256),
  ADD COLUMN "cancellationEventRevision" BIGINT;

ALTER TABLE "controlled_apply_reservation"
  ADD CONSTRAINT "controlled_apply_reservation_approval_event_id_check"
  CHECK ("approvalEventId" ~ '^[a-zA-Z0-9._:/-]{8,256}$');

ALTER TABLE "controlled_apply_reservation"
  DROP CONSTRAINT "controlled_apply_reservation_terminal_check";

ALTER TABLE "controlled_apply_reservation"
  ADD CONSTRAINT "controlled_apply_reservation_cancellation_event_check"
  CHECK (
    ("state" <> 'cancelled'
      AND "cancellationEventId" IS NULL
      AND "cancellationEventRevision" IS NULL)
    OR
    ("state" = 'cancelled'
      AND "cancellationEventId" IS NOT NULL
      AND "cancellationEventRevision" > 0)
  );

ALTER TABLE "controlled_apply_reservation"
  ADD CONSTRAINT "controlled_apply_reservation_terminal_check_v2"
  CHECK (
    ("state" = 'reserved'
      AND "completionReceiptSha256" IS NULL
      AND "cancellationReceiptSha256" IS NULL
      AND "cancellationEventId" IS NULL
      AND "cancellationEventRevision" IS NULL
      AND "completedAt" IS NULL
      AND "cancelledAt" IS NULL)
    OR
    ("state" = 'completed'
      AND "completionReceiptSha256" IS NOT NULL
      AND "cancellationReceiptSha256" IS NULL
      AND "cancellationEventId" IS NULL
      AND "cancellationEventRevision" IS NULL
      AND "completedAt" IS NOT NULL
      AND "cancelledAt" IS NULL)
    OR
    ("state" = 'cancelled'
      AND "completionReceiptSha256" IS NULL
      AND "cancellationReceiptSha256" IS NOT NULL
      AND "cancellationEventId" IS NOT NULL
      AND "cancellationEventRevision" IS NOT NULL
      AND "completedAt" IS NULL
      AND "cancelledAt" IS NOT NULL)
  );
