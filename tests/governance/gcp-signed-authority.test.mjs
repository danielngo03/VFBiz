import assert from "node:assert/strict";
import {
  createHash,
  generateKeyPairSync,
  sign as createSignature,
} from "node:crypto";
import test from "node:test";
import {
  MAX_SIGNED_AUTHORITY_BYTES,
  SignedAuthorityError,
  canonicalAuthorityJson,
  parseSignedAuthority,
  verifyAndProjectSignedAuthority,
  verifyNormalizedAuthorityProjection,
  verifySignedAuthority,
} from "../../tools/lib/gcp-signed-authority.mjs";

const NOW = Date.parse("2026-08-02T06:10:00Z");
const KMS_KEY =
  "projects/vinfast-503003/locations/asia-southeast1/keyRings/" +
  "vfbiz-controlled-apply-dev/cryptoKeys/release-authority/cryptoKeyVersions/1";
const ISSUER = "vfbiz-apply-issuer@vinfast-503003.iam.gserviceaccount.com";
const BROKER = "vfbiz-apply-broker@vinfast-503003.iam.gserviceaccount.com";
const EXECUTOR = "vfbiz-apply-executor@vinfast-503003.iam.gserviceaccount.com";
const PLAN_SHA = "5".repeat(64);
const { privateKey, publicKey } = generateKeyPairSync("ec", {
  namedCurve: "prime256v1",
});
const publicKeyPem = publicKey.export({ type: "spki", format: "pem" });

function digest(value) {
  return Promise.resolve(createHash("sha256").update(value).digest("hex"));
}

function keyDigest(key) {
  return createHash("sha256")
    .update(key.export({ type: "spki", format: "der" }))
    .digest("hex");
}

function payload(overrides = {}) {
  return {
    schema_version: 1,
    kind: "apply-decision",
    evidence_class: "human-issued",
    environment: "development",
    work_item_id: "VFBIZ-0220",
    target_work_item_id: "VFBIZ-0218",
    action: "apply-vfbiz-0217-database-credential-authority",
    approval_event_id: "approval/VFBIZ-0220/test-runtime-only",
    approval_event_occurred_at: new Date(NOW - 2 * 60_000).toISOString(),
    approval_event_revision: "1",
    approval_event_schema_sha256: "d".repeat(64),
    decision_id: "decision/VFBIZ-0220/test-runtime-only",
    decision: "authorized",
    authority_class: "named-human-workforce-approval",
    approver_role: "release-owner",
    requester_subject_sha256: "1".repeat(64),
    approver_subject_sha256: "2".repeat(64),
    approval_evidence_sha256: "3".repeat(64),
    project_id: "vinfast-503003",
    project_number: "81588547131",
    region: "asia-southeast1",
    base_revision: "4".repeat(40),
    plan_uri:
      `gs://vinfast-503003-evidence-dev/controlled-apply/plans/v1/` +
      `${PLAN_SHA}.tfplan#6`,
    plan_sha256: PLAN_SHA,
    plan_semantic_sha256: "6".repeat(64),
    claim_snapshot_sha256: "7".repeat(64),
    claim_id: "claim/VFBIZ-0220/test-runtime-only",
    claim_fencing_token: "11",
    claim_expires_at: new Date(NOW + 20 * 60_000).toISOString(),
    subject_hash_profile: "oidc-issuer-sub-v1",
    workforce_issuer_sha256: "e".repeat(64),
    workforce_tenant_sha256: "0".repeat(64),
    required_capability: "authorization.approval.approve",
    capability_policy_revision_sha256: "9".repeat(64),
    credential_authority_sha256: "8".repeat(64),
    credential_authority_generation: "9",
    recovery_protocol_sha256: "a".repeat(64),
    broker_service_account: BROKER,
    executor_service_account: EXECUTOR,
    executor_image:
      "asia-southeast1-docker.pkg.dev/vinfast-503003/vfbiz-ai-workers-dev/" +
      `controlled-apply@sha256:${"b".repeat(64)}`,
    nonce: "c".repeat(64),
    safe_to_retry: false,
    issued_at: new Date(NOW - 60_000).toISOString(),
    expires_at: new Date(NOW + 10 * 60_000).toISOString(),
    ...overrides,
  };
}

