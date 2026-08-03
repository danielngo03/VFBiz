import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { lstat, readFile, realpath } from "node:fs/promises";
import { promisify } from "node:util";
import path from "node:path";
import { assertProgramPathAllowed } from "../../config/tool-policy.js";
import { RuntimeError } from "../../domain/errors.js";
import type {
  ExecutionAuthority,
  GovernanceGateway,
  ResolvedRuntimeContext,
} from "../../ports/governance-gateway.js";

const execute = promisify(execFile);

interface ResolverOutput {
  contextKey: string;
  classification: { mode: ResolvedRuntimeContext["mode"] };
  workItem: { id: string; revision: number };
  workspaces: string[];
  ownership: {
    ownerTeam: string;
    ownerDepartment: string;
    accountableRole: string;
  };
  requiredAuthorities: string[];
  requiredReviewers: string[];
  claimRequired: boolean;
  assignment: { allowed_paths: string[] };
}

interface OrganizationRegistry {
  humanAuthorities: string[];
  teams: Array<{ id: string }>;
}

interface ClaimValidationOutput {
  ok: boolean;
  result?: {
    workItemKey: string;
    ownerTeam: string;
    contextKey: string;
  };
  message?: string;
}

export class CliGovernanceGateway implements GovernanceGateway {
  public constructor(private readonly repositoryRoot: string) {}

  public async resolve(workItemKey: string, targetPath: string): Promise<ResolvedRuntimeContext> {
    const args = [
      path.join(this.repositoryRoot, "tools/context-resolver.mjs"),
      "--path",
      targetPath,
      "--work",
      workItemKey,
      "--stage",
      "delivery",
      "--mode",
      "controlled",
      "--signals",
      "ai-tool,ai-quality-platform",
      "--multi-story",
      "--behavior-change",
    ];
    const [{ stdout }, { stdout: revision }, organizationBytes] = await Promise.all([
      execute(process.execPath, args, { cwd: this.repositoryRoot, maxBuffer: 2_000_000 }),
      execute("git", ["rev-parse", "HEAD"], { cwd: this.repositoryRoot }),
      readFile(path.join(this.repositoryRoot, ".agents/organization.json"), "utf8"),
    ]);
    let resolved: ResolverOutput;
    let organization: OrganizationRegistry;
    try {
      resolved = JSON.parse(stdout) as ResolverOutput;
      organization = JSON.parse(organizationBytes) as OrganizationRegistry;
    } catch {
      throw new RuntimeError("CONTEXT_INVALID", "governance resolver returned invalid JSON");
    }
    if (resolved.workItem.id !== workItemKey || resolved.workspaces.length !== 1) {
      throw new RuntimeError("CONTEXT_UNRESOLVED", "work item did not resolve to one owning workspace");
    }
    if (!resolved.ownership.ownerTeam || !resolved.ownership.ownerDepartment) {
      throw new RuntimeError("OWNER_UNRESOLVED", "work item owner could not be resolved");
    }
    return {
      contextKey: resolved.contextKey,
      workItemKey,
      workItemRevision: resolved.workItem.revision,
      workspace: resolved.workspaces[0] ?? "",
      ownerTeam: resolved.ownership.ownerTeam,
      ownerDepartment: resolved.ownership.ownerDepartment,
      accountableRole: resolved.ownership.accountableRole,
      mode: resolved.classification.mode,
      allowedPaths: resolved.assignment.allowed_paths,
      requiredAuthorities: resolved.requiredAuthorities,
      requiredReviewers: resolved.requiredReviewers,
      registeredTeams: organization.teams.map(({ id }) => id),
      registeredAuthorities: organization.humanAuthorities,
      claimRequired: resolved.claimRequired,
      baseRevision: revision.trim(),
    };
  }

  public async assertFresh(context: ResolvedRuntimeContext): Promise<void> {
    const current = await this.resolve(context.workItemKey, context.allowedPaths[0] ?? context.workspace);
    if (
      current.contextKey !== context.contextKey ||
      current.workItemRevision !== context.workItemRevision ||
      current.baseRevision !== context.baseRevision ||
      current.mode !== context.mode ||
      current.ownerTeam !== context.ownerTeam ||
      current.accountableRole !== context.accountableRole
    ) {
      throw new RuntimeError("STALE_CONTEXT", "work item, context or base revision changed", false);
    }
  }

