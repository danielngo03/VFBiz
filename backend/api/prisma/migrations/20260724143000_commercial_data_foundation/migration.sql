CREATE TYPE "commercial_release_state" AS ENUM (
  'draft',
  'approved',
  'active',
  'superseded',
  'rejected'
);
CREATE TYPE "price_type" AS ENUM ('msrp', 'list', 'option', 'service');
CREATE TYPE "tax_treatment" AS ENUM (
  'tax_inclusive',
  'tax_exclusive',
  'not_applicable'
);
CREATE TYPE "commercial_channel" AS ENUM (
  'public',
  'retail',
  'fleet',
  'employee'
);
CREATE TYPE "promotion_benefit_type" AS ENUM (
  'fixed_amount',
  'percentage',
  'in_kind',
  'composite'
);
CREATE TYPE "promotion_stacking_policy" AS ENUM (
  'exclusive',
  'stackable',
  'rule_based'
);
CREATE TYPE "inventory_availability_band" AS ENUM (
  'available',
  'low',
  'unavailable',
  'unknown'
);
CREATE TYPE "commercial_anomaly_severity" AS ENUM ('warning', 'blocking');
CREATE TYPE "commercial_anomaly_disposition" AS ENUM (
  'open',
  'accepted',
  'rejected',
  'resolved'
);

CREATE TABLE "commercial_data_release" (
  "id" UUID NOT NULL,
  "market" VARCHAR(8) NOT NULL,
  "releaseVersion" VARCHAR(80) NOT NULL,
  "state" "commercial_release_state" NOT NULL DEFAULT 'draft',
  "submittedByRef" VARCHAR(160) NOT NULL,
  "approvedByRef" VARCHAR(160),
  "approvalEvidenceRef" VARCHAR(512),
  "approvedAt" TIMESTAMPTZ(6),
  "activatedByRef" VARCHAR(160),
  "sourceRevisionId" UUID NOT NULL,
  "effectiveAt" TIMESTAMPTZ(6) NOT NULL,
  "activatedAt" TIMESTAMPTZ(6),
  "supersededAt" TIMESTAMPTZ(6),
  "revision" INTEGER NOT NULL DEFAULT 0,
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ(6) NOT NULL,
  CONSTRAINT "commercial_data_release_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "commercial_data_release_revision_check" CHECK ("revision" >= 0),
  CONSTRAINT "commercial_data_release_submitter_check"
    CHECK (length(btrim("submittedByRef")) > 0),
  CONSTRAINT "commercial_data_release_separation_of_duties_check"
    CHECK ("approvedByRef" IS NULL OR "approvedByRef" <> "submittedByRef"),
  CONSTRAINT "commercial_data_release_state_evidence_check" CHECK (
    (
      "state" = 'draft'
      AND "approvedByRef" IS NULL
      AND "approvalEvidenceRef" IS NULL
      AND "approvedAt" IS NULL
      AND "activatedAt" IS NULL
      AND "activatedByRef" IS NULL
      AND "supersededAt" IS NULL
    )
    OR (
      "state" = 'rejected'
      AND "activatedAt" IS NULL
      AND "activatedByRef" IS NULL
      AND "supersededAt" IS NULL
    )
    OR (
      "state" = 'approved'
      AND "approvedByRef" IS NOT NULL
      AND "approvalEvidenceRef" IS NOT NULL
      AND "approvedAt" IS NOT NULL
      AND "activatedAt" IS NULL
      AND "activatedByRef" IS NULL
      AND "supersededAt" IS NULL
    )
    OR (
      "state" = 'active'
      AND "approvedByRef" IS NOT NULL
      AND "approvalEvidenceRef" IS NOT NULL
      AND "approvedAt" IS NOT NULL
      AND "activatedAt" IS NOT NULL
      AND "activatedByRef" IS NOT NULL
      AND "supersededAt" IS NULL
    )
    OR (
      "state" = 'superseded'
      AND "approvedByRef" IS NOT NULL
      AND "approvalEvidenceRef" IS NOT NULL
      AND "approvedAt" IS NOT NULL
      AND "activatedAt" IS NOT NULL
      AND "activatedByRef" IS NOT NULL
      AND "supersededAt" IS NOT NULL
    )
  )
);

CREATE INDEX "commercial_data_release_market_state_effectiveAt_idx"
  ON "commercial_data_release"("market", "state", "effectiveAt");
