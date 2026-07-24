CREATE SEQUENCE "consent_event_event_sequence_seq";

ALTER TABLE "consent_event"
ADD COLUMN "event_sequence" BIGINT;

WITH "ordered_events" AS (
  SELECT
    "id",
    ROW_NUMBER() OVER (ORDER BY "occurredAt", "id") AS "sequence_value"
  FROM "consent_event"
)
UPDATE "consent_event" AS "event"
SET "event_sequence" = "ordered_events"."sequence_value"
FROM "ordered_events"
WHERE "event"."id" = "ordered_events"."id";

SELECT setval(
  '"consent_event_event_sequence_seq"',
  GREATEST(COALESCE((SELECT MAX("event_sequence") FROM "consent_event"), 0), 1),
  EXISTS(SELECT 1 FROM "consent_event")
);

ALTER SEQUENCE "consent_event_event_sequence_seq"
OWNED BY "consent_event"."event_sequence";

ALTER TABLE "consent_event"
ALTER COLUMN "event_sequence"
SET DEFAULT nextval('"consent_event_event_sequence_seq"'),
ALTER COLUMN "event_sequence"
SET NOT NULL;

CREATE UNIQUE INDEX "consent_event_event_sequence_key"
ON "consent_event"("event_sequence");
