import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  buildResumeBrief,
  type ResumeContextSnapshot,
} from "../../src/application/build-resume-brief.js";
import { SqliteRunStore } from "../../src/adapters/persistence/sqlite/sqlite-run-store.js";
import { StateCipher } from "../../src/adapters/persistence/sqlite/state-cipher.js";
import { enqueueInput, testStateKey } from "../helpers.js";

const temporaryRoots: string[] = [];
afterEach(async () => {
  await Promise.all(temporaryRoots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("restart and reconciliation", () => {
  it("resumes from the committed checkpoint without duplicating enqueue", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "runtime-store-test-"));
    temporaryRoots.push(root);
    const database = path.join(root, "runtime.sqlite");
    const firstStore = new SqliteRunStore(database, () => new StateCipher(testStateKey));
    firstStore.initialize();
    const run = firstStore.enqueue(enqueueInput());
    const claimed = firstStore.claimNextRun("worker-before-crash");
    expect(claimed).not.toBeNull();
    firstStore.saveCheckpoint(run.id, "agent-state", "checkpoint-before-crash");
    firstStore.close();

    const restarted = new SqliteRunStore(database, () => new StateCipher(testStateKey));
    restarted.initialize();
    const reconciled = restarted.reconcileStale("9999-12-31T23:59:59.999Z");
    expect(reconciled).toHaveLength(1);
    expect(restarted.claimNextRun("worker-after-crash")?.id).toBe(run.id);
    const checkpoint = restarted.getLatestCheckpoint(run.id);
    expect(checkpoint && restarted.decryptCheckpoint(checkpoint)).toBe("checkpoint-before-crash");
    expect(restarted.enqueue(enqueueInput()).id).toBe(run.id);
    expect(restarted.listEvents(run.id).filter(({ type }) => type === "run.enqueued")).toHaveLength(1);
    restarted.close();
  });

  it("finalizes a cancellation when its active worker dies", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "runtime-cancel-reconcile-"));
    temporaryRoots.push(root);
    const store = new SqliteRunStore(path.join(root, "runtime.sqlite"), () => new StateCipher(testStateKey));
    store.initialize();
    const run = store.enqueue(enqueueInput({ idempotencyKey: "cancel-reconcile" }));
    expect(store.claimNextRun("worker-before-cancel")?.id).toBe(run.id);
    expect(store.requestCancellation(run.id).state).toBe("running");
    const reconciled = store.reconcileStale("9999-12-31T23:59:59.999Z");
    expect(reconciled).toHaveLength(1);
    expect(reconciled[0]?.state).toBe("cancelled");
    expect(store.claimNextRun("worker-after-cancel")).toBeNull();
    store.close();
  });

  it("reconstructs the same bounded morning brief after a process restart", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "runtime-brief-restart-"));
    temporaryRoots.push(root);
    const database = path.join(root, "runtime.sqlite");
    const firstStore = new SqliteRunStore(database, () => new StateCipher(testStateKey));
    firstStore.initialize();
    const run = firstStore.enqueue(enqueueInput({ idempotencyKey: "overnight-brief" }));
    expect(firstStore.claimNextRun("worker-night")).not.toBeNull();
    firstStore.saveCheckpoint(run.id, "agent-state", "encrypted-overnight-state");
    const current = firstStore.getRun(run.id);
    expect(current).not.toBeNull();
    firstStore.transition(run.id, current?.version ?? 0, "waiting_dependency");
    firstStore.close();

    const restarted = new SqliteRunStore(database, () => new StateCipher(testStateKey));
    restarted.initialize();
    const resumeContext: ResumeContextSnapshot = {
      contextKey: "a".repeat(64),
      workItem: {
        id: "VFBIZ-0204",
        revision: 8,
        status: "active",
        sections: {
          checkpoint: {
            excerpt: "- Exact next action: resolve the overnight dependency.",
          },
          done_when: { excerpt: "- Resume is deterministic." },
        },
      },
      resumeDelta: { changedSources: [] },
      sourceRevisions: [],
    };
    const brief = await buildResumeBrief(
      {
        runId: run.id,
        headRevision: run.baseRevision ?? "",
        workingTreeDirty: false,
        changedPathCount: 0,
        now: "2026-07-31T07:00:00.000Z",
      },
      restarted,
      () => Promise.resolve(resumeContext),
    );
    expect(brief).toMatchObject({
      disposition: "human-decision-required",
      nextAction: "resolve the overnight dependency.",
      run: { id: run.id, state: "waiting_dependency" },
      latestCheckpoint: { kind: "agent-state" },
    });
    restarted.close();
  });
});