async function envelope(overrides = {}, signatureOverrides = {}) {
  const authorityPayload = payload(overrides);
  const payloadJson = canonicalAuthorityJson(authorityPayload);
  const payloadSha256 = await digest(payloadJson);
  const signatureMetadata = {
    algorithm: "EC_SIGN_P256_SHA256",
    kms_key_version: KMS_KEY,
    issuer_service_account: ISSUER,
    ...signatureOverrides,
  };
  const signature = createSignature(
    "sha256",
    Buffer.from(
      canonicalAuthorityJson({
        algorithm: signatureMetadata.algorithm,
        issuer_service_account: signatureMetadata.issuer_service_account,
        kms_key_version: signatureMetadata.kms_key_version,
        payload: authorityPayload,
        payload_sha256: payloadSha256,
        schema_version: 1,
      }),
    ),
    privateKey,
  ).toString("base64");
  const document = {
    schema_version: 1,
    payload: authorityPayload,
    payload_sha256: payloadSha256,
    signature: {
      ...signatureMetadata,
      value_base64: signature,
    },
  };
  return canonicalAuthorityJson(document);
}

function context(overrides = {}) {
  const sourceEnvelopeBytes = overrides.sourceEnvelopeBytes;
  const sourceEnvelopeSha256 = sourceEnvelopeBytes
    ? createHash("sha256").update(sourceEnvelopeBytes).digest("hex")
    : null;
  return {
    nowMs: NOW,
    expectedBrokerServiceAccount: BROKER,
    expectedExecutorServiceAccount: EXECUTOR,
    trustedKmsKeyVersions: new Map([
      [
        KMS_KEY,
        {
          algorithm: "EC_SIGN_P256_SHA256",
          issuerServiceAccount: ISSUER,
          publicKeyPem,
          publicKeySha256: keyDigest(publicKey),
          state: "ENABLED",
        },
      ],
    ]),
    verifierRevisionSha256: "f".repeat(64),
    expectedVerifierRevisionSha256: "f".repeat(64),
    sourceEnvelopeUri: sourceEnvelopeSha256
      ? `gs://vinfast-503003-evidence-dev/controlled-apply/authority-envelopes/v1/${sourceEnvelopeSha256}.json#1`
      : undefined,
    ...overrides,
  };
}

async function expectCode(operation, code) {
  await assert.rejects(operation, (error) => {
    assert.ok(error instanceof SignedAuthorityError);
    assert.equal(error.code, code);
    return true;
  });
}

test("trusted signed decision verifies but dispatch stays off by default", async () => {
  const bytes = await envelope();
  const inert = verifySignedAuthority(bytes, context());
  assert.equal(inert.signatureValid, true);
  assert.equal(inert.semanticValid, true);
  assert.equal(inert.disposition, "authorized");
  assert.equal(inert.dispatchEligible, false);
  const enabled = verifySignedAuthority(
    bytes,
    context({ allowDispatch: true }),
  );
  assert.equal(enabled.signatureValid, true);
  assert.equal(enabled.dispatchEligible, false);
  assert.equal(enabled.envelope.payload.plan_sha256, PLAN_SHA);
});

test("normalized projection is content-free and cannot widen authority", async () => {
  const bytes = await envelope();
  const normalized = verifyAndProjectSignedAuthority(
    bytes,
    context({ sourceEnvelopeBytes: bytes }),
  );
  assert.equal(normalized.schema_version, 1);
  assert.equal(normalized.profile, "gcp-controlled-apply-verified-envelope/v1");
  assert.equal(
    normalized.projection_sha256,
    createHash("sha256")
      .update(canonicalAuthorityJson(normalized.projection))
      .digest("hex"),
  );
  assert.equal(normalized.projection.source_signature_verified, true);
  assert.equal(normalized.projection.source_semantics_verified, true);
  for (const field of [
    "workforce_subject_verified",
    "workforce_capability_verified",
    "approval_event_verified",
    "cancellation_authority_verified",
    "aggregate_authority_complete",
    "dispatch_eligible",
  ])
    assert.equal(normalized.projection[field], false, field);
  const serialized = canonicalAuthorityJson(normalized);
  assert.equal(serialized.includes("value_base64"), false);
  assert.equal(serialized.includes('"signature"'), false);
  assert.equal(serialized.includes('"payload"'), false);
});

test("normalized projection requires a pinned verifier revision", async () => {
  await expectCode(
    async () =>
      verifyAndProjectSignedAuthority(
        await envelope(),
        context({ verifierRevisionSha256: "latest" }),
      ),
    "AUTHORITY_DIGEST_INVALID",
  );
});

