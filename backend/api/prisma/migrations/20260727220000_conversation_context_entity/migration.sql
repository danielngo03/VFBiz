CREATE TABLE "conversation_context_entity" (
    "id" UUID NOT NULL,
    "conversationSessionId" UUID NOT NULL,
    "subjectKeyHash" CHAR(64) NOT NULL,
    "kind" VARCHAR(40) NOT NULL,
    "opaqueReference" VARCHAR(160) NOT NULL,
    "authority" VARCHAR(80) NOT NULL,
    "sourceRevision" VARCHAR(160) NOT NULL,
    "classification" VARCHAR(40) NOT NULL DEFAULT 'non_sensitive',
    "confirmedAt" TIMESTAMPTZ(6) NOT NULL,
    "expiresAt" TIMESTAMPTZ(6) NOT NULL,
    "validationState" VARCHAR(24) NOT NULL DEFAULT 'validated',
    "provenanceDigest" CHAR(64) NOT NULL,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "conversation_context_entity_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "conversation_context_entity_kind_check" CHECK ("kind" IN ('vehicle_model', 'vehicle_variant', 'market', 'language')),
    CONSTRAINT "conversation_context_entity_classification_check" CHECK ("classification" = 'non_sensitive'),
    CONSTRAINT "conversation_context_entity_state_check" CHECK ("validationState" IN ('validated', 'expired', 'revoked')),
    CONSTRAINT "conversation_context_entity_reference_check" CHECK (length(btrim("opaqueReference")) > 0),
    CONSTRAINT "conversation_context_entity_expiry_check" CHECK ("expiresAt" > "confirmedAt"),
    CONSTRAINT "conversation_context_entity_provenance_check" CHECK ("provenanceDigest" ~ '^[a-f0-9]{64}$'),
    CONSTRAINT "conversation_context_entity_subject_check" CHECK ("subjectKeyHash" ~ '^[a-f0-9]{64}$')
);

CREATE UNIQUE INDEX "conversation_context_entity_conversationSessionId_kind_key"
    ON "conversation_context_entity"("conversationSessionId", "kind");
CREATE INDEX "conversation_context_entity_conversationSessionId_validationState_expiresAt_idx"
    ON "conversation_context_entity"("conversationSessionId", "validationState", "expiresAt");
CREATE INDEX "conversation_context_entity_subjectKeyHash_expiresAt_idx"
    ON "conversation_context_entity"("subjectKeyHash", "expiresAt");

ALTER TABLE "conversation_context_entity"
    ADD CONSTRAINT "conversation_context_entity_conversationSessionId_fkey"
    FOREIGN KEY ("conversationSessionId") REFERENCES "conversation_session"("id")
    ON DELETE CASCADE ON UPDATE CASCADE;
