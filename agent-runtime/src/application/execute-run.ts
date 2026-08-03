import type { AgentExecutor } from "../ports/agent-executor.js";
import type { GovernanceGateway } from "../ports/governance-gateway.js";
import type { RunStore } from "../ports/run-store.js";
import { RuntimeError } from "../domain/errors.js";
import type { RuntimeRun } from "../domain/runtime-run.js";
import { recordEvidence } from "./record-evidence.js";

export async function executeRun(
  runId: string,
  store: RunStore,
  governance: GovernanceGateway,
  executor: AgentExecutor,
): Promise<RuntimeRun> {
  let run = store.getRun(runId);
  if (!run) throw new RuntimeError("RUN_NOT_FOUND", `runtime run not found: ${runId}`);
  if (run.state !== "running") {
    throw new RuntimeError("RUN_NOT_EXECUTABLE", `runtime run is not running: ${run.state}`);
  }
  if (run.cancellationRequestedAt) return store.transition(run.id, run.version, "cancelled");

  const context = await governance.resolve(run.workItemKey, run.workspace);
  if (
    context.contextKey !== run.contextKey ||
    context.baseRevision !== run.baseRevision ||
    context.ownerTeam !== run.ownerTeam ||
    context.mode !== run.mode
  ) {
    return store.transition(run.id, run.version, "failed_safely", "STALE_CONTEXT");
  }
  try {
    await governance.assertExecutionAuthority(
      context,
      run.governanceClaimId && run.governanceFencingToken
        ? { claimId: run.governanceClaimId, fencingToken: run.governanceFencingToken }
        : null,
    );
  } catch (error) {
    return store.transition(
      run.id,
      run.version,
      "failed_safely",
      error instanceof RuntimeError ? error.code : "GOVERNANCE_AUTHORITY_REJECTED",
    );
  }
  store.appendEvent(run.id, "context.resolved", `context:${context.contextKey}`, {
    contextKey: context.contextKey,
    ownerTeam: context.ownerTeam,
    workspace: context.workspace,
    revision: context.baseRevision,
  });
  const activeRunId = run.id;
  const checkpoint = store.getLatestCheckpoint(activeRunId);
  const approvalDecisions = store.listApprovals()
    .filter((approval) => approval.runId === activeRunId)
    .flatMap((approval) => approval.status === "pending" ? [] : [{
        toolName: approval.toolName,
        interruptionId: approval.interruptionId,
        payloadDigest: approval.payloadDigest,
        decision: approval.status,
        reason: approval.decisionReason ?? approval.status,
      }]);
  const workerId = run.claimedBy;
  if (!workerId) throw new RuntimeError("WORKER_ID_MISSING", "running work has no worker identity");
  const abortController = new AbortController();
  const attempts = store.getUsageTotals(run.id).attempts;
  if (attempts > run.budget.maxAttempts) {
    return store.transition(run.id, run.version, "failed_safely", "ATTEMPT_BUDGET_EXCEEDED");
  }
  const executionEvent = store.appendEvent(run.id, "agent.started", `agent-start:${run.version}`, {
    workerId,
    attempt: attempts,
  });
  let heartbeatFailure: unknown = null;
  const heartbeat = () => {
    try {
      const current = store.heartbeat(activeRunId, workerId);
      if (current.cancellationRequestedAt) {
        abortController.abort(new RuntimeError("CANCEL_REQUESTED", "runtime cancellation was requested"));
      }
    } catch (error) {
      heartbeatFailure = error;
      abortController.abort(error);
    }
  };
  heartbeat();
  const heartbeatTimer = setInterval(heartbeat, 60_000);
  heartbeatTimer.unref();
  let outcome: Awaited<ReturnType<AgentExecutor["execute"]>>;
  try {
    if (executor.requiresEncryptedCheckpoint?.()) store.assertCheckpointEncryptionReady();
    outcome = await executor.execute({
      runId: run.id,
      objective: run.objective,
      context,
      budget: run.budget,
      signal: abortController.signal,
      ...(checkpoint ? { checkpointState: store.decryptCheckpoint(checkpoint) } : {}),
      ...(approvalDecisions.length > 0 ? { approvalDecisions } : {}),
    });
  } finally {
    clearInterval(heartbeatTimer);
  }
  if (heartbeatFailure) {
    throw heartbeatFailure instanceof Error
      ? heartbeatFailure
      : new RuntimeError("HEARTBEAT_FAILED", "runtime heartbeat failed with a non-error value");
  }
  heartbeat();
  if (heartbeatFailure) {
    throw heartbeatFailure instanceof Error
      ? heartbeatFailure
      : new RuntimeError("HEARTBEAT_FAILED", "runtime heartbeat failed with a non-error value");
  }
  run = store.getRun(run.id) ?? run;
  if (run.cancellationRequestedAt || abortController.signal.aborted) {
    store.recordUsage(run.id, outcome.usage, executionEvent.id);
    return store.transition(run.id, run.version, "cancelled");
  }
  if (outcome.serializedState) {
    store.saveCheckpoint(run.id, "agent-state", outcome.serializedState);
  }
  store.recordUsage(run.id, outcome.usage, executionEvent.id);
  const usage = store.getUsageTotals(run.id);
  if (
    usage.inputTokens > run.budget.maxInputTokens ||
    usage.outputTokens > run.budget.maxOutputTokens ||
    usage.estimatedUsd === null ||
    usage.estimatedUsd > run.budget.maxEstimatedUsd
  ) {
    run = store.getRun(run.id) ?? run;
    return store.transition(run.id, run.version, "failed_safely", "RUNTIME_BUDGET_EXCEEDED");
  }
  try {
    await governance.assertFresh(context);
    await governance.assertExecutionAuthority(
      context,
      run.governanceClaimId && run.governanceFencingToken
        ? { claimId: run.governanceClaimId, fencingToken: run.governanceFencingToken }
        : null,
    );
  } catch (error) {
    run = store.getRun(run.id) ?? run;
    return store.transition(
      run.id,
      run.version,
      "failed_safely",
      error instanceof RuntimeError ? error.code : "GOVERNANCE_REFRESH_FAILED",
    );
  }
  const approval = outcome.result.approvalRequest;
  const scopedAuthorities = new Set([...context.requiredAuthorities, context.accountableRole]);
  if (approval && (
    !scopedAuthorities.has(approval.requiredAuthority) ||
    !context.registeredAuthorities.includes(approval.requiredAuthority)
  )) {
    run = store.getRun(run.id) ?? run;
    return store.transition(run.id, run.version, "failed_safely", "UNKNOWN_APPROVAL_AUTHORITY");
  }
  const coordination = outcome.result.coordinationRequest;
  if (coordination && (
    !context.registeredTeams.includes(coordination.targetTeam) ||
    (coordination.requiredAuthority !== null &&
      !context.registeredAuthorities.includes(coordination.requiredAuthority))
  )) {
    run = store.getRun(run.id) ?? run;
    return store.transition(run.id, run.version, "failed_safely", "UNKNOWN_COORDINATION_TARGET");
  }
  for (const result of [outcome.result, ...outcome.specialistResults]) {
    await recordEvidence(run.id, result, store, governance, context);
  }
  store.appendEvent(run.id, "agent.completed", `agent-result:${run.version}`, {
    role: outcome.result.role,
    status: outcome.result.status,
    evidenceCount: outcome.result.evidence.length,
    findingCount: outcome.result.reviewFindings.length,
  });
  run = store.getRun(run.id) ?? run;
  if (run.cancellationRequestedAt) {
    return store.transition(run.id, run.version, "cancelled");
  }
  if (approval) {
    store.createApproval({
      runId: run.id,
      ...approval,
    });
    return store.transition(run.id, run.version, "waiting_approval");
  }
  if (outcome.result.status === "needs-decision") {
    return store.transition(run.id, run.version, "waiting_dependency");
  }
  if (outcome.result.status === "failed-safely") {
    return store.transition(run.id, run.version, "failed_safely", "AGENT_FAILED_SAFELY");
  }
  const findings = [outcome.result, ...outcome.specialistResults]
    .flatMap((result) => result.reviewFindings);
  if (findings.some((finding) => finding.severity === "P0" || finding.severity === "P1")) {
    return store.transition(run.id, run.version, "failed_safely", "OPEN_CRITICAL_FINDING");
  }
  const missingReviewer = context.requiredReviewers.find(
    (reviewer) => !outcome.specialistResults.some(
      (result) => result.role === reviewer && result.status === "completed",
    ),
  );
  if (missingReviewer) {
    return store.transition(run.id, run.version, "failed_safely", "REQUIRED_REVIEW_MISSING");
  }
  if (run.mode === "controlled") {
    run = store.transition(run.id, run.version, "reviewing");
  }
  return store.transition(run.id, run.version, "succeeded");
}
