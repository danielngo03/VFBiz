#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile, realpath, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { ROOT } from "./lib/governance.mjs";
import {
  defaultStateRoot,
  repositoryRelative,
  validateClaim,
  validatePaths,
} from "./lib/agent-control.mjs";

async function readInput() {
  if (process.argv.includes("--input"))
    return JSON.parse(
      await readFile(process.argv[process.argv.indexOf("--input") + 1], "utf8"),
    );
  let data = "";
  for await (const chunk of process.stdin) data += chunk;
  return data.trim() ? JSON.parse(data) : {};
}

function mutationPaths(payload) {
  const result = new Set(Array.isArray(payload.paths) ? payload.paths : []);
  for (const candidate of [
    payload.file_path,
    payload.filePath,
    payload.path,
    payload.tool_input?.file_path,
    payload.tool_input?.filePath,
    payload.tool_input?.path,
    payload.toolInput?.file_path,
    payload.toolInput?.filePath,
    payload.toolInput?.path,
  ])
    if (typeof candidate === "string" && candidate.length > 0)
      result.add(candidate);
  for (const patchText of [
    payload.patch,
    payload.command,
    payload.tool_input?.patch,
    payload.tool_input?.command,
    payload.toolInput?.patch,
    payload.toolInput?.command,
  ]) {
    if (typeof patchText !== "string") continue;
    for (const match of patchText.matchAll(
      /^\*\*\* (?:Add|Update|Delete) File: (.+)$/gm,
    ))
      result.add(match[1].trim());
  }
  return [...result].map((candidate) =>
    path.isAbsolute(candidate) ? path.relative(ROOT, candidate) : candidate,
  );
}

function cheapPathGuard(paths) {
  for (const candidate of paths) {
    const relative = repositoryRelative(candidate);
    const basename = path.posix.basename(relative);
    if (
      basename === ".env" ||
      (basename.startsWith(".env.") && basename !== ".env.example") ||
      /^(?:\.secrets\/|local-data\/)/.test(relative)
    )
      throw new Error(`protected local/private path: ${relative}`);
    if (/(?:^|\/)(?:id_rsa|id_ed25519|.*\.pem|.*\.key)$/.test(relative))
      throw new Error(`secret material path is forbidden: ${relative}`);
  }
}

function shellCommand(payload) {
  for (const candidate of [
    payload.command,
    payload.tool_input?.command,
    payload.toolInput?.command,
  ]) {
    if (typeof candidate === "string") return candidate;
    if (Array.isArray(candidate)) return candidate.join(" ");
  }
  return "";
}

function invocationId(payload, provider, command) {
  const explicit =
    payload.tool_use_id ??
    payload.toolUseId ??
    payload.tool_call_id ??
    payload.toolCallId ??
    payload.invocation_id ??
    payload.invocationId;
  const source =
    typeof explicit === "string" && explicit.length > 0
      ? explicit
      : `${provider}\0${payload.session_id ?? payload.sessionId ?? ""}\0${command}`;
  return createHash("sha256").update(source).digest("hex");
}

function assertNonDestructiveShell(command) {
  const normalized = command.replace(/\s+/g, " ").trim();
  const forbidden = [
    /\brm\s+(?:-[^\s]*r[^\s]*\s+|--recursive\b)/i,
    /\bgit\s+reset\s+--hard\b/i,
    /\bgit\s+clean(?:\s|$)/i,
    /\bgit\s+checkout\s+--\s+(?:\.|\/|~|\$HOME)(?:\s|$)/i,
    /\bgit\s+restore(?:\s+--\S+)*\s+(?:\.|\/|~|\$HOME)(?:\s|$)/i,
    /\bfind\s+(?:\.|\/|~|\$HOME)\b[^;&|]*\s-delete\b/i,
  ];
  if (forbidden.some((pattern) => pattern.test(normalized)))
    throw new Error(
      "broad destructive shell command is forbidden; use an explicit recoverable operation",
    );
}

function gitAt(root, args, options = {}) {
  return execFileSync("git", args, {
    cwd: root,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  }).trim();
}

function statusPaths(root) {
  const output = execFileSync(
    "git",
    ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    { cwd: root, encoding: "buffer" },
  ).toString("utf8");
  const records = output.split("\0");
  const paths = new Set();
  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    if (!record) continue;
    const status = record.slice(0, 2);
    const candidate = record.slice(3);
    if (candidate) paths.add(candidate);
    if (/[RC]/.test(status) && records[index + 1]) {
      paths.add(records[index + 1]);
      index += 1;
    }
  }
  return paths;
}

function objectHash(root, candidate) {
  try {
    return gitAt(root, ["hash-object", "--no-filters", "--", candidate]);
  } catch {
    return null;
  }
}

function indexFingerprint(root, candidate) {
  try {
    return gitAt(root, ["ls-files", "--stage", "--", candidate]);
  } catch {
    return "";
  }
}

function captureGitState(root) {
  const entries = {};
  for (const candidate of [...statusPaths(root)].sort())
    entries[candidate] = {
      worktree: objectHash(root, candidate),
      index: indexFingerprint(root, candidate),
    };
  return {
    head: gitAt(root, ["rev-parse", "HEAD"]),
    entries,
  };
}

