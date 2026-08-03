import { createHash } from "node:crypto";
import { mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export const CONTROLLED_APPLY_WORK_ITEM = "VFBIZ-0218";
export const CONTROLLED_APPLY_ACTION =
  "apply-vfbiz-0217-database-credential-authority";
export const CONTROLLED_APPLY_PROJECT = "vinfast-503003";
export const CONTROLLED_APPLY_PROJECT_NUMBER = "81588547131";
export const CONTROLLED_APPLY_REGION = "asia-southeast1";
export const CONTROLLED_APPLY_PLAN_DIRECTORY = "infra/gcp";
export const CONTROLLED_APPLY_REQUIRED_LEASES = new Map([
  ["agent-control-state", "vfbiz-local-agent-control"],
  ["gcp-vinfast-development", CONTROLLED_APPLY_PROJECT],
  ["terraform-state", "vinfast-503003-vfbiz-ai-development"],
]);
export const CONTROLLED_APPLY_CLAIM_PATHS = new Set([
  "infra/gcp/database_credential_operator.tf",
]);

const FOUNDATION_PLAN_SHA256 =
  "9bb0f86fe93f1882ea0a875b31df3295a06d166af1eaf735495ca528d0bfe04f";
const POSTAPPLY_PLAN_SHA256 =
  "878381f284660f5f4558db53b9baca5ae65dcd5346b1198eee11431fd2b2bb4b";
const SHA256 = /^[a-f0-9]{64}$/;
const CLAIM_ID = /^claim-[a-f0-9-]{36}$/;
const DECISION_ID = /^[a-zA-Z0-9._:/-]{8,256}$/;
const GCS_GENERATION = /^[1-9][0-9]*$/;
const PRINCIPAL = /^(user|serviceAccount):([^@\s]+@[^@\s]+)$/;
const FULL_REVISION = /^[a-f0-9]{40}$/;

const DECISION_KEYS = new Set([
  "action",
  "authority_class",
  "base_revision",
  "claim_id",
  "credential_authority_generation",
  "credential_authority_sha256",
  "decided_by_role",
  "decision",
  "decision_id",
  "expires_at",
  "fencing_token",
  "foundation_plan_sha256",
  "issued_at",
  "operator_principal",
  "plan_path",
  "plan_sha256",
  "postapply_plan_sha256",
  "project_id",
  "project_number",
  "recovery_evidence_sha256",
  "recovery_evidence_uri",
  "region",
  "schema_version",
  "work_item_id",
]);

const RECOVERY_KEYS = new Set([
  "action",
  "administrator_secret_id",
  "administrator_user",
  "authority_class",
  "base_revision",
  "claim_id",
  "credential_authority_generation",
  "credential_authority_sha256",
  "database_name",
  "decided_by_role",
  "decision",
  "decision_id",
  "expires_at",
  "fencing_token",
  "instance_name",
  "issued_at",
  "operator_principal",
  "plan_sha256",
  "project_id",
  "project_number",
  "recovery_protocol_revision_sha256",
  "region",
  "safe_to_retry",
  "schema_version",
  "unknown_outcome_policy",
  "work_item_id",
]);

const CREATE_RESOURCE_ALLOWLIST = new Set([
  "terraform_data.database_credential_authority_gate[0]",
  "google_service_account.database_credential_operator[0]",
  "google_project_iam_custom_role.database_credential_sql[0]",
  "google_project_iam_member.database_credential_sql[0]",
  "google_project_iam_custom_role.database_credential_secret[0]",
  "google_secret_manager_secret_iam_member.database_credential_secret[0]",
  "google_project_iam_custom_role.database_credential_evidence[0]",
  "google_storage_bucket_iam_member.database_credential_evidence[0]",
  "google_service_account_iam_member.database_credential_impersonation[0]",
]);

const CREATE_OUTPUT_ALLOWLIST = new Set([
  "database_credential_operator_service_account",
  "database_credential_authority_object",
  "database_credential_authority_generation",
]);

const READ_RESOURCE_ALLOWLIST = new Set([
  "data.google_storage_bucket_object_content.database_credential_authority[0]",
]);

export class ControlledApplyError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "ControlledApplyError";
    this.code = code;
  }
}

