import { execFile } from "node:child_process";
import { mkdtemp, realpath, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { MCPServerStdio } from "@openai/agents";
import { BoundaryViolationError, RuntimeError } from "../../domain/errors.js";
import type { CodingExecutionRequest, CodingExecutionResult, CodingExecutor } from "../../ports/coding-executor.js";
import type { WorkspaceExecutor } from "../../ports/workspace-executor.js";
import type { CodexOperationLedger } from "./codex-operation-ledger.js";

const execute = promisify(execFile);

export function buildCodexToolArguments(request: CodingExecutionRequest): Record<string, unknown> {
  return {
    prompt: [
      request.objective,
      "Work only in the declared fixture repository and allowed paths.",
      "Do not spawn or delegate to nested agents.",
      "Do not request broader permissions; return a concise evidence summary if blocked.",
    ].join("\n"),
    cwd: request.repositoryPath,
    sandbox: request.mode,
    "approval-policy": "never",
    "developer-instructions": "Nested agents and delegation are disabled. Reject any path outside the isolated fixture repository.",
  };
}

export function assertCodexObjectiveAllowed(objective: string): void {
  if (/(?:^|[\s`'"/])(backend|apps|mobile|drupal|infra|packages)\//i.test(objective)) {
    throw new BoundaryViolationError("Codex objective references a forbidden product workspace");
  }
}

export class CodexMcpExecutor implements CodingExecutor {
  public constructor(
    private readonly enabled: boolean,
    private readonly workspaces: WorkspaceExecutor,
    private readonly forbiddenRepositoryRoot?: string,
    private readonly operationLedger?: CodexOperationLedger,
  ) {}

  public async execute(request: CodingExecutionRequest): Promise<CodingExecutionResult> {
    if (!this.enabled) throw new RuntimeError("CODEX_DISABLED", "live Codex MCP execution is disabled");
    const repository = await realpath(request.repositoryPath);
    if (this.forbiddenRepositoryRoot) {
      const forbiddenBoundary = await realpath(this.forbiddenRepositoryRoot);
      if (repository === forbiddenBoundary || repository.startsWith(`${forbiddenBoundary}${path.sep}`)) {
        throw new BoundaryViolationError("Codex fixture must be isolated outside the VFBiz repository");
      }
    }
    await this.workspaces.assertFixtureWorkspace(repository);
    assertCodexObjectiveAllowed(request.objective);
    await this.workspaces.assertPathsInside(repository, request.allowedPaths);
    if (!this.operationLedger) {
      throw new RuntimeError("CODEX_LEDGER_MISSING", "Codex execution requires an operational idempotency ledger");
    }
    const operation = await this.operationLedger.begin(request);
    if (operation.recovered) return operation.recovered;
    const { stdout: beforeRevision } = await execute("git", ["rev-parse", "HEAD"], { cwd: repository });
    const isolatedCodexHome = await mkdtemp(path.join(os.tmpdir(), "vfbiz-codex-home-"));
    const serverEnvironment: Record<string, string> = {
      PATH: process.env.PATH ?? "",
      CODEX_HOME: isolatedCodexHome,
      CODEX_DISABLE_SUBAGENTS: "1",
    };
    if (process.env.OPENAI_API_KEY) serverEnvironment.OPENAI_API_KEY = process.env.OPENAI_API_KEY;
    const server = new MCPServerStdio({
      name: "codex-fixture-specialist",
      command: "codex",
      args: ["mcp-server", "--disable", "collaboration_modes"],
      cwd: repository,
      env: serverEnvironment,
      cacheToolsList: true,
      timeout: 120_000,
    });
    try {
      await server.connect();
      const tools = await server.listTools();
      if (!tools.some((tool) => tool.name === "codex")) {
        throw new RuntimeError("CODEX_TOOL_MISSING", "codex mcp-server did not expose the codex tool");
      }
      const response = await server.callToolResult("codex", buildCodexToolArguments(request));
      await this.workspaces.assertFixtureWorkspace(repository);
      const changedPaths = await this.changedPaths(repository, beforeRevision.trim());
      await this.workspaces.assertPathsInside(repository, changedPaths);
      const summary = response.content
        .map((item) => item.type === "text" ? item.text : "")
        .filter(Boolean)
        .join("\n")
        .slice(0, 8_000);
      const result = { summary, changedPaths, evidence: [`codex-mcp:${request.runId}`] };
      await this.operationLedger.complete(operation.key, result);
      return result;
    } finally {
      try {
        await server.close();
      } finally {
        await rm(isolatedCodexHome, { recursive: true, force: true });
      }
    }
  }

  private async changedPaths(repository: string, beforeRevision: string): Promise<string[]> {
    const [{ stdout: status }, { stdout: committed }] = await Promise.all([
      execute("git", ["status", "--porcelain=v1", "--untracked-files=all"], { cwd: repository }),
      execute("git", ["diff", "--name-only", beforeRevision, "HEAD"], { cwd: repository }),
    ]);
    return [...new Set([
      ...status
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => line.slice(3).split(" -> ").at(-1) ?? "")
      .filter(Boolean),
      ...committed.split(/\r?\n/).filter(Boolean),
    ])].sort();
  }

}
