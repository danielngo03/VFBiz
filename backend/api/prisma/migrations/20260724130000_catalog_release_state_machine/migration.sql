-- Catalog release evidence and state invariants.

ALTER TABLE "vehicle_catalog_release"
  ADD COLUMN "submittedByRef" VARCHAR(160) NOT NULL DEFAULT 'unassigned',
  ADD COLUMN "approvedByRef" VARCHAR(160),
  ADD COLUMN "approvalEvidenceRef" VARCHAR(512),
  ADD COLUMN "approvedAt" TIMESTAMPTZ(6),
  ADD COLUMN "activatedByRef" VARCHAR(160),
  ADD COLUMN "revision" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "updatedAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP;

UPDATE "vehicle_catalog_release" AS release
SET
  "submittedByRef" = source."submittedByRef",
  "approvedByRef" = source."approvedByRef",
  "approvalEvidenceRef" = source."approvalEvidenceRef",
  "approvedAt" = source."approvedAt",
  "activatedByRef" = CASE
    WHEN release."activatedAt" IS NOT NULL THEN source."approvedByRef"
    ELSE NULL
  END
FROM "source_revision" AS source
WHERE
  source."id" = release."sourceRevisionId"
  AND source."submittedByRef" <> 'unassigned';

ALTER TABLE "vehicle_catalog_release"
  ALTER COLUMN "submittedByRef" DROP DEFAULT,
  ALTER COLUMN "updatedAt" DROP DEFAULT;

ALTER TABLE "vehicle_catalog_release"
  ADD CONSTRAINT "vehicle_catalog_release_revision_nonnegative_check"
  CHECK ("revision" >= 0),
  ADD CONSTRAINT "vehicle_catalog_release_submitter_check"
  CHECK (length(btrim("submittedByRef")) > 0),
  ADD CONSTRAINT "vehicle_catalog_release_separation_of_duties_check"
  CHECK (
    "approvedByRef" IS NULL
    OR "approvedByRef" <> "submittedByRef"
  ),
  ADD CONSTRAINT "vehicle_catalog_release_state_evidence_check"
  CHECK (
    (
      "state" IN ('draft', 'rejected')
      AND "activatedAt" IS NULL
      AND "activatedByRef" IS NULL
      AND "supersededAt" IS NULL
    )
    OR
    (
      "state" = 'approved'
      AND "approvedByRef" IS NOT NULL
      AND "approvalEvidenceRef" IS NOT NULL
      AND "approvedAt" IS NOT NULL
      AND "activatedAt" IS NULL
      AND "activatedByRef" IS NULL
      AND "supersededAt" IS NULL
    )
    OR
    (
      "state" = 'active'
      AND "approvedByRef" IS NOT NULL
      AND "approvalEvidenceRef" IS NOT NULL
      AND "approvedAt" IS NOT NULL
      AND "activatedAt" IS NOT NULL
      AND "activatedByRef" IS NOT NULL
      AND "supersededAt" IS NULL
    )
    OR
    (
      "state" = 'superseded'
      AND "approvedByRef" IS NOT NULL
      AND "approvalEvidenceRef" IS NOT NULL
      AND "approvedAt" IS NOT NULL
      AND "activatedAt" IS NOT NULL
      AND "activatedByRef" IS NOT NULL
      AND "supersededAt" IS NOT NULL
    )
  );
