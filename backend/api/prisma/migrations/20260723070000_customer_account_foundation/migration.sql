-- Customer account foundation: typed preferences, consent and DSAR lifecycle.
-- This is an expand/migrate/contract migration for staging data only.

CREATE TYPE "customer_profile_status" AS ENUM ('active', 'suspended', 'deleted');
CREATE TYPE "consent_state" AS ENUM ('granted', 'withdrawn');
CREATE TYPE "customer_request_source" AS ENUM (
  'customer_portal',
  'mobile',
  'operations_admin',
  'system_import'
);
CREATE TYPE "customer_data_request_type" AS ENUM ('export', 'delete');
CREATE TYPE "customer_data_request_status" AS ENUM (
  'requested',
  'processing',
  'partially_completed',
  'completed',
  'rejected'
);

ALTER TABLE "customer_profile"
  ADD COLUMN "market" VARCHAR(8) NOT NULL DEFAULT 'VN',
  ADD COLUMN "communicationEmail" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN "communicationSms" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN "communicationPush" BOOLEAN NOT NULL DEFAULT false;

UPDATE "customer_profile"
SET
  "communicationEmail" = COALESCE(
    ("communicationPreferences"->>'email')::boolean,
    false
  ),
  "communicationSms" = COALESCE(
    ("communicationPreferences"->>'sms')::boolean,
    false
  ),
  "communicationPush" = COALESCE(
    ("communicationPreferences"->>'push')::boolean,
    false
  );

ALTER TABLE "customer_profile"
  ALTER COLUMN "status" DROP DEFAULT,
  ALTER COLUMN "status" TYPE "customer_profile_status"
    USING ("status"::"customer_profile_status"),
  ALTER COLUMN "status" SET DEFAULT 'active',
  DROP COLUMN "communicationPreferences";

ALTER TABLE "consent_event"
  ADD COLUMN "idempotencyKeyHash" CHAR(64),
  ADD COLUMN "requestHash" CHAR(64);

UPDATE "consent_event"
SET
  "source" = CASE
    WHEN "source" = 'portal' THEN 'customer_portal'
    WHEN "source" IN ('customer_portal', 'mobile', 'operations_admin', 'system_import')
      THEN "source"
    ELSE 'system_import'
  END,
  "idempotencyKeyHash" = repeat(md5("correlationId"::text), 2),
  "requestHash" = repeat(
    md5(
      "purpose" || ':' || "policyVersion" || ':' || "state" || ':' || "source"
    ),
    2
  );

ALTER TABLE "consent_event"
  ALTER COLUMN "idempotencyKeyHash" SET NOT NULL,
  ALTER COLUMN "requestHash" SET NOT NULL,
  ALTER COLUMN "state" TYPE "consent_state"
    USING ("state"::"consent_state"),
  ALTER COLUMN "source" TYPE "customer_request_source"
    USING ("source"::"customer_request_source");

CREATE UNIQUE INDEX "consent_event_customerProfileId_correlationId_key"
  ON "consent_event"("customerProfileId", "correlationId");

CREATE UNIQUE INDEX "consent_event_idempotency_key"
  ON "consent_event"("customerProfileId", "purpose", "idempotencyKeyHash");

ALTER TABLE "customer_data_request"
  ADD COLUMN "idempotencyKeyHash" CHAR(64),
  ADD COLUMN "requestHash" CHAR(64);

UPDATE "customer_data_request"
SET
  "idempotencyKeyHash" = repeat(md5("correlationId"::text), 2),
  "requestHash" = repeat(
    md5("requestType"::text || ':' || "correlationId"::text),
    2
  ),
  "source" = CASE
    WHEN "source" = 'portal' THEN 'customer_portal'
    WHEN "source" IN ('customer_portal', 'mobile', 'operations_admin', 'system_import')
      THEN "source"
    ELSE 'system_import'
  END;

ALTER TABLE "customer_data_request"
  ALTER COLUMN "idempotencyKeyHash" SET NOT NULL,
  ALTER COLUMN "requestHash" SET NOT NULL,
  ALTER COLUMN "requestType" TYPE "customer_data_request_type"
    USING ("requestType"::"customer_data_request_type"),
  ALTER COLUMN "status" DROP DEFAULT,
  ALTER COLUMN "status" TYPE "customer_data_request_status"
    USING ("status"::"customer_data_request_status"),
  ALTER COLUMN "status" SET DEFAULT 'requested',
  ALTER COLUMN "source" TYPE "customer_request_source"
    USING ("source"::"customer_request_source");

CREATE UNIQUE INDEX
  "customer_data_request_idempotency_key"
  ON "customer_data_request"(
    "customerProfileId",
    "requestType",
    "idempotencyKeyHash"
  );
