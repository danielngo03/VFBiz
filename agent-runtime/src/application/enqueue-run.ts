import { createHash } from "node:crypto";
import { assertBudget, defaultRuntimeBudget, type RuntimeBudget } from "../domain/budget.js";
import type { RuntimeMode, RuntimeRun } from "../domain/runtime-run.js";
import { RuntimeError } from "../domain/errors.js";
import type { GovernanceGateway } from "../ports/governance-gateway.js";
import type { RunStore } from "../ports/run-store.js";

export interface EnqueueRuntimeRequest {
  workItemKey: string;
  targetPath: string;
  objective?: string;
  mode?: RuntimeMode;
  idempotencyKey?: string;
  budget?: RuntimeBudget;
  governanceClaimId?: string;
  governanceFencingToken?: number;
}

export async function enqueueRun(
  request: EnqueueRuntimeRequest,
  store: RunStore,
  governance: GovernanceGateway,
): Promise<RuntimeRun> {
  const context = await governance.resolve(request.workItemKey, request.targetPath);
  if (request.mode && request.mode !== context.mode) {
    throw new RuntimeError(
      "MODE_OVERRIDE_REJECTED",
      `requested mode ${request.mode} does not match canonical mode ${context.mode}`,
    );
  }
  const authority = request.governanceClaimId && request.governanceFencingToken
    ? { claimId: request.governanceClaimId, fencingToken: request.governanceFencingToken }
    : null;
  if (Boolean(request.governanceClaimId) !== Boolean(request.governanceFencingToken)) {
    throw new RuntimeError(
      "CLAIM_AUTHORITY_INCOMPLETE",
      "governance claim and fencing token must be supplied together",
    );
  }
  await governance.assertExecutionAuthority(context, authority);
  const objective = request.objective ?? `Execute governed work item ${request.workItemKey}`;
  const budget = request.budget ?? defaultRuntimeBudget;
  assertBudget(budget);
  const idempotencyKey = request.idempotencyKey ?? createHash("sha256")
    .update([request.workItemKey, context.workItemRevision, context.contextKey, objective].join(":"))
    .digest("hex");
  return store.enqueue({
    workItemKey: request.workItemKey,
    idempotencyKey,
    objective,
    mode: context.mode,
    workspace: request.targetPath,
    ownerTeam: context.ownerTeam,
    contextKey: context.contextKey,
    baseRevision: context.baseRevision,
    governanceClaimId: authority?.claimId ?? null,
    governanceFencingToken: authority?.fencingToken ?? null,
    budget,
  });
}
