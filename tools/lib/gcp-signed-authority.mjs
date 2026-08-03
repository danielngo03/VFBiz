import {
  createHash,
  createPublicKey,
  verify as verifySignature,
} from "node:crypto";

export const MAX_SIGNED_AUTHORITY_BYTES = 64 * 1024;
export const SIGNED_AUTHORITY_ALGORITHM = "EC_SIGN_P256_SHA256";

const SHA256 = /^[a-f0-9]{64}$/;
const FULL_REVISION = /^[a-f0-9]{40}$/;
const GENERATION = /^[1-9][0-9]*$/;
const KMS_KEY_VERSION =
  /^projects\/vinfast-503003\/locations\/asia-southeast1\/keyRings\/[a-zA-Z0-9_-]{1,63}\/cryptoKeys\/[a-zA-Z0-9_-]{1,63}\/cryptoKeyVersions\/[1-9][0-9]*$/;
const BASE64 = /^[A-Za-z0-9+/]+={0,2}$/;
const SERVICE_ACCOUNT =
  /^[a-z][a-z0-9-]{4,29}@[a-z][a-z0-9-]{4,29}\.iam\.gserviceaccount\.com$/;
const IDENTIFIER = /^[a-zA-Z0-9._:/-]{8,256}$/;
const CANONICAL_TIMESTAMP =
  /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{3})?Z$/;
const ENVELOPE_KEYS = new Set([
  "payload",
  "payload_sha256",
  "schema_version",
  "signature",
]);
const SIGNATURE_KEYS = new Set([
  "algorithm",
  "issuer_service_account",
  "kms_key_version",
  "value_base64",
]);
const PAYLOAD_KEYS = new Set([
  "action",
  "approval_event_id",
  "approval_event_occurred_at",
  "approval_event_revision",
  "approval_event_schema_sha256",
  "approval_evidence_sha256",
  "approver_role",
  "approver_subject_sha256",
  "authority_class",
  "base_revision",
  "broker_service_account",
  "claim_snapshot_sha256",
  "claim_expires_at",
  "claim_fencing_token",
  "claim_id",
  "capability_policy_revision_sha256",
  "credential_authority_generation",
  "credential_authority_sha256",
  "decision",
  "decision_id",
  "environment",
  "evidence_class",
  "executor_image",
  "executor_service_account",
  "expires_at",
  "issued_at",
  "kind",
  "nonce",
  "plan_semantic_sha256",
  "plan_sha256",
  "plan_uri",
  "project_id",
  "project_number",
  "recovery_protocol_sha256",
  "required_capability",
  "region",
  "requester_subject_sha256",
  "safe_to_retry",
  "schema_version",
  "subject_hash_profile",
  "target_work_item_id",
  "work_item_id",
  "workforce_issuer_sha256",
  "workforce_tenant_sha256",
]);
const VERIFIED_PROJECTION_DOCUMENT_KEYS = new Set([
  "profile",
  "projection",
  "projection_sha256",
  "schema_version",
]);
const VERIFIED_PROJECTION_KEYS = new Set([
  "action",
  "aggregate_authority_complete",
  "approval_event_verified",
  "claimed_approval_event_id",
  "claimed_approval_event_occurred_at",
  "claimed_approval_event_revision",
  "claimed_approval_event_schema_sha256",
  "claimed_approver_subject_sha256",
  "authority_work_item_id",
  "base_revision",
  "broker_service_account",
  "cancellation_authority_verified",
  "claim_snapshot_sha256",
  "claimed_claim_expires_at",
  "claimed_claim_fencing_token",
  "claimed_claim_id",
  "claimed_capability_policy_revision_sha256",
  "claimed_approval_evidence_sha256",
  "claimed_approver_role",
  "claimed_authority_class",
  "credential_authority_generation",
  "credential_authority_sha256",
  "signed_payload_decision_id",
  "dispatch_eligible",
  "envelope_sha256",
  "environment",
  "executor_image",
  "executor_service_account",
  "expires_at",
  "issued_at",
  "kind",
  "nonce",
  "pairing_sha256",
  "payload_sha256",
  "plan_semantic_sha256",
  "plan_sha256",
  "plan_uri",
  "project_id",
  "project_number",
  "recovery_protocol_sha256",
  "region",
  "claimed_approver_required_capability",
  "claimed_requester_subject_sha256",
  "safe_to_retry",
  "schema_version",
  "signed_payload_disposition",
  "signed_payload_evidence_class",
  "signer_algorithm",
  "signer_issuer_service_account",
  "signer_key_state",
  "signer_kms_key_version",
  "signer_public_key_sha256",
  "source_semantics_verified",
  "source_signature_verified",
  "source_envelope_uri",
  "source_verifier_revision_sha256",
  "subject_hash_profile",
  "target_work_item_id",
  "workforce_capability_verified",
  "workforce_subject_verified",
  "claimed_workforce_issuer_sha256",
  "claimed_workforce_tenant_sha256",
]);
const INCOMPLETE_AUTHORITY_FLAGS = [
  "aggregate_authority_complete",
  "approval_event_verified",
  "cancellation_authority_verified",
  "dispatch_eligible",
  "workforce_capability_verified",
  "workforce_subject_verified",
];