function reject(code, message) {
  throw new ControlledApplyError(code, message);
}

function exactKeys(document, expected) {
  if (!document || typeof document !== "object" || Array.isArray(document))
    return false;
  const observed = new Set(Object.keys(document));
  return (
    observed.size === expected.size &&
    [...expected].every((key) => observed.has(key))
  );
}

function parseTimestamp(value, field) {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed))
    reject("DECISION_TIMESTAMP_INVALID", `${field} must be RFC3339`);
  return parsed;
}

function normalizeRevision(value) {
  if (typeof value !== "string" || !FULL_REVISION.test(value))
    reject("REVISION_INVALID", "revision must be an exact 40-byte Git SHA");
  return value;
}

function sameRevision(left, right) {
  normalizeRevision(left);
  normalizeRevision(right);
  return left === right;
}

function assertDigest(value, field) {
  if (typeof value !== "string" || !SHA256.test(value))
    reject("DECISION_DIGEST_INVALID", `${field} must be lowercase SHA-256`);
}

function assertDecisionIdentity(receipt) {
  if (receipt.schema_version !== 1)
    reject("DECISION_SCHEMA_MISMATCH", "decision schema must be version 1");
  if (
    receipt.work_item_id !== CONTROLLED_APPLY_WORK_ITEM ||
    receipt.action !== CONTROLLED_APPLY_ACTION
  )
    reject("DECISION_SCOPE_MISMATCH", "decision work item or action mismatch");
  if (
    receipt.project_id !== CONTROLLED_APPLY_PROJECT ||
    String(receipt.project_number) !== CONTROLLED_APPLY_PROJECT_NUMBER ||
    receipt.region !== CONTROLLED_APPLY_REGION
  )
    reject("DECISION_TARGET_MISMATCH", "decision GCP target mismatch");
  if (
    receipt.authority_class !== "named-human-cloud-operator" ||
    receipt.decided_by_role !== "release-owner" ||
    !DECISION_ID.test(receipt.decision_id ?? "")
  )
    reject(
      "DECISION_AUTHORITY_INVALID",
      "decision authority is not acceptable",
    );
  if (!["review-pending", "authorized"].includes(receipt.decision))
    reject("DECISION_DISPOSITION_INVALID", "decision disposition is invalid");
}

function assertDecisionBindings(receipt, context) {
  normalizeRevision(receipt.base_revision);
  normalizeRevision(context.baseRevision);
  if (!CLAIM_ID.test(receipt.claim_id ?? ""))
    reject("DECISION_CLAIM_INVALID", "decision claim id is invalid");
  if (
    !Number.isSafeInteger(receipt.fencing_token) ||
    receipt.fencing_token <= 0
  )
    reject("DECISION_FENCING_INVALID", "decision fencing token is invalid");
  if (!PRINCIPAL.test(receipt.operator_principal ?? ""))
    reject("DECISION_PRINCIPAL_INVALID", "decision principal is invalid");
  if (!GCS_GENERATION.test(String(receipt.credential_authority_generation)))
    reject("DECISION_GENERATION_INVALID", "authority generation is invalid");
  if (receipt.foundation_plan_sha256 !== FOUNDATION_PLAN_SHA256)
    reject("DECISION_FOUNDATION_MISMATCH", "foundation plan digest mismatch");
  if (receipt.postapply_plan_sha256 !== POSTAPPLY_PLAN_SHA256)
    reject("DECISION_POSTAPPLY_MISMATCH", "post-apply plan digest mismatch");
  if (receipt.plan_path !== context.planPath)
    reject("DECISION_PLAN_PATH_MISMATCH", "saved plan path mismatch");
  if (receipt.plan_sha256 !== context.planSha256)
    reject("DECISION_PLAN_DIGEST_MISMATCH", "saved plan digest mismatch");
  if (!sameRevision(receipt.base_revision, context.baseRevision))
    reject("DECISION_REVISION_MISMATCH", "decision base revision mismatch");
  if (
    receipt.claim_id !== context.claimId ||
    receipt.fencing_token !== context.fencingToken
  )
    reject("DECISION_CLAIM_MISMATCH", "decision claim or fencing mismatch");
  if (receipt.operator_principal !== context.operatorPrincipal)
    reject("DECISION_PRINCIPAL_MISMATCH", "decision operator mismatch");
  if (
    receipt.credential_authority_sha256 !== context.authoritySha256 ||
    String(receipt.credential_authority_generation) !==
      String(context.authorityGeneration)
  )
    reject("DECISION_INTENT_MISMATCH", "pre-plan authority intent mismatch");
  validateContentAddressedGcsUri(receipt.recovery_evidence_uri, {
    bucket: `${CONTROLLED_APPLY_PROJECT}-evidence-dev`,
    prefix: "database-bootstrap/admin-credential/recovery/v1",
    sha256: receipt.recovery_evidence_sha256,
  });
}

