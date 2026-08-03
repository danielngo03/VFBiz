import { describe, expect, it } from "vitest";
import { assertBudget, defaultRuntimeBudget } from "../../src/domain/budget.js";
import { canTransition } from "../../src/domain/runtime-run.js";

describe("runtime state and budgets", () => {
  it("permits only declared lifecycle transitions", () => {
    expect(canTransition("queued", "running")).toBe(true);
    expect(canTransition("running", "waiting_approval")).toBe(true);
    expect(canTransition("waiting_approval", "running")).toBe(true);
    expect(canTransition("succeeded", "running")).toBe(false);
    expect(canTransition("queued", "succeeded")).toBe(false);
  });

  it("caps same-cause attempts at two", () => {
    expect(() => assertBudget(defaultRuntimeBudget)).not.toThrow();
    expect(() => assertBudget({ ...defaultRuntimeBudget, maxAttempts: 3 })).toThrow(
      /retry budget/,
    );
  });
});