export class SignedAuthorityError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "SignedAuthorityError";
    this.code = code;
  }
}

function reject(code, message) {
  throw new SignedAuthorityError(code, message);
}

function matchesString(pattern, value) {
  return typeof value === "string" && pattern.test(value);
}

function exactKeys(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const observed = Object.keys(value);
  return (
    observed.length === expected.size &&
    observed.every((key) => expected.has(key))
  );
}

export function canonicalAuthorityJson(value, depth = 0) {
  if (depth > 32)
    reject("AUTHORITY_DEPTH_INVALID", "authority JSON nesting is too deep");
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value))
      reject("CANONICAL_NUMBER_INVALID", "non-finite number is forbidden");
    return JSON.stringify(Object.is(value, -0) ? 0 : value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value))
    return `[${value
      .map((entry) => canonicalAuthorityJson(entry, depth + 1))
      .join(",")}]`;
  if (typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}:${canonicalAuthorityJson(value[key], depth + 1)}`,
      )
      .join(",")}}`;
  }
  reject("CANONICAL_TYPE_INVALID", `unsupported JSON type: ${typeof value}`);
}

function jsonParser(text) {
  let offset = 0;
  const fail = (message) => reject("AUTHORITY_JSON_INVALID", message);
  const whitespace = () => {
    while (/\s/.test(text[offset] ?? "")) offset += 1;
  };
  const string = () => {
    if (text[offset] !== '"') fail("expected JSON string");
    const start = offset;
    offset += 1;
    while (offset < text.length) {
      const character = text[offset];
      if (character === '"') {
        offset += 1;
        try {
          return JSON.parse(text.slice(start, offset));
        } catch {
          fail("invalid JSON string");
        }
      }
      if (character === "\\") {
        offset += 2;
        continue;
      }
      if (character.charCodeAt(0) < 0x20) fail("control character in string");
      offset += 1;
    }
    fail("unterminated JSON string");
  };
  const number = () => {
    const match = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(
      text.slice(offset),
    );
    if (!match) fail("invalid JSON number");
    offset += match[0].length;
    const value = Number(match[0]);
    if (!Number.isFinite(value)) fail("non-finite JSON number");
    return value;
  };
  const value = (depth = 0) => {
    if (depth > 32)
      reject("AUTHORITY_DEPTH_INVALID", "authority JSON nesting is too deep");
    whitespace();
    if (text[offset] === '"') return string();
    if (text[offset] === "{") return object(depth + 1);
    if (text[offset] === "[") return array(depth + 1);
    for (const [token, parsed] of [
      ["true", true],
      ["false", false],
      ["null", null],
    ]) {
      if (text.startsWith(token, offset)) {
        offset += token.length;
        return parsed;
      }
    }
    return number();
  };
  const array = (depth) => {
    const result = [];
    offset += 1;
    whitespace();
    if (text[offset] === "]") {
      offset += 1;
      return result;
    }
    while (offset < text.length) {
      result.push(value(depth));
      whitespace();
      if (text[offset] === "]") {
        offset += 1;
        return result;
      }
      if (text[offset] !== ",") fail("expected array delimiter");
      offset += 1;
    }
    fail("unterminated JSON array");
  };
  const object = (depth) => {
    const result = {};
    const keys = new Set();
    offset += 1;
    whitespace();
    if (text[offset] === "}") {
      offset += 1;
      return result;
    }
    while (offset < text.length) {
      whitespace();
      const key = string();
      if (keys.has(key))
        reject("AUTHORITY_DUPLICATE_KEY", `duplicate JSON key: ${key}`);
      keys.add(key);
      whitespace();
      if (text[offset] !== ":") fail("expected object separator");
      offset += 1;
      result[key] = value(depth);
      whitespace();
      if (text[offset] === "}") {
        offset += 1;
        return result;
      }
      if (text[offset] !== ",") fail("expected object delimiter");
      offset += 1;
    }
    fail("unterminated JSON object");
  };
  const parsed = value();
  whitespace();
  if (offset !== text.length) fail("trailing JSON content");
  return parsed;
}