function assertDecisionDigests(receipt) {
  for (const field of [
    "plan_sha256",
    "credential_authority_sha256",
    "recovery_evidence_sha256",
    "foundation_plan_sha256",
    "postapply_plan_sha256",
  ])
    assertDigest(receipt[field], field);
}

function assertDecisionWindow(receipt, nowMs) {
  const issuedAt = parseTimestamp(receipt.issued_at, "issued_at");
  const expiresAt = parseTimestamp(receipt.expires_at, "expires_at");
  if (issuedAt > nowMs || expiresAt <= nowMs)
    reject("DECISION_EXPIRED", "decision is not currently valid");
  if (expiresAt <= issuedAt || expiresAt - issuedAt > 4 * 60 * 60 * 1000)
    reject("DECISION_WINDOW_INVALID", "decision window exceeds four hours");
  return { issuedAt, expiresAt };
}

export function parseDecisionReceipt(value) {
  let receipt;
  try {
    receipt =
      typeof value === "string" ? JSON.parse(value) : structuredClone(value);
  } catch {
    reject("DECISION_JSON_INVALID", "decision receipt is not valid JSON");
  }
  if (!exactKeys(receipt, DECISION_KEYS))
    reject(
      "DECISION_SHAPE_INVALID",
      "decision receipt keys do not match schema",
    );
  return receipt;
}

export function validateDecisionReceipt(receiptValue, context) {
  const receipt = parseDecisionReceipt(receiptValue);
  const nowMs = context.nowMs ?? Date.now();
  assertDecisionIdentity(receipt);
  assertDecisionDigests(receipt);
  assertDecisionBindings(receipt, context);
  const window = assertDecisionWindow(receipt, nowMs);
  return { receipt, window };
}

