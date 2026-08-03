import assert from "node:assert/strict";
import { access, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  CONTROLLED_APPLY_ACTION,
  CONTROLLED_APPLY_CLAIM_PATHS,
  CONTROLLED_APPLY_PROJECT,
  CONTROLLED_APPLY_PROJECT_NUMBER,
  CONTROLLED_APPLY_REGION,
  CONTROLLED_APPLY_REQUIRED_LEASES,
  CONTROLLED_APPLY_WORK_ITEM,
  ControlledApplyError,
  assertExecuteAuthorized,
  buildTokenCommand,
  contentFreeReceipt,
  createPlanSnapshot,
  digestBytes,
  extractCredentialAuthority,
  parseGcsGenerationUri,
  removePlanSnapshot,
  validateDecisionReceipt,
  validateExecutionState,
  validateGoogleIdentity,
  validateRecoveryReceipt,
  validateSavedPlan,
} from "../../tools/lib/gcp-controlled-apply.mjs";

const NOW = Date.parse("2026-08-02T05:30:00Z");
const BASE_REVISION = "a".repeat(40);
const PLAN_SHA256 = "b".repeat(64);
const AUTHORITY_CONTENT = '{"authority":"intent"}';
const AUTHORITY_SHA256 = digestBytes(AUTHORITY_CONTENT);
const CLAIM = "claim-11111111-1111-1111-1111-111111111111";
const FENCING = 44;
const PRINCIPAL = "user:operator@example.com";
const AUTHORITY_EXPIRES_AT = new Date(NOW + 30 * 60_000).toISOString();

const CREATE_ADDRESSES = [
  "terraform_data.database_credential_authority_gate[0]",
  "google_service_account.database_credential_operator[0]",
  "google_project_iam_custom_role.database_credential_sql[0]",
  "google_project_iam_member.database_credential_sql[0]",
  "google_project_iam_custom_role.database_credential_secret[0]",
  "google_secret_manager_secret_iam_member.database_credential_secret[0]",
  "google_project_iam_custom_role.database_credential_evidence[0]",
  "google_storage_bucket_iam_member.database_credential_evidence[0]",
  "google_service_account_iam_member.database_credential_impersonation[0]",
];

function decision(overrides = {}) {
  return {
    schema_version: 1,
    work_item_id: CONTROLLED_APPLY_WORK_ITEM,
    action: CONTROLLED_APPLY_ACTION,
    authority_class: "named-human-cloud-operator",
    decided_by_role: "release-owner",
    decision: "authorized",
    decision_id: "decision/VFBIZ-0218/test-authority",
    project_id: CONTROLLED_APPLY_PROJECT,
    project_number: CONTROLLED_APPLY_PROJECT_NUMBER,
    region: CONTROLLED_APPLY_REGION,
    plan_path: "infra/gcp/credential.tfplan",
    plan_sha256: PLAN_SHA256,
    base_revision: BASE_REVISION,
    claim_id: CLAIM,
    fencing_token: FENCING,
    operator_principal: PRINCIPAL,
    credential_authority_sha256: AUTHORITY_SHA256,
    credential_authority_generation: "123",
    recovery_evidence_sha256: "c".repeat(64),
    recovery_evidence_uri:
      `gs://vinfast-503003-evidence-dev/database-bootstrap/admin-credential/` +
      `recovery/v1/${"c".repeat(64)}.json#456`,
    foundation_plan_sha256:
      "9bb0f86fe93f1882ea0a875b31df3295a06d166af1eaf735495ca528d0bfe04f",
    postapply_plan_sha256:
      "878381f284660f5f4558db53b9baca5ae65dcd5346b1198eee11431fd2b2bb4b",
    issued_at: new Date(NOW - 60_000).toISOString(),
    expires_at: new Date(NOW + 30 * 60_000).toISOString(),
    ...overrides,
  };
}

function decisionContext(overrides = {}) {
  return {
    nowMs: NOW,
    planPath: "infra/gcp/credential.tfplan",
    planSha256: PLAN_SHA256,
    baseRevision: BASE_REVISION,
    claimId: CLAIM,
    fencingToken: FENCING,
    operatorPrincipal: PRINCIPAL,
    authoritySha256: AUTHORITY_SHA256,
    authorityGeneration: "123",
    ...overrides,
  };
}

