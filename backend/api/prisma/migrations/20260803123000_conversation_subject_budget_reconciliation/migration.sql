-- Return unused per-session reservations to the authenticated subject's daily bucket.
ALTER TABLE "conversation_session"
    ADD COLUMN "subjectBudgetDate" DATE,
    ADD COLUMN "subjectBudgetReservedModelTokens" BIGINT,
    ADD COLUMN "subjectBudgetReservedCostMicros" BIGINT,
    ADD COLUMN "subjectBudgetReconciledAt" TIMESTAMPTZ(6);

ALTER TABLE "conversation_session"
    ADD CONSTRAINT "conversation_session_subject_budget_reservation_check"
    CHECK (
        ("subjectBudgetDate" IS NULL AND "subjectBudgetReservedModelTokens" IS NULL
            AND "subjectBudgetReservedCostMicros" IS NULL)
        OR ("ownerSubjectKeyHash" IS NOT NULL
            AND "subjectBudgetDate" IS NOT NULL
            AND "subjectBudgetReservedModelTokens" IS NOT NULL
            AND "subjectBudgetReservedModelTokens" >= 0
            AND "subjectBudgetReservedCostMicros" IS NOT NULL
            AND "subjectBudgetReservedCostMicros" >= 0)
    );
