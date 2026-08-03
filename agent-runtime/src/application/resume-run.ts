import { RuntimeError } from "../domain/errors.js";
import type { RuntimeRun } from "../domain/runtime-run.js";
import type { RunStore } from "../ports/run-store.js";

export function resumeRun(
  runId: string,
  store: RunStore,
  workerId = `resume-${process.pid}`,
): RuntimeRun {
  const run = store.getRun(runId);
  if (!run) throw new RuntimeError("RUN_NOT_FOUND", `runtime run not found: ${runId}`);
  if (run.state === "waiting_approval") {
    const approvals = store.listApprovals().filter((approval) => approval.runId === runId);
    if (approvals.some((approval) => approval.status === "pending")) {
      throw new RuntimeError("APPROVAL_PENDING", "run still has pending approval decisions");
    }
    if (approvals.some((approval) => approval.status === "rejected")) {
      return store.transition(run.id, run.version, "failed_safely", "APPROVAL_REJECTED");
    }
    return store.resumeWaiting(run.id, run.version, workerId);
  }
  if (run.state === "waiting_dependency") {
    return store.resumeWaiting(run.id, run.version, workerId);
  }
  throw new RuntimeError("RUN_NOT_RESUMABLE", `runtime run is not waiting: ${run.state}`);
}
