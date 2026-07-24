-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateEnum
CREATE TYPE "DeliveryStatus" AS ENUM ('pending', 'processing', 'completed', 'failed');

-- CreateTable
CREATE TABLE "identity_subject" (
    "id" UUID NOT NULL,
    "issuer" VARCHAR(255) NOT NULL,
    "subject" VARCHAR(255) NOT NULL,
    "realm" VARCHAR(40) NOT NULL,
    "status" VARCHAR(40) NOT NULL DEFAULT 'active',
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "identity_subject_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "session_projection" (
    "id" UUID NOT NULL,
    "identitySubjectId" UUID NOT NULL,
    "sessionRefHash" CHAR(64) NOT NULL,
    "userAgentSummary" VARCHAR(255),
    "ipPrefix" VARCHAR(80),
    "authenticatedAt" TIMESTAMPTZ(6) NOT NULL,
    "expiresAt" TIMESTAMPTZ(6) NOT NULL,
    "revokedAt" TIMESTAMPTZ(6),

    CONSTRAINT "session_projection_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "cart" (
    "id" UUID NOT NULL,
    "customerProfileId" UUID NOT NULL,
    "status" VARCHAR(40) NOT NULL,
    "currency" CHAR(3) NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "expiresAt" TIMESTAMPTZ(6) NOT NULL,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "cart_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "cart_item" (
    "id" UUID NOT NULL,
    "cartId" UUID NOT NULL,
    "productRef" VARCHAR(160) NOT NULL,
    "quantity" INTEGER NOT NULL,
    "unitAmount" BIGINT NOT NULL,
    "metadata" JSONB NOT NULL,

    CONSTRAINT "cart_item_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "order_projection" (
    "id" UUID NOT NULL,
    "customerProfileId" UUID NOT NULL,
    "externalOrderRef" VARCHAR(160) NOT NULL,
    "status" VARCHAR(40) NOT NULL,
    "currency" CHAR(3) NOT NULL,
    "totalAmount" BIGINT NOT NULL,
    "sourceRevision" VARCHAR(160) NOT NULL,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "order_projection_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "customer_profile" (
    "id" UUID NOT NULL,
    "identitySubjectId" UUID NOT NULL,
    "displayName" VARCHAR(120),
    "locale" VARCHAR(8) NOT NULL DEFAULT 'vi',
    "timezone" VARCHAR(64) NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    "communicationPreferences" JSONB NOT NULL DEFAULT '{}',
    "status" VARCHAR(40) NOT NULL DEFAULT 'active',
    "version" INTEGER NOT NULL DEFAULT 1,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "customer_profile_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "consent_event" (
    "id" UUID NOT NULL,
    "customerProfileId" UUID NOT NULL,
    "purpose" VARCHAR(100) NOT NULL,
    "policyVersion" VARCHAR(80) NOT NULL,
    "state" VARCHAR(24) NOT NULL,
    "source" VARCHAR(80) NOT NULL,
    "occurredAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "consent_event_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "customer_vehicle_reference" (
    "id" UUID NOT NULL,
    "customerProfileId" UUID NOT NULL,
    "vehicleVariantId" UUID,
    "nickname" VARCHAR(80),
    "vinTokenRef" VARCHAR(255),
    "verificationState" VARCHAR(40) NOT NULL DEFAULT 'unverified',
    "version" INTEGER NOT NULL DEFAULT 1,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "customer_vehicle_reference_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "conversation_session" (
    "id" UUID NOT NULL,
    "customerProfileId" UUID,
    "assistantProfile" VARCHAR(40) NOT NULL,
    "status" VARCHAR(40) NOT NULL,
    "policyRevision" VARCHAR(160) NOT NULL,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "conversation_session_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "conversation_message" (
    "id" UUID NOT NULL,
    "conversationSessionId" UUID NOT NULL,
    "role" VARCHAR(24) NOT NULL,
    "contentObjectRef" VARCHAR(255),
    "redactedContent" TEXT,
    "citations" JSONB,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "conversation_message_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "notification" (
    "id" UUID NOT NULL,
    "customerProfileId" UUID NOT NULL,
    "channel" VARCHAR(24) NOT NULL,
    "templateKey" VARCHAR(120) NOT NULL,
    "status" "DeliveryStatus" NOT NULL DEFAULT 'pending',
    "payload" JSONB NOT NULL,
    "availableAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deliveredAt" TIMESTAMPTZ(6),

    CONSTRAINT "notification_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "vehicle_energy_profile" (
    "id" UUID NOT NULL,
    "vehicleVariantId" UUID NOT NULL,
    "usableBatteryKwh" DECIMAL(8,3) NOT NULL,
    "baseConsumptionWhPerKm" DECIMAL(8,3) NOT NULL,
    "auxiliaryPowerKw" DECIMAL(6,3) NOT NULL,
    "reserveSocPercent" DECIMAL(5,2) NOT NULL,
    "connectorStandards" TEXT[],
    "chargingCurve" JSONB NOT NULL,
    "sourceRevisionId" UUID NOT NULL,
    "validFrom" TIMESTAMPTZ(6) NOT NULL,
    "validTo" TIMESTAMPTZ(6),

    CONSTRAINT "vehicle_energy_profile_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "charging_station" (
    "id" UUID NOT NULL,
    "externalRef" VARCHAR(160) NOT NULL,
    "name" VARCHAR(160) NOT NULL,
    "latitude" DECIMAL(9,6) NOT NULL,
    "longitude" DECIMAL(9,6) NOT NULL,
    "status" VARCHAR(40) NOT NULL,
    "openingHours" JSONB,
    "sourceRevisionId" UUID NOT NULL,
    "refreshedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "charging_station_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "charging_connector" (
    "id" UUID NOT NULL,
    "chargingStationId" UUID NOT NULL,
    "standard" VARCHAR(40) NOT NULL,
    "maximumPowerKw" DECIMAL(8,3) NOT NULL,
    "status" VARCHAR(40) NOT NULL,

    CONSTRAINT "charging_connector_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "charging_tariff" (
    "id" UUID NOT NULL,
    "chargingConnectorId" UUID NOT NULL,
    "currency" CHAR(3) NOT NULL,
    "pricePerKwhMinor" BIGINT NOT NULL,
    "sourceRevisionId" UUID NOT NULL,
    "validFrom" TIMESTAMPTZ(6) NOT NULL,
    "validTo" TIMESTAMPTZ(6),

    CONSTRAINT "charging_tariff_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "trip_plan_projection" (
    "id" UUID NOT NULL,
    "customerProfileId" UUID,
    "vehicleEnergyProfileId" UUID NOT NULL,
    "requestFingerprint" CHAR(64) NOT NULL,
    "result" JSONB NOT NULL,
    "sourceRevisions" JSONB NOT NULL,
    "expiresAt" TIMESTAMPTZ(6) NOT NULL,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "trip_plan_projection_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "release_operation" (
    "id" UUID NOT NULL,
    "releaseType" VARCHAR(80) NOT NULL,
    "manifestRef" VARCHAR(255) NOT NULL,
    "requestedByRef" VARCHAR(160) NOT NULL,
    "approvedByRef" VARCHAR(160),
    "status" VARCHAR(40) NOT NULL,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completedAt" TIMESTAMPTZ(6),

    CONSTRAINT "release_operation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "reconciliation_job" (
    "id" UUID NOT NULL,
    "capability" VARCHAR(80) NOT NULL,
    "provider" VARCHAR(80) NOT NULL,
    "cursor" VARCHAR(255),
    "status" "DeliveryStatus" NOT NULL DEFAULT 'pending',
    "attempts" INTEGER NOT NULL DEFAULT 0,
    "availableAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completedAt" TIMESTAMPTZ(6),
    "lastErrorCode" VARCHAR(120),

    CONSTRAINT "reconciliation_job_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "owner_vehicle_association" (
    "id" UUID NOT NULL,
    "customerProfileId" UUID NOT NULL,
    "externalVehicleRef" VARCHAR(255) NOT NULL,
    "state" VARCHAR(40) NOT NULL,
    "verifiedAt" TIMESTAMPTZ(6),
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "owner_vehicle_association_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "service_appointment_projection" (
    "id" UUID NOT NULL,
    "customerProfileId" UUID NOT NULL,
    "externalVehicleRef" VARCHAR(255) NOT NULL,
    "providerRef" VARCHAR(160),
    "status" VARCHAR(40) NOT NULL,
    "scheduledAt" TIMESTAMPTZ(6) NOT NULL,
    "sourceRevision" VARCHAR(160) NOT NULL,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "service_appointment_projection_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "source_revision" (
    "id" UUID NOT NULL,
    "source" VARCHAR(80) NOT NULL,
    "revision" VARCHAR(160) NOT NULL,
    "checksum" CHAR(64) NOT NULL,
    "effectiveAt" TIMESTAMPTZ(6) NOT NULL,
    "expiresAt" TIMESTAMPTZ(6),
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "source_revision_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "idempotency_record" (
    "id" UUID NOT NULL,
    "namespace" VARCHAR(80) NOT NULL,
    "keyHash" CHAR(64) NOT NULL,
    "requestHash" CHAR(64) NOT NULL,
    "status" "DeliveryStatus" NOT NULL DEFAULT 'pending',
    "responseStatus" INTEGER,
    "responseBody" JSONB,
    "expiresAt" TIMESTAMPTZ(6) NOT NULL,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "idempotency_record_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "outbox_event" (
    "id" UUID NOT NULL,
    "aggregateType" VARCHAR(100) NOT NULL,
    "aggregateId" VARCHAR(100) NOT NULL,
    "eventType" VARCHAR(160) NOT NULL,
    "eventVersion" INTEGER NOT NULL,
    "payload" JSONB NOT NULL,
    "correlationId" UUID NOT NULL,
    "status" "DeliveryStatus" NOT NULL DEFAULT 'pending',
    "availableAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "publishedAt" TIMESTAMPTZ(6),
    "attempts" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "outbox_event_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "audit_event" (
    "id" UUID NOT NULL,
    "actorType" VARCHAR(40) NOT NULL,
    "actorRef" VARCHAR(160),
    "action" VARCHAR(160) NOT NULL,
    "resourceType" VARCHAR(100) NOT NULL,
    "resourceId" VARCHAR(160),
    "outcome" VARCHAR(40) NOT NULL,
    "metadata" JSONB NOT NULL,
    "correlationId" UUID NOT NULL,
    "occurredAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "audit_event_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "vehicle_model" (
    "id" UUID NOT NULL,
    "slug" VARCHAR(120) NOT NULL,
    "name" VARCHAR(120) NOT NULL,
    "category" VARCHAR(80) NOT NULL,
    "commercialStatus" VARCHAR(40) NOT NULL,
    "sourceRevisionId" UUID NOT NULL,
    "effectiveAt" TIMESTAMPTZ(6) NOT NULL,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "vehicle_model_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "vehicle_variant" (
    "id" UUID NOT NULL,
    "vehicleModelId" UUID NOT NULL,
    "code" VARCHAR(100) NOT NULL,
    "name" VARCHAR(120) NOT NULL,
    "specifications" JSONB NOT NULL,
    "commercialStatus" VARCHAR(40) NOT NULL,
    "sourceRevisionId" UUID NOT NULL,
    "effectiveAt" TIMESTAMPTZ(6) NOT NULL,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "vehicle_variant_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "price_projection" (
    "id" UUID NOT NULL,
    "vehicleVariantId" UUID NOT NULL,
    "market" VARCHAR(16) NOT NULL,
    "currency" CHAR(3) NOT NULL,
    "amountMinor" BIGINT NOT NULL,
    "sourceRevisionId" UUID NOT NULL,
    "validFrom" TIMESTAMPTZ(6) NOT NULL,
    "validTo" TIMESTAMPTZ(6),
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "price_projection_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "lead" (
    "id" UUID NOT NULL,
    "customerRef" UUID,
    "type" VARCHAR(40) NOT NULL,
    "status" VARCHAR(40) NOT NULL,
    "market" VARCHAR(16) NOT NULL,
    "payload" JSONB NOT NULL,
    "correlationId" UUID NOT NULL,
    "externalRef" VARCHAR(160),
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "lead_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "quote_projection" (
    "id" UUID NOT NULL,
    "customerRef" UUID,
    "vehicleVariantId" UUID NOT NULL,
    "status" VARCHAR(40) NOT NULL,
    "totals" JSONB NOT NULL,
    "sourceRevisions" JSONB NOT NULL,
    "expiresAt" TIMESTAMPTZ(6) NOT NULL,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "quote_projection_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "identity_subject_realm_status_idx" ON "identity_subject"("realm", "status");

-- CreateIndex
CREATE UNIQUE INDEX "identity_subject_issuer_subject_key" ON "identity_subject"("issuer", "subject");

-- CreateIndex
CREATE UNIQUE INDEX "session_projection_sessionRefHash_key" ON "session_projection"("sessionRefHash");

-- CreateIndex
CREATE INDEX "session_projection_identitySubjectId_expiresAt_idx" ON "session_projection"("identitySubjectId", "expiresAt");

-- CreateIndex
CREATE INDEX "cart_customerProfileId_status_idx" ON "cart"("customerProfileId", "status");

-- CreateIndex
CREATE INDEX "cart_item_cartId_idx" ON "cart_item"("cartId");

-- CreateIndex
CREATE UNIQUE INDEX "order_projection_externalOrderRef_key" ON "order_projection"("externalOrderRef");

-- CreateIndex
CREATE INDEX "order_projection_customerProfileId_createdAt_idx" ON "order_projection"("customerProfileId", "createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "customer_profile_identitySubjectId_key" ON "customer_profile"("identitySubjectId");

-- CreateIndex
CREATE INDEX "customer_profile_status_updatedAt_idx" ON "customer_profile"("status", "updatedAt");

-- CreateIndex
CREATE INDEX "consent_event_customerProfileId_purpose_occurredAt_idx" ON "consent_event"("customerProfileId", "purpose", "occurredAt");

-- CreateIndex
CREATE INDEX "customer_vehicle_reference_customerProfileId_verificationSt_idx" ON "customer_vehicle_reference"("customerProfileId", "verificationState");

-- CreateIndex
CREATE INDEX "conversation_session_customerProfileId_updatedAt_idx" ON "conversation_session"("customerProfileId", "updatedAt");

-- CreateIndex
CREATE INDEX "conversation_message_conversationSessionId_createdAt_idx" ON "conversation_message"("conversationSessionId", "createdAt");

-- CreateIndex
CREATE INDEX "notification_status_availableAt_idx" ON "notification"("status", "availableAt");

-- CreateIndex
CREATE INDEX "vehicle_energy_profile_vehicleVariantId_validFrom_idx" ON "vehicle_energy_profile"("vehicleVariantId", "validFrom");

-- CreateIndex
CREATE UNIQUE INDEX "charging_station_externalRef_key" ON "charging_station"("externalRef");

-- CreateIndex
CREATE INDEX "charging_station_status_refreshedAt_idx" ON "charging_station"("status", "refreshedAt");

-- CreateIndex
CREATE INDEX "charging_connector_chargingStationId_standard_status_idx" ON "charging_connector"("chargingStationId", "standard", "status");

-- CreateIndex
CREATE INDEX "charging_tariff_chargingConnectorId_validFrom_idx" ON "charging_tariff"("chargingConnectorId", "validFrom");

-- CreateIndex
CREATE INDEX "trip_plan_projection_requestFingerprint_expiresAt_idx" ON "trip_plan_projection"("requestFingerprint", "expiresAt");

-- CreateIndex
CREATE INDEX "release_operation_releaseType_status_createdAt_idx" ON "release_operation"("releaseType", "status", "createdAt");

-- CreateIndex
CREATE INDEX "reconciliation_job_status_availableAt_idx" ON "reconciliation_job"("status", "availableAt");

-- CreateIndex
CREATE UNIQUE INDEX "owner_vehicle_association_customerProfileId_externalVehicle_key" ON "owner_vehicle_association"("customerProfileId", "externalVehicleRef");

-- CreateIndex
CREATE INDEX "service_appointment_projection_customerProfileId_scheduledA_idx" ON "service_appointment_projection"("customerProfileId", "scheduledAt");

-- CreateIndex
CREATE INDEX "source_revision_source_effectiveAt_idx" ON "source_revision"("source", "effectiveAt");

-- CreateIndex
CREATE UNIQUE INDEX "source_revision_source_revision_key" ON "source_revision"("source", "revision");

-- CreateIndex
CREATE INDEX "idempotency_record_expiresAt_idx" ON "idempotency_record"("expiresAt");

-- CreateIndex
CREATE UNIQUE INDEX "idempotency_record_namespace_keyHash_key" ON "idempotency_record"("namespace", "keyHash");

-- CreateIndex
CREATE INDEX "outbox_event_status_availableAt_idx" ON "outbox_event"("status", "availableAt");

-- CreateIndex
CREATE INDEX "outbox_event_aggregateType_aggregateId_idx" ON "outbox_event"("aggregateType", "aggregateId");

-- CreateIndex
CREATE INDEX "audit_event_resourceType_resourceId_occurredAt_idx" ON "audit_event"("resourceType", "resourceId", "occurredAt");

-- CreateIndex
CREATE INDEX "audit_event_correlationId_idx" ON "audit_event"("correlationId");

-- CreateIndex
CREATE UNIQUE INDEX "vehicle_model_slug_key" ON "vehicle_model"("slug");

-- CreateIndex
CREATE INDEX "vehicle_model_commercialStatus_effectiveAt_idx" ON "vehicle_model"("commercialStatus", "effectiveAt");

-- CreateIndex
CREATE UNIQUE INDEX "vehicle_variant_code_key" ON "vehicle_variant"("code");

-- CreateIndex
CREATE INDEX "vehicle_variant_vehicleModelId_commercialStatus_idx" ON "vehicle_variant"("vehicleModelId", "commercialStatus");

-- CreateIndex
CREATE INDEX "price_projection_vehicleVariantId_market_validFrom_idx" ON "price_projection"("vehicleVariantId", "market", "validFrom");

-- CreateIndex
CREATE INDEX "lead_status_createdAt_idx" ON "lead"("status", "createdAt");

-- CreateIndex
CREATE INDEX "quote_projection_customerRef_createdAt_idx" ON "quote_projection"("customerRef", "createdAt");

-- AddForeignKey
ALTER TABLE "session_projection" ADD CONSTRAINT "session_projection_identitySubjectId_fkey" FOREIGN KEY ("identitySubjectId") REFERENCES "identity_subject"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "cart_item" ADD CONSTRAINT "cart_item_cartId_fkey" FOREIGN KEY ("cartId") REFERENCES "cart"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "customer_profile" ADD CONSTRAINT "customer_profile_identitySubjectId_fkey" FOREIGN KEY ("identitySubjectId") REFERENCES "identity_subject"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "consent_event" ADD CONSTRAINT "consent_event_customerProfileId_fkey" FOREIGN KEY ("customerProfileId") REFERENCES "customer_profile"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "customer_vehicle_reference" ADD CONSTRAINT "customer_vehicle_reference_customerProfileId_fkey" FOREIGN KEY ("customerProfileId") REFERENCES "customer_profile"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "conversation_message" ADD CONSTRAINT "conversation_message_conversationSessionId_fkey" FOREIGN KEY ("conversationSessionId") REFERENCES "conversation_session"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "vehicle_energy_profile" ADD CONSTRAINT "vehicle_energy_profile_vehicleVariantId_fkey" FOREIGN KEY ("vehicleVariantId") REFERENCES "vehicle_variant"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "charging_connector" ADD CONSTRAINT "charging_connector_chargingStationId_fkey" FOREIGN KEY ("chargingStationId") REFERENCES "charging_station"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "charging_tariff" ADD CONSTRAINT "charging_tariff_chargingConnectorId_fkey" FOREIGN KEY ("chargingConnectorId") REFERENCES "charging_connector"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "vehicle_variant" ADD CONSTRAINT "vehicle_variant_vehicleModelId_fkey" FOREIGN KEY ("vehicleModelId") REFERENCES "vehicle_model"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
