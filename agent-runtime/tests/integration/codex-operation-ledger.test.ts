import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { CodexOperationLedger } from "../../src/adapters/codex/codex-operation-ledger.js";

describe("Codex operation reconciliation", () => {
  it("refuses uncertain replay and recovers a completed result", async () => {
    const directory = await mkdtemp(path.join(os.tmpdir(), "codex-ledger-test-"));
    try {
      const ledger = new CodexOperationLedger(directory);
      const request = {
        runId: "run-fixture",
        operationId: "call-fixture-1",
        objective: "Update one synthetic fixture file",
        repositoryPath: "/tmp/fixture",
        allowedPaths: ["src"],
        mode: "workspace-write" as const,
      };
      const operation = await ledger.begin(request);
      await expect(ledger.begin(request)).rejects.toThrow(
        /refusing to replay/,
      );
      await ledger.complete(operation.key, {
        summary: "Synthetic fixture updated",
        changedPaths: ["src/counter.ts"],
        evidence: ["codex-mcp:run-fixture"],
      });
      const recovered = await ledger.begin(request);
      expect(recovered.recovered).toMatchObject({
        changedPaths: ["src/counter.ts"],
        evidence: ["codex-mcp:run-fixture"],
      });
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
});