CREATE UNIQUE INDEX "commercial_data_release_market_releaseVersion_key"
  ON "commercial_data_release"("market", "releaseVersion");
CREATE UNIQUE INDEX "commercial_data_release_one_active_market_key"
  ON "commercial_data_release"("market")
  WHERE "state" = 'active';

-- Preserve any legacy rows as DRAFT, fail-closed commercial releases. The
-- migration never promotes historical PriceProjection data to public state.
INSERT INTO "commercial_data_release" (
  "id",
  "market",
  "releaseVersion",
  "state",
  "submittedByRef",
  "sourceRevisionId",
  "effectiveAt",
  "updatedAt"
)
SELECT
  gen_random_uuid(),
  legacy."market",
  'legacy-' || substr(md5(legacy."sourceRevisionId"::text || legacy."market"), 1, 16),
  'draft'::"commercial_release_state",
  'migration:legacy-price-projection',
  legacy."sourceRevisionId",
  min(legacy."validFrom"),
  CURRENT_TIMESTAMP
FROM "price_projection" AS legacy
GROUP BY legacy."market", legacy."sourceRevisionId";

ALTER TABLE "price_projection" RENAME TO "price_offer";
ALTER TABLE "price_offer"
  RENAME CONSTRAINT "price_projection_pkey" TO "price_offer_pkey";
ALTER TABLE "price_offer"
  RENAME CONSTRAINT "price_projection_vehicleVariantId_fkey"
  TO "price_offer_vehicleVariantId_fkey";
ALTER TABLE "price_offer"
  RENAME CONSTRAINT "price_projection_sourceRevisionId_fkey"
  TO "price_offer_sourceRevisionId_fkey";
ALTER INDEX "price_projection_vehicleVariantId_market_validFrom_idx"
  RENAME TO "price_offer_legacy_vehicleVariantId_market_validFrom_idx";

ALTER TABLE "price_offer"
  ADD COLUMN "commercialReleaseId" UUID,
  ADD COLUMN "offerCode" VARCHAR(120),
  ADD COLUMN "priceType" "price_type" NOT NULL DEFAULT 'list',
  ADD COLUMN "taxTreatment" "tax_treatment" NOT NULL DEFAULT 'tax_inclusive',
  ADD COLUMN "channel" "commercial_channel" NOT NULL DEFAULT 'public',
  ADD COLUMN "eligibilitySchemaVersion" VARCHAR(40) NOT NULL DEFAULT 'legacy-v1',
  ADD COLUMN "eligibilityRules" JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE "price_offer" AS offer
SET
  "commercialReleaseId" = release."id",
  "offerCode" = 'LEGACY-' || offer."id"::text
FROM "commercial_data_release" AS release
WHERE
  release."market" = offer."market"
  AND release."sourceRevisionId" = offer."sourceRevisionId";

ALTER TABLE "price_offer"
  ALTER COLUMN "commercialReleaseId" SET NOT NULL,
  ALTER COLUMN "offerCode" SET NOT NULL,
  ALTER COLUMN "priceType" DROP DEFAULT,
  ALTER COLUMN "taxTreatment" DROP DEFAULT,
  ALTER COLUMN "channel" DROP DEFAULT,
  ALTER COLUMN "eligibilitySchemaVersion" DROP DEFAULT,
  ALTER COLUMN "eligibilityRules" DROP DEFAULT;

DROP INDEX "price_offer_legacy_vehicleVariantId_market_validFrom_idx";
CREATE INDEX "price_offer_vehicleVariantId_market_channel_priceType_valid_idx"
  ON "price_offer"(
    "vehicleVariantId",
    "market",
    "channel",
    "priceType",
    "validFrom"
  );
CREATE INDEX "price_offer_sourceRevisionId_idx"
  ON "price_offer"("sourceRevisionId");
CREATE UNIQUE INDEX "price_offer_commercialReleaseId_offerCode_key"
  ON "price_offer"("commercialReleaseId", "offerCode");

ALTER TABLE "price_offer"
  ADD CONSTRAINT "price_offer_commercialReleaseId_fkey"
    FOREIGN KEY ("commercialReleaseId")
    REFERENCES "commercial_data_release"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  ADD CONSTRAINT "price_offer_amount_positive_check"
    CHECK ("amountMinor" > 0),
  ADD CONSTRAINT "price_offer_currency_check"
    CHECK ("currency" ~ '^[A-Z]{3}$'),
  ADD CONSTRAINT "price_offer_market_check"
    CHECK ("market" ~ '^[A-Z]{2,8}$'),
  ADD CONSTRAINT "price_offer_valid_window_check"
    CHECK ("validTo" IS NULL OR "validTo" > "validFrom"),
  ADD CONSTRAINT "price_offer_code_check"
    CHECK (length(btrim("offerCode")) > 0);

