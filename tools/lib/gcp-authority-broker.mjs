import { createHash } from "node:crypto";
import {
  canonicalAuthorityPairProjection,
  canonicalAuthorityJson,
  verifySignedAuthority,
} from "./gcp-signed-authority.mjs";

const SHA256 = /^[a-f0-9]{64}$/;
const KINDS = ["apply-decision", "recovery-protocol"];
const STORE_TRANSACTORS = new WeakMap();

export class AuthorityBrokerError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "AuthorityBrokerError";
    this.code = code;
  }
}

function reject(code, message) {
  throw new AuthorityBrokerError(code, message);
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function assertDigest(value, field) {
  if (typeof value !== "string" || !SHA256.test(value))
    reject("BROKER_DIGEST_INVALID", `${field} is not a SHA-256 digest`);
}

function cloneTrustContext(context) {
  if (!(context?.trustedKmsKeyVersions instanceof Map))
    reject("BROKER_TRUST_CONFIG_INVALID", "trusted KMS registry is required");
  const trustedKmsKeyVersions = new Map();
  for (const [keyVersion, metadata] of context.trustedKmsKeyVersions) {
    trustedKmsKeyVersions.set(
      keyVersion,
      Object.freeze({
        algorithm: metadata.algorithm,
        issuerServiceAccount: metadata.issuerServiceAccount,
        publicKeyPem: metadata.publicKeyPem,
        publicKeySha256: metadata.publicKeySha256,
        state: metadata.state,
      }),
    );
  }
  const result = {
    expectedBrokerServiceAccount: context.expectedBrokerServiceAccount,
    expectedExecutorServiceAccount: context.expectedExecutorServiceAccount,
    trustedKmsKeyVersions,
  };
  if (context.maximumWindowMs !== undefined)
    result.maximumWindowMs = context.maximumWindowMs;
  return Object.freeze(result);
}

function observation(bytes, verified, trustContext) {
  const payload = verified.envelope.payload;
  const keyVersion = verified.envelope.signature.kms_key_version;
  const trusted = trustContext.trustedKmsKeyVersions.get(keyVersion);
  const canonicalBytes = Buffer.from(bytes);
  const pairingSha256 = sha256(
    canonicalAuthorityJson(canonicalAuthorityPairProjection(payload)),
  );
  return {
    disposition: verified.disposition,
    envelopeSha256: sha256(canonicalBytes),
    evidenceClass: payload.evidence_class,
    kind: verified.kind,
    nonce: payload.nonce,
    pairingSha256,
    payloadSha256: verified.envelope.payload_sha256,
    trustBinding: {
      algorithm: trusted.algorithm,
      issuerServiceAccount: trusted.issuerServiceAccount,
      keyVersion,
      publicKeySha256: trusted.publicKeySha256,
    },
    window: {
      expiresAt: verified.window.expiresAt,
      issuedAt: verified.window.issuedAt,
    },
  };
}

function view(record, duplicate = false) {
  const pairComplete = KINDS.every(
    (kind) => record.observations[kind] !== undefined,
  );
  return structuredClone({
    conformancePairComplete: pairComplete,
    dispatchEligible: false,
    duplicate,
    fencingToken: record.fencingToken,
    pairingSha256: record.pairingSha256,
    state: record.terminal
      ? record.terminal.outcome
      : record.reservation
        ? "synthetic-conformance-reserved"
        : pairComplete
          ? "pair-complete-inert"
          : "collecting",
    reservation: record.reservation,
    terminal: record.terminal,
  });
}

export class InMemoryAuthorityBrokerConformanceStore {
  #state;

  #tail = Promise.resolve();

  constructor({ maximumPairs = 1_000 } = {}) {
    if (!Number.isSafeInteger(maximumPairs) || maximumPairs <= 0)
      reject("BROKER_CAPACITY_INVALID", "maximumPairs must be positive");
    this.#state = {
      maximumPairs,
      nextFencingToken: 1,
      noncePairs: new Map(),
      pairs: new Map(),
    };
    STORE_TRANSACTORS.set(this, (operation) => this.#transaction(operation));
  }

  async #transaction(operation) {
    const previous = this.#tail;
    let release;
    this.#tail = new Promise((resolve) => {
      release = resolve;
    });
    await previous;
    try {
      const result = await operation(this.#state);
      return structuredClone(result);
    } finally {
      release();
    }
  }
}

