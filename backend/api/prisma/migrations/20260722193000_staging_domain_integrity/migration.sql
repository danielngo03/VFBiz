-- This expand migration is fail-closed: infrastructure must provision PostGIS
-- using a privileged bootstrap identity; the application migration role only
-- verifies the prerequisite.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') THEN
    RAISE EXCEPTION 'PostGIS extension must be provisioned before this migration';
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM "customer_vehicle_reference"
    WHERE "vehicleVariantId" IS NULL
  ) THEN
    RAISE EXCEPTION 'Cannot require a garage variant while legacy rows have no vehicleVariantId';
  END IF;

  IF EXISTS (
    SELECT 1 FROM "customer_vehicle_reference" garage
    LEFT JOIN "vehicle_variant" variant ON variant."id" = garage."vehicleVariantId"
    WHERE variant."id" IS NULL
  ) THEN RAISE EXCEPTION 'Cannot require a garage variant while referenced variants are missing';
  END IF;
END $$;

-- DropIndex
DROP INDEX "charging_connector_chargingStationId_standard_status_idx";

-- DropIndex
DROP INDEX "session_projection_identitySubjectId_expiresAt_idx";

-- DropIndex
DROP INDEX "source_revision_source_effectiveAt_idx";

-- DropIndex
DROP INDEX "trip_plan_projection_requestFingerprint_expiresAt_idx";

-- AlterTable: backfill provider-safe connector identity before constraints.
ALTER TABLE "charging_connector" ADD COLUMN     "externalRef" VARCHAR(160),
ADD COLUMN     "lastObservedAt" TIMESTAMPTZ(6),
ADD COLUMN     "unitCount" INTEGER NOT NULL DEFAULT 1;

UPDATE "charging_connector" connector
SET "externalRef" = 'legacy:' || connector."id"::text,
    "lastObservedAt" = station."refreshedAt",
    "status" = 'unknown'
FROM "charging_station" station
WHERE station."id" = connector."chargingStationId";

ALTER TABLE "charging_connector"
ALTER COLUMN "externalRef" SET NOT NULL,
ALTER COLUMN "lastObservedAt" SET NOT NULL;

-- AlterTable
ALTER TABLE "charging_station" ADD COLUMN     "countryCode" CHAR(2) NOT NULL DEFAULT 'VN',
ADD COLUMN     "location" geography(Point,4326),
ADD COLUMN     "locality" VARCHAR(120),
ADD COLUMN     "subdivisionCode" VARCHAR(16),
ADD COLUMN     "timezone" VARCHAR(64) NOT NULL DEFAULT 'Asia/Ho_Chi_Minh';

UPDATE "charging_station"
SET "location" = ST_SetSRID(ST_MakePoint("longitude"::double precision, "latitude"::double precision), 4326)::geography;

ALTER TABLE "charging_station" ALTER COLUMN "location" SET NOT NULL;

ALTER TABLE "charging_station"
ADD CONSTRAINT "charging_station_latitude_range_check" CHECK ("latitude" BETWEEN -90 AND 90),
ADD CONSTRAINT "charging_station_longitude_range_check" CHECK ("longitude" BETWEEN -180 AND 180);

CREATE FUNCTION sync_charging_station_location() RETURNS trigger AS $$
BEGIN
  NEW."location" := ST_SetSRID(
    ST_MakePoint(NEW."longitude"::double precision, NEW."latitude"::double precision),
    4326
  )::geography;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER "charging_station_location_sync"
BEFORE INSERT OR UPDATE OF "latitude", "longitude" ON "charging_station"
FOR EACH ROW EXECUTE FUNCTION sync_charging_station_location();

-- AlterTable
ALTER TABLE "charging_tariff" ADD COLUMN     "idleFeePerMinuteMinor" BIGINT NOT NULL DEFAULT 0,
ADD COLUMN     "sessionFeeMinor" BIGINT NOT NULL DEFAULT 0,
ADD COLUMN     "tariffSchema" VARCHAR(40) NOT NULL DEFAULT 'energy-v1',
ADD COLUMN     "taxRatePercent" DECIMAL(6,3);

-- AlterTable: existing immutable consent events use their own UUID as the
-- stable correlation seed; new writes must supply the real request ID.
ALTER TABLE "consent_event" ADD COLUMN     "correlationId" UUID,
ADD COLUMN     "evidenceRef" VARCHAR(255);

UPDATE "consent_event" SET "correlationId" = "id";
ALTER TABLE "consent_event" ALTER COLUMN "correlationId" SET NOT NULL;

