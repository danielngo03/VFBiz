import type { RuntimeRun } from "../domain/runtime-run.js";
import type { RunStore } from "../ports/run-store.js";

export function cancelRun(runId: string, store: RunStore): RuntimeRun {
  return store.requestCancellation(runId);
}