test("normalized projection rejects a deployment verifier revision mismatch", async () => {
  await expectCode(
    async () =>
      verifyAndProjectSignedAuthority(
        await envelope(),
        context({ expectedVerifierRevisionSha256: "0".repeat(64) }),
      ),
    "AUTHORITY_VERIFIER_REVISION_MISMATCH",
  );
});

test("normalized projection rejects digest tamper and authority widening", async () => {
  const bytes = await envelope();
  const normalized = verifyAndProjectSignedAuthority(
    bytes,
    context({ sourceEnvelopeBytes: bytes }),
  );
  const tampered = structuredClone(normalized);
  tampered.projection.plan_sha256 = "0".repeat(64);
  assert.throws(
    () =>
      verifyNormalizedAuthorityProjection(
        tampered,
        context({ sourceEnvelopeBytes: bytes }),
      ),
    (error) => error.code === "AUTHORITY_PROJECTION_DIGEST_MISMATCH",
  );
  const widened = structuredClone(normalized);
  widened.projection.dispatch_eligible = true;
  widened.projection_sha256 = createHash("sha256")
    .update(canonicalAuthorityJson(widened.projection))
    .digest("hex");
  assert.throws(
    () =>
      verifyNormalizedAuthorityProjection(
        widened,
        context({ sourceEnvelopeBytes: bytes }),
      ),
    (error) => error.code === "AUTHORITY_PROJECTION_WIDENED",
  );
});

test("detached and full-redigested normalized projections are never trusted", async () => {
  const bytes = await envelope();
  const normalized = verifyAndProjectSignedAuthority(
    bytes,
    context({ sourceEnvelopeBytes: bytes }),
  );
  assert.throws(
    () => verifyNormalizedAuthorityProjection(normalized),
    (error) => error.code === "AUTHORITY_PROJECTION_SOURCE_REQUIRED",
  );
  const forged = structuredClone(normalized);
  forged.projection.signed_payload_disposition = "rejected";
  forged.projection_sha256 = createHash("sha256")
    .update(canonicalAuthorityJson(forged.projection))
    .digest("hex");
  assert.throws(
    () =>
      verifyNormalizedAuthorityProjection(
        forged,
        context({ sourceEnvelopeBytes: bytes }),
      ),
    (error) => error.code === "AUTHORITY_PROJECTION_SOURCE_MISMATCH",
  );
  assert.deepEqual(
    verifyNormalizedAuthorityProjection(
      normalized,
      context({ nowMs: NOW + 1, sourceEnvelopeBytes: bytes }),
    ),
    normalized,
  );
});

test("normalized runtime rejects extra, missing and wrongly typed fields", async () => {
  const bytes = await envelope();
  const normalized = verifyAndProjectSignedAuthority(
    bytes,
    context({ sourceEnvelopeBytes: bytes }),
  );
  for (const mutate of [
    (candidate) => delete candidate.projection.plan_sha256,
    (candidate) => (candidate.projection.kind = 42),
    (candidate) => (candidate.projection.raw_customer_email = "pii@example.test"),
  ]) {
    const forged = structuredClone(normalized);
    mutate(forged);
    forged.projection_sha256 = createHash("sha256")
      .update(canonicalAuthorityJson(forged.projection))
      .digest("hex");
    assert.throws(
      () =>
        verifyNormalizedAuthorityProjection(
          forged,
          context({ sourceEnvelopeBytes: bytes }),
        ),
      (error) =>
        [
          "AUTHORITY_PROJECTION_INVALID",
          "AUTHORITY_PROJECTION_SOURCE_MISMATCH",
        ].includes(error.code),
    );
  }
});

test("untrusted issuer and altered signature fail closed", async () => {
  await expectCode(
    async () =>
      verifySignedAuthority(
        await envelope({}, { issuer_service_account: BROKER }),
        context(),
      ),
    "AUTHORITY_ISSUER_UNTRUSTED",
  );
  const tampered = JSON.parse(await envelope());
  tampered.payload.plan_semantic_sha256 = "f".repeat(64);
  await expectCode(
    async () =>
      verifySignedAuthority(canonicalAuthorityJson(tampered), context()),
    "AUTHORITY_PAYLOAD_DIGEST_MISMATCH",
  );
  const wrongSignature = JSON.parse(await envelope());
  wrongSignature.signature.value_base64 = Buffer.from(
    "not-a-valid-signature",
  ).toString("base64");
  await expectCode(
    async () =>
      verifySignedAuthority(canonicalAuthorityJson(wrongSignature), context()),
    "AUTHORITY_SIGNATURE_INVALID",
  );
});

