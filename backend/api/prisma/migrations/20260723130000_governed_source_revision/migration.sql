CREATE TYPE "source_approval_state" AS ENUM (
  'pending',
  'approved',
  'rejected',
  'retired'
);

CREATE TYPE "data_classification" AS ENUM (
  'public',
  'internal',
  'confidential',
  'restricted'
);

CREATE TYPE "vehicle_fact_subject_type" AS ENUM (
  'release',
  'model',
  'variant'
);

CREATE TYPE "vehicle_fact_group" AS ENUM (
  'identity_commercial',
  'technical_homologation',
  'battery_range_charging',
  'options_compatibility'
);

ALTER TABLE "source_revision"
  ADD COLUMN "permittedPurposes" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  ADD COLUMN "submittedByRef" VARCHAR(160) NOT NULL DEFAULT 'unassigned',
  ADD COLUMN "approvalEvidenceRef" VARCHAR(512),
  ADD COLUMN "ingestedAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP;

UPDATE "source_revision"
SET "approvalState" = 'pending'
WHERE
  "approvalState" = 'approved'
  AND (
    "ownerRef" = 'unassigned'
    OR "provenanceUri" = 'urn:vfbiz:unverified'
    OR "licenseId" = 'UNVERIFIED'
    OR "approvedByRef" IS NULL
    OR "approvedAt" IS NULL
    OR "freshnessTtlSeconds" <= 0
  );

ALTER TABLE "source_revision"
  ALTER COLUMN "classification" DROP DEFAULT,
  ALTER COLUMN "approvalState" DROP DEFAULT;

ALTER TABLE "source_revision"
  ALTER COLUMN "classification" TYPE "data_classification"
    USING (
      CASE "classification"
        WHEN 'public' THEN 'public'
        WHEN 'confidential' THEN 'confidential'
        WHEN 'restricted' THEN 'restricted'
        ELSE 'internal'
      END
    )::"data_classification",
  ALTER COLUMN "approvalState" TYPE "source_approval_state"
    USING (
      CASE "approvalState"
        WHEN 'approved' THEN 'approved'
        WHEN 'rejected' THEN 'rejected'
        WHEN 'retired' THEN 'retired'
        ELSE 'pending'
      END
    )::"source_approval_state";

ALTER TABLE "source_revision"
  ALTER COLUMN "classification" SET DEFAULT 'internal',
  ALTER COLUMN "approvalState" SET DEFAULT 'pending';

ALTER TABLE "source_revision"
  ADD CONSTRAINT "source_revision_approved_evidence_check"
  CHECK (
    "approvalState" <> 'approved'
    OR (
      "ownerRef" <> 'unassigned'
      AND "submittedByRef" <> 'unassigned'
      AND "provenanceUri" <> 'urn:vfbiz:unverified'
      AND "licenseId" <> 'UNVERIFIED'
      AND cardinality("permittedPurposes") > 0
      AND "approvedByRef" IS NOT NULL
      AND "approvedByRef" <> "submittedByRef"
      AND "approvalEvidenceRef" IS NOT NULL
      AND "approvedAt" IS NOT NULL
      AND "freshnessTtlSeconds" > 0
    )
  );

CREATE TABLE "vehicle_fact_provenance_binding" (
  "id" UUID NOT NULL,
  "catalogReleaseId" UUID NOT NULL,
  "subjectType" "vehicle_fact_subject_type" NOT NULL,
  "subjectRef" UUID NOT NULL,
  "factGroup" "vehicle_fact_group" NOT NULL,
  "sourceRevisionId" UUID NOT NULL,
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "vehicle_fact_provenance_binding_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "vehicle_fact_provenance_subject_group_key"
ON "vehicle_fact_provenance_binding"(
  "catalogReleaseId",
  "subjectType",
  "subjectRef",
  "factGroup"
);

CREATE INDEX "vehicle_fact_provenance_binding_sourceRevisionId_idx"
ON "vehicle_fact_provenance_binding"("sourceRevisionId");

ALTER TABLE "vehicle_fact_provenance_binding"
  ADD CONSTRAINT "vehicle_fact_provenance_binding_catalogReleaseId_fkey"
  FOREIGN KEY ("catalogReleaseId")
  REFERENCES "vehicle_catalog_release"("id")
  ON DELETE CASCADE
  ON UPDATE CASCADE;

ALTER TABLE "vehicle_fact_provenance_binding"
  ADD CONSTRAINT "vehicle_fact_provenance_binding_sourceRevisionId_fkey"
  FOREIGN KEY ("sourceRevisionId")
  REFERENCES "source_revision"("id")
  ON DELETE RESTRICT
  ON UPDATE CASCADE;
