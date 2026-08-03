import { execFileSync } from "node:child_process";
import { chmodSync, mkdirSync } from "node:fs";
import path from "node:path";

function git(args: string[]): string {
  return execFileSync("git", args, { encoding: "utf8" }).trim();
}

export interface RuntimeEnvironment {
  repositoryRoot: string;
  stateDirectory: string;
  databasePath: string;
  liveProviderEnabled: boolean;
  codexEnabled: boolean;
  traceEnabled: boolean;
  fixtureRepository: string | null;
  watchIntervalMs: number;
}

function enabled(value: string | undefined): boolean {
  return value === "true" || value === "1";
}

export function loadRuntimeEnvironment(source = process.env): RuntimeEnvironment {
  const repositoryRoot = git(["rev-parse", "--show-toplevel"]);
  const commonDirectory = path.resolve(
    git(["rev-parse", "--path-format=absolute", "--git-common-dir"]),
  );
  const stateDirectory = path.resolve(
    source.VFBIZ_AGENT_RUNTIME_STATE_DIR ?? path.join(commonDirectory, "vfbiz-agent-runtime"),
  );
  mkdirSync(stateDirectory, { recursive: true, mode: 0o700 });
  chmodSync(stateDirectory, 0o700);
  return {
    repositoryRoot,
    stateDirectory,
    databasePath: path.join(stateDirectory, "runtime.sqlite"),
    liveProviderEnabled: enabled(
      source.VFBIZ_AGENT_RUNTIME_LIVE_ENABLED ?? source.VFBIZ_AGENT_RUNTIME_OPENAI_ENABLED,
    ),
    codexEnabled: enabled(source.VFBIZ_AGENT_RUNTIME_CODEX_ENABLED),
    traceEnabled: enabled(source.VFBIZ_AGENT_RUNTIME_TRACE_ENABLED),
    fixtureRepository: source.VFBIZ_AGENT_RUNTIME_FIXTURE_WORKTREE
      ? path.resolve(source.VFBIZ_AGENT_RUNTIME_FIXTURE_WORKTREE)
      : null,
    watchIntervalMs: Number(source.VFBIZ_AGENT_RUNTIME_WATCH_INTERVAL_MS ?? 2_000),
  };
}