-- AlterTable
ALTER TABLE "conversation_message" ADD COLUMN     "aiReleaseRevision" VARCHAR(160),
ADD COLUMN     "idempotencyKeyHash" CHAR(64),
ADD COLUMN     "outcome" VARCHAR(40),
ADD COLUMN     "policyDecisionRef" VARCHAR(255),
ADD COLUMN     "sequence" INTEGER;

WITH numbered AS (
  SELECT "id", row_number() OVER (
    PARTITION BY "conversationSessionId" ORDER BY "createdAt", "id"
  ) AS sequence
  FROM "conversation_message"
)
UPDATE "conversation_message" message
SET "sequence" = numbered.sequence
FROM numbered
WHERE numbered."id" = message."id";

ALTER TABLE "conversation_message" ALTER COLUMN "sequence" SET NOT NULL;

-- AlterTable
ALTER TABLE "conversation_session" ADD COLUMN     "accessCapabilityHash" CHAR(64),
ADD COLUMN     "expiresAt" TIMESTAMPTZ(6),
ADD COLUMN     "locale" VARCHAR(8) NOT NULL DEFAULT 'vi',
ADD COLUMN     "retentionUntil" TIMESTAMPTZ(6);

UPDATE "conversation_session"
SET "expiresAt" = "createdAt" + INTERVAL '24 hours',
    "retentionUntil" = "createdAt" + INTERVAL '30 days';

ALTER TABLE "conversation_session"
ALTER COLUMN "expiresAt" SET NOT NULL,
ALTER COLUMN "retentionUntil" SET NOT NULL;

-- AlterTable
ALTER TABLE "customer_vehicle_reference" ADD COLUMN     "maskedVin" VARCHAR(24),
ADD COLUMN     "rejectionReasonCode" VARCHAR(120),
ADD COLUMN     "source" VARCHAR(40) NOT NULL DEFAULT 'self-reported',
ADD COLUMN     "verificationRequestedAt" TIMESTAMPTZ(6),
ADD COLUMN     "verifiedAt" TIMESTAMPTZ(6);

UPDATE "customer_vehicle_reference" garage
SET "nickname" = COALESCE(garage."nickname", variant."name", 'Xe của tôi')
FROM "vehicle_variant" variant
WHERE variant."id" = garage."vehicleVariantId";

ALTER TABLE "customer_vehicle_reference"
ALTER COLUMN "vehicleVariantId" SET NOT NULL,
ALTER COLUMN "nickname" SET NOT NULL;

-- AlterTable
ALTER TABLE "session_projection" ADD COLUMN     "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN     "deviceLabel" VARCHAR(120),
ADD COLUMN     "lastSeenAt" TIMESTAMPTZ(6),
ADD COLUMN     "providerSessionRefHash" CHAR(64);

UPDATE "session_projection" SET "lastSeenAt" = "authenticatedAt";
ALTER TABLE "session_projection" ALTER COLUMN "lastSeenAt" SET NOT NULL;

-- AlterTable
ALTER TABLE "source_revision" ADD COLUMN     "approvalState" VARCHAR(40) NOT NULL DEFAULT 'pending',
ADD COLUMN     "approvedAt" TIMESTAMPTZ(6),
ADD COLUMN     "approvedByRef" VARCHAR(160),
ADD COLUMN     "classification" VARCHAR(40) NOT NULL DEFAULT 'internal',
ADD COLUMN     "freshnessTtlSeconds" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN     "licenseId" VARCHAR(120) NOT NULL DEFAULT 'UNVERIFIED',
ADD COLUMN     "ownerRef" VARCHAR(160) NOT NULL DEFAULT 'unassigned',
ADD COLUMN     "provenanceUri" VARCHAR(1024) NOT NULL DEFAULT 'urn:vfbiz:unverified',
ADD COLUMN     "retiredAt" TIMESTAMPTZ(6);

-- AlterTable
ALTER TABLE "trip_plan_projection" ADD COLUMN     "algorithmRevision" VARCHAR(80),
ADD COLUMN     "cachePolicy" VARCHAR(40),
ADD COLUMN     "calculatedAt" TIMESTAMPTZ(6),
ADD COLUMN     "failureCode" VARCHAR(120),
ADD COLUMN     "privacyClassification" VARCHAR(40) NOT NULL DEFAULT 'customer-confidential',
ADD COLUMN     "providerPayloadStored" BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN     "request" JSONB,
ADD COLUMN     "requestSchema" VARCHAR(80) NOT NULL DEFAULT 'trip-request-v1',
ADD COLUMN     "routeProvider" VARCHAR(80),
ADD COLUMN     "routeRequestHash" CHAR(64),
ADD COLUMN     "resultSchema" VARCHAR(80) NOT NULL DEFAULT 'trip-result-v1',
ADD COLUMN     "retentionUntil" TIMESTAMPTZ(6),
ADD COLUMN     "status" VARCHAR(40) NOT NULL DEFAULT 'pending',
ADD COLUMN     "warnings" JSONB NOT NULL DEFAULT '[]',
ALTER COLUMN "result" DROP NOT NULL;

