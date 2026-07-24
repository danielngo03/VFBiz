#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import path from "node:path";
import { ROOT } from "./lib/governance.mjs";
import {
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

  if (["pre-write", "post-write", "pre-commit"].includes(phase)) {
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
  if (provider === "codex") {
    const output = advisory
      ? { systemMessage: `VFBiz checkpoint advisory: ${error.message}` }
      : {
          hookSpecificOutput: {
            hookEventName: "PreToolUse",
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
