#!/usr/bin/env node
import { RuntimeError } from "../domain/errors.js";
import type { RuntimeRun } from "../domain/runtime-run.js";
import { executeRun } from "../application/execute-run.js";
import { reconcileRuns } from "../application/reconcile-run.js";
import { createRuntime } from "../index.js";

export async function processOne(workerId = `worker-${process.pid}`): Promise<RuntimeRun | null> {
  const { store, governance, agentExecutor } = createRuntime();
  try {
    reconcileRuns(store);
    const claimed = store.claimNextRun(workerId);
    if (!claimed) return null;
    try {
      return await executeRun(claimed.id, store, governance, agentExecutor);
    } catch (error) {
      const current = store.getRun(claimed.id);
      if (current?.state === "running" || current?.state === "reviewing") {
        if (current.cancellationRequestedAt) {
          return store.transition(current.id, current.version, "cancelled");
        }
        return store.transition(
          current.id,
          current.version,
          "failed_safely",
          error instanceof RuntimeError ? error.code : "UNEXPECTED_ERROR",
        );
      }
      throw error;
    }
  } finally {
    store.close();
  }
}

export async function watch(workerId = `worker-${process.pid}`, intervalMs = 2_000): Promise<void> {
  let stopping = false;
  process.once("SIGINT", () => { stopping = true; });
  process.once("SIGTERM", () => { stopping = true; });
  while (!stopping) {
    const result = await processOne(workerId);
    if (!result) await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

if (import.meta.url === new URL(process.argv[1] ?? "", "file:").href) {
  const watchMode = process.argv.includes("--watch");
  const result = watchMode ? await watch() : await processOne();
  if (!watchMode) process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}
