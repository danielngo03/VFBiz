import { execFile } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { describe, expect, it } from "vitest";
import { assertProgramScope } from "../../src/application/check-program-scope.js";

const execute = promisify(execFile);

describe("changed-path assertion", () => {
  it("fails when a product workspace changes", async () => {
    const repository = await mkdtemp(path.join(os.tmpdir(), "runtime-scope-test-"));
    try {
      await mkdir(path.join(repository, "backend/api"), { recursive: true });
      await writeFile(path.join(repository, "backend/api/main.ts"), "export const safe = true;\n");
      await execute("git", ["init", "-b", "main"], { cwd: repository });
      await execute("git", ["config", "user.name", "Fixture"], { cwd: repository });
      await execute("git", ["config", "user.email", "fixture@invalid.example"], { cwd: repository });
      await execute("git", ["add", "."], { cwd: repository });
      await execute("git", ["commit", "-m", "baseline"], { cwd: repository });
      const { stdout } = await execute("git", ["rev-parse", "HEAD"], { cwd: repository });
      await writeFile(path.join(repository, "backend/api/main.ts"), "export const safe = false;\n");
      await expect(assertProgramScope(repository, { baseRevision: stdout.trim() })).rejects.toThrow(
        /product workspace diff/,
      );
    } finally {
      await rm(repository, { recursive: true, force: true });
    }
  });
});
