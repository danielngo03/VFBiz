-- Vehicle Catalog foundation: stable identities plus immutable atomic releases.

CREATE TYPE "vehicle_catalog_release_state" AS ENUM (
  'draft',
  'approved',
  'active',
  'superseded',
  'rejected'
);
CREATE TYPE "vehicle_commercial_status" AS ENUM (
  'announced',
  'active',
  'discontinued'
);

ALTER TABLE "source_revision"
  ADD COLUMN "observedAt" TIMESTAMPTZ(6);
UPDATE "source_revision" SET "observedAt" = "createdAt";
ALTER TABLE "source_revision"
  ALTER COLUMN "observedAt" SET NOT NULL,
  ALTER COLUMN "observedAt" SET DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE "vehicle_catalog_release" (
  "id" UUID NOT NULL,
  "market" VARCHAR(8) NOT NULL,
  "releaseVersion" VARCHAR(80) NOT NULL,
  "state" "vehicle_catalog_release_state" NOT NULL DEFAULT 'draft',
  "sourceRevisionId" UUID NOT NULL,
  "effectiveAt" TIMESTAMPTZ(6) NOT NULL,
  "activatedAt" TIMESTAMPTZ(6),
  "supersededAt" TIMESTAMPTZ(6),
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "vehicle_catalog_release_pkey" PRIMARY KEY ("id")
);

INSERT INTO "vehicle_catalog_release" (
  "id",
  "market",
  "releaseVersion",
  "state",
  "sourceRevisionId",
  "effectiveAt"
)
SELECT
  source_id,
  'VN',
  'legacy-' || replace(source_id::text, '-', ''),
  'draft'::"vehicle_catalog_release_state",
  source_id,
  min(effective_at)
FROM (
  SELECT "sourceRevisionId" AS source_id, "effectiveAt" AS effective_at
  FROM "vehicle_model"
  UNION
  SELECT "sourceRevisionId" AS source_id, "effectiveAt" AS effective_at
  FROM "vehicle_variant"
) source_rows
GROUP BY source_id;

ALTER TABLE "vehicle_model"
  ADD COLUMN "brandCode" VARCHAR(40),
  ADD COLUMN "modelCode" VARCHAR(80);

UPDATE "vehicle_model"
SET
  "brandCode" = 'VINFAST',
  "modelCode" = upper(regexp_replace("slug", '[^a-zA-Z0-9]+', '_', 'g'));

ALTER TABLE "vehicle_model"
  ALTER COLUMN "brandCode" SET NOT NULL,
  ALTER COLUMN "modelCode" SET NOT NULL;

CREATE TABLE "vehicle_model_revision" (
  "id" UUID NOT NULL,
  "vehicleModelId" UUID NOT NULL,
  "catalogReleaseId" UUID NOT NULL,
  "canonicalName" VARCHAR(120) NOT NULL,
  "category" VARCHAR(80) NOT NULL,
  "commercialStatus" "vehicle_commercial_status" NOT NULL,
  "modelYear" INTEGER,
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "vehicle_model_revision_pkey" PRIMARY KEY ("id")
);

INSERT INTO "vehicle_model_revision" (
  "id",
  "vehicleModelId",
  "catalogReleaseId",
  "canonicalName",
  "category",
  "commercialStatus"
)
SELECT
  (
    substr(md5("id"::text || ':' || "sourceRevisionId"::text), 1, 8) || '-' ||
    substr(md5("id"::text || ':' || "sourceRevisionId"::text), 9, 4) || '-' ||
    '4' || substr(md5("id"::text || ':' || "sourceRevisionId"::text), 14, 3) || '-' ||
    'a' || substr(md5("id"::text || ':' || "sourceRevisionId"::text), 18, 3) || '-' ||
    substr(md5("id"::text || ':' || "sourceRevisionId"::text), 21, 12)
  )::uuid,
  "id",
  "sourceRevisionId",
  "name",
  "category",
  CASE
    WHEN "commercialStatus" = 'active' THEN 'active'
    WHEN "commercialStatus" = 'discontinued' THEN 'discontinued'
    ELSE 'announced'
  END::"vehicle_commercial_status"