  public async assertExecutionAuthority(
    context: ResolvedRuntimeContext,
    authority: ExecutionAuthority | null,
  ): Promise<void> {
    if (!context.claimRequired && !authority) return;
    if (!authority) {
      throw new RuntimeError(
        "CLAIM_REQUIRED",
        `canonical ${context.mode} context requires an active governance claim`,
      );
    }
    const control = path.join(this.repositoryRoot, "tools/agent-control.mjs");
    let stdout: string;
    try {
      ({ stdout } = await execute(process.execPath, [
        control,
        "claim",
        "validate",
        "--claim",
        authority.claimId,
        "--fencing-token",
        String(authority.fencingToken),
      ], { cwd: this.repositoryRoot, maxBuffer: 1_000_000 }));
      await execute(process.execPath, [
        control,
        "paths",
        "validate",
        "--claim",
        authority.claimId,
        "--fencing-token",
        String(authority.fencingToken),
        "--paths",
        JSON.stringify(context.allowedPaths),
      ], { cwd: this.repositoryRoot, maxBuffer: 1_000_000 });
    } catch (error) {
      const detail = error instanceof Error && "stdout" in error && typeof error.stdout === "string"
        ? error.stdout.trim()
        : "";
      throw new RuntimeError(
        "CLAIM_AUTHORITY_REJECTED",
        detail || "governance claim, fencing token or allowed paths were rejected",
      );
    }
    const validation = JSON.parse(stdout) as ClaimValidationOutput;
    if (
      !validation.ok ||
      validation.result?.workItemKey !== context.workItemKey ||
      validation.result.ownerTeam !== context.ownerTeam ||
      validation.result.contextKey !== context.contextKey
    ) {
      throw new RuntimeError(
        "CLAIM_CONTEXT_MISMATCH",
        "governance claim does not match the resolved work item, team or context revision",
      );
    }
  }

  public async verifyArtifact(
    context: ResolvedRuntimeContext,
    artifact: { path: string; sha256: string },
  ): Promise<void> {
    assertProgramPathAllowed(artifact.path);
    const normalized = artifact.path.replaceAll(path.sep, "/").replace(/^\.\//, "");
    if (!context.allowedPaths.some((allowed) => {
      const boundary = allowed.replaceAll(path.sep, "/").replace(/\/$/, "");
      return normalized === boundary || normalized.startsWith(`${boundary}/`);
    })) {
      throw new RuntimeError("ARTIFACT_PATH_REJECTED", `artifact is outside canonical allowed paths: ${artifact.path}`);
    }
    const repositoryBoundary = await realpath(this.repositoryRoot);
    const absolute = path.resolve(repositoryBoundary, artifact.path);
    let cursor = repositoryBoundary;
    for (const segment of path.relative(repositoryBoundary, absolute).split(path.sep).filter(Boolean)) {
      cursor = path.join(cursor, segment);
      const metadata = await lstat(cursor).catch(() => null);
      if (!metadata) throw new RuntimeError("ARTIFACT_MISSING", `artifact does not exist: ${artifact.path}`);
      if (metadata.isSymbolicLink()) {
        throw new RuntimeError("ARTIFACT_SYMLINK_REJECTED", `artifact path contains a symlink: ${artifact.path}`);
      }
    }
    const metadata = await lstat(absolute);
    if (!metadata.isFile() || metadata.size > 10_000_000) {
      throw new RuntimeError("ARTIFACT_INVALID", `artifact must be a regular file of at most 10 MB: ${artifact.path}`);
    }
    const digest = createHash("sha256").update(await readFile(absolute)).digest("hex");
    if (digest !== artifact.sha256) {
      throw new RuntimeError("ARTIFACT_DIGEST_MISMATCH", `artifact digest does not match bytes: ${artifact.path}`);
    }
  }
}
