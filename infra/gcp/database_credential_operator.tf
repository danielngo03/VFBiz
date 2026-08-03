locals {
  database_credential_operator_account_id    = "vfbiz-ai-dev-db-credential"
  database_credential_operator_email         = "${local.database_credential_operator_account_id}@${var.project_id}.iam.gserviceaccount.com"
  database_credential_foundation_plan_sha256 = "9bb0f86fe93f1882ea0a875b31df3295a06d166af1eaf735495ca528d0bfe04f"
  database_credential_postapply_plan_sha256  = "878381f284660f5f4558db53b9baca5ae65dcd5346b1198eee11431fd2b2bb4b"
  database_credential_authority_name         = var.database_credential_authority_sha256 == "" ? "" : "database-bootstrap/admin-credential/authority/v1/${var.database_credential_authority_sha256}.json"
  database_credential_witness_name           = var.database_credential_authority_sha256 == "" ? "" : "database-bootstrap/admin-credential/v1/${var.database_credential_authority_sha256}.json"
  database_credential_authority_packet       = var.database_credential_operator_enabled ? try(jsondecode(data.google_storage_bucket_object_content.database_credential_authority[0].content), {}) : {}
  database_credential_sql_permissions        = toset(["cloudsql.databases.get", "cloudsql.instances.get", "cloudsql.users.update"])
  database_credential_sql_condition          = "resource.name == 'projects/${var.project_id}/instances/${local.database_instance_name}' && resource.type == 'sqladmin.googleapis.com/Instance'"
  database_credential_secret_permissions     = toset(["secretmanager.secrets.get", "secretmanager.versions.access", "secretmanager.versions.add", "secretmanager.versions.list"])
  database_credential_evidence_permissions   = toset(["storage.buckets.get", "storage.objects.create", "storage.objects.get"])
  database_credential_evidence_condition = join(" || ", [
    "resource.name == 'projects/_/buckets/${local.evidence_bucket}'",
    "resource.name == 'projects/_/buckets/${local.evidence_bucket}/objects/${local.database_credential_witness_name}'",
  ])
  database_credential_authority_keys = toset([
    "action", "administrator_secret_id", "administrator_user", "authority_class",
    "claim_id", "database_name", "decided_by_role", "decision", "decision_id",
    "environment", "evidence_bucket", "expires_at", "fencing_token",
    "foundation_plan_sha256", "instance_name", "issued_at", "operator_principal",
    "operator_service_account", "postapply_plan_sha256", "project_id",
    "project_number", "region", "schema_version", "work_item_id",
  ])
  database_credential_authority_digest_matches = var.database_credential_operator_enabled && try(
    sha256(data.google_storage_bucket_object_content.database_credential_authority[0].content) == var.database_credential_authority_sha256,
    false,
  )
  database_credential_authority_generation_matches = var.database_credential_operator_enabled && try(
    tostring(data.google_storage_bucket_object_content.database_credential_authority[0].generation) == var.database_credential_authority_generation,
    false,
  )
  database_credential_authority_packet_binding_valid = var.database_credential_operator_enabled && try(
    toset(keys(local.database_credential_authority_packet)) == local.database_credential_authority_keys &&
    tonumber(local.database_credential_authority_packet.schema_version) == 1 &&
    local.database_credential_authority_packet.work_item_id == "VFBIZ-0216" &&
    local.database_credential_authority_packet.action == "prepare-cloud-sql-bootstrap-credential/apply" &&
    local.database_credential_authority_packet.environment == "development" &&
    local.database_credential_authority_packet.authority_class == "named-human-cloud-operator" &&
    local.database_credential_authority_packet.decision == "authorized" &&
    local.database_credential_authority_packet.decided_by_role == "release-owner" &&
    can(regex("^[a-zA-Z0-9._:/-]{8,256}$", local.database_credential_authority_packet.decision_id)) &&
    local.database_credential_authority_packet.project_id == var.project_id &&
    tostring(local.database_credential_authority_packet.project_number) == var.project_number &&
    local.database_credential_authority_packet.region == var.region &&
    local.database_credential_authority_packet.instance_name == local.database_instance_name &&
    local.database_credential_authority_packet.database_name == local.database_name &&
    local.database_credential_authority_packet.administrator_user == "postgres" &&
    local.database_credential_authority_packet.administrator_secret_id == local.database_bootstrap_secret_id &&
    local.database_credential_authority_packet.evidence_bucket == local.evidence_bucket &&
    local.database_credential_authority_packet.operator_principal == var.database_credential_operator_principal &&
    local.database_credential_authority_packet.operator_service_account == local.database_credential_operator_email &&
    local.database_credential_authority_packet.foundation_plan_sha256 == local.database_credential_foundation_plan_sha256 &&
    local.database_credential_authority_packet.postapply_plan_sha256 == local.database_credential_postapply_plan_sha256 &&
    can(regex("^claim-[a-f0-9-]{36}$", local.database_credential_authority_packet.claim_id)) &&
    tonumber(local.database_credential_authority_packet.fencing_token) > 0 &&
    timecmp(local.database_credential_authority_packet.expires_at, local.database_credential_authority_packet.issued_at) > 0 &&
    timecmp(local.database_credential_authority_packet.expires_at, timeadd(local.database_credential_authority_packet.issued_at, "4h")) <= 0,
    false,
  )
  database_credential_authority_valid_at_plan = var.database_credential_operator_enabled && try(
    timecmp(local.database_credential_authority_packet.issued_at, plantimestamp()) <= 0 &&
    timecmp(local.database_credential_authority_packet.expires_at, plantimestamp()) > 0,
    false,
  )
}

