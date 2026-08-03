import { createHash } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { RuntimeError } from "../../domain/errors.js";
import type { CodingExecutionRequest, CodingExecutionResult } from "../../ports/coding-executor.js";

export interface CodexOperationToken {
  key: string;
  recovered?: CodingExecutionResult;
}

export class CodexOperationLedger {
  public constructor(private readonly directory: string) {}

  public async begin(request: CodingExecutionRequest): Promise<CodexOperationToken> {
    await mkdir(this.directory, { recursive: true, mode: 0o700 });
    const key = createHash("sha256")
      .update(JSON.stringify({
        runId: request.runId,
        operationId: request.operationId,
        objective: request.objective,
        allowedPaths: [...request.allowedPaths].sort(),
        mode: request.mode,
      }))
      .digest("hex");
    const completedPath = path.join(this.directory, `${key}.completed.json`);
    const completed = await readFile(completedPath, "utf8").then(
      (value) => JSON.parse(value) as { changedPaths: string[]; evidence: string[] },
      () => null,
    );
    if (completed) {
      return {
        key,
        recovered: {
          summary: "Recovered a previously completed Codex fixture operation from the idempotency ledger.",
          changedPaths: completed.changedPaths,
          evidence: completed.evidence,
        },
      };
    }
    const intentPath = path.join(this.directory, `${key}.intent`);
    try {
      await writeFile(intentPath, `${new Date().toISOString()}\n`, { flag: "wx", mode: 0o600 });
    } catch (error) {
      const code = error instanceof Error && "code" in error ? String(error.code) : "";
      if (code === "EEXIST") {
        throw new RuntimeError(
          "CODEX_RECONCILIATION_REQUIRED",
          "a prior Codex operation has uncertain completion; refusing to replay it",
        );
      }
      throw error;
    }
    return { key };
  }

  public async complete(key: string, result: CodingExecutionResult): Promise<void> {
    const completedPath = path.join(this.directory, `${key}.completed.json`);
    const temporaryPath = `${completedPath}.${process.pid}.tmp`;
    await writeFile(
      temporaryPath,
      `${JSON.stringify({ changedPaths: result.changedPaths, evidence: result.evidence })}\n`,
      { mode: 0o600 },
    );
    await rename(temporaryPath, completedPath);
  }
}