function recovery(overrides = {}) {
  return {
    schema_version: 1,
    work_item_id: "VFBIZ-0216",
    action: "reconcile-cloud-sql-bootstrap-credential-ambiguity",
    authority_class: "named-human-cloud-operator",
    decided_by_role: "release-owner",
    decision: "recovery-protocol-accepted",
    decision_id: "decision/VFBIZ-0216/recovery-test",
    project_id: CONTROLLED_APPLY_PROJECT,
    project_number: CONTROLLED_APPLY_PROJECT_NUMBER,
    region: CONTROLLED_APPLY_REGION,
    instance_name: "vfbiz-ai-postgres-dev",
    database_name: "vfbiz_ai",
    administrator_user: "postgres",
    administrator_secret_id: "vfbiz-ai-database-bootstrap-url-dev",
    base_revision: BASE_REVISION,
    claim_id: CLAIM,
    fencing_token: FENCING,
    operator_principal: PRINCIPAL,
    plan_sha256: PLAN_SHA256,
    credential_authority_sha256: AUTHORITY_SHA256,
    credential_authority_generation: "123",
    recovery_protocol_revision_sha256: "e".repeat(64),
    safe_to_retry: false,
    unknown_outcome_policy: "fail-closed-no-rerun",
    issued_at: new Date(NOW - 60_000).toISOString(),
    expires_at: AUTHORITY_EXPIRES_AT,
    ...overrides,
  };
}

function planContext(overrides = {}) {
  return {
    operatorPrincipal: PRINCIPAL,
    authorityExpiresAt: AUTHORITY_EXPIRES_AT,
    authoritySha256: AUTHORITY_SHA256,
    ...overrides,
  };
}

function afterValues(address) {
  const project = CONTROLLED_APPLY_PROJECT;
  const email = `vfbiz-ai-dev-db-credential@${project}.iam.gserviceaccount.com`;
  const member = `serviceAccount:${email}`;
  const role = (id) => `projects/${project}/roles/${id}`;
  const values = {
    "terraform_data.database_credential_authority_gate[0]": {
      input: null,
      triggers_replace: null,
    },
    "google_service_account.database_credential_operator[0]": {
      account_id: "vfbiz-ai-dev-db-credential",
      project,
    },
    "google_project_iam_custom_role.database_credential_sql[0]": {
      project,
      role_id: "vfbizAiDatabaseCredentialSql",
      permissions: [
        "cloudsql.databases.get",
        "cloudsql.instances.get",
        "cloudsql.users.update",
      ],
    },
    "google_project_iam_member.database_credential_sql[0]": {
      project,
      role: role("vfbizAiDatabaseCredentialSql"),
      member,
      condition: [
        {
          title: "vfbiz-db-credential-exact-instance",
          description:
            "Limit credential inspection, update and operation polling to the reviewed development instance.",
          expression:
            "resource.name == 'projects/vinfast-503003/instances/vfbiz-ai-postgres-dev' && resource.type == 'sqladmin.googleapis.com/Instance'",
        },
      ],
    },
    "google_project_iam_custom_role.database_credential_secret[0]": {
      project,
      role_id: "vfbizAiDatabaseCredentialSecret",
      permissions: [
        "secretmanager.secrets.get",
        "secretmanager.versions.access",
        "secretmanager.versions.add",
        "secretmanager.versions.list",
      ],
    },
    "google_secret_manager_secret_iam_member.database_credential_secret[0]": {
      project,
      secret_id: "vfbiz-ai-database-bootstrap-url-dev",
      role: role("vfbizAiDatabaseCredentialSecret"),
      member,
    },
    "google_project_iam_custom_role.database_credential_evidence[0]": {
      project,
      role_id: "vfbizAiDatabaseCredentialEvidence",
      permissions: [
        "storage.buckets.get",
        "storage.objects.create",
        "storage.objects.get",
      ],
    },
    "google_storage_bucket_iam_member.database_credential_evidence[0]": {
      bucket: `${project}-evidence-dev`,
      role: role("vfbizAiDatabaseCredentialEvidence"),
      member,
      condition: [
        {
          title: "vfbiz-db-credential-exact-evidence",
          description:
            "Allow bucket inspection and one digest-bound completion witness; exclude the authority namespace.",
          expression:
            `resource.name == 'projects/_/buckets/${project}-evidence-dev' || ` +
            `resource.name == 'projects/_/buckets/${project}-evidence-dev/objects/` +
            `database-bootstrap/admin-credential/v1/${AUTHORITY_SHA256}.json'`,
        },
      ],
    },
    "google_service_account_iam_member.database_credential_impersonation[0]": {
      service_account_id: `projects/${project}/serviceAccounts/${email}`,
      role: "roles/iam.serviceAccountTokenCreator",
      member: PRINCIPAL,
      condition: [
        {
          title: "vfbiz-db-credential-authority-expiry",
          description: "Permit only the reviewed one-time credential window.",
          expression: `request.time < timestamp(\"${AUTHORITY_EXPIRES_AT}\")`,
        },
      ],
    },
  };
  return structuredClone(values[address]);
}

