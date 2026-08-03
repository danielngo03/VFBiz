import { describe, expect, it } from "vitest";
import { SqliteRunStore } from "../../src/adapters/persistence/sqlite/sqlite-run-store.js";
import { StateCipher } from "../../src/adapters/persistence/sqlite/state-cipher.js";
import { decideApproval } from "../../src/application/decide-approval.js";
import { enqueueInput, testStateKey } from "../helpers.js";

describe("approval lifecycle", () => {
  it("requires the exact external human authority", () => {
    const store = new SqliteRunStore(":memory:", () => new StateCipher(testStateKey));
    store.initialize();
    const run = store.enqueue(enqueueInput());
    const approval = store.createApproval({
      runId: run.id,
      toolName: "ask_implementer",
      interruptionId: "call-fixture-1",
      reason: "Synthetic fixture write",
      requestedByRole: "orchestrator",
      requiredAuthority: "engineering-lead",
      payloadDigest: "b".repeat(64),
    });
    expect(() => decideApproval({
      approvalId: approval.id,
      decision: "approved",
      decidedBy: "agent:orchestrator",
      reason: "self approval",
    }, store)).toThrow(/requires human:engineering-lead/);
    expect(() => store.decideApproval({
      approvalId: approval.id,
      decision: "approved",
      decidedBy: "human:robot-ceo",
      reason: "adapter bypass attempt",
    })).toThrow(/requires human:engineering-lead/);
    expect(decideApproval({
      approvalId: approval.id,
      decision: "approved",
      decidedBy: "human:engineering-lead",
      reason: "Fixture-only execution authorized",
    }, store).status).toBe("approved");
    const laterCall = store.createApproval({
      runId: run.id,
      toolName: "ask_implementer",
      interruptionId: "call-fixture-2",
      reason: "A distinct later fixture write",
      requestedByRole: "orchestrator",
      requiredAuthority: "engineering-lead",
      payloadDigest: "b".repeat(64),
    });
    expect(laterCall.id).not.toBe(approval.id);
    expect(laterCall.status).toBe("pending");
    store.close();
  });
});
