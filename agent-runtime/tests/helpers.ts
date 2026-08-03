import { defaultRuntimeBudget } from "../src/domain/budget.js";
import type { EnqueueRunInput } from "../src/domain/runtime-run.js";

export const testStateKey = Buffer.alloc(32, 7).toString("base64");

export function enqueueInput(overrides: Partial<EnqueueRunInput> = {}): EnqueueRunInput {
  return {
    workItemKey: "VFBIZ-0204",
    idempotencyKey: "fixture-enqueue",
    objective: "Perform one synthetic fixture task",
    mode: "controlled",
    workspace: "agent-runtime",
    ownerTeam: "agent-platform",
    contextKey: "a".repeat(64),
    baseRevision: "731ba5f459eada0ac9af52b179c74f8e6696d40d",
    governanceClaimId: "claim-fixture",
    governanceFencingToken: 1,
    budget: defaultRuntimeBudget,
    ...overrides,
  };
}
