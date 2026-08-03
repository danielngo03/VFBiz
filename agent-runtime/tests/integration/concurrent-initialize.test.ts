import { execFile } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { describe, expect, it } from "vitest";

const execute = promisify(execFile);

describe("concurrent runtime initialization", () => {
  it("serializes first-run schema migrations across local processes", async () => {
    const stateDirectory = await mkdtemp(path.join(os.tmpdir(), "runtime-concurrent-init-"));
    const repositoryRoot = path.resolve(import.meta.dirname, "../../..");
    const cli = path.join(repositoryRoot, "agent-runtime/src/entrypoints/cli.ts");
    const environment = {
      ...process.env,
      VFBIZ_AGENT_RUNTIME_STATE_DIR: stateDirectory,
      VFBIZ_AGENT_RUNTIME_OPENAI_ENABLED: "false",
      VFBIZ_AGENT_RUNTIME_CODEX_ENABLED: "false",
      VFBIZ_AGENT_RUNTIME_TRACE_ENABLED: "false",
    };
    try {
      const results = await Promise.all([
        execute(process.execPath, ["--import", "tsx", cli, "doctor"], { cwd: repositoryRoot, env: environment }),
        execute(process.execPath, ["--import", "tsx", cli, "doctor"], { cwd: repositoryRoot, env: environment }),
      ]);
      for (const { stdout } of results) {
        expect(JSON.parse(stdout) as { ok: boolean }).toMatchObject({ ok: true });
      }
    } finally {
      await rm(stateDirectory, { recursive: true, force: true });
    }
  });
});
