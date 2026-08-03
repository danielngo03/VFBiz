import assert from "node:assert/strict";
import {
  createHash,
  generateKeyPairSync,
  sign as createSignature,
} from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  AuthorityBrokerConformanceModel,
  AuthorityBrokerError,
  InMemoryAuthorityBrokerConformanceStore,
} from "../../tools/lib/gcp-authority-broker.mjs";
import { canonicalAuthorityJson } from "../../tools/lib/gcp-signed-authority.mjs";

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

function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}

function payload(kind, overrides = {}) {
  const recovery = kind === "recovery-protocol";
  return {
    schema_version: 1,
    kind,
    evidence_class: "synthetic-test-only",
    environment: "test",
    work_item_id: "VFBIZ-0220",
    target_work_item_id: recovery ? "VFBIZ-0216" : "VFBIZ-0218",
    action: recovery
      ? "accept-vfbiz-0216-recovery-protocol"
      : "apply-vfbiz-0217-database-credential-authority",
    approval_event_id: `approval/VFBIZ-0220/${kind}`,
    approval_event_occurred_at: new Date(NOW - 2 * 60_000).toISOString(),
    approval_event_revision: "1",
    approval_event_schema_sha256: "d".repeat(64),
    decision_id: `synthetic/VFBIZ-0220/${kind}`,
    decision: "review-pending",
    authority_class: "synthetic-test-only",
    approver_role: recovery ? "security-owner" : "release-owner",
    requester_subject_sha256: "1".repeat(64),
    approver_subject_sha256: recovery ? "3".repeat(64) : "2".repeat(64),
    approval_evidence_sha256: recovery ? "4".repeat(64) : "3".repeat(64),
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
    claim_id: "claim/VFBIZ-0220/controlled-apply-pair",
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

function envelope(kind, overrides = {}) {
  const authorityPayload = payload(kind, overrides);
  const payloadJson = canonicalAuthorityJson(authorityPayload);
  const payloadSha256 = digest(payloadJson);
  const signatureMetadata = {
    algorithm: "EC_SIGN_P256_SHA256",
    issuer_service_account: ISSUER,
    kms_key_version: KMS_KEY,
  };
  const valueBase64 = createSignature(
    "sha256",
    Buffer.from(
      canonicalAuthorityJson({
        ...signatureMetadata,
        payload: authorityPayload,
        payload_sha256: payloadSha256,
        schema_version: 1,
      }),
    ),
    privateKey,
  ).toString("base64");
  return canonicalAuthorityJson({
    payload: authorityPayload,
    payload_sha256: payloadSha256,
    schema_version: 1,
    signature: { ...signatureMetadata, value_base64: valueBase64 },
  });
}

function trustContext() {
  return {
    expectedBrokerServiceAccount: BROKER,
    expectedExecutorServiceAccount: EXECUTOR,
    trustedKmsKeyVersions: new Map([
      [
        KMS_KEY,
        {
          algorithm: "EC_SIGN_P256_SHA256",
          issuerServiceAccount: ISSUER,
          publicKeyPem: publicKey.export({ type: "spki", format: "pem" }),
          publicKeySha256: digest(
            publicKey.export({ type: "spki", format: "der" }),
          ),
          state: "ENABLED",
        },
      ],
    ]),
  };
}

function broker(store = new InMemoryAuthorityBrokerConformanceStore()) {
  return {
    model: new AuthorityBrokerConformanceModel({
      clock: () => NOW,
      store,
      trustContextProvider: trustContext,
    }),
    store,
  };
}

async function expectCode(operation, code) {
  await assert.rejects(operation, (error) => {
    assert.ok(error instanceof AuthorityBrokerError);
    assert.equal(error.code, code);
    return true;
  });
}

test("duplicate and reordered delivery converge without dispatch", async () => {
  const { model } = broker();
  const recoveryEnvelope = envelope("recovery-protocol");
  const recovery = await model.register(recoveryEnvelope);
  assert.equal(recovery.conformancePairComplete, false);
  const duplicate = await model.register(recoveryEnvelope);
  assert.equal(duplicate.duplicate, true);
  const complete = await model.register(envelope("apply-decision"));
  assert.equal(complete.conformancePairComplete, true);
  assert.equal("aggregateReady" in complete, false);
  assert.equal(complete.state, "pair-complete-inert");
  assert.equal(complete.dispatchEligible, false);
});

test("concurrent duplicate delivery commits one observation", async () => {
  const { model } = broker();
  const bytes = envelope("apply-decision");
  const results = await Promise.all([
    model.register(bytes),
    model.register(bytes),
    model.register(bytes),
  ]);
  assert.equal(results.filter(({ duplicate }) => duplicate).length, 2);
  assert.equal(
    new Set(results.map(({ fencingToken }) => fencingToken)).size,
    1,
  );
  assert.equal(
    new Set(results.map(({ pairingSha256 }) => pairingSha256)).size,
    1,
  );
  assert.ok(results.every(({ dispatchEligible }) => !dispatchEligible));
});

test("same nonce cannot bind a different plan pair", async () => {
  const { model } = broker();
  await model.register(envelope("apply-decision"));
  await expectCode(
    () =>
      model.register(
        envelope("recovery-protocol", {
          plan_semantic_sha256: "f".repeat(64),
        }),
      ),
    "BROKER_NONCE_REPLAY",
  );
});

test("same kind cannot be replaced inside one pair", async () => {
  const { model } = broker();
  await model.register(envelope("apply-decision"));
  await expectCode(
    () =>
      model.register(
        envelope("apply-decision", {
          approver_subject_sha256: "e".repeat(64),
        }),
      ),
    "BROKER_KIND_CONFLICT",
  );
});

test("shared store resumes after broker restart", async () => {
  const first = broker();
  const initial = await first.model.register(envelope("apply-decision"));
  const resumed = broker(first.store).model;
  const complete = await resumed.register(envelope("recovery-protocol"));
  assert.equal(complete.pairingSha256, initial.pairingSha256);
  assert.equal(complete.fencingToken, initial.fencingToken);
  assert.equal(complete.conformancePairComplete, true);
  assert.equal(complete.dispatchEligible, false);
});

test("cancellation is fenced, idempotent and terminally immutable", async () => {
  const { model } = broker();
  const registered = await model.register(envelope("apply-decision"));
  const receiptSha256 = "d".repeat(64);
  await expectCode(
    () =>
      model.cancelSyntheticConformance({
        cancellationReceiptSha256: receiptSha256,
        fencingToken: registered.fencingToken + 1,
        pairingSha256: registered.pairingSha256,
      }),
    "BROKER_STALE_FENCE",
  );
  const cancelled = await model.cancelSyntheticConformance({
    cancellationReceiptSha256: receiptSha256,
    fencingToken: registered.fencingToken,
    pairingSha256: registered.pairingSha256,
  });
  assert.equal(cancelled.state, "synthetic-conformance-cancelled");
  assert.equal(cancelled.dispatchEligible, false);
  const replay = await model.cancelSyntheticConformance({
    cancellationReceiptSha256: receiptSha256,
    fencingToken: registered.fencingToken,
    pairingSha256: registered.pairingSha256,
  });
  assert.equal(replay.duplicate, true);
  await expectCode(
    () =>
      model.cancelSyntheticConformance({
        cancellationReceiptSha256: "e".repeat(64),
        fencingToken: registered.fencingToken,
        pairingSha256: registered.pairingSha256,
      }),
    "BROKER_TERMINAL_IMMUTABLE",
  );
  await expectCode(
    () => model.register(envelope("recovery-protocol")),
    "BROKER_TERMINAL_IMMUTABLE",
  );
});

test("trust registry is refreshed for every delivery", async () => {
  const store = new InMemoryAuthorityBrokerConformanceStore();
  let state = "ENABLED";
  const model = new AuthorityBrokerConformanceModel({
    clock: () => NOW,
    store,
    trustContextProvider: () => {
      const context = trustContext();
      context.trustedKmsKeyVersions.get(KMS_KEY).state = state;
      return context;
    },
  });
  await model.register(envelope("apply-decision"));
  state = "DISABLED";
  await assert.rejects(
    () => model.register(envelope("recovery-protocol")),
    (error) => error.code === "AUTHORITY_ISSUER_UNTRUSTED",
  );
});

test("broker evaluates expiry from its clock on every delivery", async () => {
  const store = new InMemoryAuthorityBrokerConformanceStore();
  let nowMs = NOW;
  const model = new AuthorityBrokerConformanceModel({
    clock: () => nowMs,
    store,
    trustContextProvider: trustContext,
  });
  await model.register(envelope("apply-decision"));
  nowMs += 11 * 60_000;
  await assert.rejects(
    () => model.register(envelope("recovery-protocol")),
    (error) => error.code === "AUTHORITY_WINDOW_INVALID",
  );
});

test("expired delivery consumes no nonce, pair or fencing token", async () => {
  const store = new InMemoryAuthorityBrokerConformanceStore();
  const expired = new AuthorityBrokerConformanceModel({
    clock: () => NOW + 11 * 60_000,
    store,
    trustContextProvider: trustContext,
  });
  await assert.rejects(
    () => expired.register(envelope("apply-decision")),
    (error) => error.code === "AUTHORITY_WINDOW_INVALID",
  );
  const current = broker(store).model;
  const registered = await current.register(envelope("apply-decision"));
  assert.equal(registered.fencingToken, 1);
});

test("store mutation capability is not exposed", () => {
  const store = new InMemoryAuthorityBrokerConformanceStore();
  assert.equal("transaction" in store, false);
  assert.equal(
    Object.getOwnPropertyNames(Object.getPrototypeOf(store)).length,
    1,
  );
});

test("synthetic conformance reservation and completion consume once", async () => {
  const { model } = broker();
  const apply = await model.register(envelope("apply-decision"));
  await model.register(envelope("recovery-protocol"));
  const reservationReceiptSha256 = "d".repeat(64);
  const completionReceiptSha256 = "e".repeat(64);
  const reservation = await model.reserveSyntheticConformance({
    fencingToken: apply.fencingToken,
    pairingSha256: apply.pairingSha256,
    reservationReceiptSha256,
  });
  assert.equal(reservation.state, "synthetic-conformance-reserved");
  assert.equal(reservation.dispatchEligible, false);
  const duplicate = await model.reserveSyntheticConformance({
    fencingToken: apply.fencingToken,
    pairingSha256: apply.pairingSha256,
    reservationReceiptSha256,
  });
  assert.equal(duplicate.duplicate, true);
  const terminal = await model.completeSyntheticConformance({
    completionReceiptSha256,
    fencingToken: apply.fencingToken,
    outcome: "synthetic-conformance-succeeded",
    pairingSha256: apply.pairingSha256,
    reservationReceiptSha256,
  });
  assert.equal(terminal.state, "synthetic-conformance-succeeded");
  assert.equal(terminal.dispatchEligible, false);
  const completionReplay = await model.completeSyntheticConformance({
    completionReceiptSha256,
    fencingToken: apply.fencingToken,
    outcome: "synthetic-conformance-succeeded",
    pairingSha256: apply.pairingSha256,
    reservationReceiptSha256,
  });
  assert.equal(completionReplay.duplicate, true);
  await expectCode(
    () =>
      model.completeSyntheticConformance({
        completionReceiptSha256: "f".repeat(64),
        fencingToken: apply.fencingToken,
        outcome: "synthetic-conformance-failed",
        pairingSha256: apply.pairingSha256,
        reservationReceiptSha256,
      }),
    "BROKER_TERMINAL_IMMUTABLE",
  );
});

test("reservation rechecks pair expiry and live trust", async () => {
  for (const failure of ["expired", "revoked"]) {
    const store = new InMemoryAuthorityBrokerConformanceStore();
    let nowMs = NOW;
    let trustState = "ENABLED";
    const model = new AuthorityBrokerConformanceModel({
      clock: () => nowMs,
      store,
      trustContextProvider: () => {
        const context = trustContext();
        context.trustedKmsKeyVersions.get(KMS_KEY).state = trustState;
        return context;
      },
    });
    const registered = await model.register(envelope("apply-decision"));
    await model.register(envelope("recovery-protocol"));
    if (failure === "expired") nowMs += 11 * 60_000;
    else trustState = "DISABLED";
    await expectCode(
      () =>
        model.reserveSyntheticConformance({
          fencingToken: registered.fencingToken,
          pairingSha256: registered.pairingSha256,
          reservationReceiptSha256: "d".repeat(64),
        }),
      failure === "expired"
        ? "BROKER_PAIR_WINDOW_EXPIRED"
        : "BROKER_TRUST_STALE",
    );
  }
});

test("capacity fails closed before allocating another pair", async () => {
  const store = new InMemoryAuthorityBrokerConformanceStore({
    maximumPairs: 1,
  });
  const model = broker(store).model;
  await model.register(envelope("apply-decision"));
  await expectCode(
    () =>
      model.register(
        envelope("apply-decision", {
          nonce: "f".repeat(64),
        }),
      ),
    "BROKER_CAPACITY_EXCEEDED",
  );
});

test("human-issued authority is rejected by the synthetic model", async () => {
  const { model } = broker();
  await expectCode(
    () =>
      model.register(
        envelope("apply-decision", {
          authority_class: "named-human-workforce-approval",
          decision: "authorized",
          environment: "development",
          evidence_class: "human-issued",
        }),
      ),
    "BROKER_CONFORMANCE_EVIDENCE_INVALID",
  );
});

test("controlled-apply runtime entrypoints cannot import conformance model", async () => {
  for (const path of [
    "tools/gcp-controlled-apply.mjs",
    "tools/lib/gcp-controlled-apply.mjs",
  ]) {
    const source = await readFile(path, "utf8");
    assert.equal(source.includes("gcp-authority-broker"), false, path);
    assert.equal(
      source.includes("AuthorityBrokerConformanceModel"),
      false,
      path,
    );
  }
});