FROM "vehicle_model";

ALTER TABLE "vehicle_variant"
  ADD COLUMN "variantCode" VARCHAR(100);

UPDATE "vehicle_variant" SET "variantCode" = "code";
ALTER TABLE "vehicle_variant" ALTER COLUMN "variantCode" SET NOT NULL;

CREATE TABLE "vehicle_variant_revision" (
  "id" UUID NOT NULL,
  "vehicleVariantId" UUID NOT NULL,
  "catalogReleaseId" UUID NOT NULL,
  "canonicalName" VARCHAR(120) NOT NULL,
  "commercialStatus" "vehicle_commercial_status" NOT NULL,
  "seats" INTEGER,
  "drivetrain" VARCHAR(40),
  "grossBatteryCapacityKwh" DECIMAL(8,3),
  "usableBatteryCapacityKwh" DECIMAL(8,3),
  "declaredRangeKm" DECIMAL(9,2),
  "rangeTestStandard" VARCHAR(40),
  "maximumAcChargePowerKw" DECIMAL(8,2),
  "maximumDcChargePowerKw" DECIMAL(8,2),
  "connectorStandards" TEXT[] NOT NULL,
  "specificationSchemaVersion" VARCHAR(40) NOT NULL,
  "extensionData" JSONB NOT NULL,
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "vehicle_variant_revision_pkey" PRIMARY KEY ("id")
);

INSERT INTO "vehicle_variant_revision" (
  "id",
  "vehicleVariantId",
  "catalogReleaseId",
  "canonicalName",
  "commercialStatus",
  "connectorStandards",
  "specificationSchemaVersion",
  "extensionData"
)
SELECT
  (
    substr(md5("id"::text || ':' || "sourceRevisionId"::text), 1, 8) || '-' ||
    substr(md5("id"::text || ':' || "sourceRevisionId"::text), 9, 4) || '-' ||
    '4' || substr(md5("id"::text || ':' || "sourceRevisionId"::text), 14, 3) || '-' ||
    'a' || substr(md5("id"::text || ':' || "sourceRevisionId"::text), 18, 3) || '-' ||
    substr(md5("id"::text || ':' || "sourceRevisionId"::text), 21, 12)
  )::uuid,
  "id",
  "sourceRevisionId",
  "name",
  CASE
    WHEN "commercialStatus" = 'active' THEN 'active'
    WHEN "commercialStatus" = 'discontinued' THEN 'discontinued'
    ELSE 'announced'
  END::"vehicle_commercial_status",
  ARRAY[]::TEXT[],
  'legacy-v1',
  "specifications"
FROM "vehicle_variant";

DROP INDEX IF EXISTS "vehicle_model_commercialStatus_effectiveAt_idx";
DROP INDEX IF EXISTS "vehicle_variant_code_key";
DROP INDEX IF EXISTS "vehicle_variant_vehicleModelId_commercialStatus_idx";

ALTER TABLE "vehicle_model"
  DROP CONSTRAINT IF EXISTS "vehicle_model_sourceRevisionId_fkey",
  DROP COLUMN "name",
  DROP COLUMN "category",
  DROP COLUMN "commercialStatus",
  DROP COLUMN "sourceRevisionId",
  DROP COLUMN "effectiveAt";

ALTER TABLE "vehicle_variant"
  DROP CONSTRAINT IF EXISTS "vehicle_variant_sourceRevisionId_fkey",
  DROP COLUMN "code",
  DROP COLUMN "name",
  DROP COLUMN "specifications",
  DROP COLUMN "commercialStatus",
  DROP COLUMN "sourceRevisionId",
  DROP COLUMN "effectiveAt";

