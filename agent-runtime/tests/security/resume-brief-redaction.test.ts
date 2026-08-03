import { describe, expect, it } from "vitest";
import {
  buildResumeBrief,
  type ResumeContextSnapshot,
} from "../../src/application/build-resume-brief.js";
import { SqliteRunStore } from "../../src/adapters/persistence/sqlite/sqlite-run-store.js";
import { StateCipher } from "../../src/adapters/persistence/sqlite/state-cipher.js";
import { enqueueInput, testStateKey } from "../helpers.js";

const resumeContext: ResumeContextSnapshot = {
  contextKey: "a".repeat(64),
  workItem: {
    id: "VFBIZ-0204",
    revision: 8,
    status: "active",
    sections: {
      checkpoint: {
        excerpt: "- Exact next action: obtain the required human approval.",
      },
      done_when: { excerpt: "- Approval remains external." },
    },
  },
  resumeDelta: { changedSources: [] },
  sourceRevisions: [],
};

describe("resume brief redaction", () => {
  it("never exposes objective, checkpoint plaintext or raw event payload", async () => {
    const store = new SqliteRunStore(":memory:", () => new StateCipher(testStateKey));
    store.initialize();
    const run = store.enqueue(
      enqueueInput({ objective: "secret-objective-value" }),
    );
    const claimed = store.claimNextRun("worker-night");
    expect(claimed).not.toBeNull();
    store.saveCheckpoint(run.id, "agent-state", "secret-checkpoint-value");
    store.appendEvent(run.id, "agent.completed", "sensitive-event", {
      rawToolOutput: "secret-tool-output-value",
    });
    store.createApproval({
      runId: run.id,
      toolName: "ask_implementer",
      interruptionId: "overnight-call",
      reason: "secret-approval-reason",
      requestedByRole: "orchestrator",
      requiredAuthority: "engineering-lead",
      payloadDigest: "d".repeat(64),
    });
    const current = store.getRun(run.id);
    expect(current).not.toBeNull();
    store.transition(run.id, current?.version ?? 0, "waiting_approval");

    const brief = await buildResumeBrief(
      {
        runId: run.id,
        headRevision: run.baseRevision ?? "",
        workingTreeDirty: false,
        changedPathCount: 0,
        now: "2026-07-31T00:00:00.000Z",
      },
      store,
      () => Promise.resolve(resumeContext),
    );
    const serialized = JSON.stringify(brief);
    for (const forbidden of [
      "secret-objective-value",
      "secret-checkpoint-value",
      "secret-tool-output-value",
      "secret-approval-reason",
    ]) {
      expect(serialized).not.toContain(forbidden);
    }
    expect(brief.latestCheckpoint?.stateDigest).toMatch(/^[a-f0-9]{64}$/);
    expect(brief.approvals[0]).toMatchObject({
      requiredAuthority: "engineering-lead",
      payloadDigest: "d".repeat(64),
    });
    expect(brief.safeguards).toMatchObject({
      checkpointDecrypted: false,
      rawEventPayloadIncluded: false,
      runtimeSuccessIsAcceptance: false,
    });
    store.close();
  });
});