export function parseSignedAuthority(bytes) {
  const encoded = Buffer.isBuffer(bytes) ? bytes : Buffer.from(bytes);
  if (encoded.length === 0 || encoded.length > MAX_SIGNED_AUTHORITY_BYTES)
    reject("AUTHORITY_SIZE_INVALID", "authority envelope exceeds byte policy");
  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(encoded);
  } catch {
    reject("AUTHORITY_ENCODING_INVALID", "authority envelope is not UTF-8");
  }
  const envelope = jsonParser(text);
  if (canonicalAuthorityJson(envelope) !== text)
    reject(
      "AUTHORITY_NOT_CANONICAL",
      "authority envelope is not canonical JSON",
    );
  return envelope;
}

function assertDigest(value, field) {
  if (typeof value !== "string" || !SHA256.test(value))
    reject("AUTHORITY_DIGEST_INVALID", `${field} is not a SHA-256 digest`);
}

function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}

function publicKeyDigest(publicKey) {
  return createHash("sha256")
    .update(publicKey.export({ type: "spki", format: "der" }))
    .digest("hex");
}

function signingProjection(envelope) {
  return {
    algorithm: envelope.signature.algorithm,
    issuer_service_account: envelope.signature.issuer_service_account,
    kms_key_version: envelope.signature.kms_key_version,
    payload: envelope.payload,
    payload_sha256: envelope.payload_sha256,
    schema_version: envelope.schema_version,
  };
}

export function canonicalAuthorityPairProjection(payload) {
  return {
    base_revision: payload.base_revision,
    broker_service_account: payload.broker_service_account,
    claim_snapshot_sha256: payload.claim_snapshot_sha256,
    claim_id: payload.claim_id,
    claim_fencing_token: payload.claim_fencing_token,
    credential_authority_generation: payload.credential_authority_generation,
    credential_authority_sha256: payload.credential_authority_sha256,
    environment: payload.environment,
    executor_image: payload.executor_image,
    executor_service_account: payload.executor_service_account,
    nonce: payload.nonce,
    plan_semantic_sha256: payload.plan_semantic_sha256,
    plan_sha256: payload.plan_sha256,
    plan_uri: payload.plan_uri,
    project_id: payload.project_id,
    project_number: payload.project_number,
    recovery_protocol_sha256: payload.recovery_protocol_sha256,
    region: payload.region,
    requester_subject_sha256: payload.requester_subject_sha256,
    schema_version: 1,
    work_item_id: payload.work_item_id,
  };
}