data "google_storage_bucket_object_content" "database_credential_authority" {
  count  = var.database_credential_operator_enabled ? 1 : 0
  bucket = local.evidence_bucket
  name   = local.database_credential_authority_name
}

resource "terraform_data" "database_credential_authority_gate" {
  count = var.database_credential_operator_enabled ? 1 : 0

  lifecycle {
    precondition {
      condition = (
        var.project_id == "vinfast-503003" &&
        var.project_number == "81588547131" &&
        var.region == "asia-southeast1" &&
        var.database_foundation_enabled &&
        can(regex("^[a-f0-9]{64}$", var.database_credential_authority_sha256)) &&
        can(regex("^[1-9][0-9]*$", var.database_credential_authority_generation)) &&
        can(regex("^(user|serviceAccount):[^@[:space:]]+@[^@[:space:]]+$", var.database_credential_operator_principal)) &&
        local.database_credential_authority_digest_matches &&
        local.database_credential_authority_generation_matches &&
        local.database_credential_authority_packet_binding_valid &&
        local.database_credential_authority_valid_at_plan &&
        try(timecmp(local.database_credential_authority_packet.issued_at, timestamp()) <= 0, false) &&
        try(timecmp(local.database_credential_authority_packet.expires_at, timestamp()) > 0, false)
      )
      error_message = "Database credential authority must be an exact, unexpired, externally issued packet bound to the reviewed foundation, named operator, active claim and one Singapore credential action."
    }
  }
}

resource "google_service_account" "database_credential_operator" {
  count        = var.database_credential_operator_enabled ? 1 : 0
  account_id   = local.database_credential_operator_account_id
  display_name = "VFBiz AI development database credential operator"
  depends_on   = [terraform_data.database_credential_authority_gate]
  lifecycle { prevent_destroy = true }
}

resource "google_project_iam_custom_role" "database_credential_sql" {
  count       = var.database_credential_operator_enabled ? 1 : 0
  role_id     = "vfbizAiDatabaseCredentialSql"
  title       = "VFBiz AI database credential SQL operator"
  description = "Inspect the private development database, update one SQL user credential and poll the resulting operation."
  permissions = local.database_credential_sql_permissions
  depends_on  = [terraform_data.database_credential_authority_gate]
  lifecycle { prevent_destroy = true }
}

resource "google_project_iam_member" "database_credential_sql" {
  count   = var.database_credential_operator_enabled ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.database_credential_sql[0].id
  member  = "serviceAccount:${google_service_account.database_credential_operator[0].email}"

  condition {
    title       = "vfbiz-db-credential-exact-instance"
    description = "Limit credential inspection, update and operation polling to the reviewed development instance."
    expression  = local.database_credential_sql_condition
  }
}

resource "google_project_iam_custom_role" "database_credential_secret" {
  count       = var.database_credential_operator_enabled ? 1 : 0
  role_id     = "vfbizAiDatabaseCredentialSecret"
  title       = "VFBiz AI database credential secret operator"
  description = "Inspect one administrator secret, create exactly one version and verify its payload without update or delete authority."
  permissions = local.database_credential_secret_permissions
  depends_on  = [terraform_data.database_credential_authority_gate]
  lifecycle { prevent_destroy = true }
}

resource "google_secret_manager_secret_iam_member" "database_credential_secret" {
  count     = var.database_credential_operator_enabled ? 1 : 0
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_bootstrap_url[0].secret_id
  role      = google_project_iam_custom_role.database_credential_secret[0].id
  member    = "serviceAccount:${google_service_account.database_credential_operator[0].email}"
}

resource "google_project_iam_custom_role" "database_credential_evidence" {
  count       = var.database_credential_operator_enabled ? 1 : 0
  role_id     = "vfbizAiDatabaseCredentialEvidence"
  title       = "VFBiz AI database credential evidence operator"
  description = "Inspect the evidence bucket and create or read exact immutable authority and completion witnesses without list, update or delete authority."
  permissions = local.database_credential_evidence_permissions
  depends_on  = [terraform_data.database_credential_authority_gate]
  lifecycle { prevent_destroy = true }
}

resource "google_storage_bucket_iam_member" "database_credential_evidence" {
  count  = var.database_credential_operator_enabled ? 1 : 0
  bucket = google_storage_bucket.evidence.name
  role   = google_project_iam_custom_role.database_credential_evidence[0].id
  member = "serviceAccount:${google_service_account.database_credential_operator[0].email}"

  condition {
    title       = "vfbiz-db-credential-exact-evidence"
    description = "Allow bucket inspection and one digest-bound completion witness; exclude the authority namespace."
    expression  = local.database_credential_evidence_condition
  }
}

resource "google_service_account_iam_member" "database_credential_impersonation" {
  count              = var.database_credential_operator_enabled ? 1 : 0
  service_account_id = google_service_account.database_credential_operator[0].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = var.database_credential_operator_principal

  condition {
    title       = "vfbiz-db-credential-authority-expiry"
    description = "Permit only the reviewed one-time credential window."
    expression  = "request.time < timestamp(\"${try(local.database_credential_authority_packet.expires_at, "1970-01-01T00:00:00Z")}\")"
  }

  depends_on = [terraform_data.database_credential_authority_gate]
}