export function validateRecoveryReceipt(receiptValue, context) {
  const receipt = parseDecisionReceiptWithKeys(receiptValue, RECOVERY_KEYS, {
    invalidJson: "RECOVERY_JSON_INVALID",
    invalidShape: "RECOVERY_SHAPE_INVALID",
  });
  if (
    receipt.schema_version !== 1 ||
    receipt.work_item_id !== "VFBIZ-0216" ||
    receipt.action !== "reconcile-cloud-sql-bootstrap-credential-ambiguity" ||
    receipt.authority_class !== "named-human-cloud-operator" ||
    receipt.decided_by_role !== "release-owner" ||
    receipt.decision !== "recovery-protocol-accepted" ||
    receipt.safe_to_retry !== false ||
    receipt.unknown_outcome_policy !== "fail-closed-no-rerun"
  )
    reject("RECOVERY_AUTHORITY_INVALID", "recovery authority is invalid");
  if (!DECISION_ID.test(receipt.decision_id ?? ""))
    reject("RECOVERY_DECISION_INVALID", "recovery decision id is invalid");
  if (
    receipt.project_id !== CONTROLLED_APPLY_PROJECT ||
    String(receipt.project_number) !== CONTROLLED_APPLY_PROJECT_NUMBER ||
    receipt.region !== CONTROLLED_APPLY_REGION ||
    receipt.instance_name !== "vfbiz-ai-postgres-dev" ||
    receipt.database_name !== "vfbiz_ai" ||
    receipt.administrator_user !== "postgres" ||
    receipt.administrator_secret_id !== "vfbiz-ai-database-bootstrap-url-dev"
  )
    reject("RECOVERY_TARGET_MISMATCH", "recovery target is invalid");
  for (const field of [
    "plan_sha256",
    "credential_authority_sha256",
    "recovery_protocol_revision_sha256",
  ])
    assertDigest(receipt[field], field);
  normalizeRevision(receipt.base_revision);
  if (
    receipt.base_revision !== context.baseRevision ||
    receipt.plan_sha256 !== context.planSha256 ||
    receipt.claim_id !== context.claimId ||
    receipt.fencing_token !== context.fencingToken ||
    receipt.operator_principal !== context.operatorPrincipal ||
    receipt.credential_authority_sha256 !== context.authoritySha256 ||
    String(receipt.credential_authority_generation) !==
      String(context.authorityGeneration)
  )
    reject("RECOVERY_BINDING_MISMATCH", "recovery bindings are invalid");
  if (!CLAIM_ID.test(receipt.claim_id ?? ""))
    reject("RECOVERY_CLAIM_INVALID", "recovery claim is invalid");
  if (
    !Number.isSafeInteger(receipt.fencing_token) ||
    receipt.fencing_token <= 0 ||
    !PRINCIPAL.test(receipt.operator_principal ?? "") ||
    !GCS_GENERATION.test(String(receipt.credential_authority_generation))
  )
    reject("RECOVERY_IDENTITY_INVALID", "recovery identity is invalid");
  assertDecisionWindow(receipt, context.nowMs ?? Date.now());
  return receipt;
}

function parseDecisionReceiptWithKeys(value, keys, codes) {
  let receipt;
  try {
    receipt =
      typeof value === "string" ? JSON.parse(value) : structuredClone(value);
  } catch {
    reject(codes.invalidJson, "receipt is not valid JSON");
  }
  if (!exactKeys(receipt, keys))
    reject(codes.invalidShape, "receipt keys do not match schema");
  return receipt;
}

function isActive(record, nowMs, minimumRemainingMs) {
  return (
    record?.state === "active" &&
    Date.parse(record.expiresAt) > nowMs + minimumRemainingMs
  );
}

function findActiveLease(state, claim, resourceClass, resourceKey, context) {
  const lease = (state.leases ?? []).find(
    (candidate) =>
      claim.leaseIds.includes(candidate.leaseId) &&
      candidate.holderClaimId === claim.claimId &&
      candidate.resourceClass === resourceClass &&
      candidate.resourceKey === resourceKey,
  );
  if (!isActive(lease, context.nowMs, context.minimumRemainingMs))
    reject(
      "LEASE_NOT_ACTIVE",
      `required lease is not active: ${resourceClass}/${resourceKey}`,
    );
  if (!sameRevision(lease.baseRevision, context.baseRevision))
    reject("LEASE_REVISION_MISMATCH", "lease base revision mismatch");
  return lease;
}