export class AuthorityBrokerConformanceModel {
  #clock;
  #transaction;
  #trustContextProvider;

  constructor({ clock = Date.now, store, trustContextProvider }) {
    if (!(store instanceof InMemoryAuthorityBrokerConformanceStore))
      reject(
        "BROKER_STORE_INVALID",
        "only the explicit in-memory conformance store is supported",
      );
    if (typeof clock !== "function")
      reject("BROKER_CLOCK_INVALID", "broker clock must be callable");
    if (typeof trustContextProvider !== "function")
      reject(
        "BROKER_TRUST_PROVIDER_INVALID",
        "broker trust context provider must be callable",
      );
    this.#clock = clock;
    this.#transaction = STORE_TRANSACTORS.get(store);
    this.#trustContextProvider = trustContextProvider;
  }

  async register(envelopeBytes) {
    const immutableBytes = Buffer.from(envelopeBytes);
    return this.#transaction((state) => {
      const nowMs = this.#clock();
      const trustContext = cloneTrustContext(this.#trustContextProvider());
      const verified = verifySignedAuthority(immutableBytes, {
        ...trustContext,
        nowMs,
      });
      if (!verified.signatureValid || !verified.semanticValid)
        reject("BROKER_OBSERVATION_INVALID", "authority verification failed");
      if (
        verified.envelope.payload.evidence_class !== "synthetic-test-only" ||
        verified.envelope.payload.environment !== "test" ||
        verified.disposition !== "review-pending"
      )
        reject(
          "BROKER_CONFORMANCE_EVIDENCE_INVALID",
          "conformance model accepts only inert synthetic evidence",
        );
      const candidate = observation(immutableBytes, verified, trustContext);
      const noncePair = state.noncePairs.get(candidate.nonce);
      if (noncePair && noncePair !== candidate.pairingSha256)
        reject("BROKER_NONCE_REPLAY", "nonce is already bound to another pair");
      let record = state.pairs.get(candidate.pairingSha256);
      if (!record) {
        if (state.pairs.size >= state.maximumPairs)
          reject("BROKER_CAPACITY_EXCEEDED", "broker pair capacity is full");
        record = {
          createdAt: nowMs,
          fencingToken: state.nextFencingToken,
          observations: {},
          pairingSha256: candidate.pairingSha256,
          reservation: null,
          terminal: null,
        };
        state.nextFencingToken += 1;
        state.pairs.set(candidate.pairingSha256, record);
        state.noncePairs.set(candidate.nonce, candidate.pairingSha256);
      }
      if (record.terminal)
        reject("BROKER_TERMINAL_IMMUTABLE", "authority pair is terminal");
      if (
        Object.values(record.observations).some(
          ({ window }) => window.expiresAt <= nowMs,
        )
      )
        reject(
          "BROKER_PAIR_WINDOW_EXPIRED",
          "an existing authority observation has expired",
        );
      const existing = record.observations[candidate.kind];
      if (existing) {
        if (existing.envelopeSha256 !== candidate.envelopeSha256)
          reject(
            "BROKER_KIND_CONFLICT",
            "authority kind already has a different envelope",
          );
        return view(record, true);
      }
      record.observations[candidate.kind] = candidate;
      return view(record);
    });
  }

  async reserveSyntheticConformance({
    fencingToken,
    pairingSha256,
    reservationReceiptSha256,
  }) {
    assertDigest(reservationReceiptSha256, "reservationReceiptSha256");
    assertDigest(pairingSha256, "pairingSha256");
    this.#assertFence(fencingToken);
    return this.#transaction((state) => {
      const nowMs = this.#clock();
      const record = state.pairs.get(pairingSha256);
      if (!record) reject("BROKER_PAIR_NOT_FOUND", "authority pair is unknown");
      if (record.fencingToken !== fencingToken)
        reject("BROKER_STALE_FENCE", "fencing token is stale");
      if (!KINDS.every((kind) => record.observations[kind]))
        reject("BROKER_PAIR_INCOMPLETE", "authority pair is incomplete");
      this.#assertRecordCurrent(
        record,
        nowMs,
        cloneTrustContext(this.#trustContextProvider()),
      );
      if (record.terminal) {
        reject("BROKER_TERMINAL_IMMUTABLE", "terminal receipt is immutable");
      }
      if (record.reservation) {
        if (record.reservation.receiptSha256 === reservationReceiptSha256)
          return view(record, true);
        reject("BROKER_RESERVATION_CONFLICT", "pair is already reserved");
      }
      record.reservation = { receiptSha256: reservationReceiptSha256 };
      return view(record);
    });
  }

  async completeSyntheticConformance({
    completionReceiptSha256,
    fencingToken,
    outcome,
    pairingSha256,
    reservationReceiptSha256,
  }) {
    assertDigest(completionReceiptSha256, "completionReceiptSha256");
    assertDigest(pairingSha256, "pairingSha256");
    assertDigest(reservationReceiptSha256, "reservationReceiptSha256");
    this.#assertFence(fencingToken);
    if (
      ![
        "synthetic-conformance-failed",
        "synthetic-conformance-succeeded",
        "synthetic-conformance-unknown",
      ].includes(outcome)
    )
      reject("BROKER_OUTCOME_INVALID", "conformance outcome is invalid");
    return this.#transaction((state) => {
      const record = state.pairs.get(pairingSha256);
      if (!record) reject("BROKER_PAIR_NOT_FOUND", "authority pair is unknown");
      if (record.fencingToken !== fencingToken)
        reject("BROKER_STALE_FENCE", "fencing token is stale");
      if (
        !record.reservation ||
        record.reservation.receiptSha256 !== reservationReceiptSha256
      )
        reject("BROKER_RESERVATION_MISMATCH", "reservation receipt mismatches");
      if (record.terminal) {
        if (
          record.terminal.outcome === outcome &&
          record.terminal.receiptSha256 === completionReceiptSha256
        )
          return view(record, true);
        reject("BROKER_TERMINAL_IMMUTABLE", "terminal receipt is immutable");
      }
      record.terminal = { outcome, receiptSha256: completionReceiptSha256 };
      return view(record);
    });
  }

  async cancelSyntheticConformance({
    cancellationReceiptSha256,
    fencingToken,
    pairingSha256,
  }) {
    assertDigest(cancellationReceiptSha256, "cancellationReceiptSha256");
    assertDigest(pairingSha256, "pairingSha256");
    this.#assertFence(fencingToken);
    return this.#transaction((state) => {
      const record = state.pairs.get(pairingSha256);
      if (!record) reject("BROKER_PAIR_NOT_FOUND", "authority pair is unknown");
      if (record.fencingToken !== fencingToken)
        reject("BROKER_STALE_FENCE", "fencing token is stale");
      if (record.terminal) {
        if (
          record.terminal.outcome === "synthetic-conformance-cancelled" &&
          record.terminal.receiptSha256 === cancellationReceiptSha256
        )
          return view(record, true);
        reject("BROKER_TERMINAL_IMMUTABLE", "terminal receipt is immutable");
      }
      record.terminal = {
        outcome: "synthetic-conformance-cancelled",
        receiptSha256: cancellationReceiptSha256,
      };
      return view(record);
    });
  }

  #assertFence(fencingToken) {
    if (!Number.isSafeInteger(fencingToken) || fencingToken <= 0)
      reject("BROKER_FENCING_INVALID", "fencing token is invalid");
  }

  #assertRecordCurrent(record, nowMs, trustContext) {
    for (const candidate of Object.values(record.observations)) {
      if (
        candidate.window.issuedAt > nowMs ||
        candidate.window.expiresAt <= nowMs
      )
        reject("BROKER_PAIR_WINDOW_EXPIRED", "authority pair has expired");
      const current = trustContext.trustedKmsKeyVersions.get(
        candidate.trustBinding.keyVersion,
      );
      if (
        !current ||
        current.state !== "ENABLED" ||
        current.algorithm !== candidate.trustBinding.algorithm ||
        current.issuerServiceAccount !==
          candidate.trustBinding.issuerServiceAccount ||
        current.publicKeySha256 !== candidate.trustBinding.publicKeySha256
      )
        reject("BROKER_TRUST_STALE", "authority signer is no longer trusted");
    }
  }
}
