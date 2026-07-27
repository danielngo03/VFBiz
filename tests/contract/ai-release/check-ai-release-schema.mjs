import { readFile } from "node:fs/promises";
import process from "node:process";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const digest = "a".repeat(64);
const artifact = (ref) => ({ ref, sha256: digest });
const scope = {
  assistant_profile: "customer-assistant",
  environment: "staging",
};

const safeApprovals = ["security", "release"].map((role) => ({
  approval_id: `safe-${role}`,
  authority_role: `${role}-owner`,
  approver_subject: `subject-safe-${role}`,
  approved_at: "2026-07-26T05:00:00Z",
  evidence_ref: `approval://safe/${role}`,
  evidence_sha256: digest,
  target_safe_release_core_sha256: digest,
}));
const staticSafeRelease = {
  safe_release_id: "static-safe-1",
  safe_release_ref: "safe-release://customer/static-safe-1",
  safe_release_core_sha256: digest,
  approval_set_sha256: digest,
  safe_release_envelope_sha256: digest,
  template_ref: "prompt://customer/static-safe-1",
  template_sha256: digest,
  response_policy_ref: "policy://customer/static-safe-1",
  response_policy_sha256: digest,
  ...scope,
  effective_at: "2026-07-26T04:00:00Z",
  expires_at: "2027-07-26T04:00:00Z",
  approvals: safeApprovals,
};
const staticSafeTarget = {
  kind: "static_safe_release",
  safe_release_id: staticSafeRelease.safe_release_id,
  safe_release_ref: staticSafeRelease.safe_release_ref,
  safe_release_core_sha256: digest,
  approval_set_sha256: digest,
  safe_release_envelope_sha256: digest,
  ...scope,
};
const activationTarget = {
  kind: "activation",
  activation_id: "activation-1",
  activation_envelope_sha256: digest,
  candidate_id: "candidate-1",
  candidate_sha256: digest,
  ...scope,
};
const transactionContext = {
  idempotency_key: "activate-1",
  correlation_id: "correlation-1",
  actor_subject: "subject-release-owner",
  reason: "Promote an evaluated customer assistant release.",
};
const activationEvent = {
  event_ref: "history://customer-assistant/staging/1",
  sequence: 1,
  previous_event_sha256: null,
  event_sha256: digest,
  event_type: "activated",
  from_target: staticSafeTarget,
  to_target: activationTarget,
  activation_envelope_sha256: digest,
  pointer_revision: 2,
  transaction_context: transactionContext,
  occurred_at: "2026-07-26T05:00:01Z",
};

const validRelease = {
  schema_version: 3,
  activation_id: "activation-1",
  candidate: {
    candidate_id: "candidate-1",
    content_sha256: digest,
    ...scope,
    requested_by_subject: "subject-proposer",
    gate_policy_revision: "release-gate-v3",
    gate_policy_sha256: digest,
    artifacts: {
      model_deployment: artifact("model://customer-assistant/staging-1"),
      prompt: artifact("prompt://customer-assistant/staging-1"),
      output_schema: artifact("schema://grounded-answer/v3"),
      graph: artifact("graph://customer-assistant/v3"),
      policy: artifact("policy://customer-assistant/v3"),
      validator: artifact("validator://grounding/v3"),
      knowledge_profile: artifact("knowledge://customer-public/v1"),
      retriever: artifact("retriever://hybrid/v1"),
      embedding_generation_sha256: digest,
      dataset_releases: [artifact("dataset://assistant-gold/v1")],
      tool_registry: artifact("tools://customer-read-only/v1"),
      evaluator: artifact("evaluator://assistant-release/v3"),
    },
  },
  automated_gate: {
    evidence_ref: "evaluation://assistant-release/candidate-1",
    evidence_sha256: digest,
    target_candidate_sha256: digest,
    ...scope,
    gate_policy_revision: "release-gate-v3",
    gate_policy_sha256: digest,
  },
  approvals: ["security", "release"].map((role) => ({
    approval_id: `activation-${role}`,
    authority_role: `${role}-owner`,
    approver_subject: `subject-${role}`,
    approved_at: "2026-07-26T05:00:00Z",
    evidence_ref: `approval://activation/${role}`,
    evidence_sha256: digest,
    target_candidate_sha256: digest,
    ...scope,
  })),
  effective_at: "2026-07-26T05:00:00Z",
  expires_at: "2026-08-02T05:00:00Z",
  rollback_target: staticSafeTarget,
  kill_switch_registry_ref: "tools://kill-switch/customer-assistant",
  kill_switch_registry_sha256: digest,
  rollback_drill_evidence_ref: "drill://customer-assistant/staging-1",
  rollback_drill_evidence_sha256: digest,
  promotion_evidence_ref: "approval://promotion/activation-1",
  promotion_evidence_sha256: digest,
  promotion_evidence_target_sha256: digest,
  approval_set_sha256: digest,
  activation_core_sha256: digest,
  activation_envelope_sha256: digest,
  digest_projection_version: 1,
  static_safe_release: staticSafeRelease,
  transaction_context: transactionContext,
  pointer_transition: {
    operation: "activate",
    ...scope,
    from_target: staticSafeTarget,
    to_target: activationTarget,
    expected_pointer_revision: 1,
    result_pointer_revision: 2,
  },
  activation_event: activationEvent,
  outbox_event: {
    event_ref: "outbox://customer-assistant/staging/1",
    schema_version: 1,
    aggregate_id: "customer-assistant:staging",
    ...scope,
    correlation_id: transactionContext.correlation_id,
    idempotency_key: transactionContext.idempotency_key,
    event_type: activationEvent.event_type,
    pointer_revision: activationEvent.pointer_revision,
    history_event_sha256: activationEvent.event_sha256,
    occurred_at: activationEvent.occurred_at,
    payload_sha256: digest,
  },
};

const schema = JSON.parse(
  await readFile(
    new URL("../../../contracts/ai/ai-release-manifest.schema.json", import.meta.url),
    "utf8",
  ),
);
const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
const validate = ajv.compile(schema);

if (!validate(validRelease)) {
  throw new Error(`positive release fixture failed: ${ajv.errorsText(validate.errors)}`);
}

for (const [name, mutation] of [
  ["legacy schema", (value) => (value.schema_version = 2)],
  [
    "unapproved URI scheme",
    (value) => (value.static_safe_release.safe_release_ref = "https://example.invalid"),
  ],
  [
    "missing pointer revision",
    (value) => delete value.pointer_transition.expected_pointer_revision,
  ],
]) {
  const invalid = structuredClone(validRelease);
  mutation(invalid);
  if (validate(invalid)) throw new Error(`${name} fixture unexpectedly passed`);
}

process.stdout.write("Assistant Release v3 schema fixtures passed.\n");