CREATE UNIQUE INDEX "vehicle_catalog_release_market_releaseVersion_key"
  ON "vehicle_catalog_release"("market", "releaseVersion");
CREATE INDEX "vehicle_catalog_release_market_state_effectiveAt_idx"
  ON "vehicle_catalog_release"("market", "state", "effectiveAt");
CREATE UNIQUE INDEX "vehicle_catalog_release_one_active_market"
  ON "vehicle_catalog_release"("market")
  WHERE "state" = 'active';

CREATE UNIQUE INDEX "vehicle_model_brandCode_modelCode_key"
  ON "vehicle_model"("brandCode", "modelCode");
CREATE UNIQUE INDEX "vehicle_model_revision_vehicleModelId_catalogReleaseId_key"
  ON "vehicle_model_revision"("vehicleModelId", "catalogReleaseId");
CREATE INDEX "vehicle_model_revision_catalogReleaseId_commercialStatus_idx"
  ON "vehicle_model_revision"("catalogReleaseId", "commercialStatus");

CREATE UNIQUE INDEX "vehicle_variant_vehicleModelId_variantCode_key"
  ON "vehicle_variant"("vehicleModelId", "variantCode");
CREATE UNIQUE INDEX
  "vehicle_variant_revision_vehicleVariantId_catalogReleaseId_key"
  ON "vehicle_variant_revision"("vehicleVariantId", "catalogReleaseId");
CREATE INDEX "vehicle_variant_revision_catalogReleaseId_commercialStatus_idx"
  ON "vehicle_variant_revision"("catalogReleaseId", "commercialStatus");

ALTER TABLE "vehicle_catalog_release"
  ADD CONSTRAINT "vehicle_catalog_release_sourceRevisionId_fkey"
  FOREIGN KEY ("sourceRevisionId") REFERENCES "source_revision"("id")
  ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "vehicle_model_revision"
  ADD CONSTRAINT "vehicle_model_revision_vehicleModelId_fkey"
  FOREIGN KEY ("vehicleModelId") REFERENCES "vehicle_model"("id")
  ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "vehicle_model_revision"
  ADD CONSTRAINT "vehicle_model_revision_catalogReleaseId_fkey"
  FOREIGN KEY ("catalogReleaseId") REFERENCES "vehicle_catalog_release"("id")
  ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "vehicle_variant_revision"
  ADD CONSTRAINT "vehicle_variant_revision_vehicleVariantId_fkey"
  FOREIGN KEY ("vehicleVariantId") REFERENCES "vehicle_variant"("id")
  ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "vehicle_variant_revision"
  ADD CONSTRAINT "vehicle_variant_revision_catalogReleaseId_fkey"
  FOREIGN KEY ("catalogReleaseId") REFERENCES "vehicle_catalog_release"("id")
  ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "vehicle_model_revision"
  ADD CONSTRAINT "vehicle_model_revision_modelYear_check"
  CHECK ("modelYear" IS NULL OR "modelYear" BETWEEN 2000 AND 2200);
ALTER TABLE "vehicle_variant_revision"
  ADD CONSTRAINT "vehicle_variant_revision_numeric_check"
  CHECK (
    ("seats" IS NULL OR "seats" > 0)
    AND ("grossBatteryCapacityKwh" IS NULL OR "grossBatteryCapacityKwh" > 0)
    AND ("usableBatteryCapacityKwh" IS NULL OR "usableBatteryCapacityKwh" > 0)
    AND (
      "grossBatteryCapacityKwh" IS NULL
      OR "usableBatteryCapacityKwh" IS NULL
      OR "usableBatteryCapacityKwh" <= "grossBatteryCapacityKwh"
    )
    AND ("declaredRangeKm" IS NULL OR "declaredRangeKm" > 0)
    AND ("maximumAcChargePowerKw" IS NULL OR "maximumAcChargePowerKw" > 0)
    AND ("maximumDcChargePowerKw" IS NULL OR "maximumDcChargePowerKw" > 0)
  );