function assertEnvelopeShape(envelope) {
  if (!exactKeys(envelope, ENVELOPE_KEYS) || envelope.schema_version !== 1)
    reject("AUTHORITY_SHAPE_INVALID", "authority envelope shape is invalid");
  if (!exactKeys(envelope.signature, SIGNATURE_KEYS))
    reject("AUTHORITY_SIGNATURE_SHAPE_INVALID", "signature shape is invalid");
  if (!exactKeys(envelope.payload, PAYLOAD_KEYS))
    reject("AUTHORITY_PAYLOAD_SHAPE_INVALID", "payload shape is invalid");
  if (envelope.payload.schema_version !== 1)
    reject("AUTHORITY_PAYLOAD_VERSION_INVALID", "payload version is invalid");
}

function assertTarget(payload, context) {
  const expected = [
    [payload.work_item_id, "VFBIZ-0220"],
    [payload.project_id, "vinfast-503003"],
    [payload.project_number, "81588547131"],
    [payload.region, "asia-southeast1"],
    [payload.broker_service_account, context.expectedBrokerServiceAccount],
    [payload.executor_service_account, context.expectedExecutorServiceAccount],
  ];
  if (expected.some(([actual, wanted]) => actual !== wanted))
    reject("AUTHORITY_TARGET_MISMATCH", "authority target is invalid");
  if (!matchesString(FULL_REVISION, payload.base_revision))
    reject("AUTHORITY_REVISION_INVALID", "base revision must be full SHA-1");
  if (
    typeof payload.credential_authority_generation !== "string" ||
    !GENERATION.test(payload.credential_authority_generation)
  )
    reject("AUTHORITY_GENERATION_INVALID", "authority generation is invalid");
  if (!matchesString(SERVICE_ACCOUNT, payload.broker_service_account))
    reject("AUTHORITY_BROKER_INVALID", "broker identity is invalid");
  if (!matchesString(SERVICE_ACCOUNT, payload.executor_service_account))
    reject("AUTHORITY_EXECUTOR_INVALID", "executor identity is invalid");
  if (payload.broker_service_account === payload.executor_service_account)
    reject("AUTHORITY_DUTY_CONFLICT", "broker and executor must differ");
}

function assertDecision(payload) {
  if (!matchesString(IDENTIFIER, payload.decision_id))
    reject("AUTHORITY_DECISION_ID_INVALID", "decision id is invalid");
  if (payload.requester_subject_sha256 === payload.approver_subject_sha256)
    reject("AUTHORITY_DUTY_CONFLICT", "requester and approver must differ");
  if (payload.safe_to_retry !== false)
    reject(
      "AUTHORITY_RETRY_POLICY_INVALID",
      "recovery must remain fail-closed",
    );
  if (payload.kind === "apply-decision") {
    if (
      payload.target_work_item_id !== "VFBIZ-0218" ||
      payload.action !== "apply-vfbiz-0217-database-credential-authority" ||
      payload.approver_role !== "release-owner" ||
      payload.required_capability !== "authorization.approval.approve" ||
      !["review-pending", "authorized", "rejected"].includes(payload.decision)
    )
      reject("AUTHORITY_DECISION_INVALID", "apply decision is invalid");
  } else if (payload.kind === "recovery-protocol") {
    if (
      payload.target_work_item_id !== "VFBIZ-0216" ||
      payload.action !== "accept-vfbiz-0216-recovery-protocol" ||
      payload.approver_role !== "security-owner" ||
      payload.required_capability !== "authorization.approval.approve" ||
      !["review-pending", "protocol-accepted", "rejected"].includes(
        payload.decision,
      )
    )
      reject("AUTHORITY_DECISION_INVALID", "recovery decision is invalid");
  } else reject("AUTHORITY_KIND_INVALID", "authority kind is invalid");
  if (payload.evidence_class === "synthetic-test-only") {
    if (
      payload.environment !== "test" ||
      payload.authority_class !== "synthetic-test-only" ||
      payload.decision !== "review-pending"
    )
      reject("AUTHORITY_SYNTHETIC_INVALID", "synthetic evidence is not inert");
  } else if (
    payload.evidence_class !== "human-issued" ||
    !["development", "staging"].includes(payload.environment) ||
    payload.authority_class !== "named-human-workforce-approval"
  )
    reject("AUTHORITY_CLASS_INVALID", "human authority class is invalid");
}