export function validateExecutionState(state, context) {
  const nowMs = context.nowMs ?? Date.now();
  const minimumRemainingMs = context.minimumRemainingMs ?? 5 * 60 * 1000;
  const claim = (state.claims ?? []).find(
    (candidate) => candidate.claimId === context.claimId,
  );
  if (!isActive(claim, nowMs, minimumRemainingMs))
    reject("CLAIM_NOT_ACTIVE", "execution claim is not active long enough");
  if (
    claim.workItemKey !== CONTROLLED_APPLY_WORK_ITEM ||
    claim.runMode !== "scoped-write" ||
    claim.ownerTeam !== "agent-platform" ||
    claim.accountableHumanRole !== "release-owner"
  )
    reject("CLAIM_SCOPE_MISMATCH", "execution claim has the wrong scope");
  if (claim.fencingToken !== context.fencingToken)
    reject("CLAIM_FENCING_MISMATCH", "execution fencing token is stale");
  if (!sameRevision(claim.baseRevision, context.baseRevision))
    reject("CLAIM_REVISION_MISMATCH", "execution claim revision mismatch");
  if (
    !Array.isArray(claim.allowedPaths) ||
    claim.allowedPaths.length !== CONTROLLED_APPLY_CLAIM_PATHS.size ||
    !claim.allowedPaths.every((entry) =>
      CONTROLLED_APPLY_CLAIM_PATHS.has(entry),
    )
  )
    reject("CLAIM_PATH_MISMATCH", "execution claim paths are not exact");
  const leaseContext = {
    nowMs,
    minimumRemainingMs,
    baseRevision: context.baseRevision,
  };
  const leases = [...CONTROLLED_APPLY_REQUIRED_LEASES].map(([kind, key]) =>
    findActiveLease(state, claim, kind, key, leaseContext),
  );
  return { claim, leases };
}

function actionKey(actions) {
  return JSON.stringify(actions ?? []);
}

function sameSet(actual, expected) {
  return (
    Array.isArray(actual) &&
    actual.length === expected.size &&
    actual.every((entry) => expected.has(entry))
  );
}

function assertExactValue(actual, expected, field) {
  if (JSON.stringify(actual) !== JSON.stringify(expected))
    reject("PLAN_SEMANTIC_MISMATCH", `${field} is not exact`);
}

function assertKnown(change, fields) {
  for (const field of fields)
    if (change.change?.after_unknown?.[field])
      reject("PLAN_UNKNOWN_SECURITY_VALUE", `${change.address}.${field}`);
}

function expectedRole(project, roleId) {
  return `projects/${project}/roles/${roleId}`;
}

function planIdentity(context) {
  const project = CONTROLLED_APPLY_PROJECT;
  const serviceAccount =
    "vfbiz-ai-dev-db-credential@vinfast-503003.iam.gserviceaccount.com";
  const member = `serviceAccount:${serviceAccount}`;
  const witness =
    `resource.name == 'projects/_/buckets/${project}-evidence-dev' || ` +
    `resource.name == 'projects/_/buckets/${project}-evidence-dev/objects/` +
    `database-bootstrap/admin-credential/v1/${context.authoritySha256}.json'`;
  return {
    project,
    serviceAccount,
    member,
    witness,
    sqlRole: expectedRole(project, "vfbizAiDatabaseCredentialSql"),
    secretRole: expectedRole(project, "vfbizAiDatabaseCredentialSecret"),
    evidenceRole: expectedRole(project, "vfbizAiDatabaseCredentialEvidence"),
  };
}

function validateCustomRole(change, after, identity, specification) {
  assertKnown(change, ["project", "role_id", "permissions"]);
  assertExactValue(
    [after.project, after.role_id],
    [identity.project, specification.roleId],
    `${specification.name} role identity`,
  );
  if (!sameSet(after.permissions, new Set(specification.permissions)))
    reject(
      "PLAN_SEMANTIC_MISMATCH",
      `${specification.name} permissions are not exact`,
    );
}

function validateSqlBinding(change, after, identity) {
  assertKnown(change, ["project", "role", "member", "condition"]);
  assertExactValue(
    [after.project, after.role, after.member, after.condition],
    [
      identity.project,
      identity.sqlRole,
      identity.member,
      [
        {
          title: "vfbiz-db-credential-exact-instance",
          description:
            "Limit credential inspection, update and operation polling to the reviewed development instance.",
          expression:
            "resource.name == 'projects/vinfast-503003/instances/vfbiz-ai-postgres-dev' && resource.type == 'sqladmin.googleapis.com/Instance'",
        },
      ],
    ],
    "SQL IAM binding",
  );
}