function plan(overrides = {}) {
  return {
    resource_changes: [
      ...CREATE_ADDRESSES.map((address) => ({
        address,
        change: {
          actions: ["create"],
          after: afterValues(address),
          after_unknown: {},
        },
      })),
      {
        address:
          "data.google_storage_bucket_object_content.database_credential_authority[0]",
        change: { actions: ["read"] },
      },
    ],
    output_changes: Object.fromEntries(
      [
        "database_credential_operator_service_account",
        "database_credential_authority_object",
        "database_credential_authority_generation",
      ].map((name) => [name, { actions: ["create"] }]),
    ),
    planned_values: {
      root_module: {
        resources: [
          {
            address:
              "data.google_storage_bucket_object_content.database_credential_authority[0]",
            values: { content: AUTHORITY_CONTENT, generation: 123 },
          },
        ],
      },
    },
    ...overrides,
  };
}

function state(overrides = {}) {
  const expiresAt = new Date(NOW + 30 * 60_000).toISOString();
  const leases = [...CONTROLLED_APPLY_REQUIRED_LEASES].map(
    ([resourceClass, resourceKey], index) => ({
      leaseId: `lease-${index}`,
      holderClaimId: CLAIM,
      resourceClass,
      resourceKey,
      baseRevision: BASE_REVISION,
      state: "active",
      expiresAt,
    }),
  );
  return {
    claims: [
      {
        claimId: CLAIM,
        workItemKey: CONTROLLED_APPLY_WORK_ITEM,
        ownerTeam: "agent-platform",
        accountableHumanRole: "release-owner",
        runMode: "scoped-write",
        baseRevision: BASE_REVISION,
        fencingToken: FENCING,
        state: "active",
        expiresAt,
        allowedPaths: [...CONTROLLED_APPLY_CLAIM_PATHS],
        leaseIds: leases.map(({ leaseId }) => leaseId),
      },
    ],
    leases,
    ...overrides,
  };
}

function executionContext(overrides = {}) {
  return {
    nowMs: NOW,
    minimumRemainingMs: 5 * 60_000,
    claimId: CLAIM,
    fencingToken: FENCING,
    baseRevision: BASE_REVISION,
    ...overrides,
  };
}

function expectCode(operation, code) {
  assert.throws(operation, (error) => {
    assert.ok(error instanceof ControlledApplyError);
    assert.equal(error.code, code);
    return true;
  });
}

test("valid authority, execution state and exact create plan pass", () => {
  const validated = validateDecisionReceipt(decision(), decisionContext());
  assert.equal(validated.receipt.decision, "authorized");
  assert.equal(
    validateExecutionState(state(), executionContext()).leases.length,
    3,
  );
  assert.deepEqual(validateSavedPlan(plan(), planContext()), {
    disposition: "create-only",
    createCount: 9,
    resourceCount: 10,
  });
  assert.deepEqual(extractCredentialAuthority(plan()), {
    sha256: AUTHORITY_SHA256,
    generation: "123",
    content: AUTHORITY_CONTENT,
  });
});

test("recovery receipt is exact, bound and fail-closed on unknown outcome", () => {
  assert.equal(
    validateRecoveryReceipt(recovery(), decisionContext()).decision,
    "recovery-protocol-accepted",
  );
  expectCode(
    () =>
      validateRecoveryReceipt(
        recovery({ safe_to_retry: true }),
        decisionContext(),
      ),
    "RECOVERY_AUTHORITY_INVALID",
  );
  expectCode(
    () =>
      validateRecoveryReceipt(
        recovery({ plan_sha256: "f".repeat(64) }),
        decisionContext(),
      ),
    "RECOVERY_BINDING_MISMATCH",
  );
});

test("released and short-lived claims fail before execution", () => {
  const released = state();
  released.claims[0].state = "released";
  expectCode(
    () => validateExecutionState(released, executionContext()),
    "CLAIM_NOT_ACTIVE",
  );
  const short = state();
  short.claims[0].expiresAt = new Date(NOW + 60_000).toISOString();
  expectCode(
    () => validateExecutionState(short, executionContext()),
    "CLAIM_NOT_ACTIVE",
  );
});