function assertDigestsAndUris(payload) {
  for (const field of [
    "approval_evidence_sha256",
    "approval_event_schema_sha256",
    "approver_subject_sha256",
    "claim_snapshot_sha256",
    "capability_policy_revision_sha256",
    "credential_authority_sha256",
    "nonce",
    "plan_semantic_sha256",
    "plan_sha256",
    "recovery_protocol_sha256",
    "requester_subject_sha256",
    "workforce_issuer_sha256",
    "workforce_tenant_sha256",
  ])
    assertDigest(payload[field], field);
  const planPattern = new RegExp(
    `^gs://vinfast-503003-evidence-dev/controlled-apply/plans/v1/${payload.plan_sha256}\\.tfplan#[1-9][0-9]*$`,
  );
  if (!matchesString(planPattern, payload.plan_uri))
    reject("AUTHORITY_PLAN_URI_INVALID", "plan URI is not content-addressed");
  const imagePattern =
    /^asia-southeast1-docker\.pkg\.dev\/vinfast-503003\/[a-z0-9._/-]+@sha256:[a-f0-9]{64}$/;
  if (!matchesString(imagePattern, payload.executor_image))
    reject("AUTHORITY_IMAGE_INVALID", "executor image is not digest-pinned");
  if (
    !matchesString(IDENTIFIER, payload.claim_id) ||
    !matchesString(GENERATION, payload.claim_fencing_token) ||
    !matchesString(IDENTIFIER, payload.approval_event_id) ||
    !matchesString(GENERATION, payload.approval_event_revision) ||
    payload.subject_hash_profile !== "oidc-issuer-sub-v1"
  )
    reject("AUTHORITY_JOIN_KEY_INVALID", "authority join keys are invalid");
}

function assertWindow(payload, context) {
  const parseTimestamp = (value) => {
    if (!matchesString(CANONICAL_TIMESTAMP, value))
      reject(
        "AUTHORITY_TIMESTAMP_INVALID",
        "authority timestamp is not canonical RFC3339 UTC",
      );
    const parsed = Date.parse(value);
    if (!Number.isFinite(parsed))
      reject("AUTHORITY_TIMESTAMP_INVALID", "authority timestamp is invalid");
    const normalized = value.includes(".")
      ? new Date(parsed).toISOString()
      : new Date(parsed).toISOString().replace(".000Z", "Z");
    if (normalized !== value)
      reject("AUTHORITY_TIMESTAMP_INVALID", "authority timestamp is invalid");
    return parsed;
  };
  const issuedAt = parseTimestamp(payload.issued_at);
  const expiresAt = parseTimestamp(payload.expires_at);
  const claimExpiresAt = parseTimestamp(payload.claim_expires_at);
  const approvalOccurredAt = parseTimestamp(payload.approval_event_occurred_at);
  const nowMs = Object.hasOwn(context, "nowMs") ? context.nowMs : Date.now();
  if (!Number.isSafeInteger(nowMs) || nowMs < 0)
    reject("AUTHORITY_VERIFICATION_TIME_INVALID", "verification time is invalid");
  const configuredMaximumWindowMs = Object.hasOwn(context, "maximumWindowMs")
    ? context.maximumWindowMs
    : 15 * 60_000;
  if (
    !Number.isSafeInteger(configuredMaximumWindowMs) ||
    configuredMaximumWindowMs <= 0
  )
    reject("AUTHORITY_WINDOW_CONFIG_INVALID", "maximum authority window is invalid");
  const maximumWindowMs = Math.min(configuredMaximumWindowMs, 4 * 60 * 60_000);
  if (
    issuedAt > nowMs ||
    expiresAt <= nowMs ||
    expiresAt <= issuedAt ||
    claimExpiresAt < expiresAt ||
    approvalOccurredAt > issuedAt ||
    expiresAt - issuedAt > maximumWindowMs
  )
    reject("AUTHORITY_WINDOW_INVALID", "authority window is invalid");
  return { issuedAt, expiresAt };
}

