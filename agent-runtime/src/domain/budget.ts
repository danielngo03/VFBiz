export interface RuntimeBudget {
  maxTurns: number;
  maxAttempts: number;
  maxInputTokens: number;
  maxOutputTokens: number;
  maxEstimatedUsd: number;
}

export const defaultRuntimeBudget: RuntimeBudget = Object.freeze({
  maxTurns: 24,
  maxAttempts: 2,
  maxInputTokens: 100_000,
  maxOutputTokens: 25_000,
  maxEstimatedUsd: 25,
});

export function assertBudget(budget: RuntimeBudget): void {
  for (const [name, value] of Object.entries(budget)) {
    if (!Number.isFinite(value) || value <= 0) {
      throw new Error(`runtime budget ${name} must be a positive number`);
    }
  }
  if (budget.maxAttempts > 2) {
    throw new Error("runtime retry budget cannot exceed organization policy");
  }
  if (!Number.isInteger(budget.maxTurns) || budget.maxTurns > 30) {
    throw new Error("runtime turn budget must be an integer no greater than 30");
  }
}
