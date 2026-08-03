import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { describe, expect, it } from "vitest";
import { SqliteRunStore } from "../../src/adapters/persistence/sqlite/sqlite-run-store.js";
import { StateCipher } from "../../src/adapters/persistence/sqlite/state-cipher.js";
import { enqueueInput, testStateKey } from "../helpers.js";

describe("legacy runtime schema migration", () => {
  it("upgrades approval, usage and checkpoint idempotency without dropping the ledger", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "runtime-legacy-schema-"));
    const databasePath = path.join(root, "runtime.sqlite");
    try {
      const initialStore = new SqliteRunStore(databasePath, () => new StateCipher(testStateKey));
      initialStore.initialize();
      const initialRun = initialStore.enqueue(enqueueInput({ idempotencyKey: "legacy-migration" }));
      const initialCheckpoint = initialStore.saveCheckpoint(initialRun.id, "agent-state", "same-state");
      const initialApproval = initialStore.createApproval({
        runId: initialRun.id,
        toolName: "codex_fixture",
        interruptionId: "call-before-downgrade",
        reason: "fixture",
        requestedByRole: "orchestrator",
        requiredAuthority: "engineering-lead",
        payloadDigest: "d".repeat(64),
      });
      initialStore.recordUsage(
        initialRun.id,
        { inputTokens: 3, outputTokens: 2, estimatedUsd: 0.05, model: "legacy" },
        "legacy-segment",
      );
      initialStore.close();

      const legacy = new DatabaseSync(databasePath);
      legacy.exec(`
        PRAGMA foreign_keys = OFF;
        ALTER TABLE runtime_checkpoint RENAME TO runtime_checkpoint_current;
        CREATE TABLE runtime_checkpoint (
          id TEXT PRIMARY KEY, run_id TEXT NOT NULL, sequence INTEGER NOT NULL,
          kind TEXT NOT NULL, encrypted_state TEXT NOT NULL, state_digest TEXT NOT NULL,
          created_at TEXT NOT NULL, UNIQUE(run_id, sequence)
        );
        INSERT INTO runtime_checkpoint SELECT * FROM runtime_checkpoint_current;
        DROP TABLE runtime_checkpoint_current;
        ALTER TABLE runtime_approval RENAME TO runtime_approval_current;
        CREATE TABLE runtime_approval (
          id TEXT PRIMARY KEY, run_id TEXT NOT NULL, tool_name TEXT NOT NULL,
          reason TEXT NOT NULL, requested_by_role TEXT NOT NULL,
          required_authority TEXT NOT NULL, payload_digest TEXT NOT NULL,
          status TEXT NOT NULL, decided_by TEXT, decision_reason TEXT,
          requested_at TEXT NOT NULL, decided_at TEXT,
          UNIQUE(run_id, tool_name, payload_digest)
        );
        INSERT INTO runtime_approval (
          id, run_id, tool_name, reason, requested_by_role, required_authority,
          payload_digest, status, decided_by, decision_reason, requested_at, decided_at
        ) SELECT
          id, run_id, tool_name, reason, requested_by_role, required_authority,
          payload_digest, status, decided_by, decision_reason, requested_at, decided_at
        FROM runtime_approval_current;
        DROP TABLE runtime_approval_current;
        ALTER TABLE runtime_usage RENAME TO runtime_usage_current;
        CREATE TABLE runtime_usage (
          id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
          input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
          estimated_usd REAL, model TEXT, created_at TEXT NOT NULL
        );
        INSERT INTO runtime_usage (
          id, run_id, input_tokens, output_tokens, estimated_usd, model, created_at
        ) SELECT id, run_id, input_tokens, output_tokens, estimated_usd, model, created_at
        FROM runtime_usage_current;
        DROP TABLE runtime_usage_current;
      `);
      legacy.close();

      const store = new SqliteRunStore(databasePath, () => new StateCipher(testStateKey));
      store.initialize();
      const run = store.enqueue(enqueueInput({ idempotencyKey: "legacy-migration" }));
      expect(run.id).toBe(initialRun.id);
      expect(store.saveCheckpoint(run.id, "agent-state", "same-state").id).toBe(initialCheckpoint.id);
      expect(store.getApproval(initialApproval.id)?.interruptionId).toBe(`legacy-${initialApproval.id}`);
      expect(store.createApproval({
        runId: run.id,
        toolName: "codex_fixture",
        interruptionId: "call-after-migration",
        reason: "fixture",
        requestedByRole: "orchestrator",
        requiredAuthority: "engineering-lead",
        payloadDigest: "d".repeat(64),
      }).interruptionId).toBe("call-after-migration");
      const usage = { inputTokens: 10, outputTokens: 5, estimatedUsd: 0.1, model: "fixture" };
      store.recordUsage(run.id, usage, "segment-1");
      store.recordUsage(run.id, usage, "segment-2");
      expect(store.getUsageTotals(run.id)).toMatchObject({
        inputTokens: 23,
        outputTokens: 12,
        estimatedUsd: 0.25,
      });
      store.close();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
