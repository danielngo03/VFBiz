import type { RuntimeBudget } from "./budget.js";

export const runtimeStates = [
  "queued",
  "running",
  "waiting_approval",
  "waiting_dependency",
  "reviewing",
  "succeeded",
  "failed_safely",
  "cancelled",
] as const;

export type RuntimeState = (typeof runtimeStates)[number];
export type RuntimeMode = "discovery" | "bounded" | "controlled";

export interface RuntimeRun {
  id: string;
  workItemKey: string;
  idempotencyKey: string;
  state: RuntimeState;
  mode: RuntimeMode;
  objective: string;
  workspace: string;
  ownerTeam: string | null;
  contextKey: string | null;
  baseRevision: string | null;
  governanceClaimId: string | null;
  governanceFencingToken: number | null;
  claimedBy: string | null;
  heartbeatAt: string | null;
  cancellationRequestedAt: string | null;
  failureCode: string | null;
  version: number;
  budget: RuntimeBudget;
  createdAt: string;
  updatedAt: string;
}

export interface EnqueueRunInput {
  workItemKey: string;
  idempotencyKey: string;
  objective: string;
  mode: RuntimeMode;
  workspace: string;
  ownerTeam: string;
  contextKey: string;
  baseRevision: string;
  governanceClaimId: string | null;
  governanceFencingToken: number | null;
  budget: RuntimeBudget;
}

export const terminalStates = new Set<RuntimeState>([
  "succeeded",
  "failed_safely",
  "cancelled",
]);

export function canTransition(from: RuntimeState, to: RuntimeState): boolean {
  const transitions: Record<RuntimeState, readonly RuntimeState[]> = {
    queued: ["running", "cancelled", "failed_safely"],
    running: [
      "waiting_approval",
      "waiting_dependency",
      "reviewing",
      "succeeded",
      "failed_safely",
      "cancelled",
    ],
    waiting_approval: ["running", "failed_safely", "cancelled"],
    waiting_dependency: ["running", "failed_safely", "cancelled"],
    reviewing: ["running", "succeeded", "failed_safely", "cancelled"],
    succeeded: [],
    failed_safely: [],
    cancelled: [],
  };
  return transitions[from].includes(to);
}