CREATE TABLE "promotion" (
  "id" UUID NOT NULL,
  "commercialReleaseId" UUID NOT NULL,
  "promotionCode" VARCHAR(120) NOT NULL,
  "promotionVersion" VARCHAR(80) NOT NULL,
  "title" VARCHAR(240) NOT NULL,
  "market" VARCHAR(8) NOT NULL,
  "channel" "commercial_channel" NOT NULL,
  "vehicleModelId" UUID,
  "vehicleVariantId" UUID,
  "benefitType" "promotion_benefit_type" NOT NULL,
  "benefitAmountMinor" BIGINT,
  "benefitPercentage" DECIMAL(7,4),
  "currency" CHAR(3),
  "benefitSchemaVersion" VARCHAR(40) NOT NULL,
  "benefitDefinition" JSONB NOT NULL,
  "eligibilitySchemaVersion" VARCHAR(40) NOT NULL,
  "eligibilityRules" JSONB NOT NULL,
  "stackingPolicy" "promotion_stacking_policy" NOT NULL,
  "sourceRevisionId" UUID NOT NULL,
  "validFrom" TIMESTAMPTZ(6) NOT NULL,
  "validTo" TIMESTAMPTZ(6),
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "promotion_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "promotion_market_check" CHECK ("market" ~ '^[A-Z]{2,8}$'),
  CONSTRAINT "promotion_scope_check"
    CHECK (num_nonnulls("vehicleModelId", "vehicleVariantId") <= 1),
  CONSTRAINT "promotion_valid_window_check"
    CHECK ("validTo" IS NULL OR "validTo" > "validFrom"),
  CONSTRAINT "promotion_percentage_check"
    CHECK (
      "benefitPercentage" IS NULL
      OR ("benefitPercentage" > 0 AND "benefitPercentage" <= 100)
    ),
  CONSTRAINT "promotion_amount_check"
    CHECK ("benefitAmountMinor" IS NULL OR "benefitAmountMinor" > 0),
  CONSTRAINT "promotion_currency_check"
    CHECK ("currency" IS NULL OR "currency" ~ '^[A-Z]{3}$'),
  CONSTRAINT "promotion_benefit_shape_check" CHECK (
    ("benefitType" = 'fixed_amount' AND "benefitAmountMinor" IS NOT NULL
      AND "currency" IS NOT NULL AND "benefitPercentage" IS NULL)
    OR ("benefitType" = 'percentage' AND "benefitPercentage" IS NOT NULL
      AND "benefitAmountMinor" IS NULL)
    OR ("benefitType" IN ('in_kind', 'composite'))
  )
);

CREATE INDEX "promotion_market_channel_validFrom_idx"
  ON "promotion"("market", "channel", "validFrom");
CREATE INDEX "promotion_vehicleModelId_vehicleVariantId_idx"
  ON "promotion"("vehicleModelId", "vehicleVariantId");
CREATE INDEX "promotion_sourceRevisionId_idx"
  ON "promotion"("sourceRevisionId");
CREATE UNIQUE INDEX
  "promotion_commercialReleaseId_promotionCode_promotionVersio_key"
  ON "promotion"(
    "commercialReleaseId",
    "promotionCode",
    "promotionVersion"
  );

CREATE TABLE "inventory_observation" (
  "id" UUID NOT NULL,
  "vehicleVariantId" UUID NOT NULL,
  "locationRef" VARCHAR(160) NOT NULL,
  "market" VARCHAR(8) NOT NULL,
  "availabilityBand" "inventory_availability_band" NOT NULL,
  "availableUnits" INTEGER,
  "sourceRevisionId" UUID NOT NULL,
  "observedAt" TIMESTAMPTZ(6) NOT NULL,
  "expiresAt" TIMESTAMPTZ(6) NOT NULL,
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "inventory_observation_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "inventory_observation_window_check"
    CHECK ("expiresAt" > "observedAt"),
  CONSTRAINT "inventory_observation_units_check"
    CHECK ("availableUnits" IS NULL OR "availableUnits" >= 0),
  CONSTRAINT "inventory_observation_market_check"
    CHECK ("market" ~ '^[A-Z]{2,8}$'),
  CONSTRAINT "inventory_observation_location_check"
    CHECK (length(btrim("locationRef")) > 0)
);

