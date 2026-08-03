import { access, writeFile } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { GitWorktreeExecutor } from "../../src/adapters/workspace/git-worktree-executor.js";

describe("fixture worktree", () => {
  it("creates and disposes an isolated synthetic Git worktree", async () => {
    const executor = new GitWorktreeExecutor();
    const source = path.resolve(import.meta.dirname, "../fixtures/sample-repository");
    const workspace = await executor.createFixtureWorktree(source, "run-fixture");
    expect(workspace.branch).toBe("runtime/run-fixture");
    expect(workspace.baseRevision).toMatch(/^[a-f0-9]{40}$/);
    await executor.assertFixtureWorkspace(workspace.root);
    await writeFile(path.join(workspace.root, "synthetic.txt"), "fixture only\n");
    await executor.assertPathsInside(workspace.root, ["synthetic.txt"]);
    await workspace.dispose();
    await expect(access(workspace.root)).rejects.toThrow();
  });
});
