-- Prevent authenticated customers from resetting the daily AI budget by creating new sessions.
CREATE TABLE "conversation_subject_budget" (
    "subjectKeyHash" CHAR(64) NOT NULL,
    "budgetDate" DATE NOT NULL,
    "remainingModelTokens" BIGINT NOT NULL,
    "remainingCostMicros" BIGINT NOT NULL,
    "version" BIGINT NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "conversation_subject_budget_pkey" PRIMARY KEY ("subjectKeyHash", "budgetDate"),
    CONSTRAINT "conversation_subject_budget_remaining_check" CHECK (
        "remainingModelTokens" >= 0 AND "remainingCostMicros" >= 0
    ),
    CONSTRAINT "conversation_subject_budget_version_check" CHECK ("version" >= 0)
);

CREATE INDEX "conversation_subject_budget_budgetDate_updatedAt_idx"
    ON "conversation_subject_budget" ("budgetDate", "updatedAt");