function changedPathsBetween(root, before, after) {
  const changed = new Set();
  for (const candidate of new Set([
    ...Object.keys(before.entries),
    ...Object.keys(after.entries),
  ])) {
    if (
      JSON.stringify(before.entries[candidate] ?? null) !==
      JSON.stringify(after.entries[candidate] ?? null)
    )
      changed.add(candidate);
  }
  if (before.head !== after.head) {
    for (const candidate of gitAt(root, [
      "diff",
      "--name-only",
      "-z",
      before.head,
      after.head,
    ]).split("\0"))
      if (candidate) changed.add(candidate);
  }
  return [...changed].sort();
}

async function shellSnapshotFile(payload, provider, command) {
  const directory = path.join(defaultStateRoot(), "hook-invocations");
  await mkdir(directory, { recursive: true });
  return path.join(
    directory,
    `${invocationId(payload, provider, command)}.json`,
  );
}

async function preShell(
  payload,
  provider,
  claimId,
  fencingToken,
  requiresClaim,
) {
  const command = shellCommand(payload);
  if (!command) throw new Error("shell hook requires an observed command");
  assertNonDestructiveShell(command);
  if (claimId) await validateClaim(claimId, { fencingToken });
  else if (requiresClaim)
    throw new Error(
      "this controlled, parallel or delegated shell requires an active claim",
    );
  const root = await realpath(
    path.resolve(process.env.VFBIZ_HOOK_REPOSITORY_ROOT ?? ROOT),
  );
  const snapshotFile = await shellSnapshotFile(payload, provider, command);
  await writeFile(
    snapshotFile,
    `${JSON.stringify({
      schemaVersion: 1,
      root,
      claimId: claimId ?? null,
      fencingToken: fencingToken ?? null,
      requiresClaim,
      before: captureGitState(root),
    })}\n`,
    { mode: 0o600, flag: "wx" },
  );
}

async function postShell(payload, provider) {
  const command = shellCommand(payload);
  if (!command) throw new Error("shell hook requires an observed command");
  const snapshotFile = await shellSnapshotFile(payload, provider, command);
  let snapshot;
  try {
    snapshot = JSON.parse(await readFile(snapshotFile, "utf8"));
    const root = await realpath(snapshot.root);
    const changed = changedPathsBetween(
      root,
      snapshot.before,
      captureGitState(root),
    );
    if (changed.length === 0) return;
    cheapPathGuard(changed);
    if (!snapshot.claimId)
      throw new Error(
        `shell mutation requires an active claim; observed paths: ${changed.join(", ")}`,
      );
    await validatePaths(snapshot.claimId, changed, {
      fencingToken: snapshot.fencingToken,
    });
  } finally {
    await rm(snapshotFile, { force: true });
  }
}

const phase = process.argv[2];
const provider =
  process.argv[3] ?? (process.env.CODEX_THREAD_ID ? "codex" : "generic");
try {
  const payload = await readInput();
  const claimId = payload.claimId ?? process.env.VFBIZ_CLAIM_ID;
  const fencingToken = payload.fencingToken ?? process.env.VFBIZ_FENCING_TOKEN;
  const requiresClaim =
    payload.requireClaim === true || process.env.VFBIZ_REQUIRE_CLAIM === "1";
  const paths = mutationPaths(payload);

  if (phase === "pre-shell")
    await preShell(payload, provider, claimId, fencingToken, requiresClaim);
  else if (phase === "post-shell") await postShell(payload, provider);
  else if (["pre-write", "post-write", "pre-commit"].includes(phase)) {
    if (paths.length === 0)
      throw new Error(`${phase} requires an observed repository path`);
    cheapPathGuard(paths);
    if (claimId) await validatePaths(claimId, paths, { fencingToken });
    else if (requiresClaim)
      throw new Error(
        "this controlled, parallel or delegated write requires an active claim",
      );
  } else if (claimId) await validateClaim(claimId, { fencingToken });
  else if (requiresClaim && phase !== "pre-compact")
    throw new Error("active claim is required");

  if (provider === "codex") {
    if (phase === "pre-compact")
      process.stdout.write(
        `${JSON.stringify({ systemMessage: "VFBiz: compact only after an atomic checkpoint with observed Git state." })}\n`,
      );
  } else {
    process.stdout.write(
      `${JSON.stringify({ ok: true, phase, decision: phase === "pre-compact" ? "advisory" : "allow", claimed: Boolean(claimId) })}\n`,
    );
  }
} catch (error) {
  const advisory = phase === "pre-compact";
  // Claude Code and Codex both parse `hookSpecificOutput.permissionDecision`
  // as the official structured deny response; only providers that do not
  // understand it fall back to the generic exit-code-2 signal below.
  if (provider === "codex" || provider === "claude") {
    const output = advisory
      ? { systemMessage: `VFBiz checkpoint advisory: ${error.message}` }
      : {
          hookSpecificOutput: {
            hookEventName: phase.startsWith("post")
              ? "PostToolUse"
              : "PreToolUse",
            permissionDecision: "deny",
            permissionDecisionReason: error.message,
          },
        };
    process.stdout.write(`${JSON.stringify(output)}\n`);
  } else {
    process.stdout.write(
      `${JSON.stringify({ ok: advisory, phase, decision: advisory ? "advisory" : "block", code: "VFBIZ_GUARD", message: error.message })}\n`,
    );
    if (!advisory) process.exitCode = 2;
  }
}
