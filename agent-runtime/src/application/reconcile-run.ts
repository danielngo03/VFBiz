import type { RuntimeRun } from "../domain/runtime-run.js";
import type { RunStore } from "../ports/run-store.js";

export function reconcileRuns(store: RunStore, staleAfterMs = 5 * 60_000): RuntimeRun[] {
  return store.reconcileStale(new Date(Date.now() - staleAfterMs).toISOString());
}