CREATE INDEX "inventory_observation_vehicleVariantId_market_expiresAt_idx"
  ON "inventory_observation"("vehicleVariantId", "market", "expiresAt");
CREATE INDEX "inventory_observation_locationRef_expiresAt_idx"
  ON "inventory_observation"("locationRef", "expiresAt");
CREATE UNIQUE INDEX
  "inventory_observation_vehicleVariantId_locationRef_sourceRe_key"
  ON "inventory_observation"(
    "vehicleVariantId",
    "locationRef",
    "sourceRevisionId",
    "observedAt"
  );

CREATE TABLE "commercial_fact_anomaly" (
  "id" UUID NOT NULL,
  "priceOfferId" UUID,
  "promotionId" UUID,
  "inventoryObservationId" UUID,
  "ruleCode" VARCHAR(120) NOT NULL,
  "ruleVersion" VARCHAR(40) NOT NULL,
  "severity" "commercial_anomaly_severity" NOT NULL,
  "disposition" "commercial_anomaly_disposition" NOT NULL DEFAULT 'open',
  "evidence" JSONB NOT NULL,
  "detectedAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "resolvedAt" TIMESTAMPTZ(6),
  "resolvedByRef" VARCHAR(160),
  CONSTRAINT "commercial_fact_anomaly_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "commercial_fact_anomaly_target_check" CHECK (
    num_nonnulls(
      "priceOfferId",
      "promotionId",
      "inventoryObservationId"
    ) = 1
  ),
  CONSTRAINT "commercial_fact_anomaly_resolution_check" CHECK (
    (
      "disposition" = 'resolved'
      AND "resolvedAt" IS NOT NULL
      AND "resolvedByRef" IS NOT NULL
    )
    OR (
      "disposition" <> 'resolved'
      AND "resolvedAt" IS NULL
      AND "resolvedByRef" IS NULL
    )
  )
);

CREATE INDEX "commercial_fact_anomaly_priceOfferId_disposition_idx"
  ON "commercial_fact_anomaly"("priceOfferId", "disposition");
CREATE INDEX "commercial_fact_anomaly_promotionId_disposition_idx"
  ON "commercial_fact_anomaly"("promotionId", "disposition");
CREATE INDEX
  "commercial_fact_anomaly_inventoryObservationId_disposition_idx"
  ON "commercial_fact_anomaly"("inventoryObservationId", "disposition");

ALTER TABLE "commercial_data_release"
  ADD CONSTRAINT "commercial_data_release_sourceRevisionId_fkey"
  FOREIGN KEY ("sourceRevisionId") REFERENCES "source_revision"("id")
  ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "promotion"
  ADD CONSTRAINT "promotion_commercialReleaseId_fkey"
    FOREIGN KEY ("commercialReleaseId")
    REFERENCES "commercial_data_release"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  ADD CONSTRAINT "promotion_vehicleModelId_fkey"
    FOREIGN KEY ("vehicleModelId") REFERENCES "vehicle_model"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  ADD CONSTRAINT "promotion_vehicleVariantId_fkey"
    FOREIGN KEY ("vehicleVariantId") REFERENCES "vehicle_variant"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  ADD CONSTRAINT "promotion_sourceRevisionId_fkey"
    FOREIGN KEY ("sourceRevisionId") REFERENCES "source_revision"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "inventory_observation"
  ADD CONSTRAINT "inventory_observation_vehicleVariantId_fkey"
    FOREIGN KEY ("vehicleVariantId") REFERENCES "vehicle_variant"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE,
  ADD CONSTRAINT "inventory_observation_sourceRevisionId_fkey"
    FOREIGN KEY ("sourceRevisionId") REFERENCES "source_revision"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "commercial_fact_anomaly"
  ADD CONSTRAINT "commercial_fact_anomaly_priceOfferId_fkey"
    FOREIGN KEY ("priceOfferId") REFERENCES "price_offer"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  ADD CONSTRAINT "commercial_fact_anomaly_promotionId_fkey"
    FOREIGN KEY ("promotionId") REFERENCES "promotion"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  ADD CONSTRAINT "commercial_fact_anomaly_inventoryObservationId_fkey"
    FOREIGN KEY ("inventoryObservationId") REFERENCES "inventory_observation"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