test("stale fencing token and base revision fail closed", () => {
  expectCode(
    () =>
      validateExecutionState(state(), executionContext({ fencingToken: 43 })),
    "CLAIM_FENCING_MISMATCH",
  );
  expectCode(
    () =>
      validateExecutionState(
        state(),
        executionContext({ baseRevision: "d".repeat(40) }),
      ),
    "CLAIM_REVISION_MISMATCH",
  );
});

test("claim requires exact team, path set and full revision", () => {
  const wrongPath = state();
  wrongPath.claims[0].allowedPaths = ["infra/gcp/README.md"];
  expectCode(
    () => validateExecutionState(wrongPath, executionContext()),
    "CLAIM_PATH_MISMATCH",
  );
  const prefixPath = state();
  prefixPath.claims[0].allowedPaths = ["infra/gcp-evil"];
  expectCode(
    () => validateExecutionState(prefixPath, executionContext()),
    "CLAIM_PATH_MISMATCH",
  );
  const shortRevision = state();
  shortRevision.claims[0].baseRevision = BASE_REVISION.slice(0, 7);
  expectCode(
    () => validateExecutionState(shortRevision, executionContext()),
    "REVISION_INVALID",
  );
});

test("missing and expired exclusive leases fail closed", () => {
  const missing = state();
  missing.leases.pop();
  expectCode(
    () => validateExecutionState(missing, executionContext()),
    "LEASE_NOT_ACTIVE",
  );
  const expired = state();
  expired.leases[0].expiresAt = new Date(NOW - 1).toISOString();
  expectCode(
    () => validateExecutionState(expired, executionContext()),
    "LEASE_NOT_ACTIVE",
  );
});

test("decision receipt rejects expiry, plan drift and stale claim", () => {
  expectCode(
    () =>
      validateDecisionReceipt(
        decision({ expires_at: new Date(NOW - 1).toISOString() }),
        decisionContext(),
      ),
    "DECISION_EXPIRED",
  );
  expectCode(
    () =>
      validateDecisionReceipt(
        decision(),
        decisionContext({ planSha256: "d".repeat(64) }),
      ),
    "DECISION_PLAN_DIGEST_MISMATCH",
  );
  expectCode(
    () =>
      validateDecisionReceipt(
        decision(),
        decisionContext({ fencingToken: 45 }),
      ),
    "DECISION_CLAIM_MISMATCH",
  );
});

test("decision receipt rejects authority intent and operator mismatch", () => {
  expectCode(
    () =>
      validateDecisionReceipt(
        decision(),
        decisionContext({ authorityGeneration: "124" }),
      ),
    "DECISION_INTENT_MISMATCH",
  );
  expectCode(
    () =>
      validateDecisionReceipt(
        decision(),
        decisionContext({ operatorPrincipal: "user:other@example.com" }),
      ),
    "DECISION_PRINCIPAL_MISMATCH",
  );
});

test("plan verifier rejects update, unrelated create and partial create set", () => {
  const update = plan();
  update.resource_changes[0].change.actions = ["update"];
  expectCode(
    () => validateSavedPlan(update, planContext()),
    "PLAN_ACTION_FORBIDDEN",
  );
  const unrelated = plan();
  unrelated.resource_changes.push({
    address: "google_cloud_run_v2_service.public_chat",
    change: { actions: ["create"] },
  });
  expectCode(
    () => validateSavedPlan(unrelated, planContext()),
    "PLAN_ACTION_FORBIDDEN",
  );
  const partial = plan();
  partial.resource_changes.splice(0, 1);
  expectCode(
    () => validateSavedPlan(partial, planContext()),
    "PLAN_CREATE_SET_INCOMPLETE",
  );
});

test("plan verifier allows only the exact authority data read", () => {
  const withRead = plan();
  assert.equal(
    validateSavedPlan(withRead, planContext()).disposition,
    "create-only",
  );
  withRead.resource_changes.at(-1).address =
    "data.google_storage_bucket_object_content.other";
  expectCode(
    () => validateSavedPlan(withRead, planContext()),
    "PLAN_ACTION_FORBIDDEN",
  );
});