UPDATE "trip_plan_projection"
SET "algorithmRevision" = COALESCE(NULLIF("algorithmRevision", ''), 'legacy-unverified'),
    "cachePolicy" = 'do-not-reuse',
    "request" = '{}'::jsonb,
    "routeProvider" = 'legacy-unverified',
    "routeRequestHash" = repeat('0', 64),
    "status" = 'unavailable',
    "failureCode" = 'legacy_input_unavailable',
    "retentionUntil" = LEAST("expiresAt", "createdAt" + INTERVAL '30 days');

ALTER TABLE "trip_plan_projection"
ALTER COLUMN "algorithmRevision" SET NOT NULL,
ALTER COLUMN "cachePolicy" SET NOT NULL,
ALTER COLUMN "request" SET NOT NULL,
ALTER COLUMN "routeProvider" SET NOT NULL,
ALTER COLUMN "routeRequestHash" SET NOT NULL,
ALTER COLUMN "retentionUntil" SET NOT NULL;

-- AlterTable
ALTER TABLE "vehicle_energy_profile" ADD COLUMN     "algorithmRevision" VARCHAR(80),
ADD COLUMN     "chargingCurveSchema" VARCHAR(40) NOT NULL DEFAULT 'v1';

UPDATE "vehicle_energy_profile" SET "algorithmRevision" = 'legacy-unverified';
ALTER TABLE "vehicle_energy_profile" ALTER COLUMN "algorithmRevision" SET NOT NULL;

