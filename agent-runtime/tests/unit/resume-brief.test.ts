import { describe, expect, it } from "vitest";
import {
  buildResumeBrief,
  type ResumeContextSnapshot,
} from "../../src/application/build-resume-brief.js";
import { SqliteRunStore } from "../../src/adapters/persistence/sqlite/sqlite-run-store.js";
import { StateCipher } from "../../src/adapters/persistence/sqlite/state-cipher.js";
import { enqueueInput, testStateKey } from "../helpers.js";

function context(
  overrides: Partial<ResumeContextSnapshot> = {},
): ResumeContextSnapshot {
  return {
    contextKey: "a".repeat(64),
    workItem: {
      id: "VFBIZ-0204",
      revision: 8,
      status: "active",
      sections: {
        checkpoint: {
          excerpt:
            "- Runtime persisted.\n- Exact next action: inspect the morning brief before resume.",
        },
        done_when: {
          excerpt: "- Desktop can recover context without provider memory.",
        },
      },
    },
    resumeDelta: { changedSources: [] },
    sourceRevisions: [
      {
        kind: "instruction",
        path: "AGENTS.md",
        sourceHash: "b".repeat(64),
      },
    ],
    ...overrides,
  };
}

describe("runtime resume brief", () => {
  it("uses the canonical work-item checkpoint when no runtime run exists", async () => {
    const store = new SqliteRunStore(":memory:", () => new StateCipher(testStateKey));
    store.initialize();
    const brief = await buildResumeBrief(
      {
        workItemKey: "VFBIZ-0204",
        targetPath: "agent-runtime",
        headRevision: "731ba5f459eada0ac9af52b179c74f8e6696d40d",
        workingTreeDirty: false,
        changedPathCount: 0,
        now: "2026-07-31T00:00:00.000Z",
      },
      store,
      () => Promise.resolve(context()),
    );
    expect(brief.disposition).toBe("no-runtime-run");
    expect(brief.nextAction).toBe("inspect the morning brief before resume.");
    expect(brief.workItem?.id).toBe("VFBIZ-0204");
    store.close();
  });

  it("requires a fresh context before a stale run can resume", async () => {
    const store = new SqliteRunStore(":memory:", () => new StateCipher(testStateKey));
    store.initialize();
    const run = store.enqueue(enqueueInput());
    const brief = await buildResumeBrief(
      {
        runId: run.id,
        headRevision: run.baseRevision ?? "",
        workingTreeDirty: true,
        changedPathCount: 4,
        now: "2026-07-31T00:00:00.000Z",
      },
      store,
      () => Promise.resolve(context({ contextKey: "c".repeat(64) })),
    );
    expect(brief.disposition).toBe("stale-context");
    expect(brief.context?.changedSources).toEqual([]);
    expect(brief.safeguards.claimValidationRequiredBeforeExecution).toBe(true);
    store.close();
  });

  it("selects the latest open run for a work item", async () => {
    const store = new SqliteRunStore(":memory:", () => new StateCipher(testStateKey));
    store.initialize();
    const first = store.enqueue(enqueueInput({ idempotencyKey: "first-run" }));
    store.requestCancellation(first.id);
    const second = store.enqueue(enqueueInput({ idempotencyKey: "second-run" }));
    const brief = await buildResumeBrief(
      {
        workItemKey: "VFBIZ-0204",
        headRevision: second.baseRevision ?? "",
        workingTreeDirty: false,
        changedPathCount: 0,
        now: "2026-07-31T00:00:00.000Z",
      },
      store,
      () => Promise.resolve(context()),
    );
    expect(brief.run?.id).toBe(second.id);
    expect(brief.disposition).toBe("worker-required");
    store.close();
  });
});
