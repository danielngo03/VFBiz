import { execFileSync } from "node:child_process";
import {
  mkdir,
  open,
  readFile,
  realpath,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { ROOT, loadOrganization } from "./governance.mjs";
import { readFrontmatter } from "./frontmatter.mjs";

function nowIso() {
  return new Date().toISOString();
}
function plusMinutes(minutes) {
  return new Date(Date.now() + minutes * 60_000).toISOString();
}
function git(cwd, args) {
  return execFileSync("git", args, { cwd, encoding: "utf8" }).trim();
}
function gitRefIdentity(cwd) {
  try {
    return git(cwd, ["symbolic-ref", "--quiet", "--short", "HEAD"]);
  } catch {
    return `detached:${git(cwd, ["rev-parse", "HEAD"])}`;
  }
}
function sameRevision(left, right) {
  return left === right || left.startsWith(right) || right.startsWith(left);
}
function assertProvider(provider) {
  if (
    !provider ||
    typeof provider.name !== "string" ||
    provider.name.length === 0 ||
    typeof provider.adapterVersion !== "string" ||
    provider.adapterVersion.length === 0
  )
    throw new Error("provider name, adapter and adapterVersion are required");
  if (!["codex", "claude", "gemini", "generic"].includes(provider.adapter))
    throw new Error(`invalid provider adapter: ${provider.adapter}`);
}
async function assertCachedContext(contextKey) {
  const common = git(ROOT, ["rev-parse", "--git-common-dir"]);
  const file = path.resolve(
    ROOT,
    common,
    "vfbiz-context",
    `${contextKey}.json`,
  );
  let cached;
  try {
    cached = JSON.parse(await readFile(file, "utf8"));
  } catch {
    throw new Error(`cached context manifest not found: ${contextKey}`);
  }
  if (cached.contextKey !== contextKey)
    throw new Error(`cached context manifest key mismatch: ${contextKey}`);
}

export function repositoryRelative(value) {
  if (typeof value !== "string" || !value || path.isAbsolute(value))
    throw new Error(`invalid repository path: ${value}`);
  const parts = value.split(/[\\/]+/);
  if (parts.includes(".."))
    throw new Error(`path traversal is forbidden: ${value}`);
  const absolute = path.resolve(ROOT, value);
  const relative = path.relative(ROOT, absolute).split(path.sep).join("/");
  if (relative.startsWith("../") || path.isAbsolute(relative))
    throw new Error(`path escapes repository: ${value}`);
  return relative || ".";
}

export function pathsOverlap(left, right) {
  const a = repositoryRelative(left).replace(/\/$/, "");
  const b = repositoryRelative(right).replace(/\/$/, "");
  return a === b || a.startsWith(`${b}/`) || b.startsWith(`${a}/`);
}

function sharedResourceForPath(candidate, organization) {
  const relative = repositoryRelative(candidate);
  return [...(organization.controlPlane.sharedPathResources ?? [])]
    .map((entry) => ({
      ...entry,
      path: repositoryRelative(entry.path),
    }))
    .filter(
      (entry) =>
        relative === entry.path || relative.startsWith(`${entry.path}/`),
    )
    .sort((left, right) => right.path.length - left.path.length)[0]?.resource;
}

export async function assertNoSymlinkEscape(candidate) {
  const relative = repositoryRelative(candidate);
  const rootReal = await realpath(ROOT);
  let probe = path.resolve(ROOT, relative);
  while (probe !== ROOT) {
    try {
      await stat(probe);
      break;
    } catch {
      probe = path.dirname(probe);
    }
  }
  const probeReal = await realpath(probe);
  if (probeReal !== rootReal && !probeReal.startsWith(`${rootReal}${path.sep}`))
    throw new Error(`symlink escapes repository: ${candidate}`);
  return relative;
}

export function defaultStateRoot() {
  if (process.env.VFBIZ_AGENT_STATE_DIR)
    return path.resolve(process.env.VFBIZ_AGENT_STATE_DIR);
  const common = execFileSync("git", ["rev-parse", "--git-common-dir"], {
    cwd: ROOT,
    encoding: "utf8",
  }).trim();
  return path.resolve(ROOT, common, "vfbiz-agent-control");
}

export class AgentControlStore {
  constructor(stateRoot = defaultStateRoot(), options = {}) {
    this.stateRoot = stateRoot;
    this.stateFile = path.join(stateRoot, "state.json");
    this.lockFile = path.join(stateRoot, "dispatcher.lock");
    this.lockStaleMs = options.lockStaleMs ?? 5_000;
  }

  async init() {
    await mkdir(this.stateRoot, { recursive: true });
  }

  async read() {
    await this.init();
    try {
      return JSON.parse(await readFile(this.stateFile, "utf8"));
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      return {
        version: 2,
        fencingCounter: 0,
        claims: [],
        leases: [],
        runs: [],
        findings: [],
        coordinationRequests: [],
      };
    }
  }

  async withLock(operation) {
    await this.init();
    let lock;
    for (let attempt = 0; attempt < 2 && !lock; attempt += 1) {
      try {
        lock = await open(this.lockFile, "wx", 0o600);
      } catch (error) {
        if (error.code !== "EEXIST") throw error;
        let stale = false;
        try {
          const current = JSON.parse(await readFile(this.lockFile, "utf8"));
          const age = Date.now() - Date.parse(current.acquiredAt);
          stale = !processAlive(Number(current.pid)) && age > this.lockStaleMs;
        } catch (readError) {
          if (readError.code === "ENOENT") continue;
        }
        if (stale) {
          await rm(this.lockFile, { force: true });
          continue;
        }
        throw new Error(
          "dispatcher is busy; retry must be initiated by the caller",
        );
      }
    }
    if (!lock) throw new Error("dispatcher lock could not be acquired");
    try {
      await lock.writeFile(
        JSON.stringify({ pid: process.pid, acquiredAt: nowIso() }),
      );
      const state = await this.read();
      const expiry = expireState(state);
      const result = await operation(state, expiry);
      const temp = `${this.stateFile}.${process.pid}.tmp`;
      await writeFile(temp, `${JSON.stringify(state, null, 2)}\n`, {
        mode: 0o600,
      });
      await rename(temp, this.stateFile);
      return result;
    } finally {
      await lock?.close();
      await rm(this.lockFile, { force: true });
    }
  }
}

function active(record) {
  return record.state === "active" && Date.parse(record.expiresAt) > Date.now();
}

function processAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

function expireState(state) {
  const now = Date.now();
  const expired = { claims: 0, leases: 0 };
  for (const record of [...(state.claims ?? []), ...(state.leases ?? [])]) {
    if (record.state === "active" && Date.parse(record.expiresAt) <= now) {
      record.state = "expired";
      if (state.claims?.includes(record)) expired.claims += 1;
      else expired.leases += 1;
    }
  }
  state.findings ??= [];
  state.coordinationRequests ??= [];
  return expired;
}

/**
 * Persist expiry transitions without acquiring/releasing a claim. This is the
 * safe recovery action for a shared Git-common-directory control store.
 */
export async function reconcileAgentControlState(options = {}) {
  const store = options.store ?? new AgentControlStore();
  return store.withLock(async (_state, expired) => ({
    expiredClaims: expired.claims,
    expiredLeases: expired.leases,
  }));
}

function assertTeam(organization, teamId, label) {
  if (!organization.teams.some(({ id }) => id === teamId))
    throw new Error(`${label} is not a canonical team: ${teamId}`);
}

export async function createCoordinationRequest(input, options = {}) {
  const organization = await loadOrganization();
  const store = options.store ?? new AgentControlStore();
  if (!/^VFBIZ-[0-9]{4}$/.test(input.workItemKey ?? ""))
    throw new Error("coordination request requires a valid work item key");
  assertTeam(organization, input.requestingTeam, "requesting team");
  assertTeam(organization, input.owningTeam, "owning team");
  if (input.requestingTeam === input.owningTeam)
    throw new Error("coordination request must cross a team boundary");
  for (const [field, value] of [
    ["shared outcome", input.sharedOutcome],
    ["interface or dependency", input.interfaceOrDependency],
    ["decision or artifact needed", input.decisionOrArtifactNeeded],
    ["required by", input.requiredBy],
  ]) {
    if (typeof value !== "string" || value.trim().length === 0)
      throw new Error(`${field} is required`);
  }
  if (!input.blocking && !input.defaultIfNotBlocking)
    throw new Error("non-blocking coordination requires a safe default");
  return store.withLock(async (state) => {
    const now = nowIso();
    const record = {
      schemaVersion: 2,
      coordinationId: `coord-${randomUUID()}`,
      workItemKey: input.workItemKey,
      requestingTeam: input.requestingTeam,
      owningTeam: input.owningTeam,
      sharedOutcome: input.sharedOutcome.trim(),
      interfaceOrDependency: input.interfaceOrDependency.trim(),
      factsAlreadyKnown: [...new Set(input.factsAlreadyKnown ?? [])],
      decisionOrArtifactNeeded: input.decisionOrArtifactNeeded.trim(),
      blocking: Boolean(input.blocking),
      requiredBy: input.requiredBy,
      ...(input.defaultIfNotBlocking
        ? { defaultIfNotBlocking: input.defaultIfNotBlocking.trim() }
        : {}),
      state: "open",
      responses: [],
      createdAt: now,
      updatedAt: now,
    };
    state.coordinationRequests.push(record);
    return record;
  });
}

export async function respondCoordinationRequest(input, options = {}) {
  const organization = await loadOrganization();
  const store = options.store ?? new AgentControlStore();
  assertTeam(organization, input.responderTeam, "responder team");
  if (typeof input.response !== "string" || input.response.trim().length === 0)
    throw new Error("coordination response is required");
  return store.withLock(async (state) => {
    const record = state.coordinationRequests.find(
      ({ coordinationId }) => coordinationId === input.coordinationId,
    );
    if (!record) throw new Error("coordination request not found");
    if (!["open", "responded"].includes(record.state))
      throw new Error(`coordination request is ${record.state}`);
    if (record.owningTeam !== input.responderTeam)
      throw new Error("only the owning team may respond");
    const now = nowIso();
    record.responses.push({
      responderTeam: input.responderTeam,
      response: input.response.trim(),
      evidenceRefs: [...new Set(input.evidenceRefs ?? [])],
      respondedAt: now,
    });
    record.state = "responded";
    record.updatedAt = now;
    return record;
  });
}

export async function closeCoordinationRequest(input, options = {}) {
  const organization = await loadOrganization();
  const store = options.store ?? new AgentControlStore();
  assertTeam(organization, input.closedBy, "closing team");
  if (
    typeof input.resolution !== "string" ||
    input.resolution.trim().length === 0
  )
    throw new Error("coordination resolution is required");
  return store.withLock(async (state) => {
    const record = state.coordinationRequests.find(
      ({ coordinationId }) => coordinationId === input.coordinationId,
    );
    if (!record) throw new Error("coordination request not found");
    if (!["open", "responded"].includes(record.state))
      throw new Error(`coordination request is ${record.state}`);
    if (![record.requestingTeam, record.owningTeam].includes(input.closedBy))
      throw new Error("only a participating team may close coordination");
    const now = nowIso();
    record.state = "closed";
    record.resolution = input.resolution.trim();
    record.closedBy = input.closedBy;
    record.updatedAt = now;
    return record;
  });
}

export async function getCoordinationRequest(coordinationId, options = {}) {
  const store = options.store ?? new AgentControlStore();
  const state = await store.read();
  return (
    state.coordinationRequests?.find(
      (record) => record.coordinationId === coordinationId,
    ) ?? null
  );
}

function assertAttemptBudget(
  state,
  organization,
  workItemKey,
  attemptNumber,
  causeFingerprint,
) {
  if (attemptNumber > organization.runtime.maxSameCauseAttempts)
    throw new Error("needs-decision: same-cause attempt limit reached");
  if (!causeFingerprint) return;
  const attempts = state.runs.filter(
    (run) =>
      run.workItemKey === workItemKey &&
      run.causeFingerprint === causeFingerprint,
  ).length;
  if (attempts >= organization.runtime.maxSameCauseAttempts)
    throw new Error("needs-decision: same-cause attempt limit reached");
}

export async function acquireClaim(envelope, options = {}) {
  const organization = await loadOrganization();
  const store = options.store ?? new AgentControlStore();
  const allowedPaths = [];
  for (const candidate of envelope.allowedPaths ?? [])
    allowedPaths.push(await assertNoSymlinkEscape(candidate));
  if (
    !envelope.workItemKey ||
    !envelope.runId ||
    !envelope.provider ||
    !envelope.baseRevision
  )
    throw new Error(
      "workItemKey, runId, provider and baseRevision are required",
    );
  if (!/^VFBIZ-[0-9]{4}$/.test(envelope.workItemKey))
    throw new Error(`invalid work item key: ${envelope.workItemKey}`);
  if (!["read-only", "scoped-write"].includes(envelope.runMode))
    throw new Error(`invalid run mode: ${envelope.runMode}`);
  assertProvider(envelope.provider);
  if (!/^[a-f0-9]{64}$/.test(envelope.contextKey ?? ""))
    throw new Error("contextKey must be a SHA-256 hex digest");
  if (allowedPaths.length === 0)
    throw new Error("at least one allowed path is required");
  if (
    envelope.runMode === "scoped-write" &&
    (!envelope.branch || !envelope.worktree)
  )
    throw new Error("scoped-write claim requires branch and worktree");
  const workspace = repositoryRelative(envelope.workspace);

  let canonicalWorkItem = null;
  const verifyWorkItem = options.verifyWorkItem ?? options.store === undefined;
  if (verifyWorkItem) {
    const file = path.join(
      ROOT,
      "docs/work/items",
      `${envelope.workItemKey}.md`,
    );
    canonicalWorkItem = await readFrontmatter(file).catch(() => {
      throw new Error(
        `canonical work item does not exist: ${envelope.workItemKey}`,
      );
    });
    if (
      !["ready", "active", "review"].includes(
        canonicalWorkItem.attributes.status,
      )
    )
      throw new Error(
        `work item is not claimable in status ${canonicalWorkItem.attributes.status}`,
      );
    const itemPaths = canonicalWorkItem.attributes.allowed_paths ?? [];
    if (
      allowedPaths.some(
        (candidate) =>
          !itemPaths.some((allowed) => pathsOverlap(candidate, allowed)),
      )
    ) {
      throw new Error("claim paths exceed canonical work-item allowed_paths");
    }
    const team = organization.teams.find(
      ({ id }) => id === canonicalWorkItem.attributes.owner_team,
    );
    if (!team)
      throw new Error(
        `canonical work item has unknown owner team: ${canonicalWorkItem.attributes.owner_team}`,
      );
    const declaredResources = new Set(
      canonicalWorkItem.attributes.exclusive_resources ?? [],
    );
    const isDeclaredSharedPath = (candidate) => {
      const resource = sharedResourceForPath(candidate, organization);
      return resource !== undefined && declaredResources.has(resource);
    };
    if (
      workspace !== "." &&
      allowedPaths.some(
        (candidate) =>
          !pathsOverlap(candidate, workspace) &&
          !isDeclaredSharedPath(candidate),
      )
    )
      throw new Error(
        "allowed paths must remain inside the claimed workspace or use a declared shared resource",
      );
    if (
      allowedPaths.some(
        (candidate) =>
          !(team.paths ?? []).some((owned) => pathsOverlap(candidate, owned)) &&
          !isDeclaredSharedPath(candidate),
      )
    ) {
      throw new Error(`claim paths exceed owner-team boundary: ${team.id}`);
    }
  } else if (
    workspace !== "." &&
    allowedPaths.some((candidate) => !pathsOverlap(candidate, workspace))
  ) {
    throw new Error("allowed paths must remain inside the claimed workspace");
  }

  const verifyGitState = options.verifyGitState ?? options.store === undefined;
  const verifyContextCache =
    options.verifyContextCache ?? options.store === undefined;
  if (verifyContextCache) await assertCachedContext(envelope.contextKey);
  if (envelope.runMode === "scoped-write" && verifyGitState) {
    const worktree = path.resolve(envelope.worktree);
    const rootCommon = path.resolve(
      ROOT,
      git(ROOT, ["rev-parse", "--git-common-dir"]),
    );
    const worktreeCommon = path.resolve(
      worktree,
      git(worktree, ["rev-parse", "--git-common-dir"]),
    );
    if (rootCommon !== worktreeCommon)
      throw new Error(
        "claimed worktree does not belong to the VFBiz repository",
      );
    const head = git(worktree, ["rev-parse", "HEAD"]);
    if (!sameRevision(head, envelope.baseRevision))
      throw new Error(
        `stale base revision: expected ${envelope.baseRevision}, observed ${head}`,
      );
    const branch = gitRefIdentity(worktree);
    if (branch !== envelope.branch)
      throw new Error(
        `branch mismatch: expected ${envelope.branch}, observed ${branch}`,
      );
    const dirty = git(worktree, [
      "status",
      "--porcelain",
      "--",
      ...allowedPaths,
    ]);
    if (dirty) throw new Error("claimed paths are dirty before preflight");
  }
  return store.withLock(async (state) => {
    assertAttemptBudget(
      state,
      organization,
      envelope.workItemKey,
      envelope.attemptNumber ?? 1,
      envelope.causeFingerprint,
    );
    const live = state.claims.filter(active);
    if (
      envelope.runMode === "scoped-write" &&
      live.filter((x) => x.runMode === "scoped-write").length >=
        organization.runtime.maxWriterLanes
    )
      throw new Error("maximum concurrent writer lanes reached");
    if (
      live.some(
        (x) =>
          x.workItemKey === envelope.workItemKey &&
          x.runMode === "scoped-write",
      )
    )
      throw new Error(
        `work item already has an active writer: ${envelope.workItemKey}`,
      );
    for (const claim of live.filter((x) => x.runMode === "scoped-write")) {
      if (
        allowedPaths.some((a) =>
          claim.allowedPaths.some((b) => pathsOverlap(a, b)),
        )
      )
        throw new Error(
          `allowed path conflicts with active claim ${claim.claimId}`,
        );
    }
    state.fencingCounter += 1;
    const claim = {
      schemaVersion: 2,
      claimId: envelope.claimId ?? `claim-${randomUUID()}`,
      workItemKey: envelope.workItemKey,
      runId: envelope.runId,
      agentRole: envelope.role,
      runMode: envelope.runMode,
      provider: envelope.provider,
      ownerTeam: canonicalWorkItem?.attributes.owner_team ?? envelope.ownerTeam,
      accountableHumanRole: envelope.accountableHumanRole,
      workspace,
      baseRevision: envelope.baseRevision,
      branch: envelope.branch,
      worktree: envelope.worktree,
      allowedPaths,
      leaseIds: [],
      requiredResources:
        canonicalWorkItem?.attributes.exclusive_resources ?? null,
      contextKey: envelope.contextKey,
      issuedBy: options.issuedBy ?? "vfbiz-single-dispatcher",
      claimedAt: nowIso(),
      expiresAt: plusMinutes(organization.runtime.claimTtlMinutes),
      state: "active",
      fencingToken: state.fencingCounter,
    };
    state.claims.push(claim);
    state.runs.push({
      schemaVersion: 2,
      runId: claim.runId,
      workItemKey: claim.workItemKey,
      claimId: claim.claimId,
      agentRole: claim.agentRole,
      runMode: claim.runMode,
      provider: claim.provider,
      attemptNumber: envelope.attemptNumber ?? 1,
      causeFingerprint: envelope.causeFingerprint ?? undefined,
      findingFingerprints: [],
      contextKey: claim.contextKey,
      baseRevision: claim.baseRevision,
      status: "running",
      startedAt: claim.claimedAt,
      cost: {
        source: "unavailable",
        inputTokens: null,
        outputTokens: null,
        estimatedUsd: null,
      },
    });
    return claim;
  });
}

export async function acquireLease(claimId, resource, options = {}) {
  const organization = await loadOrganization();
  const store = options.store ?? new AgentControlStore();
  return store.withLock(async (state) => {
    const claim = state.claims.find((x) => x.claimId === claimId && active(x));
    if (!claim) throw new Error(`active claim not found: ${claimId}`);
    if (
      Array.isArray(claim.requiredResources) &&
      !claim.requiredResources.includes(resource.resourceClass)
    )
      throw new Error(
        `resource class is not declared by work item: ${resource.resourceClass}`,
      );
    const key = resource.resourceKey;
    if (
      state.leases.some(
        (x) =>
          active(x) &&
          (x.resourceKey === key ||
            (x.resourcePath &&
              resource.resourcePath &&
              pathsOverlap(x.resourcePath, resource.resourcePath))),
      )
    )
      throw new Error(`exclusive resource already leased: ${key}`);
    state.fencingCounter += 1;
    const lease = {
      schemaVersion: 2,
      leaseId: resource.leaseId ?? `lease-${randomUUID()}`,
      resourceClass: resource.resourceClass,
      resourceKey: key,
      resourcePath: resource.resourcePath
        ? repositoryRelative(resource.resourcePath)
        : undefined,
      holderClaimId: claim.claimId,
      holderRunId: claim.runId,
      baseRevision: claim.baseRevision,
      issuedBy: options.issuedBy ?? "vfbiz-single-dispatcher",
      acquiredAt: nowIso(),
      expiresAt: plusMinutes(organization.runtime.leaseTtlMinutes),
      state: "active",
      renewalCount: 0,
      fencingToken: state.fencingCounter,
    };
    state.leases.push(lease);
    claim.leaseIds.push(lease.leaseId);
    claim.fencingToken = lease.fencingToken;
    return lease;
  });
}

export async function validateClaim(claimId, options = {}) {
  const store = options.store ?? new AgentControlStore();
  return store.withLock(async (state) => {
    const claim = state.claims.find((x) => x.claimId === claimId);
    if (!claim || !active(claim))
      throw new Error(
        `claim is not active: ${claimId}${claim?.state === "expired" ? " (expired)" : ""}`,
      );
    if (
      options.fencingToken &&
      claim.fencingToken !== Number(options.fencingToken)
    )
      throw new Error("stale fencing token");
    return claim;
  });
}

export async function heartbeatClaim(claimId, fencingToken, options = {}) {
  const organization = await loadOrganization();
  const store = options.store ?? new AgentControlStore();
  return store.withLock(async (state) => {
    const claim = state.claims.find((x) => x.claimId === claimId && active(x));
    if (!claim) throw new Error(`active claim not found: ${claimId}`);
    if (claim.fencingToken !== Number(fencingToken))
      throw new Error("stale fencing token");
    claim.lastHeartbeatAt = nowIso();
    claim.expiresAt = plusMinutes(organization.runtime.claimTtlMinutes);
    return claim;
  });
}

export async function renewLease(claimId, leaseId, fencingToken, options = {}) {
  const organization = await loadOrganization();
  const store = options.store ?? new AgentControlStore();
  return store.withLock(async (state) => {
    const claim = state.claims.find((x) => x.claimId === claimId && active(x));
    if (!claim) throw new Error(`active claim not found: ${claimId}`);
    const lease = state.leases.find(
      (x) => x.leaseId === leaseId && x.holderClaimId === claimId && active(x),
    );
    if (!lease) throw new Error(`active lease not found: ${leaseId}`);
    if (claim.fencingToken !== Number(fencingToken))
      throw new Error("stale fencing token");
    if (lease.renewalCount >= organization.runtime.maxLeaseRenewals)
      throw new Error("maximum lease renewals reached");
    state.fencingCounter += 1;
    lease.renewalCount += 1;
    lease.renewedAt = nowIso();
    lease.expiresAt = plusMinutes(organization.runtime.leaseTtlMinutes);
    lease.fencingToken = state.fencingCounter;
    claim.fencingToken = state.fencingCounter;
    return lease;
  });
}

function requiresRiskReviewForSignal(signal) {
  return /(?:^|[-_])(ai|auth|authentication|authorization|contract|data|dependency|legal|migration|payment|pii|privacy|production|release|security)(?:$|[-_])/.test(
    String(signal).toLowerCase(),
  );
}

function currentFindingDispositions(findings, workItemKey) {
  const current = new Map();
  for (const finding of findings
    .filter((record) => record.workItemKey === workItemKey)
    .sort(
      (left, right) =>
        Number(left.cycle ?? 0) - Number(right.cycle ?? 0) ||
        Date.parse(left.recordedAt ?? 0) - Date.parse(right.recordedAt ?? 0),
    ))
    current.set(finding.fingerprint, finding);
  return [...current.values()];
}

export async function assertWorkReviewComplete(item, options = {}) {
  const mode = item?.attributes?.mode;
  if (!["controlled", "parallel"].includes(mode)) return { required: false };
  const workItemKey = item.attributes.id;
  const store = options.store ?? new AgentControlStore();
  const state = await store.read();
  const latestWriter = state.runs
    .filter(
      (run) =>
        run.workItemKey === workItemKey &&
        run.status === "completed" &&
        (run.runMode === "scoped-write" ||
          ["implementer", "integrator", "synthetic-dataset-builder"].includes(
            run.agentRole,
          )),
    )
    .sort(
      (left, right) =>
        Date.parse(right.finishedAt ?? 0) - Date.parse(left.finishedAt ?? 0),
    )[0];
  if (!latestWriter?.finishedAt)
    throw new Error(
      `work item cannot complete: review ledger is missing completed implementation evidence for ${workItemKey}`,
    );
  const completedReviews = state.runs.filter(
    (run) =>
      run.workItemKey === workItemKey &&
      run.status === "completed" &&
      ["reviewer-verifier", "risk-reviewer"].includes(run.agentRole) &&
      Date.parse(run.startedAt ?? 0) >= Date.parse(latestWriter.finishedAt),
  );
  const completedRoles = new Set(completedReviews.map((run) => run.agentRole));
  if (!completedRoles.has("reviewer-verifier"))
    throw new Error(
      `work item cannot complete: review ledger is missing reviewer-verifier evidence for the current implementation of ${workItemKey}`,
    );
  const requiresRiskReview = (item.attributes.controlled_signals ?? []).some(
    requiresRiskReviewForSignal,
  );
  if (requiresRiskReview && !completedRoles.has("risk-reviewer"))
    throw new Error(
      `work item cannot complete: risk-reviewer evidence is required for ${workItemKey}`,
    );
  const open = currentFindingDispositions(
    state.findings ?? [],
    workItemKey,
  ).filter((finding) => finding.disposition === "open");
  if (open.length)
    throw new Error(
      `work item cannot complete with open finding(s): ${open
        .map(({ fingerprint }) => fingerprint)
        .join(", ")}`,
    );
  return {
    required: true,
    completedRoles: [...completedRoles].sort(),
    requiresRiskReview,
  };
}

export async function validatePaths(claimId, paths, options = {}) {
  const organization = await loadOrganization();
  const store = options.store ?? new AgentControlStore();
  const normalized = [];
  for (const candidate of paths)
    normalized.push(await assertNoSymlinkEscape(candidate));
  return store.withLock(async (state) => {
    const claim = state.claims.find((record) => record.claimId === claimId);
    if (!claim || !active(claim))
      throw new Error(
        `claim is not active: ${claimId}${claim?.state === "expired" ? " (expired)" : ""}`,
      );
    if (
      options.fencingToken &&
      claim.fencingToken !== Number(options.fencingToken)
    )
      throw new Error("stale fencing token");
    const outside = normalized.filter(
      (candidate) =>
        !claim.allowedPaths.some((allowed) => pathsOverlap(candidate, allowed)),
    );
    if (outside.length)
      throw new Error(`paths outside claim: ${outside.join(", ")}`);
    for (const candidate of normalized) {
      const resource = sharedResourceForPath(candidate, organization);
      if (
        resource &&
        !state.leases.some(
          (lease) =>
            active(lease) &&
            lease.holderClaimId === claimId &&
            lease.resourceClass === resource,
        )
      )
        throw new Error(
          `active ${resource} lease is required for shared path: ${candidate}`,
        );
    }
    return { claimId, paths: normalized };
  });
}

export async function releaseClaim(claimId, evidenceRef, options = {}) {
  if (!evidenceRef) throw new Error("release evidence is required");
  const store = options.store ?? new AgentControlStore();
  return store.withLock(async (state) => {
    const claim = state.claims.find((x) => x.claimId === claimId);
    if (!claim || !active(claim))
      throw new Error(`active claim not found: ${claimId}`);
    const releasedAt = nowIso();
    for (const lease of state.leases.filter(
      (x) => x.holderClaimId === claimId && active(x),
    ))
      Object.assign(lease, {
        state: "released",
        releasedAt,
        releaseEvidenceRef: evidenceRef,
      });
    Object.assign(claim, {
      state: "released",
      releasedAt,
      releaseEvidenceRef: evidenceRef,
    });
    const run = state.runs.find((x) => x.runId === claim.runId);
    if (run)
      Object.assign(run, {
        status: "completed",
        finishedAt: releasedAt,
        headRevision: options.headRevision ?? claim.baseRevision,
        exitState: options.exitState ?? "completed",
        reportRef: evidenceRef,
      });
    return claim;
  });
}

export async function handoffClaim(claimId, capsule, successor, options = {}) {
  const organization = await loadOrganization();
  const store = options.store ?? new AgentControlStore();
  if (!successor?.runId) throw new Error("successor runId is required");
  assertProvider(successor.provider);
  if (!/^[a-f0-9]{64}$/.test(successor.contextKey ?? ""))
    throw new Error("successor contextKey must be a SHA-256 hex digest");
  if (!capsule.cleanCheckpoint?.gitStatusClean)
    throw new Error("handoff requires a clean checkpoint");
  if (!capsule.cleanCheckpoint?.revision)
    throw new Error("handoff requires a clean checkpoint revision");
  const words = JSON.stringify(capsule).split(/\s+/).length;
  if (words > organization.runtime.maxCapsuleTokens)
    throw new Error("capsule exceeds the 1500-token safety approximation");
  const verifyGitState = options.verifyGitState ?? options.store === undefined;
  const verifyContextCache =
    options.verifyContextCache ?? options.store === undefined;
  if (verifyContextCache) await assertCachedContext(successor.contextKey);
  if (verifyGitState) {
    const snapshot = await store.read();
    const currentClaim = snapshot.claims.find(
      (record) => record.claimId === claimId && active(record),
    );
    if (!currentClaim) throw new Error(`active claim not found: ${claimId}`);
    if (!currentClaim.worktree || !currentClaim.branch)
      throw new Error("handoff requires a scoped worktree claim");
    const worktree = path.resolve(currentClaim.worktree);
    const rootCommon = path.resolve(
      ROOT,
      git(ROOT, ["rev-parse", "--git-common-dir"]),
    );
    const worktreeCommon = path.resolve(
      worktree,
      git(worktree, ["rev-parse", "--git-common-dir"]),
    );
    if (rootCommon !== worktreeCommon)
      throw new Error(
        "handoff worktree does not belong to the VFBiz repository",
      );
    const branch = gitRefIdentity(worktree);
    if (branch !== currentClaim.branch)
      throw new Error(
        `handoff branch mismatch: expected ${currentClaim.branch}, observed ${branch}`,
      );
    const head = git(worktree, ["rev-parse", "HEAD"]);
    if (!sameRevision(head, capsule.cleanCheckpoint.revision))
      throw new Error(
        `handoff revision mismatch: expected ${capsule.cleanCheckpoint.revision}, observed ${head}`,
      );
    if (git(worktree, ["status", "--porcelain"]))
      throw new Error("handoff worktree is dirty");
  }
  return store.withLock(async (state) => {
    const claim = state.claims.find((x) => x.claimId === claimId && active(x));
    if (!claim) throw new Error(`active claim not found: ${claimId}`);
    if (state.runs.some((run) => run.runId === successor.runId))
      throw new Error(`successor run already exists: ${successor.runId}`);
    const previous = state.runs.find((x) => x.runId === claim.runId);
    const sameCause = state.runs.filter(
      (x) =>
        x.workItemKey === claim.workItemKey &&
        x.causeFingerprint &&
        x.causeFingerprint === successor.causeFingerprint,
    ).length;
    if (sameCause >= organization.runtime.maxSameCauseHandoffs)
      throw new Error("same-cause handoff limit reached");
    assertAttemptBudget(
      state,
      organization,
      claim.workItemKey,
      successor.attemptNumber ?? 1,
      successor.causeFingerprint,
    );
    state.fencingCounter += 1;
    if (previous)
      Object.assign(previous, {
        status: "handoff-ready",
        finishedAt: nowIso(),
        headRevision: capsule.cleanCheckpoint.revision,
        handoffToRunId: successor.runId,
      });
    claim.runId = successor.runId;
    claim.provider = successor.provider;
    claim.baseRevision = capsule.cleanCheckpoint.revision;
    claim.contextKey = successor.contextKey;
    claim.predecessorRunId = previous?.runId;
    claim.fencingToken = state.fencingCounter;
    claim.expiresAt = plusMinutes(organization.runtime.claimTtlMinutes);
    for (const lease of state.leases.filter(
      (x) => x.holderClaimId === claimId && active(x),
    )) {
      lease.holderRunId = successor.runId;
      lease.fencingToken = state.fencingCounter;
    }
    state.runs.push({
      schemaVersion: 2,
      runId: successor.runId,
      workItemKey: claim.workItemKey,
      claimId,
      agentRole: claim.agentRole,
      runMode: claim.runMode,
      provider: successor.provider,
      attemptNumber: successor.attemptNumber ?? 1,
      causeFingerprint: successor.causeFingerprint ?? undefined,
      findingFingerprints: [],
      contextKey: successor.contextKey,
      baseRevision: capsule.cleanCheckpoint.revision,
      predecessorRunId: previous?.runId,
      status: "running",
      startedAt: nowIso(),
      cost: {
        source: "unavailable",
        inputTokens: null,
        outputTokens: null,
        estimatedUsd: null,
      },
    });
    return claim;
  });
}

export async function recordReviewFinding(runId, finding, options = {}) {
  const organization = await loadOrganization();
  const store = options.store ?? new AgentControlStore();
  if (!finding?.fingerprint || !finding?.evidenceHash)
    throw new Error("finding fingerprint and evidenceHash are required");
  if (!/^[a-f0-9]{64}$/.test(finding.evidenceHash))
    throw new Error("finding evidenceHash must be SHA-256");
  const cycle = Number(finding.cycle);
  if (!Number.isInteger(cycle) || cycle < 1)
    throw new Error("finding cycle must be a positive integer");
  if (cycle > organization.runtime.maxReviewFixCycles)
    throw new Error("review/fix cycle limit reached");
  if (
    !["open", "resolved", "false-positive", "superseded"].includes(
      finding.disposition ?? "open",
    )
  )
    throw new Error("invalid finding disposition");
  return store.withLock(async (state) => {
    const run = state.runs.find((record) => record.runId === runId);
    if (!run) throw new Error(`provider run not found: ${runId}`);
    const duplicate = state.findings.find(
      (record) =>
        record.workItemKey === run.workItemKey &&
        record.fingerprint === finding.fingerprint &&
        record.evidenceHash === finding.evidenceHash,
    );
    if (duplicate) throw new Error("duplicate finding without new evidence");
    const record = {
      workItemKey: run.workItemKey,
      runId,
      fingerprint: finding.fingerprint,
      evidenceHash: finding.evidenceHash,
      cycle,
      severity: finding.severity ?? "medium",
      disposition: finding.disposition ?? "open",
      recordedAt: nowIso(),
    };
    state.findings.push(record);
    run.findingFingerprints ??= [];
    if (!run.findingFingerprints.includes(finding.fingerprint))
      run.findingFingerprints.push(finding.fingerprint);
    return record;
  });
}

export async function resetStore(store) {
  await rm(store.stateRoot, { recursive: true, force: true });
}