function decodeCanonicalBase64(value) {
  if (typeof value !== "string" || value.length > 256 || !BASE64.test(value))
    reject("AUTHORITY_SIGNATURE_ENCODING_INVALID", "signature is not base64");
  const decoded = Buffer.from(value, "base64");
  if (decoded.length === 0 || decoded.toString("base64") !== value)
    reject(
      "AUTHORITY_SIGNATURE_ENCODING_INVALID",
      "signature is not canonical",
    );
  return decoded;
}

function trustedSigner(signature, context) {
  if (signature.algorithm !== SIGNED_AUTHORITY_ALGORITHM)
    reject("AUTHORITY_ALGORITHM_INVALID", "signature algorithm is invalid");
  if (!matchesString(KMS_KEY_VERSION, signature.kms_key_version))
    reject("AUTHORITY_KMS_KEY_INVALID", "KMS key version is invalid");
  const trusted = context.trustedKmsKeyVersions?.get(signature.kms_key_version);
  if (
    !trusted ||
    trusted.issuerServiceAccount !== signature.issuer_service_account ||
    trusted.algorithm !== SIGNED_AUTHORITY_ALGORITHM ||
    trusted.state !== "ENABLED" ||
    !matchesString(SHA256, trusted.publicKeySha256) ||
    !matchesString(SERVICE_ACCOUNT, signature.issuer_service_account)
  )
    reject("AUTHORITY_ISSUER_UNTRUSTED", "authority issuer is not trusted");
  if (
    [
      context.expectedBrokerServiceAccount,
      context.expectedExecutorServiceAccount,
    ].includes(signature.issuer_service_account)
  )
    reject("AUTHORITY_DUTY_CONFLICT", "issuer cannot be broker or executor");
  let publicKey;
  try {
    publicKey =
      trusted.publicKeyPem?.type === "public"
        ? trusted.publicKeyPem
        : createPublicKey(trusted.publicKeyPem);
  } catch {
    reject("AUTHORITY_PUBLIC_KEY_INVALID", "trusted public key is invalid");
  }
  if (
    publicKey.asymmetricKeyType !== "ec" ||
    publicKey.asymmetricKeyDetails?.namedCurve !== "prime256v1"
  )
    reject(
      "AUTHORITY_KEY_ALGORITHM_MISMATCH",
      "trusted public key is not ECDSA P-256",
    );
  if (publicKeyDigest(publicKey) !== trusted.publicKeySha256)
    reject(
      "AUTHORITY_PUBLIC_KEY_DIGEST_MISMATCH",
      "trusted public key digest is invalid",
    );
  return publicKey;
}

export function verifySignedAuthority(bytes, context) {
  const envelope = parseSignedAuthority(bytes);
  assertEnvelopeShape(envelope);
  const payloadJson = canonicalAuthorityJson(envelope.payload);
  assertDigest(envelope.payload_sha256, "payload_sha256");
  if (digest(payloadJson) !== envelope.payload_sha256)
    reject("AUTHORITY_PAYLOAD_DIGEST_MISMATCH", "payload digest mismatch");
  assertTarget(envelope.payload, context);
  assertDecision(envelope.payload);
  assertDigestsAndUris(envelope.payload);
  const window = assertWindow(envelope.payload, context);
  const publicKey = trustedSigner(envelope.signature, context);
  const signature = decodeCanonicalBase64(envelope.signature.value_base64);
  let signatureValid = false;
  try {
    signatureValid = verifySignature(
      "sha256",
      Buffer.from(canonicalAuthorityJson(signingProjection(envelope))),
      publicKey,
      signature,
    );
  } catch {
    signatureValid = false;
  }
  if (!signatureValid)
    reject("AUTHORITY_SIGNATURE_INVALID", "authority signature is invalid");
  return {
    envelope,
    window,
    signatureValid: true,
    semanticValid: true,
    kind: envelope.payload.kind,
    disposition: envelope.payload.decision,
    dispatchEligible: false,
  };
}

