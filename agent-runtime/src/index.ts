import { AgentsSdkExecutor } from "./adapters/openai/agents-sdk-executor.js";
import { CliGovernanceGateway } from "./adapters/governance/cli-governance-gateway.js";
import { SqliteRunStore } from "./adapters/persistence/sqlite/sqlite-run-store.js";
import { CodexMcpExecutor } from "./adapters/codex/codex-mcp-executor.js";
import { CodexOperationLedger } from "./adapters/codex/codex-operation-ledger.js";
import { IsolatedFixtureCodingExecutor } from "./adapters/codex/isolated-fixture-coding-executor.js";
import { GitWorktreeExecutor } from "./adapters/workspace/git-worktree-executor.js";
import { loadRuntimeEnvironment } from "./config/env.js";
import path from "node:path";
import { realpathSync } from "node:fs";
import { BoundaryViolationError } from "./domain/errors.js";

export function createRuntime() {
  const environment = loadRuntimeEnvironment();
  const store = new SqliteRunStore(environment.databasePath);
  store.initialize();
  const governance = new CliGovernanceGateway(environment.repositoryRoot);
  const workspaceExecutor = new GitWorktreeExecutor();
  const fixturesBoundary = realpathSync(path.join(
    environment.repositoryRoot,
    "agent-runtime/tests/fixtures",
  ));
  const fixtureSource = realpathSync(
    environment.fixtureRepository ?? path.join(fixturesBoundary, "sample-repository"),
  );
  if (fixtureSource !== fixturesBoundary && !fixtureSource.startsWith(`${fixturesBoundary}${path.sep}`)) {
    throw new BoundaryViolationError("fixture source must be registered under runtime tests/fixtures");
  }
  const codexDelegate = new CodexMcpExecutor(
    environment.codexEnabled,
    workspaceExecutor,
    environment.repositoryRoot,
    new CodexOperationLedger(path.join(environment.stateDirectory, "codex-operations")),
  );
  const codingExecutor = new IsolatedFixtureCodingExecutor(
    fixtureSource,
    workspaceExecutor,
    codexDelegate,
  );
  const agentExecutor = new AgentsSdkExecutor(
    environment.openAiEnabled,
    environment.traceEnabled,
    undefined,
    codingExecutor,
    fixtureSource,
  );
  return { environment, store, governance, agentExecutor };
}

export * from "./agents/agent-result.js";
export * from "./application/enqueue-run.js";
export * from "./domain/runtime-run.js";
export * from "./ports/agent-executor.js";
export * from "./ports/governance-gateway.js";
export * from "./ports/run-store.js";