function validateEvidenceBinding(change, after, identity) {
  assertKnown(change, ["bucket", "role", "member", "condition"]);
  assertExactValue(
    [after.bucket, after.role, after.member, after.condition],
    [
      `${identity.project}-evidence-dev`,
      identity.evidenceRole,
      identity.member,
      [
        {
          title: "vfbiz-db-credential-exact-evidence",
          description:
            "Allow bucket inspection and one digest-bound completion witness; exclude the authority namespace.",
          expression: identity.witness,
        },
      ],
    ],
    "evidence IAM binding",
  );
}

function validateImpersonationBinding(change, after, context, identity) {
  assertKnown(change, ["service_account_id", "role", "member", "condition"]);
  assertExactValue(
    [after.service_account_id, after.role, after.member, after.condition],
    [
      `projects/${identity.project}/serviceAccounts/${identity.serviceAccount}`,
      "roles/iam.serviceAccountTokenCreator",
      context.operatorPrincipal,
      [
        {
          title: "vfbiz-db-credential-authority-expiry",
          description: "Permit only the reviewed one-time credential window.",
          expression: `request.time < timestamp(\"${context.authorityExpiresAt}\")`,
        },
      ],
    ],
    "impersonation IAM binding",
  );
}

function createSemanticChecks(change, after, context, identity) {
  return {
    "terraform_data.database_credential_authority_gate[0]": () => {
      assertKnown(change, ["input", "triggers_replace"]);
      assertExactValue(after.input ?? null, null, "authority gate input");
      assertExactValue(
        after.triggers_replace ?? null,
        null,
        "authority gate replacement",
      );
    },
    "google_service_account.database_credential_operator[0]": () => {
      assertKnown(change, ["account_id", "project"]);
      assertExactValue(
        [after.account_id, after.project],
        ["vfbiz-ai-dev-db-credential", identity.project],
        "operator service account",
      );
    },
    "google_project_iam_custom_role.database_credential_sql[0]": () =>
      validateCustomRole(change, after, identity, {
        name: "SQL",
        roleId: "vfbizAiDatabaseCredentialSql",
        permissions: [
          "cloudsql.databases.get",
          "cloudsql.instances.get",
          "cloudsql.users.update",
        ],
      }),
    "google_project_iam_member.database_credential_sql[0]": () =>
      validateSqlBinding(change, after, identity),
    "google_project_iam_custom_role.database_credential_secret[0]": () =>
      validateCustomRole(change, after, identity, {
        name: "secret",
        roleId: "vfbizAiDatabaseCredentialSecret",
        permissions: [
          "secretmanager.secrets.get",
          "secretmanager.versions.access",
          "secretmanager.versions.add",
          "secretmanager.versions.list",
        ],
      }),
    "google_secret_manager_secret_iam_member.database_credential_secret[0]":
      () => {
        assertKnown(change, ["project", "secret_id", "role", "member"]);
        assertExactValue(
          [after.project, after.secret_id, after.role, after.member],
          [
            identity.project,
            "vfbiz-ai-database-bootstrap-url-dev",
            identity.secretRole,
            identity.member,
          ],
          "secret IAM binding",
        );
      },
    "google_project_iam_custom_role.database_credential_evidence[0]": () =>
      validateCustomRole(change, after, identity, {
        name: "evidence",
        roleId: "vfbizAiDatabaseCredentialEvidence",
        permissions: [
          "storage.buckets.get",
          "storage.objects.create",
          "storage.objects.get",
        ],
      }),
    "google_storage_bucket_iam_member.database_credential_evidence[0]": () =>
      validateEvidenceBinding(change, after, identity),
    "google_service_account_iam_member.database_credential_impersonation[0]":
      () => validateImpersonationBinding(change, after, context, identity),
  };
}

function validateCreateSemantics(change, context) {
  const after = change.change?.after;
  if (!after || typeof after !== "object")
    reject("PLAN_SEMANTIC_MISMATCH", `${change.address} lacks after values`);
  const checks = createSemanticChecks(
    change,
    after,
    context,
    planIdentity(context),
  );
  const check = checks[change.address];
  if (!check)
    reject("PLAN_ACTION_FORBIDDEN", `forbidden plan action: ${change.address}`);
  check();
}