export function verifyAndProjectSignedAuthority(bytes, context) {
  const nowMs = context.nowMs ?? Date.now();
  if (!Number.isSafeInteger(nowMs) || nowMs < 0)
    reject(
      "AUTHORITY_VERIFICATION_TIME_INVALID",
      "verification time is invalid",
    );
  assertDigest(
    context.expectedVerifierRevisionSha256,
    "expectedVerifierRevisionSha256",
  );
  assertDigest(context.verifierRevisionSha256, "verifierRevisionSha256");
  if (context.verifierRevisionSha256 !== context.expectedVerifierRevisionSha256)
    reject(
      "AUTHORITY_VERIFIER_REVISION_MISMATCH",
      "verifier revision is not the expected deployment revision",
    );
  const verified = verifySignedAuthority(bytes, { ...context, nowMs });
  if (verified.dispatchEligible !== false)
    reject(
      "AUTHORITY_PROJECTION_DISPATCH_INVALID",
      "verified envelope cannot authorize dispatch",
    );
  const envelope = verified.envelope;
  const payload = envelope.payload;
  const envelopeSha256 = digest(canonicalAuthorityJson(envelope));
  const sourceEnvelopePattern = new RegExp(
    `^gs://vinfast-503003-evidence-dev/controlled-apply/authority-envelopes/v1/${envelopeSha256}\\.json#[1-9][0-9]*$`,
  );
  if (!matchesString(sourceEnvelopePattern, context.sourceEnvelopeUri))
    reject(
      "AUTHORITY_SOURCE_LOCATOR_INVALID",
      "source envelope locator must bind exact digest and generation",
    );
  const trusted = context.trustedKmsKeyVersions.get(
    envelope.signature.kms_key_version,
  );
  const projection = {
    action: payload.action,
    aggregate_authority_complete: false,
    approval_event_verified: false,
    claimed_approval_event_id: payload.approval_event_id,
    claimed_approval_event_occurred_at: payload.approval_event_occurred_at,
    claimed_approval_event_revision: payload.approval_event_revision,
    claimed_approval_event_schema_sha256: payload.approval_event_schema_sha256,
    claimed_approval_evidence_sha256: payload.approval_evidence_sha256,
    claimed_approver_role: payload.approver_role,
    claimed_approver_subject_sha256: payload.approver_subject_sha256,
    base_revision: payload.base_revision,
    broker_service_account: payload.broker_service_account,
    cancellation_authority_verified: false,
    claim_snapshot_sha256: payload.claim_snapshot_sha256,
    claimed_claim_expires_at: payload.claim_expires_at,
    claimed_claim_fencing_token: payload.claim_fencing_token,
    claimed_claim_id: payload.claim_id,
    claimed_capability_policy_revision_sha256:
      payload.capability_policy_revision_sha256,
    claimed_authority_class: payload.authority_class,
    credential_authority_generation: payload.credential_authority_generation,
    credential_authority_sha256: payload.credential_authority_sha256,
    signed_payload_decision_id: payload.decision_id,
    dispatch_eligible: false,
    signed_payload_disposition: verified.disposition,
    envelope_sha256: envelopeSha256,
    environment: payload.environment,
    signed_payload_evidence_class: payload.evidence_class,
    executor_image: payload.executor_image,
    executor_service_account: payload.executor_service_account,
    expires_at: payload.expires_at,
    issued_at: payload.issued_at,
    kind: verified.kind,
    nonce: payload.nonce,
    pairing_sha256: digest(
      canonicalAuthorityJson(canonicalAuthorityPairProjection(payload)),
    ),
    payload_sha256: envelope.payload_sha256,
    plan_semantic_sha256: payload.plan_semantic_sha256,
    plan_sha256: payload.plan_sha256,
    plan_uri: payload.plan_uri,
    project_id: payload.project_id,
    project_number: payload.project_number,
    recovery_protocol_sha256: payload.recovery_protocol_sha256,
    region: payload.region,
    claimed_approver_required_capability: payload.required_capability,
    claimed_requester_subject_sha256: payload.requester_subject_sha256,
    safe_to_retry: false,
    schema_version: 1,
    source_semantics_verified: true,
    signer_algorithm: envelope.signature.algorithm,
    signer_issuer_service_account: envelope.signature.issuer_service_account,
    signer_key_state: trusted.state,
    signer_kms_key_version: envelope.signature.kms_key_version,
    signer_public_key_sha256: trusted.publicKeySha256,
    target_work_item_id: payload.target_work_item_id,
    source_envelope_uri: context.sourceEnvelopeUri,
    source_verifier_revision_sha256: context.verifierRevisionSha256,
    subject_hash_profile: payload.subject_hash_profile,
    source_signature_verified: true,
    workforce_capability_verified: false,
    workforce_subject_verified: false,
    claimed_workforce_issuer_sha256: payload.workforce_issuer_sha256,
    claimed_workforce_tenant_sha256: payload.workforce_tenant_sha256,
    authority_work_item_id: payload.work_item_id,
  };
  const document = {
    profile: "gcp-controlled-apply-verified-envelope/v1",
    projection,
    projection_sha256: digest(canonicalAuthorityJson(projection)),
    schema_version: 1,
  };
  assertNormalizedAuthorityProjectionShape(document);
  return structuredClone(document);
}

