import { describe, expect, it } from "vitest";
import { SqliteRunStore } from "../../src/adapters/persistence/sqlite/sqlite-run-store.js";
import { StateCipher } from "../../src/adapters/persistence/sqlite/state-cipher.js";
import { enqueueInput, testStateKey } from "../helpers.js";

describe("SQLite run store", () => {
  it("deduplicates enqueue and events and uses optimistic versions", () => {
    const store = new SqliteRunStore(":memory:", () => new StateCipher(testStateKey));
    store.initialize();
    const first = store.enqueue(enqueueInput());
    const duplicate = store.enqueue(enqueueInput());
    expect(duplicate.id).toBe(first.id);
    expect(store.listEvents(first.id)).toHaveLength(1);
    const enqueuedEvent = store.listEvents(first.id)[0];
    expect(enqueuedEvent?.actor).toBe("runtime");
    expect(enqueuedEvent?.contextKey).toBe("a".repeat(64));
    expect(enqueuedEvent?.payloadDigest).toMatch(/^[a-f0-9]{64}$/);
    const claimed = store.claimNextRun("worker-test");
    expect(claimed?.state).toBe("running");
    const heartbeat = store.heartbeat(first.id, "worker-test");
    expect(heartbeat.version).toBe(claimed?.version);
    expect(heartbeat.heartbeatAt).not.toBeNull();
    expect(() => store.heartbeat(first.id, "wrong-worker")).toThrow(/no longer owns/);
    expect(() => store.transition(first.id, first.version, "succeeded")).toThrow(/concurrently/);
    store.close();
  });

  it("encrypts checkpoints before persistence", () => {
    const store = new SqliteRunStore(":memory:", () => new StateCipher(testStateKey));
    store.initialize();
    const run = store.enqueue(enqueueInput());
    const checkpoint = store.saveCheckpoint(run.id, "agent-state", "synthetic-state");
    expect(checkpoint.encryptedState).not.toContain("synthetic-state");
    expect(store.decryptCheckpoint(checkpoint)).toBe("synthetic-state");
    store.close();
  });

  it("counts identical usage from distinct execution segments", () => {
    const store = new SqliteRunStore(":memory:", () => new StateCipher(testStateKey));
    store.initialize();
    const run = store.enqueue(enqueueInput());
    const usage = { inputTokens: 10, outputTokens: 5, estimatedUsd: 0.25, model: "fixture-model" };
    store.recordUsage(run.id, usage, "execution-segment-1");
    store.recordUsage(run.id, usage, "execution-segment-2");
    store.recordUsage(run.id, usage, "execution-segment-2");
    expect(store.getUsageTotals(run.id)).toMatchObject({
      inputTokens: 20,
      outputTokens: 10,
      estimatedUsd: 0.5,
    });
    store.close();
  });
});