-- CreateTable
CREATE TABLE "customer_data_request" (
    "id" UUID NOT NULL,
    "customerProfileId" UUID NOT NULL,
    "requestType" VARCHAR(24) NOT NULL,
    "status" VARCHAR(40) NOT NULL DEFAULT 'requested',
    "source" VARCHAR(80) NOT NULL,
    "artifactObjectRef" VARCHAR(255),
    "rejectionCode" VARCHAR(120),
    "correlationId" UUID NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "requestedAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "processingAt" TIMESTAMPTZ(6),
    "completedAt" TIMESTAMPTZ(6),
    "retentionUntil" TIMESTAMPTZ(6),

    CONSTRAINT "customer_data_request_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "conversation_citation" (
    "id" UUID NOT NULL,
    "conversationMessageId" UUID NOT NULL,
    "sourceId" VARCHAR(160) NOT NULL,
    "title" VARCHAR(255) NOT NULL,
    "uri" VARCHAR(1024) NOT NULL,
    "sourceRevision" VARCHAR(160) NOT NULL,
    "evidenceHash" CHAR(64) NOT NULL,
    "retrievedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "conversation_citation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "tool_proposal_record" (
    "id" UUID NOT NULL,
    "conversationMessageId" UUID NOT NULL,
    "toolName" VARCHAR(120) NOT NULL,
    "schemaVersion" VARCHAR(80) NOT NULL,
    "argumentsObjectRef" VARCHAR(255),
    "argumentsHash" CHAR(64) NOT NULL,
    "requiredScope" VARCHAR(160) NOT NULL,
    "status" VARCHAR(40) NOT NULL DEFAULT 'proposed',
    "policyDecisionRef" VARCHAR(255),
    "expiresAt" TIMESTAMPTZ(6) NOT NULL,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "tool_proposal_record_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "support_handoff" (
    "id" UUID NOT NULL,
    "conversationSessionId" UUID NOT NULL,
    "reasonCode" VARCHAR(120) NOT NULL,
    "status" VARCHAR(40) NOT NULL DEFAULT 'requested',
    "externalRef" VARCHAR(160),
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "support_handoff_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "release_decision_event" (
    "id" UUID NOT NULL,
    "releaseOperationId" UUID NOT NULL,
    "reviewerRef" VARCHAR(160) NOT NULL,
    "decision" VARCHAR(24) NOT NULL,
    "reasonCode" VARCHAR(120),
    "evidenceRef" VARCHAR(255) NOT NULL,
    "correlationId" UUID NOT NULL,
    "occurredAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "release_decision_event_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "customer_data_request_customerProfileId_requestedAt_idx" ON "customer_data_request"("customerProfileId", "requestedAt");

-- CreateIndex
CREATE INDEX "customer_data_request_status_requestedAt_idx" ON "customer_data_request"("status", "requestedAt");

-- CreateIndex
CREATE UNIQUE INDEX "customer_data_request_correlationId_key" ON "customer_data_request"("correlationId");

-- CreateIndex
CREATE INDEX "conversation_citation_conversationMessageId_idx" ON "conversation_citation"("conversationMessageId");

-- CreateIndex
CREATE INDEX "conversation_citation_sourceId_sourceRevision_idx" ON "conversation_citation"("sourceId", "sourceRevision");

-- CreateIndex
CREATE INDEX "tool_proposal_record_conversationMessageId_status_idx" ON "tool_proposal_record"("conversationMessageId", "status");

-- CreateIndex
CREATE INDEX "tool_proposal_record_toolName_createdAt_idx" ON "tool_proposal_record"("toolName", "createdAt");

-- CreateIndex
CREATE INDEX "support_handoff_status_createdAt_idx" ON "support_handoff"("status", "createdAt");

-- CreateIndex
CREATE INDEX "support_handoff_conversationSessionId_idx" ON "support_handoff"("conversationSessionId");

-- CreateIndex
CREATE INDEX "release_decision_event_releaseOperationId_occurredAt_idx" ON "release_decision_event"("releaseOperationId", "occurredAt");

-- CreateIndex
CREATE UNIQUE INDEX "release_decision_event_releaseOperationId_reviewerRef_key" ON "release_decision_event"("releaseOperationId", "reviewerRef");

-- CreateIndex
CREATE INDEX "charging_connector_chargingStationId_standard_status_lastOb_idx" ON "charging_connector"("chargingStationId", "standard", "status", "lastObservedAt");

-- CreateIndex: route-near-station queries require a spatial index.
CREATE INDEX "charging_station_location_gist_idx" ON "charging_station" USING GIST ("location");

-- CreateIndex
CREATE UNIQUE INDEX "charging_connector_chargingStationId_externalRef_key" ON "charging_connector"("chargingStationId", "externalRef");

-- CreateIndex
CREATE UNIQUE INDEX "conversation_message_conversationSessionId_sequence_key" ON "conversation_message"("conversationSessionId", "sequence");

-- CreateIndex
CREATE UNIQUE INDEX "conversation_session_accessCapabilityHash_key" ON "conversation_session"("accessCapabilityHash");

-- CreateIndex
CREATE INDEX "customer_vehicle_reference_vehicleVariantId_idx" ON "customer_vehicle_reference"("vehicleVariantId");

-- CreateIndex
CREATE UNIQUE INDEX "session_projection_providerSessionRefHash_key" ON "session_projection"("providerSessionRefHash");

-- CreateIndex
CREATE INDEX "session_projection_identitySubjectId_revokedAt_expiresAt_idx" ON "session_projection"("identitySubjectId", "revokedAt", "expiresAt");

-- CreateIndex
CREATE INDEX "source_revision_source_approvalState_effectiveAt_idx" ON "source_revision"("source", "approvalState", "effectiveAt");

-- CreateIndex
CREATE INDEX "source_revision_classification_expiresAt_idx" ON "source_revision"("classification", "expiresAt");

-- CreateIndex
CREATE INDEX "trip_plan_projection_requestFingerprint_algorithmRevision_e_idx" ON "trip_plan_projection"("requestFingerprint", "algorithmRevision", "expiresAt");

-- CreateIndex
CREATE INDEX "trip_plan_projection_customerProfileId_createdAt_idx" ON "trip_plan_projection"("customerProfileId", "createdAt");

-- CreateIndex
CREATE INDEX "trip_plan_projection_status_expiresAt_idx" ON "trip_plan_projection"("status", "expiresAt");

-- AddForeignKey
ALTER TABLE "customer_data_request" ADD CONSTRAINT "customer_data_request_customerProfileId_fkey" FOREIGN KEY ("customerProfileId") REFERENCES "customer_profile"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "customer_vehicle_reference" ADD CONSTRAINT "customer_vehicle_reference_vehicleVariantId_fkey" FOREIGN KEY ("vehicleVariantId") REFERENCES "vehicle_variant"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey: authenticated sessions retain a subject relationship while
-- anonymous sessions remain nullable and require a capability at application level.
ALTER TABLE "conversation_session" ADD CONSTRAINT "conversation_session_customerProfileId_fkey" FOREIGN KEY ("customerProfileId") REFERENCES "customer_profile"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "conversation_citation" ADD CONSTRAINT "conversation_citation_conversationMessageId_fkey" FOREIGN KEY ("conversationMessageId") REFERENCES "conversation_message"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "tool_proposal_record" ADD CONSTRAINT "tool_proposal_record_conversationMessageId_fkey" FOREIGN KEY ("conversationMessageId") REFERENCES "conversation_message"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "support_handoff" ADD CONSTRAINT "support_handoff_conversationSessionId_fkey" FOREIGN KEY ("conversationSessionId") REFERENCES "conversation_session"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "vehicle_energy_profile" ADD CONSTRAINT "vehicle_energy_profile_sourceRevisionId_fkey" FOREIGN KEY ("sourceRevisionId") REFERENCES "source_revision"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "charging_station" ADD CONSTRAINT "charging_station_sourceRevisionId_fkey" FOREIGN KEY ("sourceRevisionId") REFERENCES "source_revision"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "charging_tariff" ADD CONSTRAINT "charging_tariff_sourceRevisionId_fkey" FOREIGN KEY ("sourceRevisionId") REFERENCES "source_revision"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "trip_plan_projection" ADD CONSTRAINT "trip_plan_projection_customerProfileId_fkey" FOREIGN KEY ("customerProfileId") REFERENCES "customer_profile"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "trip_plan_projection" ADD CONSTRAINT "trip_plan_projection_vehicleEnergyProfileId_fkey" FOREIGN KEY ("vehicleEnergyProfileId") REFERENCES "vehicle_energy_profile"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "release_decision_event" ADD CONSTRAINT "release_decision_event_releaseOperationId_fkey" FOREIGN KEY ("releaseOperationId") REFERENCES "release_operation"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "vehicle_model" ADD CONSTRAINT "vehicle_model_sourceRevisionId_fkey" FOREIGN KEY ("sourceRevisionId") REFERENCES "source_revision"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "vehicle_variant" ADD CONSTRAINT "vehicle_variant_sourceRevisionId_fkey" FOREIGN KEY ("sourceRevisionId") REFERENCES "source_revision"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "price_projection" ADD CONSTRAINT "price_projection_vehicleVariantId_fkey" FOREIGN KEY ("vehicleVariantId") REFERENCES "vehicle_variant"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "price_projection" ADD CONSTRAINT "price_projection_sourceRevisionId_fkey" FOREIGN KEY ("sourceRevisionId") REFERENCES "source_revision"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- Domain integrity checks. Application/domain validation remains mandatory,
-- but critical trip and pricing inputs must also fail closed at persistence.
ALTER TABLE "vehicle_energy_profile"
ADD CONSTRAINT "vehicle_energy_profile_values_check" CHECK (
  "usableBatteryKwh" > 0
  AND "baseConsumptionWhPerKm" > 0
  AND "auxiliaryPowerKw" >= 0
  AND "reserveSocPercent" BETWEEN 0 AND 100
  AND ("validTo" IS NULL OR "validTo" > "validFrom")
);

ALTER TABLE "charging_connector"
ADD CONSTRAINT "charging_connector_capacity_check" CHECK (
  "maximumPowerKw" > 0 AND "unitCount" > 0
);

ALTER TABLE "charging_tariff"
ADD CONSTRAINT "charging_tariff_values_check" CHECK (
  "pricePerKwhMinor" >= 0
  AND "sessionFeeMinor" >= 0
  AND "idleFeePerMinuteMinor" >= 0
  AND ("taxRatePercent" IS NULL OR "taxRatePercent" BETWEEN 0 AND 100)
  AND ("validTo" IS NULL OR "validTo" > "validFrom")
);

ALTER TABLE "trip_plan_projection"
ADD CONSTRAINT "trip_plan_payload_check" CHECK (
  jsonb_typeof("request") = 'object'
  AND ("result" IS NULL OR jsonb_typeof("result") = 'object')
  AND jsonb_typeof("sourceRevisions") = 'object'
  AND jsonb_typeof("warnings") = 'array'
  AND "providerPayloadStored" = false
  AND "retentionUntil" <= "expiresAt"
);

ALTER TABLE "source_revision"
ADD CONSTRAINT "source_revision_approval_check" CHECK (
  ("approvalState" = 'approved' AND "approvedByRef" IS NOT NULL AND "approvedAt" IS NOT NULL)
  OR ("approvalState" <> 'approved' AND "approvedAt" IS NULL)
);

ALTER TABLE "release_operation"
ADD CONSTRAINT "release_operation_separation_of_duties_check" CHECK (
  "approvedByRef" IS NULL OR "approvedByRef" <> "requestedByRef"
);
