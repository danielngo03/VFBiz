CREATE OR REPLACE FUNCTION conversation_task_slots_are_safe_v2(
    task_id UUID,
    task_expires_at TIMESTAMPTZ,
    pending_slots JSONB,
    collected_slots JSONB
)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    pending_name TEXT;
    pending_names TEXT[] := ARRAY[]::TEXT[];
    collected_name TEXT;
    collected_value JSONB;
    confirmed_at TIMESTAMPTZ;
    expires_at TIMESTAMPTZ;
BEGIN
    IF jsonb_typeof(pending_slots) <> 'array'
        OR jsonb_array_length(pending_slots) > 16
        OR jsonb_typeof(collected_slots) <> 'object'
        OR (
            SELECT count(*)
            FROM jsonb_object_keys(collected_slots)
        ) > 16
    THEN
        RETURN FALSE;
    END IF;

    FOR pending_name IN SELECT jsonb_array_elements_text(pending_slots)
    LOOP
        IF pending_name !~ '^[a-z][a-z0-9_.-]{0,63}$'
            OR pending_name = ANY(pending_names)
        THEN
            RETURN FALSE;
        END IF;
        pending_names := array_append(pending_names, pending_name);
    END LOOP;

    FOR collected_name, collected_value IN
        SELECT key, value FROM jsonb_each(collected_slots)
    LOOP
        IF collected_name !~ '^[a-z][a-z0-9_.-]{0,63}$'
            OR collected_name = ANY(pending_names)
            OR jsonb_typeof(collected_value) <> 'object'
            OR collected_value
                <> jsonb_build_object(
                    'kind', collected_value -> 'kind',
                    'authority', collected_value -> 'authority',
                    'authorityDigest', collected_value -> 'authorityDigest',
                    'opaqueReference', collected_value -> 'opaqueReference',
                    'sourceRevision', collected_value -> 'sourceRevision',
                    'confirmedAt', collected_value -> 'confirmedAt',
                    'expiresAt', collected_value -> 'expiresAt',
                    'provenanceDigest', collected_value -> 'provenanceDigest',
                    'slot', collected_value -> 'slot',
                    'taskId', collected_value -> 'taskId'
                )
            OR collected_value ->> 'kind' <> 'receipt'
            OR collected_value ->> 'taskId' <> task_id::text
            OR collected_value ->> 'slot' <> collected_name
            OR collected_value ->> 'authority' NOT IN (
                'business_policy',
                'customer_garage',
                'customer_profile',
                'locale_policy',
                'market_catalog',
                'vehicle_catalog'
            )
            OR collected_value ->> 'opaqueReference'
                !~ '^(vehicle|market|locale|profile|garage|policy|product|account):ref/v1/[a-f0-9]{64}$'
            OR collected_value ->> 'authorityDigest' !~ '^[a-f0-9]{64}$'
            OR collected_value ->> 'provenanceDigest' !~ '^[a-f0-9]{64}$'
            OR collected_value ->> 'sourceRevision'
                !~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$'
            OR collected_value ->> 'confirmedAt'
                !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
            OR collected_value ->> 'expiresAt'
                !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
        THEN
            RETURN FALSE;
        END IF;

        BEGIN
            confirmed_at := (collected_value ->> 'confirmedAt')::timestamptz;
            expires_at := (collected_value ->> 'expiresAt')::timestamptz;
        EXCEPTION WHEN OTHERS THEN
            RETURN FALSE;
        END;
        IF expires_at <= confirmed_at OR expires_at > task_expires_at THEN
            RETURN FALSE;
        END IF;
    END LOOP;

    RETURN TRUE;
END;
$$;

ALTER TABLE "conversation_task_context"
    DROP CONSTRAINT "conversation_task_context_slots_check";

-- The preceding migration allowed a weaker opaque-reference envelope without
-- task/slot binding. Those values cannot be upgraded into authority receipts
-- without re-validating the underlying business entity. Expire affected tasks
-- fail-closed so the next customer turn starts a fresh authoritative task.
INSERT INTO "outbox_event" (
    "id",
    "aggregateType",
    "aggregateId",
    "eventType",
    "eventVersion",
    "payload",
    "correlationId"
)
SELECT
    gen_random_uuid(),
    'conversation',
    "conversationSessionId"::text,
    'conversation.task.receipt_invalidated',
    1,
    jsonb_build_object(
        'reason', 'legacy_slot_receipt_unverifiable',
        'previousTaskVersion', "taskVersion",
        'previousProvenanceDigest', "provenanceDigest",
        'invalidatedReceiptSetSha256',
            encode(digest("collectedSlots"::text, 'sha256'), 'hex'),
        'invalidatedSlotCount', (
            SELECT count(*) FROM jsonb_object_keys("collectedSlots")
        ),
        'migrationRevision', '20260729160000'
    ),
    gen_random_uuid()
FROM "conversation_task_context"
WHERE "collectedSlots" <> '{}'::jsonb;

UPDATE "conversation_task_context"
SET
    "taskState" = 'expired',
    "closedAt" = COALESCE("closedAt", CURRENT_TIMESTAMP),
    "pendingSlots" = '[]'::jsonb,
    "collectedSlots" = '{}'::jsonb,
    "taskVersion" = "taskVersion" + 1,
    "provenanceDigest" = encode(
        digest(
            concat_ws(
                ':',
                "conversationSessionId"::text,
                "taskId"::text,
                "provenanceDigest",
                encode(digest("collectedSlots"::text, 'sha256'), 'hex'),
                '20260729160000'
            ),
            'sha256'
        ),
        'hex'
    )
WHERE "collectedSlots" <> '{}'::jsonb;

ALTER TABLE "conversation_task_context"
    ADD CONSTRAINT "conversation_task_context_slots_check"
    CHECK (
        conversation_task_slots_are_safe_v2(
            "taskId",
            "expiresAt",
            "pendingSlots",
            "collectedSlots"
        )
    ) NOT VALID;

ALTER TABLE "conversation_task_context"
    VALIDATE CONSTRAINT "conversation_task_context_slots_check";
