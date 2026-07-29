CREATE FUNCTION conversation_task_slots_are_safe(
    pending_slots JSONB,
    collected_slots JSONB
) RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    pending_slot JSONB;
    pending_name TEXT;
    pending_names TEXT[] := ARRAY[]::TEXT[];
    collected_name TEXT;
    collected_value JSONB;
    collected_count INTEGER;
    reference_value TEXT;
    authority_digest TEXT;
BEGIN
    IF jsonb_typeof(pending_slots) <> 'array'
        OR jsonb_typeof(collected_slots) <> 'object'
    THEN
        RETURN FALSE;
    END IF;

    SELECT count(*) INTO collected_count FROM jsonb_each(collected_slots);
    IF jsonb_array_length(pending_slots) > 16
        OR octet_length(pending_slots::TEXT) > 4096
        OR collected_count > 16
        OR octet_length(collected_slots::TEXT) > 8192
    THEN
        RETURN FALSE;
    END IF;

    FOR pending_slot IN SELECT value FROM jsonb_array_elements(pending_slots)
    LOOP
        IF jsonb_typeof(pending_slot) <> 'string' THEN
            RETURN FALSE;
        END IF;

        pending_name := pending_slot #>> '{}';
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
            OR jsonb_typeof(collected_value -> 'kind') <> 'string'
            OR collected_value ->> 'kind' <> 'opaque_reference'
            OR jsonb_typeof(collected_value -> 'reference') <> 'string'
            OR jsonb_typeof(collected_value -> 'authorityDigest') <> 'string'
        THEN
            RETURN FALSE;
        END IF;

        reference_value := collected_value ->> 'reference';
        authority_digest := collected_value ->> 'authorityDigest';
        IF reference_value
            !~ '^(vehicle|market|locale|profile|garage|policy|product|account):[a-z0-9][a-z0-9._/-]{0,143}$'
            OR authority_digest !~ '^[a-f0-9]{64}$'
        THEN
            RETURN FALSE;
        END IF;
    END LOOP;

    RETURN TRUE;
END;
$$;

CREATE TABLE "conversation_task_context" (
    "conversationSessionId" UUID NOT NULL,
    "taskId" UUID NOT NULL,
    "intent" VARCHAR(120) NOT NULL,
    "intentRevision" VARCHAR(160) NOT NULL,
    "pendingSlots" JSONB NOT NULL,
    "collectedSlots" JSONB NOT NULL,
    "sourceTurnId" UUID,
    "taskVersion" BIGINT NOT NULL DEFAULT 1,
    "lastFencingToken" BIGINT NOT NULL DEFAULT 0,
    "taskState" VARCHAR(32) NOT NULL,
    "authorizationContextDigest" CHAR(64) NOT NULL,
    "assistantReleaseActivationId" VARCHAR(160) NOT NULL,
    "assistantReleaseManifestSha256" CHAR(64) NOT NULL,
    "graphRevision" VARCHAR(160) NOT NULL,
    "policyRevision" VARCHAR(160) NOT NULL,
    "knowledgeRevision" VARCHAR(160) NOT NULL,
    "classification" VARCHAR(40) NOT NULL DEFAULT 'non_sensitive',
    "provenanceDigest" CHAR(64) NOT NULL,
    "expiresAt" TIMESTAMPTZ(6) NOT NULL,
    "closedAt" TIMESTAMPTZ(6),
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "conversation_task_context_pkey"
        PRIMARY KEY ("conversationSessionId"),
    CONSTRAINT "conversation_task_context_taskId_key"
        UNIQUE ("taskId"),
    CONSTRAINT "conversation_task_context_state_check"
        CHECK (
            "taskState" IN (
                'active',
                'awaiting_clarification',
                'closed',
                'expired'
            )
        ),
    CONSTRAINT "conversation_task_context_intent_check"
        CHECK ("intent" ~ '^[a-z][a-z0-9_.-]{0,119}$'),
    CONSTRAINT "conversation_task_context_slots_check"
        CHECK (conversation_task_slots_are_safe("pendingSlots", "collectedSlots")),
    CONSTRAINT "conversation_task_context_version_check"
        CHECK ("taskVersion" > 0 AND "lastFencingToken" >= 0),
    CONSTRAINT "conversation_task_context_digest_check"
        CHECK (
            "authorizationContextDigest" ~ '^[a-f0-9]{64}$'
            AND "assistantReleaseManifestSha256" ~ '^[a-f0-9]{64}$'
            AND "provenanceDigest" ~ '^[a-f0-9]{64}$'
        ),
    CONSTRAINT "conversation_task_context_classification_check"
        CHECK ("classification" = 'non_sensitive'),
    CONSTRAINT "conversation_task_context_expiry_check"
        CHECK ("expiresAt" > "createdAt"),
    CONSTRAINT "conversation_task_context_lifecycle_check"
        CHECK (
            (
                "taskState" IN ('active', 'awaiting_clarification')
                AND "closedAt" IS NULL
            )
            OR (
                "taskState" IN ('closed', 'expired')
                AND "closedAt" IS NOT NULL
            )
        )
);

CREATE INDEX "conversation_task_context_taskState_expiresAt_idx"
    ON "conversation_task_context"("taskState", "expiresAt");

CREATE INDEX "conversation_task_context_assistantReleaseActivationId_assi_idx"
    ON "conversation_task_context"(
        "assistantReleaseActivationId",
        "assistantReleaseManifestSha256"
    );

ALTER TABLE "conversation_task_context"
    ADD CONSTRAINT "conversation_task_context_conversationSessionId_fkey"
    FOREIGN KEY ("conversationSessionId")
    REFERENCES "conversation_session"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "conversation_turn"
    ADD CONSTRAINT "conversation_turn_id_conversationSessionId_key"
    UNIQUE ("id", "conversationSessionId");

ALTER TABLE "conversation_task_context"
    ADD CONSTRAINT "conversation_task_context_sourceTurnId_conversationSession_fkey"
    FOREIGN KEY ("sourceTurnId", "conversationSessionId")
    REFERENCES "conversation_turn"("id", "conversationSessionId")
    ON DELETE CASCADE ON UPDATE CASCADE;
