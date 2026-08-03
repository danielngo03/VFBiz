import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { forbiddenProductPrefixes } from "../config/tool-policy.js";
import { BoundaryViolationError } from "../domain/errors.js";

const execute = promisify(execFile);

export interface ScopeSnapshot {
  version: 1;
  repositoryRoot: string;
  entries: Record<string, string>;
}

async function changedProductPaths(repositoryRoot: string, baseRevision?: string): Promise<string[]> {
  const fromStatus = await execute(
    "git",
    ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--", ...forbiddenProductPrefixes],
    { cwd: repositoryRoot },
  );
  const paths = new Set(
    fromStatus.stdout
      .split("\0")
      .filter(Boolean)
      .map((entry) => entry.slice(3).split(" -> ").at(-1) ?? "")
      .filter(Boolean),
  );
  if (baseRevision) {
    const committed = await execute(
      "git",
      ["diff", "--name-only", `${baseRevision}...HEAD`, "--", ...forbiddenProductPrefixes],
      { cwd: repositoryRoot },
    );
    for (const candidate of committed.stdout.split(/\r?\n/).filter(Boolean)) paths.add(candidate);
  }
  return [...paths].sort();
}

async function fingerprint(repositoryRoot: string, candidate: string): Promise<string> {
  const bytes = await readFile(path.join(repositoryRoot, candidate)).catch(() => null);
  return bytes ? createHash("sha256").update(bytes).digest("hex") : "missing";
}

async function entriesFor(repositoryRoot: string, baseRevision?: string): Promise<Record<string, string>> {
  const entries: Record<string, string> = {};
  for (const candidate of await changedProductPaths(repositoryRoot, baseRevision)) {
    entries[candidate] = await fingerprint(repositoryRoot, candidate);
  }
  return entries;
}

export async function writeScopeSnapshot(
  repositoryRoot: string,
  destination: string,
): Promise<ScopeSnapshot> {
  const snapshot: ScopeSnapshot = {
    version: 1,
    repositoryRoot,
    entries: await entriesFor(repositoryRoot),
  };
  await writeFile(destination, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600 });
  return snapshot;
}

export async function assertProgramScope(
  repositoryRoot: string,
  options: { baseRevision?: string; baselineFile?: string } = {},
): Promise<void> {
  let baseRevision = options.baseRevision;
  if (!baseRevision && !options.baselineFile) {
    baseRevision = process.env.VFBIZ_AGENT_RUNTIME_SCOPE_BASE;
    if (!baseRevision) {
      baseRevision = await execute("git", ["merge-base", "HEAD", "origin/main"], {
        cwd: repositoryRoot,
      }).then(({ stdout }) => stdout.trim(), () => undefined);
    }
    if (!baseRevision) {
      baseRevision = await execute("git", ["rev-parse", "HEAD^"], {
        cwd: repositoryRoot,
      }).then(({ stdout }) => stdout.trim(), () => undefined);
    }
  }
  const current = await entriesFor(repositoryRoot, baseRevision);
  if (!options.baselineFile) {
    const paths = Object.keys(current);
    if (paths.length > 0) {
      throw new BoundaryViolationError(`product workspace diff detected: ${paths.join(", ")}`);
    }
    return;
  }
  const baseline = JSON.parse(await readFile(options.baselineFile, "utf8")) as ScopeSnapshot;
  if (baseline.version !== 1 || baseline.repositoryRoot !== repositoryRoot) {
    throw new BoundaryViolationError("changed-path baseline does not belong to this repository");
  }
  const preExistingUntrackedDirectories = Object.entries(baseline.entries)
    .filter(([candidate, digest]) => candidate.endsWith("/") && digest === "missing")
    .map(([candidate]) => candidate);
  const comparableCurrent = Object.fromEntries(
    Object.entries(current).filter(
      ([candidate]) =>
        !preExistingUntrackedDirectories.some((directory) => candidate.startsWith(directory)),
    ),
  );
  const comparableBaseline = Object.fromEntries(
    Object.entries(baseline.entries).filter(([candidate]) => !candidate.endsWith("/")),
  );
  const allPaths = new Set([...Object.keys(comparableBaseline), ...Object.keys(comparableCurrent)]);
  const changed = [...allPaths].filter((candidate) => baseline.entries[candidate] !== current[candidate]);
  if (changed.length > 0) {
    throw new BoundaryViolationError(`program changed a product workspace path: ${changed.join(", ")}`);
  }
}
