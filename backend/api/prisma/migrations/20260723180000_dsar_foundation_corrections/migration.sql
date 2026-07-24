-- Correct DSAR target ordering, legacy snapshots and evidence constraints.

DROP INDEX IF EXISTS "customer_data_request_correlationId_key";
CREATE INDEX "customer_data_request_correlationId_idx"
  ON "customer_data_request"("correlationId");

ALTER TABLE "customer_data_request"
  ADD COLUMN "executionDeadlineAt" TIMESTAMPTZ(6),
  ALTER COLUMN "targetSetRevision" SET DEFAULT 'dsar-targets-v2';

ALTER TABLE "customer_data_request_target"
  ADD COLUMN "legalHoldAuthorityRef" VARCHAR(160),
  ADD COLUMN "legalHoldPurpose" VARCHAR(240),
  ADD COLUMN "legalHoldEvidenceRef" VARCHAR(255),
  ADD COLUMN "legalHoldEffectiveAt" TIMESTAMPTZ(6),
  ADD COLUMN "legalHoldExpiresAt" TIMESTAMPTZ(6);

ALTER TABLE "customer_data_request_target"
  DROP CONSTRAINT "customer_data_request_target_attempt_check",
  ADD CONSTRAINT "customer_data_request_target_attempt_check"
    CHECK (
      "attemptCount" >= 0
      AND "maxAttempts" > 0
      AND "attemptCount" <= "maxAttempts"
    ),
  ADD CONSTRAINT "customer_data_request_target_processing_check"
    CHECK (
      "state" <> 'processing'
      OR (
        "claimOwner" IS NOT NULL
        AND "leaseExpiresAt" IS NOT NULL
        AND "fencingToken" > 0
      )
    ),
  ADD CONSTRAINT "customer_data_request_target_completed_check"
    CHECK (
      "state" <> 'completed'
      OR (
        "completedAt" IS NOT NULL
        AND "evidenceCode" IS NOT NULL
        AND "evidenceHash" IS NOT NULL
      )
    ),
  ADD CONSTRAINT "customer_data_request_target_legal_hold_check"
    CHECK (
      "state" <> 'legally_retained'
      OR (
        "legalHoldAuthorityRef" IS NOT NULL
        AND "legalHoldPurpose" IS NOT NULL
        AND "legalHoldEvidenceRef" IS NOT NULL
        AND "legalHoldEffectiveAt" IS NOT NULL
        AND "legalHoldExpiresAt" IS NOT NULL
        AND "legalHoldExpiresAt" > "legalHoldEffectiveAt"
      )
    );

WITH target_plan("requestType", "targetKey", "phase", "targetVersion") AS (
  VALUES
    ('export'::"customer_data_request_type", 'access-identity', 1, 'v1'),
    ('export'::"customer_data_request_type", 'customer-core', 2, 'v1'),
    ('export'::"customer_data_request_type", 'engagement-data', 3, 'v1'),
    ('export'::"customer_data_request_type", 'mobility-data', 3, 'v1'),
    ('export'::"customer_data_request_type", 'commerce-ownership-data', 3, 'v1'),
    ('export'::"customer_data_request_type", 'ai-data', 4, 'v1'),
    ('export'::"customer_data_request_type", 'object-storage-cache', 5, 'v1'),
    ('export'::"customer_data_request_type", 'telemetry-backup', 6, 'v1'),
    ('delete'::"customer_data_request_type", 'customer-core', 1, 'v1'),
    ('delete'::"customer_data_request_type", 'engagement-data', 2, 'v1'),
    ('delete'::"customer_data_request_type", 'mobility-data', 2, 'v1'),
    ('delete'::"customer_data_request_type", 'commerce-ownership-data', 2, 'v1'),
    ('delete'::"customer_data_request_type", 'ai-data', 3, 'v1'),
    ('delete'::"customer_data_request_type", 'object-storage-cache', 4, 'v1'),
    ('delete'::"customer_data_request_type", 'telemetry-backup', 5, 'v1'),
    ('delete'::"customer_data_request_type", 'access-identity', 6, 'v1')
)
INSERT INTO "customer_data_request_target" (
  "id",
  "requestId",
  "targetKey",
  "targetVersion",
  "phase",
  "updatedAt"
)
SELECT
  gen_random_uuid(),
  request."id",
  plan."targetKey",
  plan."targetVersion",
  plan."phase",
  CURRENT_TIMESTAMP
FROM "customer_data_request" AS request
JOIN target_plan AS plan ON plan."requestType" = request."requestType"
ON CONFLICT ("requestId", "targetKey") DO UPDATE
SET
  "phase" = EXCLUDED."phase",
  "targetVersion" = EXCLUDED."targetVersion",
  "updatedAt" = CURRENT_TIMESTAMP;

INSERT INTO "customer_data_request_event" (
  "id",
  "requestId",
  "eventType",
  "outcomeCode",
  "correlationId"
)
SELECT
  gen_random_uuid(),
  request."id",
  'request.snapshot.reconciled',
  'target-set-v2',
  request."correlationId"
FROM "customer_data_request" AS request
WHERE NOT EXISTS (
  SELECT 1
  FROM "customer_data_request_event" AS event
  WHERE event."requestId" = request."id"
);

UPDATE "customer_data_request"
SET "targetSetRevision" = 'dsar-targets-v2'
WHERE "targetSetRevision" <> 'dsar-targets-v2';
