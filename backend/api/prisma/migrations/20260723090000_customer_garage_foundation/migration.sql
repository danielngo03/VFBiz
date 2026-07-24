-- Customer Garage is a self-reported preference, not verified ownership.

CREATE TYPE "customer_garage_entry_status" AS ENUM ('active', 'archived');
CREATE TYPE "customer_garage_entry_source" AS ENUM ('self-reported', 'imported');

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM "customer_vehicle_reference"
    WHERE
      "vinTokenRef" IS NOT NULL
      OR "maskedVin" IS NOT NULL
      OR "verificationState" <> 'unverified'
      OR "verificationRequestedAt" IS NOT NULL
      OR "verifiedAt" IS NOT NULL
      OR "rejectionReasonCode" IS NOT NULL
  ) THEN
    RAISE EXCEPTION
      'Garage migration refused: legacy VIN or verification data requires an explicit ownership migration';
  END IF;
END
$$;

ALTER TABLE "customer_vehicle_reference"
  ADD COLUMN "isPrimary" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN "status" "customer_garage_entry_status" NOT NULL DEFAULT 'active',
  ADD COLUMN "createIdempotencyKeyHash" CHAR(64),
  ADD COLUMN "createRequestHash" CHAR(64);

UPDATE "customer_vehicle_reference"
SET
  "createIdempotencyKeyHash" = repeat(md5("id"::text), 2),
  "createRequestHash" = repeat(
    md5("vehicleVariantId"::text || ':' || coalesce("nickname", '')),
    2
  );

ALTER TABLE "customer_vehicle_reference"
  ALTER COLUMN "nickname" DROP NOT NULL,
  ALTER COLUMN "createIdempotencyKeyHash" SET NOT NULL,
  ALTER COLUMN "createRequestHash" SET NOT NULL,
  ALTER COLUMN "source" DROP DEFAULT,
  ALTER COLUMN "source" TYPE "customer_garage_entry_source"
    USING ("source"::"customer_garage_entry_source"),
  ALTER COLUMN "source" SET DEFAULT 'self-reported',
  DROP COLUMN "vinTokenRef",
  DROP COLUMN "maskedVin",
  DROP COLUMN "verificationState",
  DROP COLUMN "verificationRequestedAt",
  DROP COLUMN "verifiedAt",
  DROP COLUMN "rejectionReasonCode";

DROP INDEX IF EXISTS
  "customer_vehicle_reference_customerProfileId_verificationSt_idx";
DROP INDEX IF EXISTS "customer_vehicle_reference_vehicleVariantId_idx";

CREATE UNIQUE INDEX "customer_garage_entry_create_idempotency_key"
  ON "customer_vehicle_reference"(
    "customerProfileId",
    "createIdempotencyKeyHash"
  );
CREATE INDEX "customer_garage_entry_customer_status_updated_idx"
  ON "customer_vehicle_reference"("customerProfileId", "status", "updatedAt");
CREATE INDEX "customer_vehicle_reference_vehicleVariantId_idx"
  ON "customer_vehicle_reference"("vehicleVariantId");
CREATE UNIQUE INDEX "customer_garage_entry_one_primary_active"
  ON "customer_vehicle_reference"("customerProfileId")
  WHERE "status" = 'active' AND "isPrimary" = true;
