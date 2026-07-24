#!/usr/bin/env node
import {
  mkdtemp,
  mkdir,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import {
  AgentControlStore,
  acquireClaim,
  acquireLease,
  handoffClaim,
  heartbeatClaim,
  pathsOverlap,
  recordReviewFinding,
  releaseClaim,
  renewLease,
  resetStore,
  validateClaim,
  validatePaths,
} from "./lib/agent-control.mjs";

const stateRoot = await mkdtemp(path.join(os.tmpdir(), "vfbiz-agent-control-"));
const store = new AgentControlStore(stateRoot);
let failed = 0;
function assert(condition, message) {
  if (!condition) {
    failed += 1;
    process.stderr.write(`- ${message}\n`);
  }
}
async function rejects(operation, pattern, message) {
  try {
    await operation();
    assert(false, message);
  } catch (error) {
    assert(pattern.test(error.message), `${message}: ${error.message}`);
  }
}
function hookOutput(result, message) {
  assert(
    result.stdout?.trim(),
    `${message}: hook returned no JSON (status=${result.status}, stderr=${result.stderr?.trim() || "empty"})`,
  );
  if (!result.stdout?.trim()) return {};
  try {
    return JSON.parse(result.stdout);
  } catch (error) {
    assert(false, `${message}: invalid hook JSON (${error.message})`);
    return {};
  }
}
const provider = {
  name: "test-provider",
  adapter: "generic",
  adapterVersion: "2",
};
const base = {
  schemaVersion: 2,
  role: "implementer",
  runMode: "scoped-write",
  provider,
  accountableHumanRole: "engineering-lead",
  workspace: ".",
  baseRevision: "abcdef1",
  contextKey: "a".repeat(64),
  branch: "agent/test",
  worktree: "/tmp/vfbiz-test",
  attemptNumber: 1,
};

try {
  const first = await acquireClaim(
    {
      ...base,
      workItemKey: "VFBIZ-0001",
      runId: "run-1",
      allowedPaths: ["docs/product"],
    },
    { store },
  );
  assert(
    first.state === "active" && first.fencingToken === 1,
    "first claim must be active",
  );
  await validatePaths(first.claimId, ["docs/product/vision.md"], {
    store,
    fencingToken: first.fencingToken,
  });
  await rejects(
    () => validatePaths(first.claimId, ["backend/api"], { store }),
    /outside claim/,
    "out-of-scope path must fail",
  );
  await rejects(
    () => validatePaths(first.claimId, ["../escape"], { store }),
    /traversal/,
    "traversal must fail",
  );
  await rejects(
    () =>
      acquireClaim(
        {
          ...base,
          workItemKey: "VFBIZ-0002",
          runId: "run-2",
          allowedPaths: ["docs"],
        },
        { store },
      ),
    /conflicts/,
    "ancestor path overlap must fail",
  );
  const second = await acquireClaim(
    {
      ...base,
      workItemKey: "VFBIZ-0002",
      runId: "run-2",
      branch: "agent/two",
      allowedPaths: ["backend/api"],
    },
    { store },
  );
  const third = await acquireClaim(
    {
      ...base,
      workItemKey: "VFBIZ-0003",
      runId: "run-3",
      branch: "agent/three",
      allowedPaths: ["mobile"],
    },
    { store },
  );
  await rejects(
    () =>
      validatePaths(
        second.claimId,
        ["backend/api/prisma/migrations/next/migration.sql"],
        { store, fencingToken: second.fencingToken },
      ),
    /database-migration lease is required/,
    "shared migration path must require its exclusive lease",
  );
  const migrationLease = await acquireLease(
    second.claimId,
    {
      resourceClass: "database-migration",
      resourceKey: "api-migrations",
      resourcePath: "backend/api/prisma/migrations",
    },
    { store },
  );
  await validatePaths(
    second.claimId,
    ["backend/api/prisma/migrations/next/migration.sql"],
    { store, fencingToken: migrationLease.fencingToken },
  );
  await rejects(
    () =>
      acquireClaim(
        {
          ...base,
          workItemKey: "VFBIZ-0004",
          runId: "run-4",
          branch: "agent/four",
          allowedPaths: ["infra"],
        },
        { store },
      ),
    /maximum concurrent writer/,
    "fourth writer must fail",
  );
  const lease = await acquireLease(
    first.claimId,
    { resourceClass: "public-contract", resourceKey: "public-v1" },
    { store },
  );
  await rejects(
    () =>
      acquireLease(
        second.claimId,
        { resourceClass: "public-contract", resourceKey: "public-v1" },
        { store },
      ),
    /already leased/,
    "lease collision must fail",
  );
  const heartbeat = await heartbeatClaim(first.claimId, lease.fencingToken, {
    store,
  });
  assert(
    heartbeat.lastHeartbeatAt && heartbeat.state === "active",
    "claim heartbeat must extend an active claim",
  );
  const renewed = await renewLease(
    first.claimId,
    lease.leaseId,
    lease.fencingToken,
    { store },
  );
  assert(
    renewed.renewalCount === 1 && renewed.fencingToken > lease.fencingToken,
    "lease renewal must rotate fencing and increment renewal count",
  );
  const hookEnvironment = {
    ...process.env,
    VFBIZ_AGENT_STATE_DIR: stateRoot,
    VFBIZ_CLAIM_ID: first.claimId,
    VFBIZ_FENCING_TOKEN: String(renewed.fencingToken),
  };
  const allowedHook = spawnSync(
    process.execPath,
    ["tools/agent-hook.mjs", "pre-write", "generic"],
    {
      cwd: process.cwd(),
      env: hookEnvironment,
      input: JSON.stringify({
        tool_input: { file_path: "docs/product/vision.md" },
      }),
      encoding: "utf8",
    },
  );
  assert(
    allowedHook.status === 0 &&
      hookOutput(allowedHook, "provider allow hook").decision === "allow",
    "provider hook must extract and allow an owned mutation path",
  );
  const deniedHook = spawnSync(
    process.execPath,
    ["tools/agent-hook.mjs", "pre-write", "generic"],
    {
      cwd: process.cwd(),
      env: hookEnvironment,
      input: JSON.stringify({
        tool_input: { file_path: "backend/api/src/main.ts" },
      }),
      encoding: "utf8",
    },
  );
  assert(
    deniedHook.status === 2 &&
      hookOutput(deniedHook, "provider deny hook").decision === "block",
    "provider hook must block an out-of-scope mutation path",
  );
  const missingPathHook = spawnSync(
    process.execPath,
    ["tools/agent-hook.mjs", "pre-write", "generic"],
    { cwd: process.cwd(), env: hookEnvironment, input: "{}", encoding: "utf8" },
  );
  assert(
    missingPathHook.status === 2,
    "provider hook must not allow a mutation without an observed path",
  );
  const unclaimedFastHook = spawnSync(
    process.execPath,
    ["tools/agent-hook.mjs", "pre-write", "generic"],
    {
      cwd: process.cwd(),
      env: {
        ...process.env,
        VFBIZ_AGENT_STATE_DIR: stateRoot,
        VFBIZ_CLAIM_ID: "",
        VFBIZ_FENCING_TOKEN: "",
        VFBIZ_REQUIRE_CLAIM: "0",
      },
      input: JSON.stringify({ tool_input: { file_path: "README.md" } }),
      encoding: "utf8",
    },
  );
  assert(
    unclaimedFastHook.status === 0 &&
      hookOutput(unclaimedFastHook, "unclaimed fast hook").claimed === false,
    "fast/bounded local hook must allow safe unclaimed writes",
  );
  const missingControlledClaim = spawnSync(
    process.execPath,
    ["tools/agent-hook.mjs", "pre-write", "generic"],
    {
      cwd: process.cwd(),
      env: {
        ...process.env,
        VFBIZ_AGENT_STATE_DIR: stateRoot,
        VFBIZ_CLAIM_ID: "",
        VFBIZ_REQUIRE_CLAIM: "1",
      },
      input: JSON.stringify({ tool_input: { file_path: "README.md" } }),
      encoding: "utf8",
    },
  );
  assert(
    missingControlledClaim.status === 2,
    "controlled/delegated hook must reject a missing claim",
  );
  const codexDeniedHook = spawnSync(
    process.execPath,
    ["tools/agent-hook.mjs", "pre-write", "codex"],
    {
      cwd: process.cwd(),
      env: hookEnvironment,
      input: JSON.stringify({
        tool_input: { file_path: "backend/api/src/main.ts" },
      }),
      encoding: "utf8",
    },
  );
  const codexDenied = hookOutput(codexDeniedHook, "Codex deny hook");
  assert(
    codexDeniedHook.status === 0 &&
      codexDenied.hookSpecificOutput?.permissionDecision === "deny",
    "Codex hook must use the official structured deny response",
  );
  await rejects(
    () =>
      handoffClaim(
        first.claimId,
        {
          cleanCheckpoint: { revision: "abcdef1", gitStatusClean: true },
          nextAction: "Reject an invalid successor provider.",
        },
        {
          runId: "run-invalid-provider",
          provider: {
            name: "successor",
            adapter: "unsupported",
            adapterVersion: "2",
          },
          contextKey: "b".repeat(64),
          causeFingerprint: "quota",
        },
        { store, verifyGitState: false },
      ),
    /invalid provider adapter/,
    "handoff must validate the successor provider envelope",
  );
  const handedOff = await handoffClaim(
    first.claimId,
    {
      cleanCheckpoint: { revision: "abcdef1", gitStatusClean: true },
      nextAction: "Continue validation",
    },
    {
      runId: "run-1b",
      provider: { name: "successor", adapter: "claude", adapterVersion: "2" },
      contextKey: "b".repeat(64),
      causeFingerprint: "quota",
    },
    { store, verifyGitState: false },
  );
  assert(
    handedOff.baseRevision === "abcdef1" &&
      handedOff.contextKey === "b".repeat(64),
    "handoff must advance claim revision and context manifest",
  );
  const evidenceOne = "1".repeat(64);
  const evidenceTwo = "2".repeat(64);
  await recordReviewFinding(
    "run-1b",
    { fingerprint: "authorization-gap", evidenceHash: evidenceOne, cycle: 1 },
    { store },
  );
  await rejects(
    () =>
      recordReviewFinding(
        "run-1b",
        {
          fingerprint: "authorization-gap",
          evidenceHash: evidenceOne,
          cycle: 1,
        },
        { store },
      ),
    /duplicate finding/,
    "duplicate finding without new evidence must fail",
  );
  await recordReviewFinding(
    "run-1b",
    { fingerprint: "authorization-gap", evidenceHash: evidenceTwo, cycle: 2 },
    { store },
  );
  await rejects(
    () =>
      recordReviewFinding(
        "run-1b",
        { fingerprint: "new-gap", evidenceHash: "3".repeat(64), cycle: 3 },
        { store },
      ),
    /cycle limit/,
    "third review/fix cycle must fail",
  );
  await rejects(
    () =>
      validateClaim(first.claimId, { store, fencingToken: lease.fencingToken }),
    /stale fencing/,
    "old provider fencing token must fail",
  );
  await releaseClaim(first.claimId, "evidence:test", { store });
  await rejects(
    () => validateClaim(first.claimId, { store }),
    /not active/,
    "released claim must fail",
  );
  assert(
    pathsOverlap("contracts", "contracts/openapi/public.yaml"),
    "ancestor resources must overlap",
  );
  assert(second && third, "independent claims must be created");
  const outside = path.join(stateRoot, "outside");
  await mkdir(outside);
  const link = path.join(process.cwd(), ".agent-state-test-link");
  try {
    await symlink(outside, link);
    await rejects(
      () =>
        validatePaths(second.claimId, [".agent-state-test-link/file"], {
          store,
        }),
      /symlink escapes|outside claim/,
      "symlink escape must fail",
    );
  } finally {
    await import("node:fs/promises").then((fs) => fs.rm(link, { force: true }));
  }

  const attemptRoot = await mkdtemp(
    path.join(os.tmpdir(), "vfbiz-agent-attempts-"),
  );
  const attemptStore = new AgentControlStore(attemptRoot);
  const attemptBase = {
    ...base,
    workItemKey: "VFBIZ-0010",
    allowedPaths: ["docs"],
    causeFingerprint: "same-root-cause",
  };
  const attemptOne = await acquireClaim(
    { ...attemptBase, runId: "attempt-1", attemptNumber: 1 },
    { store: attemptStore },
  );
  await releaseClaim(attemptOne.claimId, "evidence:attempt-1", {
    store: attemptStore,
  });
  const attemptTwo = await acquireClaim(
    { ...attemptBase, runId: "attempt-2", attemptNumber: 2 },
    { store: attemptStore },
  );
  await releaseClaim(attemptTwo.claimId, "evidence:attempt-2", {
    store: attemptStore,
  });
  await rejects(
    () =>
      acquireClaim(
        { ...attemptBase, runId: "attempt-3", attemptNumber: 3 },
        { store: attemptStore },
      ),
    /needs-decision/,
    "third same-cause attempt must require a decision",
  );
  await resetStore(attemptStore);

  const staleRoot = await mkdtemp(
    path.join(os.tmpdir(), "vfbiz-agent-stale-lock-"),
  );
  const staleStore = new AgentControlStore(staleRoot, { lockStaleMs: 0 });
  await staleStore.init();
  await writeFile(
    staleStore.lockFile,
    JSON.stringify({ pid: 99999999, acquiredAt: "2000-01-01T00:00:00.000Z" }),
  );
  await staleStore.withLock(async (state) => {
    state.recovered = true;
  });
  assert(
    JSON.parse(await readFile(staleStore.stateFile, "utf8")).recovered === true,
    "stale dispatcher lock must be recovered",
  );
  await writeFile(
    staleStore.lockFile,
    JSON.stringify({ pid: process.pid, acquiredAt: new Date().toISOString() }),
  );
  await rejects(
    () => staleStore.withLock(async () => undefined),
    /dispatcher is busy/,
    "live dispatcher lock must not be stolen",
  );
  await rm(staleStore.lockFile, { force: true });
  await resetStore(staleStore);

  await store.withLock(async (state) => {
    const claim = state.claims.find(
      (record) => record.claimId === second.claimId,
    );
    claim.expiresAt = "2000-01-01T00:00:00.000Z";
  });
  await rejects(
    () => validateClaim(second.claimId, { store }),
    /expired/,
    "expired claim must be marked and rejected",
  );

  const gitRoot = await mkdtemp(
    path.join(os.tmpdir(), "vfbiz-agent-git-handoff-"),
  );
  const gitStore = new AgentControlStore(gitRoot);
  const observedHead = spawnSync("git", ["rev-parse", "HEAD"], {
    cwd: process.cwd(),
    encoding: "utf8",
  }).stdout.trim();
  const observedBranch = spawnSync(
    "git",
    ["symbolic-ref", "--quiet", "--short", "HEAD"],
    { cwd: process.cwd(), encoding: "utf8" },
  ).stdout.trim();
  const gitClaim = await acquireClaim(
    {
      ...base,
      workItemKey: "VFBIZ-0020",
      runId: "git-handoff-1",
      baseRevision: observedHead,
      branch: observedBranch,
      worktree: process.cwd(),
      allowedPaths: ["tools"],
    },
    { store: gitStore },
  );
  await rejects(
    () =>
      handoffClaim(
        gitClaim.claimId,
        {
          cleanCheckpoint: { revision: "deadbee", gitStatusClean: true },
          nextAction: "Must reject a stale revision.",
        },
        {
          runId: "git-handoff-2",
          provider,
          contextKey: "c".repeat(64),
          causeFingerprint: "provider-quota",
        },
        { store: gitStore, verifyGitState: true },
      ),
    /revision mismatch/,
    "stale Git revision must reject handoff",
  );
  const dirtyProbe = path.join(process.cwd(), ".agent-control-handoff-probe");
  try {
    await writeFile(dirtyProbe, "dirty handoff probe\n");
    await rejects(
      () =>
        handoffClaim(
          gitClaim.claimId,
          {
            cleanCheckpoint: { revision: observedHead, gitStatusClean: true },
            nextAction: "Must reject dirty worktree.",
          },
          {
            runId: "git-handoff-3",
            provider,
            contextKey: "d".repeat(64),
            causeFingerprint: "provider-quota",
          },
          { store: gitStore, verifyGitState: true },
        ),
      /worktree is dirty/,
      "dirty Git worktree must reject handoff",
    );
  } finally {
    await rm(dirtyProbe, { force: true });
    await resetStore(gitStore);
  }
} finally {
  await resetStore(store);
}

if (failed) process.exit(1);
process.stdout.write(
  "Agent control checks passed: claims, writer cap, paths, hooks, stale-lock recovery, attempt/review limits, fencing, Git-verified handoff and expiry.\n",
);