test("runtime types and KMS key resource match the contract", async () => {
  await expectCode(
    async () =>
      verifySignedAuthority(
        await envelope({ project_number: 81588547131 }),
        context(),
      ),
    "AUTHORITY_TARGET_MISMATCH",
  );
  await expectCode(
    async () =>
      verifySignedAuthority(
        await envelope({ credential_authority_generation: 9 }),
        context(),
      ),
    "AUTHORITY_GENERATION_INVALID",
  );
  const invalidKmsKey = "caller-controlled-key-version";
  await expectCode(
    async () =>
      verifySignedAuthority(
        await envelope({}, { kms_key_version: invalidKmsKey }),
        context({
          trustedKmsKeyVersions: new Map([
            [
              invalidKmsKey,
              {
                algorithm: "EC_SIGN_P256_SHA256",
                issuerServiceAccount: ISSUER,
                publicKeyPem,
                publicKeySha256: keyDigest(publicKey),
                state: "ENABLED",
              },
            ],
          ]),
        }),
      ),
    "AUTHORITY_KMS_KEY_INVALID",
  );
});

test("regex-backed payload fields reject array and object coercion", async () => {
  const cases = [
    ["base_revision", "4".repeat(40), "AUTHORITY_REVISION_INVALID"],
    ["broker_service_account", BROKER, "AUTHORITY_TARGET_MISMATCH"],
    ["executor_service_account", EXECUTOR, "AUTHORITY_TARGET_MISMATCH"],
    [
      "decision_id",
      "decision/VFBIZ-0220/test-runtime-only",
      "AUTHORITY_DECISION_ID_INVALID",
    ],
    [
      "plan_uri",
      `gs://vinfast-503003-evidence-dev/controlled-apply/plans/v1/${PLAN_SHA}.tfplan#6`,
      "AUTHORITY_PLAN_URI_INVALID",
    ],
    [
      "executor_image",
      "asia-southeast1-docker.pkg.dev/vinfast-503003/" +
        `vfbiz-ai-workers-dev/controlled-apply@sha256:${"b".repeat(64)}`,
      "AUTHORITY_IMAGE_INVALID",
    ],
  ];
  for (const [field, validValue, code] of cases) {
    for (const invalidValue of [[validValue], { value: validValue }]) {
      await expectCode(
        async () =>
          verifySignedAuthority(
            await envelope({ [field]: invalidValue }),
            context(),
          ),
        code,
      );
    }
  }
});

test("regex-backed signature fields reject array and object coercion", async () => {
  for (const invalidValue of [[KMS_KEY], { value: KMS_KEY }]) {
    await expectCode(
      async () =>
        verifySignedAuthority(
          await envelope({}, { kms_key_version: invalidValue }),
          context(),
        ),
      "AUTHORITY_KMS_KEY_INVALID",
    );
  }
  for (const invalidValue of [[ISSUER], { value: ISSUER }]) {
    await expectCode(
      async () =>
        verifySignedAuthority(
          await envelope({}, { issuer_service_account: invalidValue }),
          context(),
        ),
      "AUTHORITY_ISSUER_UNTRUSTED",
    );
  }
});

test("declared P-256 algorithm rejects other trusted key types and curves", async () => {
  for (const candidate of [
    generateKeyPairSync("ec", { namedCurve: "secp384r1" }),
    generateKeyPairSync("rsa", { modulusLength: 1024 }),
  ]) {
    const authorityPayload = payload();
    const payloadJson = canonicalAuthorityJson(authorityPayload);
    const payloadSha256 = await digest(payloadJson);
    const valueBase64 = createSignature(
      "sha256",
      Buffer.from(
        canonicalAuthorityJson({
          algorithm: "EC_SIGN_P256_SHA256",
          issuer_service_account: ISSUER,
          kms_key_version: KMS_KEY,
          payload: authorityPayload,
          payload_sha256: payloadSha256,
          schema_version: 1,
        }),
      ),
      candidate.privateKey,
    ).toString("base64");
    const bytes = canonicalAuthorityJson({
      payload: authorityPayload,
      payload_sha256: payloadSha256,
      schema_version: 1,
      signature: {
        algorithm: "EC_SIGN_P256_SHA256",
        issuer_service_account: ISSUER,
        kms_key_version: KMS_KEY,
        value_base64: valueBase64,
      },
    });
    await expectCode(
      async () =>
        verifySignedAuthority(
          bytes,
          context({
            trustedKmsKeyVersions: new Map([
              [
                KMS_KEY,
                {
                  algorithm: "EC_SIGN_P256_SHA256",
                  issuerServiceAccount: ISSUER,
                  publicKeyPem: candidate.publicKey,
                  publicKeySha256: keyDigest(candidate.publicKey),
                  state: "ENABLED",
                },
              ],
            ]),
          }),
        ),
      "AUTHORITY_KEY_ALGORITHM_MISMATCH",
    );
  }
});

