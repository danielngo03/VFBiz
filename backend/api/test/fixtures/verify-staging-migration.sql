DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM customer_vehicle_reference
    WHERE "vehicleVariantId" = '00000000-0000-0000-0000-000000000011'
      AND nickname = 'VF Test 1'
  ) THEN RAISE EXCEPTION 'garage backfill failed';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM charging_connector
    WHERE status = 'unknown' AND "lastObservedAt" IS NOT NULL
  ) THEN RAISE EXCEPTION 'connector freshness backfill failed';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM trip_plan_projection
    WHERE status = 'unavailable'
      AND "algorithmRevision" = 'legacy-unverified'
      AND "providerPayloadStored" = false
  ) THEN RAISE EXCEPTION 'trip fail-closed backfill failed';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM conversation_message WHERE sequence = 1
  ) THEN RAISE EXCEPTION 'message sequence backfill failed';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE indexname = 'charging_station_location_gist_idx'
  ) THEN RAISE EXCEPTION 'PostGIS GIST index missing';
  END IF;
END $$;
