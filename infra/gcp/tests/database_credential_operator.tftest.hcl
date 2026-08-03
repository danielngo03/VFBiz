mock_provider "google" {}

override_resource {
  target = google_compute_network.database
  values = { id = "projects/vinfast-503003/global/networks/vfbiz-ai-database-dev" }
}

override_resource {
  target = google_service_account.push
  values = {
    name  = "projects/vinfast-503003/serviceAccounts/vfbiz-ai-dev-push@vinfast-503003.iam.gserviceaccount.com"
    email = "vfbiz-ai-dev-push@vinfast-503003.iam.gserviceaccount.com"
  }
}

override_resource {
  target = google_service_account.vertex_smoke
  values = {
    name  = "projects/vinfast-503003/serviceAccounts/vfbiz-vertex-smoke@vinfast-503003.iam.gserviceaccount.com"
    email = "vfbiz-vertex-smoke@vinfast-503003.iam.gserviceaccount.com"
  }
}

override_resource {
  target = google_service_account.database_credential_operator
  values = {
    name  = "projects/vinfast-503003/serviceAccounts/vfbiz-ai-dev-db-credential@vinfast-503003.iam.gserviceaccount.com"
    email = "vfbiz-ai-dev-db-credential@vinfast-503003.iam.gserviceaccount.com"
  }
}

variables {
  project_id                             = "vinfast-503003"
  project_number                         = "81588547131"
  billing_account_id                     = "000000-000000-000000"
  document_ai_processor_id               = "4d2384d940a52fa5"
  database_foundation_enabled            = true
  database_credential_operator_principal = "user:operator@example.com"
}

run "disabled_lane_creates_nothing" {
  command = plan
  variables { database_credential_operator_enabled = false }

  assert {
    condition     = length(google_service_account.database_credential_operator) == 0
    error_message = "Disabled authority must not create a service account."
  }
  assert {
    condition     = length(google_service_account_iam_member.database_credential_impersonation) == 0
    error_message = "Disabled authority must not grant impersonation."
  }
}

run "permission_contract_is_bounded" {
  command = plan
  variables {
    database_credential_operator_enabled     = true
    database_credential_authority_generation = "122"
    database_credential_authority_sha256     = sha256("{}")
  }
  override_data {
    target = data.google_storage_bucket_object_content.database_credential_authority
    values = { generation = 123, content = "{}" }
  }
  expect_failures = [terraform_data.database_credential_authority_gate[0]]

  assert {
    condition = local.database_credential_sql_permissions == toset([
      "cloudsql.databases.get", "cloudsql.instances.get", "cloudsql.users.update",
    ])
    error_message = "SQL permissions must match the exact three-action contract."
  }
  assert {
    condition = local.database_credential_sql_condition == (
      "resource.name == 'projects/vinfast-503003/instances/vfbiz-ai-postgres-dev' && resource.type == 'sqladmin.googleapis.com/Instance'"
    )
    error_message = "SQL permission binding must be scoped to the exact reviewed Cloud SQL instance."
  }
  assert {
    condition = local.database_credential_secret_permissions == toset([
      "secretmanager.secrets.get", "secretmanager.versions.access", "secretmanager.versions.add", "secretmanager.versions.list",
    ])
    error_message = "Secret permissions exceed the administrator-secret contract."
  }
  assert {
    condition = local.database_credential_evidence_permissions == toset([
      "storage.buckets.get", "storage.objects.create", "storage.objects.get",
    ])
    error_message = "Evidence permissions must not include list, update or delete."
  }
  assert {
    condition = (
      strcontains(local.database_credential_evidence_condition, local.database_credential_witness_name) &&
      !strcontains(local.database_credential_evidence_condition, "/authority/")
    )
    error_message = "Evidence IAM condition must allow only the exact completion witness and exclude the authority namespace."
  }
}

run "generation_mismatch_fails_closed_before_identity" {
  command = plan
  variables {
    database_credential_operator_enabled     = true
    database_credential_authority_generation = "122"
    database_credential_authority_sha256     = sha256("{}")
  }
  override_data {
    target = data.google_storage_bucket_object_content.database_credential_authority
    values = { generation = 123, content = "{}" }
  }
  expect_failures = [terraform_data.database_credential_authority_gate[0]]

  assert {
    condition     = local.database_credential_authority_digest_matches
    error_message = "Generation mismatch fixture must still match the supplied content digest."
  }
  assert {
    condition     = !local.database_credential_authority_generation_matches
    error_message = "Generation mismatch fixture must exercise the generation predicate."
  }
}

run "expired_exact_shape_packet_fails_closed" {
  command = plan
  variables {
    database_credential_operator_enabled     = true
    database_credential_authority_generation = "123"
    database_credential_authority_sha256     = "a5a447d5c63bd06d1bcd12089356ca2932a4cb539a72f39a08397d878414d851"
  }
  override_data {
    target = data.google_storage_bucket_object_content.database_credential_authority
    values = {
      generation = 123
      content    = "{\"action\":\"prepare-cloud-sql-bootstrap-credential/apply\",\"administrator_secret_id\":\"vfbiz-ai-database-bootstrap-url-dev\",\"administrator_user\":\"postgres\",\"authority_class\":\"named-human-cloud-operator\",\"claim_id\":\"claim-11111111-1111-1111-1111-111111111111\",\"database_name\":\"vfbiz_ai\",\"decided_by_role\":\"release-owner\",\"decision\":\"authorized\",\"decision_id\":\"decision/VFBIZ-0216/expired-authority\",\"environment\":\"development\",\"evidence_bucket\":\"vinfast-503003-evidence-dev\",\"expires_at\":\"2020-01-01T01:00:00Z\",\"fencing_token\":401,\"foundation_plan_sha256\":\"9bb0f86fe93f1882ea0a875b31df3295a06d166af1eaf735495ca528d0bfe04f\",\"instance_name\":\"vfbiz-ai-postgres-dev\",\"issued_at\":\"2020-01-01T00:00:00Z\",\"operator_principal\":\"user:operator@example.com\",\"operator_service_account\":\"vfbiz-ai-dev-db-credential@vinfast-503003.iam.gserviceaccount.com\",\"postapply_plan_sha256\":\"878381f284660f5f4558db53b9baca5ae65dcd5346b1198eee11431fd2b2bb4b\",\"project_id\":\"vinfast-503003\",\"project_number\":\"81588547131\",\"region\":\"asia-southeast1\",\"schema_version\":1,\"work_item_id\":\"VFBIZ-0216\"}"
    }
  }
  expect_failures = [terraform_data.database_credential_authority_gate[0]]

  assert {
    condition     = local.database_credential_authority_digest_matches && local.database_credential_authority_generation_matches
    error_message = "Expired fixture must have a matching digest and generation."
  }
  assert {
    condition     = local.database_credential_authority_packet_binding_valid
    error_message = "Expired fixture must satisfy every non-temporal packet binding."
  }
  assert {
    condition     = !local.database_credential_authority_valid_at_plan
    error_message = "Expired fixture must fail specifically at the plan-time validity window."
  }
}