test("trusted key metadata is pinned, enabled and digest-bound", async () => {
  for (const [overrides, code] of [
    [{ state: "DISABLED" }, "AUTHORITY_ISSUER_UNTRUSTED"],
    [{ algorithm: "RSA_SIGN_PSS_2048_SHA256" }, "AUTHORITY_ISSUER_UNTRUSTED"],
    [
      { publicKeySha256: "0".repeat(64) },
      "AUTHORITY_PUBLIC_KEY_DIGEST_MISMATCH",
    ],
  ]) {
    await expectCode(
      async () =>
        verifySignedAuthority(
          await envelope(),
          context({
            trustedKmsKeyVersions: new Map([
              [
                KMS_KEY,
                {
                  algorithm: "EC_SIGN_P256_SHA256",
                  issuerServiceAccount: ISSUER,
                  publicKeyPem,
                  publicKeySha256: keyDigest(publicKey),
                  state: "ENABLED",
                  ...overrides,
                },
              ],
            ]),
          }),
        ),
      code,
    );
  }
});

test("signature binds issuer, key version and declared algorithm", async () => {
  const signed = JSON.parse(await envelope());
  signed.signature.algorithm = "EC_SIGN_P256_SHA256";
  signed.signature.kms_key_version = KMS_KEY.replace(/\/1$/, "/2");
  const trusted = context();
  trusted.trustedKmsKeyVersions.set(
    signed.signature.kms_key_version,
    trusted.trustedKmsKeyVersions.get(KMS_KEY),
  );
  await expectCode(
    async () => verifySignedAuthority(canonicalAuthorityJson(signed), trusted),
    "AUTHORITY_SIGNATURE_INVALID",
  );
});

test("requester cannot approve its own decision", async () => {
  await expectCode(
    async () =>
      verifySignedAuthority(
        await envelope({ approver_subject_sha256: "1".repeat(64) }),
        context(),
      ),
    "AUTHORITY_DUTY_CONFLICT",
  );
});

test("claim, capability and approval-event join keys fail closed", async () => {
  for (const [overrides, code] of [
    [{ claim_fencing_token: "0" }, "AUTHORITY_JOIN_KEY_INVALID"],
    [{ approval_event_revision: "latest" }, "AUTHORITY_JOIN_KEY_INVALID"],
    [{ subject_hash_profile: "subject-only" }, "AUTHORITY_JOIN_KEY_INVALID"],
    [
      { required_capability: "controlled-apply:recover" },
      "AUTHORITY_DECISION_INVALID",
    ],
    [
      { claim_expires_at: new Date(NOW + 5 * 60_000).toISOString() },
      "AUTHORITY_WINDOW_INVALID",
    ],
    [
      { approval_event_occurred_at: new Date(NOW + 1).toISOString() },
      "AUTHORITY_WINDOW_INVALID",
    ],
  ])
    await expectCode(
      async () => verifySignedAuthority(await envelope(overrides), context()),
      code,
    );
});

test("all signed timestamps require canonical RFC3339 UTC strings", async () => {
  for (const field of [
    "issued_at",
    "expires_at",
    "claim_expires_at",
    "approval_event_occurred_at",
  ]) {
    const valid = payload()[field];
    for (const invalid of [
      [valid],
      { value: valid },
      1,
      "2026-08-02 06:00:00Z",
      "2026-08-02T13:00:00+07:00",
      "2026-02-30T06:00:00Z",
      "2026-13-01T06:00:00Z",
    ])
      await expectCode(
        async () =>
          verifySignedAuthority(await envelope({ [field]: invalid }), context()),
        "AUTHORITY_TIMESTAMP_INVALID",
      );
  }
});