export function validateSavedPlan(plan, semanticContext = {}) {
  if (
    !plan ||
    typeof plan !== "object" ||
    !Array.isArray(plan.resource_changes)
  )
    reject("PLAN_JSON_INVALID", "saved plan JSON is incomplete");
  const creates = new Set();
  const reads = new Set();
  const observedAddresses = new Set();
  for (const change of plan.resource_changes) {
    if (observedAddresses.has(change.address))
      reject("PLAN_ADDRESS_DUPLICATE", `duplicate address: ${change.address}`);
    observedAddresses.add(change.address);
    const actions = actionKey(change.change?.actions);
    if (actions === '["no-op"]') continue;
    if (actions === '["read"]' && READ_RESOURCE_ALLOWLIST.has(change.address)) {
      reads.add(change.address);
      continue;
    }
    if (
      actions !== '["create"]' ||
      !CREATE_RESOURCE_ALLOWLIST.has(change.address)
    )
      reject(
        "PLAN_ACTION_FORBIDDEN",
        `forbidden plan action: ${change.address}`,
      );
    creates.add(change.address);
  }
  const createCount = creates.size;
  if (createCount > 0) {
    if (!sameSet([...creates], CREATE_RESOURCE_ALLOWLIST))
      reject(
        "PLAN_CREATE_SET_INCOMPLETE",
        "credential create set is incomplete",
      );
    if (!sameSet([...reads], READ_RESOURCE_ALLOWLIST))
      reject("PLAN_READ_SET_INCOMPLETE", "authority read set is incomplete");
    if (
      typeof semanticContext.operatorPrincipal !== "string" ||
      typeof semanticContext.authorityExpiresAt !== "string" ||
      !SHA256.test(semanticContext.authoritySha256 ?? "")
    )
      reject(
        "PLAN_SEMANTIC_CONTEXT_MISSING",
        "plan semantics lack authority context",
      );
    for (const change of plan.resource_changes)
      if (actionKey(change.change?.actions) === '["create"]')
        validateCreateSemantics(change, semanticContext);
  } else if (reads.size > 0) {
    reject("PLAN_READ_WITHOUT_CREATE", "authority read cannot stand alone");
  }
  const changedOutputs = new Set();
  for (const [name, change] of Object.entries(plan.output_changes ?? {})) {
    const actions = actionKey(change.actions);
    if (actions === '["no-op"]') continue;
    if (actions !== '["create"]' || !CREATE_OUTPUT_ALLOWLIST.has(name))
      reject("PLAN_OUTPUT_FORBIDDEN", `forbidden output action: ${name}`);
    changedOutputs.add(name);
  }
  if (
    (createCount > 0 &&
      !sameSet([...changedOutputs], CREATE_OUTPUT_ALLOWLIST)) ||
    (createCount === 0 && changedOutputs.size > 0)
  )
    reject("PLAN_OUTPUT_SET_INCOMPLETE", "credential output set is incomplete");
  return {
    disposition: createCount === 0 ? "default-no-change" : "create-only",
    createCount,
    resourceCount: plan.resource_changes.length,
  };
}

function flattenPlannedResources(module, result = []) {
  if (!module || typeof module !== "object") return result;
  result.push(...(module.resources ?? []));
  for (const child of module.child_modules ?? [])
    flattenPlannedResources(child, result);
  return result;
}

export function extractCredentialAuthority(plan) {
  const resource = flattenPlannedResources(
    plan?.planned_values?.root_module,
  ).find(
    (candidate) =>
      candidate.address ===
      "data.google_storage_bucket_object_content.database_credential_authority[0]",
  );
  const content = resource?.values?.content;
  const generation = String(resource?.values?.generation ?? "");
  if (typeof content !== "string" || !GCS_GENERATION.test(generation))
    reject(
      "PLAN_AUTHORITY_MISSING",
      "saved plan lacks pinned authority intent",
    );
  return { sha256: digestBytes(content), generation, content };
}