function assertNormalizedAuthorityProjectionShape(document) {
  if (
    !exactKeys(document, VERIFIED_PROJECTION_DOCUMENT_KEYS) ||
    document.schema_version !== 1 ||
    document.profile !== "gcp-controlled-apply-verified-envelope/v1" ||
    !exactKeys(document.projection, VERIFIED_PROJECTION_KEYS)
  )
    reject(
      "AUTHORITY_PROJECTION_INVALID",
      "verified authority projection shape is invalid",
    );
  assertDigest(document.projection_sha256, "projection_sha256");
  if (
    digest(canonicalAuthorityJson(document.projection)) !==
    document.projection_sha256
  )
    reject(
      "AUTHORITY_PROJECTION_DIGEST_MISMATCH",
      "verified authority projection digest mismatches",
    );
  if (
    document.projection.source_signature_verified !== true ||
    document.projection.source_semantics_verified !== true ||
    INCOMPLETE_AUTHORITY_FLAGS.some(
      (field) => document.projection[field] !== false,
    )
  )
    reject(
      "AUTHORITY_PROJECTION_WIDENED",
      "verified envelope projection cannot claim aggregate authority",
    );
}

export function verifyNormalizedAuthorityProjection(document, context) {
  if (!context?.sourceEnvelopeBytes)
    reject(
      "AUTHORITY_PROJECTION_SOURCE_REQUIRED",
      "detached normalized projections are not trusted evidence",
    );
  const expected = verifyAndProjectSignedAuthority(
    context.sourceEnvelopeBytes,
    context,
  );
  assertNormalizedAuthorityProjectionShape(document);
  if (canonicalAuthorityJson(document) !== canonicalAuthorityJson(expected))
    reject(
      "AUTHORITY_PROJECTION_SOURCE_MISMATCH",
      "normalized projection does not match the reverified signed envelope",
    );
  return structuredClone(document);
}
