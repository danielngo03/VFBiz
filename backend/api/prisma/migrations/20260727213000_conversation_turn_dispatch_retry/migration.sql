ALTER TABLE "conversation_turn"
    ADD COLUMN "dispatchAttempts" INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN "dispatchAvailableAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN "dispatchFailureCode" VARCHAR(64),
    ADD COLUMN "dispatchFailedAt" TIMESTAMPTZ(6);

CREATE INDEX "conversation_turn_status_dispatchAvailableAt_receivedSequence_idx"
    ON "conversation_turn"("status", "dispatchAvailableAt", "receivedSequence");
