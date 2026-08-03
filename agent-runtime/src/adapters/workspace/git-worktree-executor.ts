import { execFile } from "node:child_process";
import { cp, lstat, mkdtemp, readFile, readdir, realpath, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { BoundaryViolationError } from "../../domain/errors.js";
import type { FixtureWorkspace, WorkspaceExecutor } from "../../ports/workspace-executor.js";

const execute = promisify(execFile);

export class GitWorktreeExecutor implements WorkspaceExecutor {
  public async createFixtureWorktree(sourceFixture: string, runId: string): Promise<FixtureWorkspace> {
    await this.assertPathsInside(sourceFixture, ["."]);
    const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "vfbiz-agent-runtime-"));
    const seed = path.join(temporaryRoot, "seed");
    const worktree = path.join(temporaryRoot, "worktree");
    await cp(sourceFixture, seed, { recursive: true, force: false });
    await execute("git", ["init", "-b", "main"], { cwd: seed });
    await execute("git", ["config", "user.name", "VFBiz Fixture"], { cwd: seed });
    await execute("git", ["config", "user.email", "fixture@invalid.example"], { cwd: seed });
    await execute("git", ["add", "."], { cwd: seed });
    await execute("git", ["commit", "-m", "fixture baseline"], { cwd: seed });
    const { stdout: revision } = await execute("git", ["rev-parse", "HEAD"], { cwd: seed });
    const branch = `runtime/${runId.replace(/[^A-Za-z0-9._-]/g, "-")}`;
    await execute("git", ["worktree", "add", "-b", branch, worktree, "HEAD"], { cwd: seed });
    await writeFile(
      path.join(temporaryRoot, ".vfbiz-agent-runtime-fixture.json"),
      `${JSON.stringify({ version: 1, root: worktree, branch, baseRevision: revision.trim() })}\n`,
      { mode: 0o600 },
    );
    return {
      root: worktree,
      branch,
      baseRevision: revision.trim(),
      dispose: async () => {
        await rm(temporaryRoot, { recursive: true, force: true });
      },
    };
  }

  public async assertFixtureWorkspace(workspaceRoot: string): Promise<void> {
    const root = await realpath(workspaceRoot);
    const temporaryBoundary = await realpath(os.tmpdir());
    const relative = path.relative(temporaryBoundary, root);
    const [fixtureDirectory, leaf, ...rest] = relative.split(path.sep);
    if (
      !fixtureDirectory?.startsWith("vfbiz-agent-runtime-") ||
      leaf !== "worktree" ||
      rest.length > 0
    ) {
      throw new BoundaryViolationError("fixture worktree was not created inside the runtime temporary boundary");
    }
    const temporaryRoot = path.join(temporaryBoundary, fixtureDirectory);
    const attestation = JSON.parse(
      await readFile(path.join(temporaryRoot, ".vfbiz-agent-runtime-fixture.json"), "utf8"),
    ) as { version: number; root: string; branch: string; baseRevision: string };
    const [{ stdout: branch }, { stdout: commonDirectory }, { stdout: revision }] = await Promise.all([
      execute("git", ["symbolic-ref", "--short", "HEAD"], { cwd: root }),
      execute("git", ["rev-parse", "--path-format=absolute", "--git-common-dir"], { cwd: root }),
      execute("git", ["rev-parse", attestation.baseRevision], { cwd: root }),
    ]);
    const common = await realpath(commonDirectory.trim());
    const expectedCommon = await realpath(path.join(temporaryRoot, "seed", ".git"));
    if (
      attestation.version !== 1 ||
      await realpath(attestation.root) !== root ||
      !attestation.branch.startsWith("runtime/") ||
      branch.trim() !== attestation.branch ||
      revision.trim() !== attestation.baseRevision ||
      common !== expectedCommon
    ) {
      throw new BoundaryViolationError("fixture worktree attestation or Git common directory is invalid");
    }
    await this.assertPathsInside(root, ["."]);
  }

  public async assertPathsInside(workspaceRoot: string, paths: string[]): Promise<void> {
    const boundary = await realpath(workspaceRoot);
    for (const candidate of paths) {
      if (path.isAbsolute(candidate)) throw new BoundaryViolationError(`absolute fixture path is forbidden: ${candidate}`);
      const absolute = path.resolve(boundary, candidate);
      if (absolute !== boundary && !absolute.startsWith(`${boundary}${path.sep}`)) {
        throw new BoundaryViolationError(`fixture path escapes worktree: ${candidate}`);
      }
      let cursor = boundary;
      for (const segment of path.relative(boundary, absolute).split(path.sep).filter(Boolean)) {
        cursor = path.join(cursor, segment);
        const metadata = await lstat(cursor).catch((error: unknown) => {
          const code = error instanceof Error && "code" in error ? String(error.code) : "";
          if (code === "ENOENT") return null;
          throw error;
        });
        if (metadata?.isSymbolicLink()) {
          throw new BoundaryViolationError(`symlink path is forbidden in fixture execution: ${candidate}`);
        }
      }
      const target = await lstat(absolute).catch((error: unknown) => {
        const code = error instanceof Error && "code" in error ? String(error.code) : "";
        if (code === "ENOENT") return null;
        throw error;
      });
      if (target?.isDirectory()) await this.assertTreeHasNoSymlinks(absolute, candidate);
    }
  }

  private async assertTreeHasNoSymlinks(directory: string, requestedPath: string): Promise<void> {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      if (entry.isSymbolicLink()) {
        throw new BoundaryViolationError(
          `symlink path is forbidden in fixture execution: ${requestedPath}/${entry.name}`,
        );
      }
      if (entry.isDirectory()) {
        await this.assertTreeHasNoSymlinks(path.join(directory, entry.name), requestedPath);
      }
    }
  }
}
