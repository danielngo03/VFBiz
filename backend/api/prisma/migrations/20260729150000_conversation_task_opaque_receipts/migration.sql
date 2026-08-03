CREATE OR REPLACE FUNCTION conversation_task_slots_are_safe(
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
    reference_value TEXT;
    authority_digest TEXT;
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

    FOR pending_name IN
        SELECT jsonb_array_elements_text(pending_slots)
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
                    'reference', collected_value -> 'reference',
                    'authorityDigest', collected_value -> 'authorityDigest'
                )
            OR collected_value ->> 'kind' <> 'opaque_reference'
            OR jsonb_typeof(collected_value -> 'reference') <> 'string'
            OR jsonb_typeof(collected_value -> 'authorityDigest') <> 'string'
        THEN
            RETURN FALSE;
        END IF;

        reference_value := collected_value ->> 'reference';
        authority_digest := collected_value ->> 'authorityDigest';
        IF reference_value
            !~ '^(vehicle|market|locale|profile|garage|policy|product|account):ref/v1/[a-f0-9]{64}$'
            OR authority_digest !~ '^[a-f0-9]{64}$'
        THEN
            RETURN FALSE;
        END IF;
    END LOOP;

    RETURN TRUE;
END;
$$;

ALTER TABLE "conversation_task_context"
    DROP CONSTRAINT "conversation_task_context_slots_check";

ALTER TABLE "conversation_task_context"
    ADD CONSTRAINT "conversation_task_context_slots_check"
    CHECK (
        conversation_task_slots_are_safe("pendingSlots", "collectedSlots")
    ) NOT VALID;

ALTER TABLE "conversation_task_context"
    VALIDATE CONSTRAINT "conversation_task_context_slots_check";
