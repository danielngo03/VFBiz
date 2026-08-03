#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { AgentControlStore } from "./lib/agent-control.mjs";
import {
  ControlledApplyError,
  buildTokenCommand,
  contentFreeReceipt,
  createPlanSnapshot,
  digestBytes,
  extractCredentialAuthority,
  parseGcsGenerationUri,
  removePlanSnapshot,
  resolvePlanPath,
  validateContentAddressedGcsUri,
  validateDecisionReceipt,
  validateExecutionState,
  validateGoogleIdentity,
  validateRecoveryReceipt,
  validateSavedPlan,
} from "./lib/gcp-controlled-apply.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MINIMUM_AUTHORITY_REMAINING_MS = 15 * 60 * 1000;
const GIT = "/usr/bin/git";
const GCLOUD = "/opt/homebrew/bin/gcloud";
const TOFU = "/opt/homebrew/bin/tofu";

function reject(code, message) {
  throw new ControlledApplyError(code, message);
}

function parseArguments(argv) {
  const result = { execute: false };
  const accepted = new Set([
    "--claim",
    "--fencing-token",
    "--plan",
    "--decision-uri",
    "--decision-sha256",
    "--principal",
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--execute") {
      result.execute = true;
      continue;
    }
    if (!accepted.has(argument) || !argv[index + 1]?.length)
      reject("ARGUMENT_INVALID", `unknown or incomplete argument: ${argument}`);
    const key = argument
      .slice(2)
      .replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    if (result[key] !== undefined)
      reject("ARGUMENT_DUPLICATE", `duplicate argument: ${argument}`);
    result[key] = argv[index + 1];
    index += 1;
  }
  for (const field of [
    "claim",
    "fencingToken",
    "plan",
    "decisionUri",
    "decisionSha256",
    "principal",
  ])
    if (!result[field])
      reject("ARGUMENT_MISSING", `missing argument: ${field}`);
  const fencingToken = Number(result.fencingToken);
  if (!Number.isSafeInteger(fencingToken) || fencingToken <= 0)
    reject("ARGUMENT_FENCING_INVALID", "fencing token must be positive");
  if (!/^[a-f0-9]{64}$/.test(result.decisionSha256))
    reject("ARGUMENT_DIGEST_INVALID", "decision digest must be SHA-256");
  if (result.execute)
    reject(
      "EXECUTE_BROKER_REQUIRED",
      "local execution is disabled until remote signed authority is available",
    );
  return { ...result, fencingToken };
}

function sanitizedEnvironment() {
  return {
    PATH: "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
    ...Object.fromEntries(
      ["HOME", "CLOUDSDK_CONFIG", "LANG", "LC_ALL", "SSL_CERT_FILE"]
        .filter((key) => process.env[key] !== undefined)
        .map((key) => [key, process.env[key]]),
    ),
  };
}

function runText(file, args, options = {}) {
  try {
    return execFileSync(file, args, {
      cwd: ROOT,
      encoding: "utf8",
      maxBuffer: 16 * 1024 * 1024,
      stdio: ["ignore", "pipe", "pipe"],
      env: sanitizedEnvironment(),
      ...options,
    }).trim();
  } catch {
    reject("SUBPROCESS_FAILED", `${file} preflight failed`);
  }
}

function currentRevision() {
  return runText(GIT, ["rev-parse", "HEAD"]);
}

function assertControlledPathsClean() {
  const output = runText(GIT, [
    "status",
    "--porcelain",
    "--",
    "infra/gcp/database_credential_operator.tf",
    "infra/gcp/tests/database_credential_operator.tftest.hcl",
  ]);
  if (output) reject("WORKTREE_NOT_CLEAN", "controlled IaC paths are dirty");
}

function obtainAccessToken(principal) {
  const command = buildTokenCommand(principal);
  const token = runText(GCLOUD, command.args);
  if (token.length < 32 || /\s/.test(token))
    reject("GOOGLE_TOKEN_INVALID", "gcloud returned an invalid access token");
  return token;
}