test("plan URI, executor image and recovery retry policy are exact", async () => {
  await expectCode(
    async () =>
      verifySignedAuthority(
        await envelope({ plan_uri: "gs://other/plan.tfplan#1" }),
        context(),
      ),
    "AUTHORITY_PLAN_URI_INVALID",
  );
  await expectCode(
    async () =>
      verifySignedAuthority(
        await envelope({ executor_image: "latest" }),
        context(),
      ),
    "AUTHORITY_IMAGE_INVALID",
  );
  await expectCode(
    async () =>
      verifySignedAuthority(await envelope({ safe_to_retry: true }), context()),
    "AUTHORITY_RETRY_POLICY_INVALID",
  );
});

test("synthetic evidence cannot self-promote", async () => {
  await expectCode(
    async () =>
      verifySignedAuthority(
        await envelope({
          evidence_class: "synthetic-test-only",
          environment: "test",
          authority_class: "synthetic-test-only",
          decision: "authorized",
        }),
        context({ allowDispatch: true }),
      ),
    "AUTHORITY_SYNTHETIC_INVALID",
  );
});

test("recovery protocol requires security owner and never claims retry safe", async () => {
  const recovery = await envelope({
    kind: "recovery-protocol",
    target_work_item_id: "VFBIZ-0216",
    action: "accept-vfbiz-0216-recovery-protocol",
    approver_role: "security-owner",
    required_capability: "authorization.approval.approve",
    decision: "protocol-accepted",
  });
  assert.equal(
    verifySignedAuthority(recovery, context({ allowDispatch: true }))
      .signatureValid,
    true,
  );
  assert.equal(
    verifySignedAuthority(recovery, context({ allowDispatch: true }))
      .dispatchEligible,
    false,
  );
  await expectCode(
    async () =>
      verifySignedAuthority(
        await envelope({
          kind: "recovery-protocol",
          target_work_item_id: "VFBIZ-0216",
          action: "accept-vfbiz-0216-recovery-protocol",
          decision: "protocol-accepted",
          approver_role: "release-owner",
        }),
        context(),
      ),
    "AUTHORITY_DECISION_INVALID",
  );
});

test("expired, long-lived and future envelopes fail closed", async () => {
  await expectCode(
    async () =>
      verifySignedAuthority(
        await envelope({ expires_at: new Date(NOW - 1).toISOString() }),
        context(),
      ),
    "AUTHORITY_WINDOW_INVALID",
  );
  await expectCode(
    async () =>
      verifySignedAuthority(
        await envelope({
          expires_at: new Date(NOW + 60 * 60_000).toISOString(),
        }),
        context(),
      ),
    "AUTHORITY_WINDOW_INVALID",
  );
  await expectCode(
    async () =>
      verifySignedAuthority(
        await envelope({ issued_at: new Date(NOW + 1).toISOString() }),
        context(),
      ),
    "AUTHORITY_WINDOW_INVALID",
  );
});

test("verification clock and window configuration are fail-closed", async () => {
  for (const [override, code] of [
    [{ nowMs: Number.NaN }, "AUTHORITY_VERIFICATION_TIME_INVALID"],
    [{ nowMs: Number.POSITIVE_INFINITY }, "AUTHORITY_VERIFICATION_TIME_INVALID"],
    [{ nowMs: null }, "AUTHORITY_VERIFICATION_TIME_INVALID"],
    [{ maximumWindowMs: Number.NaN }, "AUTHORITY_WINDOW_CONFIG_INVALID"],
    [{ maximumWindowMs: 0 }, "AUTHORITY_WINDOW_CONFIG_INVALID"],
    [{ maximumWindowMs: null }, "AUTHORITY_WINDOW_CONFIG_INVALID"],
  ])
    await expectCode(
      async () => verifySignedAuthority(await envelope(), context(override)),
      code,
    );
});

test("duplicate keys, noncanonical JSON and oversized payloads are rejected", () => {
  assert.throws(
    () => parseSignedAuthority('{"schema_version":1,"schema_version":1}'),
    (error) => error.code === "AUTHORITY_DUPLICATE_KEY",
  );
  assert.throws(
    () => parseSignedAuthority('{ "schema_version": 1 }'),
    (error) => error.code === "AUTHORITY_NOT_CANONICAL",
  );
  assert.throws(
    () =>
      parseSignedAuthority(Buffer.alloc(MAX_SIGNED_AUTHORITY_BYTES + 1, 0x61)),
    (error) => error.code === "AUTHORITY_SIZE_INVALID",
  );
  const deeplyNested = `${"[".repeat(34)}null${"]".repeat(34)}`;
  assert.throws(
    () => parseSignedAuthority(deeplyNested),
    (error) => error.code === "AUTHORITY_DEPTH_INVALID",
  );
});