test("plan verifier rejects duplicate, public, expanded and unknown semantics", () => {
  const duplicate = plan();
  duplicate.resource_changes[1] = structuredClone(
    duplicate.resource_changes[0],
  );
  expectCode(
    () => validateSavedPlan(duplicate, planContext()),
    "PLAN_ADDRESS_DUPLICATE",
  );
  const publicMember = plan();
  publicMember.resource_changes[3].change.after.member = "allUsers";
  expectCode(
    () => validateSavedPlan(publicMember, planContext()),
    "PLAN_SEMANTIC_MISMATCH",
  );
  const expanded = plan();
  expanded.resource_changes[2].change.after.permissions.push(
    "resourcemanager.projects.setIamPolicy",
  );
  expectCode(
    () => validateSavedPlan(expanded, planContext()),
    "PLAN_SEMANTIC_MISMATCH",
  );
  const noCondition = plan();
  noCondition.resource_changes[3].change.after.condition = [];
  expectCode(
    () => validateSavedPlan(noCondition, planContext()),
    "PLAN_SEMANTIC_MISMATCH",
  );
  const unknown = plan();
  unknown.resource_changes[3].change.after_unknown = { member: true };
  expectCode(
    () => validateSavedPlan(unknown, planContext()),
    "PLAN_UNKNOWN_SECURITY_VALUE",
  );
});

test("default no-change plan validates but cannot execute", () => {
  const noChange = plan({
    resource_changes: [
      {
        address: "google_storage_bucket.evidence",
        change: { actions: ["no-op"] },
      },
    ],
    output_changes: {},
  });
  const result = validateSavedPlan(noChange);
  assert.equal(result.disposition, "default-no-change");
  expectCode(
    () => assertExecuteAuthorized(decision(), result),
    "EXECUTE_BROKER_REQUIRED",
  );
});

test("pending human decision can validate but cannot execute", () => {
  const receipt = validateDecisionReceipt(
    decision({ decision: "review-pending" }),
    decisionContext(),
  ).receipt;
  expectCode(
    () =>
      assertExecuteAuthorized(
        receipt,
        validateSavedPlan(plan(), planContext()),
      ),
    "EXECUTE_BROKER_REQUIRED",
  );
});

test("Google token subject and token command bind the named principal", () => {
  assert.deepEqual(
    validateGoogleIdentity(
      { email: "operator@example.com", email_verified: true },
      PRINCIPAL,
    ),
    { kind: "user", email: "operator@example.com" },
  );
  expectCode(
    () =>
      validateGoogleIdentity(
        { email: "other@example.com", email_verified: true },
        PRINCIPAL,
      ),
    "GOOGLE_IDENTITY_MISMATCH",
  );
  assert.deepEqual(buildTokenCommand(PRINCIPAL).args, [
    "auth",
    "print-access-token",
    "--quiet",
    "--account=operator@example.com",
  ]);
});

test("GCS decision URI must pin a generation and forbid traversal", () => {
  assert.deepEqual(
    parseGcsGenerationUri(
      "gs://vinfast-503003-evidence-dev/authority/decision.json#123",
    ),
    {
      bucket: "vinfast-503003-evidence-dev",
      object: "authority/decision.json",
      generation: "123",
    },
  );
  expectCode(
    () => parseGcsGenerationUri("gs://bucket/authority/../decision.json#123"),
    "DECISION_URI_INVALID",
  );
});

test("local apply invocation remains disabled pending remote signed broker", () => {
  expectCode(
    () =>
      assertExecuteAuthorized(
        decision(),
        validateSavedPlan(plan(), planContext()),
      ),
    "EXECUTE_BROKER_REQUIRED",
  );
});

test("plan validation uses a private content-identical snapshot", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "vfbiz-plan-source-"));
  const source = path.join(directory, "source.tfplan");
  await writeFile(source, "authorized-plan", { mode: 0o600 });
  const snapshot = await createPlanSnapshot(source);
  try {
    await writeFile(source, "replacement-plan", { mode: 0o600 });
    assert.equal(await readFile(snapshot.absolute, "utf8"), "authorized-plan");
    assert.equal(snapshot.sha256, digestBytes("authorized-plan"));
  } finally {
    await removePlanSnapshot(snapshot);
    await rm(directory, { recursive: true, force: true });
  }
  await assert.rejects(() => access(snapshot.absolute));
});

test("completion receipt pseudonymizes the operator principal", () => {
  const receipt = contentFreeReceipt({
    applied: false,
    claimId: CLAIM,
    fencingToken: FENCING,
    planSha256: PLAN_SHA256,
    planDisposition: "create-only",
    decisionSha256: "d".repeat(64),
    decisionGeneration: "123",
    operatorPrincipal: PRINCIPAL,
    nowMs: NOW,
  });
  assert.equal(receipt.operator_principal_sha256, digestBytes(PRINCIPAL));
  assert.equal(receipt.execution_eligible, false);
  assert.ok(!JSON.stringify(receipt).includes("operator@example.com"));
});