async function fetchJson(url, token, code) {
  const response = await fetch(url, {
    headers: { authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok)
    reject(code, `Google preflight failed with ${response.status}`);
  try {
    return await response.json();
  } catch {
    reject(code, "Google preflight returned malformed JSON");
  }
}

async function validateTokenSubject(token, principal) {
  const document = await fetchJson(
    "https://www.googleapis.com/oauth2/v3/userinfo",
    token,
    "GOOGLE_IDENTITY_UNAVAILABLE",
  );
  return validateGoogleIdentity(document, principal);
}

async function fetchPinnedObject(uri, expectedDigest, token, expectedLocation) {
  const object = expectedLocation
    ? validateContentAddressedGcsUri(uri, expectedLocation)
    : parseGcsGenerationUri(uri);
  const url =
    `https://storage.googleapis.com/storage/v1/b/${encodeURIComponent(object.bucket)}` +
    `/o/${encodeURIComponent(object.object)}?alt=media&generation=${object.generation}`;
  const response = await fetch(url, {
    headers: { authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok)
    reject(
      "GCS_OBJECT_FETCH_FAILED",
      `GCS fetch failed with ${response.status}`,
    );
  const bytes = Buffer.from(await response.arrayBuffer());
  if (digestBytes(bytes) !== expectedDigest)
    reject("GCS_OBJECT_DIGEST_MISMATCH", "GCS object digest mismatch");
  return {
    bytes,
    text: bytes.toString("utf8"),
    generation: object.generation,
  };
}

function readSavedPlanJson(plan) {
  const output = runText(TOFU, [
    "-chdir=infra/gcp",
    "show",
    "-json",
    plan.absolute,
  ]);
  try {
    return JSON.parse(output);
  } catch {
    reject("PLAN_JSON_INVALID", "tofu returned malformed plan JSON");
  }
}

function parseAuthorityContext(authority, principal) {
  let document;
  try {
    document = JSON.parse(authority.content);
  } catch {
    reject("PLAN_AUTHORITY_INVALID", "plan authority content is malformed");
  }
  if (
    document.operator_principal !== principal ||
    !Number.isFinite(Date.parse(document.expires_at))
  )
    reject("PLAN_AUTHORITY_INVALID", "plan authority context is invalid");
  return {
    operatorPrincipal: principal,
    authorityExpiresAt: document.expires_at,
    authoritySha256: authority.sha256,
  };
}

async function validateAndMaybeExecute(arguments_, state) {
  const nowMs = Date.now();
  const baseRevision = currentRevision();
  assertControlledPathsClean();
  validateExecutionState(state, {
    nowMs,
    minimumRemainingMs: MINIMUM_AUTHORITY_REMAINING_MS,
    claimId: arguments_.claim,
    fencingToken: arguments_.fencingToken,
    baseRevision,
  });
  const plan = await resolvePlanPath(ROOT, arguments_.plan);
  const snapshot = await createPlanSnapshot(plan.absolute);
  try {
    const planSha256 = snapshot.sha256;
    const planJson = readSavedPlanJson(snapshot);
    const authority = extractCredentialAuthority(planJson);
    const planResult = validateSavedPlan(
      planJson,
      parseAuthorityContext(authority, arguments_.principal),
    );
    const accessToken = obtainAccessToken(arguments_.principal);
    await validateTokenSubject(accessToken, arguments_.principal);
    const decisionObject = await fetchPinnedObject(
      arguments_.decisionUri,
      arguments_.decisionSha256,
      accessToken,
      {
        bucket: "vinfast-503003-evidence-dev",
        prefix: "database-bootstrap/admin-credential/decision/v1",
        sha256: arguments_.decisionSha256,
      },
    );
    const decision = validateDecisionReceipt(decisionObject.text, {
      nowMs,
      planPath: plan.repositoryRelative,
      planSha256,
      baseRevision,
      claimId: arguments_.claim,
      fencingToken: arguments_.fencingToken,
      operatorPrincipal: arguments_.principal,
      authoritySha256: authority.sha256,
      authorityGeneration: authority.generation,
    });
    const recoveryObject = await fetchPinnedObject(
      decision.receipt.recovery_evidence_uri,
      decision.receipt.recovery_evidence_sha256,
      accessToken,
      {
        bucket: "vinfast-503003-evidence-dev",
        prefix: "database-bootstrap/admin-credential/recovery/v1",
        sha256: decision.receipt.recovery_evidence_sha256,
      },
    );
    validateRecoveryReceipt(recoveryObject.text, {
      nowMs,
      baseRevision,
      planSha256,
      claimId: arguments_.claim,
      fencingToken: arguments_.fencingToken,
      operatorPrincipal: arguments_.principal,
      authoritySha256: authority.sha256,
      authorityGeneration: authority.generation,
    });
    validateExecutionState(state, {
      nowMs: Date.now(),
      minimumRemainingMs: MINIMUM_AUTHORITY_REMAINING_MS,
      claimId: arguments_.claim,
      fencingToken: arguments_.fencingToken,
      baseRevision,
    });
    if (decision.window.expiresAt <= nowMs + MINIMUM_AUTHORITY_REMAINING_MS)
      reject(
        "DECISION_TOO_CLOSE_TO_EXPIRY",
        "decision expires before validation deadline",
      );
    if (currentRevision() !== baseRevision)
      reject("REVISION_CHANGED", "Git revision changed during validation");
    assertControlledPathsClean();
    return contentFreeReceipt({
      applied: false,
      claimId: arguments_.claim,
      fencingToken: arguments_.fencingToken,
      planSha256,
      planDisposition: planResult.disposition,
      decisionSha256: arguments_.decisionSha256,
      decisionGeneration: decisionObject.generation,
      operatorPrincipal: arguments_.principal,
      nowMs,
    });
  } finally {
    await removePlanSnapshot(snapshot);
  }
}

async function main() {
  const arguments_ = parseArguments(process.argv.slice(2));
  const commonDirectory = runText(GIT, ["rev-parse", "--git-common-dir"]);
  const store = new AgentControlStore(
    path.resolve(ROOT, commonDirectory, "vfbiz-agent-control"),
  );
  const receipt = await store.withLock((state) =>
    validateAndMaybeExecute(arguments_, state),
  );
  process.stdout.write(`${JSON.stringify({ ok: true, receipt })}\n`);
}

main().catch((error) => {
  const code =
    error instanceof ControlledApplyError ? error.code : "UNEXPECTED";
  process.stderr.write(`${JSON.stringify({ ok: false, code })}\n`);
  process.exitCode = 2;
});