export function assertExecuteAuthorized(receipt, planResult) {
  void receipt;
  void planResult;
  reject(
    "EXECUTE_BROKER_REQUIRED",
    "local execution is disabled until remote signed authority is available",
  );
}

export function principalEmail(principal) {
  const match = PRINCIPAL.exec(principal ?? "");
  if (!match) reject("PRINCIPAL_INVALID", "principal is invalid");
  return { kind: match[1], email: match[2] };
}

export function buildTokenCommand(principal) {
  const identity = principalEmail(principal);
  const args = ["auth", "print-access-token", "--quiet"];
  if (identity.kind === "user") args.push(`--account=${identity.email}`);
  else args.push(`--impersonate-service-account=${identity.email}`);
  return { file: "gcloud", args, identity };
}

export function validateGoogleIdentity(document, principal) {
  const expected = principalEmail(principal);
  if (
    !document ||
    typeof document !== "object" ||
    document.email !== expected.email ||
    document.email_verified !== true
  )
    reject("GOOGLE_IDENTITY_MISMATCH", "Google token subject mismatch");
  return expected;
}

export function parseGcsGenerationUri(value) {
  const match =
    /^gs:\/\/([a-z0-9][a-z0-9._-]{1,221})\/(.+)#([1-9][0-9]*)$/.exec(
      value ?? "",
    );
  if (!match || match[2].includes(".."))
    reject("DECISION_URI_INVALID", "decision URI must pin one GCS generation");
  return { bucket: match[1], object: match[2], generation: match[3] };
}

export function validateContentAddressedGcsUri(value, expected) {
  const parsed = parseGcsGenerationUri(value);
  const expectedObject = `${expected.prefix}/${expected.sha256}.json`;
  if (parsed.bucket !== expected.bucket || parsed.object !== expectedObject)
    reject(
      "GCS_OBJECT_SCOPE_MISMATCH",
      "GCS object is outside its authority namespace",
    );
  return parsed;
}

export function digestBytes(value) {
  return createHash("sha256").update(value).digest("hex");
}

export async function digestFile(file) {
  return digestBytes(await readFile(file));
}

export async function createPlanSnapshot(source) {
  const bytes = await readFile(source);
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "vfbiz-controlled-plan-"),
  );
  const absolute = path.join(directory, "authorized.tfplan");
  await writeFile(absolute, bytes, { flag: "wx", mode: 0o400 });
  return { absolute, sha256: digestBytes(bytes), directory };
}

export async function removePlanSnapshot(snapshot) {
  if (snapshot?.directory)
    await rm(snapshot.directory, { recursive: true, force: true });
}

export async function resolvePlanPath(root, requested) {
  const planRoot = await realpath(
    path.join(root, CONTROLLED_APPLY_PLAN_DIRECTORY),
  );
  const candidate = await realpath(path.resolve(root, requested));
  if (
    !candidate.startsWith(`${planRoot}${path.sep}`) ||
    !candidate.endsWith(".tfplan")
  )
    reject("PLAN_PATH_INVALID", "saved plan must be inside infra/gcp");
  return {
    absolute: candidate,
    repositoryRelative: path
      .relative(root, candidate)
      .split(path.sep)
      .join("/"),
    tofuRelative: path.relative(planRoot, candidate).split(path.sep).join("/"),
  };
}

export function buildApplyInvocation(plan, accessToken) {
  void plan;
  void accessToken;
  reject("EXECUTE_BROKER_REQUIRED", "local apply invocation is disabled");
}

export function contentFreeReceipt(context) {
  return {
    schema_version: 1,
    applied: Boolean(context.applied),
    execution_eligible: false,
    work_item_id: CONTROLLED_APPLY_WORK_ITEM,
    claim_id: context.claimId,
    fencing_token: context.fencingToken,
    plan_sha256: context.planSha256,
    plan_disposition: context.planDisposition,
    decision_sha256: context.decisionSha256,
    decision_generation: context.decisionGeneration,
    operator_principal_sha256: digestBytes(context.operatorPrincipal),
    observed_at: new Date(context.nowMs ?? Date.now()).toISOString(),
  };
}
