locals {
  tuning_rehearsal_bucket      = "${var.project_id}-tuning-rehearsal-dev"
  tuning_rehearsal_upload_sa   = "vfbiz-ai-tuning-upload"
  tuning_rehearsal_baseline_sa = "vfbiz-ai-tuning-baseline"
  tuning_rehearsal_job_sa      = "vfbiz-ai-tuning-job"
  tuning_candidate_prefix = (
    var.tuning_rehearsal_candidate_manifest_sha256 == ""
    ? ""
    : "candidates/${var.tuning_rehearsal_candidate_manifest_sha256}/gemini"
  )
  tuning_operator_enabled = (
    var.tuning_rehearsal_enabled &&
    var.tuning_rehearsal_operator_member != "" &&
    var.tuning_rehearsal_operator_expires_at != ""
  )
}

resource "google_storage_bucket" "tuning_rehearsal" {
  count                       = var.tuning_rehearsal_enabled ? 1 : 0
  name                        = local.tuning_rehearsal_bucket
  location                    = var.tuning_rehearsal_region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels = merge(var.labels, {
    authority = "synthetic-rehearsal"
    data_use  = "tuning-development"
  })

  versioning {
    enabled = true
  }

  retention_policy {
    retention_period = 86400
    is_locked        = false
  }

  soft_delete_policy {
    retention_duration_seconds = 0
  }

  lifecycle_rule {
    condition {
      age = 21
    }
    action {
      type = "Delete"
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_service_account" "tuning_rehearsal_upload" {
  count        = var.tuning_rehearsal_enabled ? 1 : 0
  account_id   = local.tuning_rehearsal_upload_sa
  display_name = "VFBiz synthetic tuning upload"
  description  = "Create and verify immutable synthetic train/validation objects only."
}

resource "google_service_account" "tuning_rehearsal_baseline" {
  count        = var.tuning_rehearsal_enabled ? 1 : 0
  account_id   = local.tuning_rehearsal_baseline_sa
  display_name = "VFBiz synthetic tuning baseline"
  description  = "Run bounded development-only model prediction without dataset access."
}

resource "google_service_account" "tuning_rehearsal_job" {
  count        = var.tuning_rehearsal_enabled ? 1 : 0
  account_id   = local.tuning_rehearsal_job_sa
  display_name = "VFBiz synthetic tuning job"
  description  = "Create/get/cancel one bounded synthetic tuning job and read exact train/validation objects."
}

resource "google_project_iam_custom_role" "tuning_rehearsal_object_writer" {
  count       = var.tuning_rehearsal_enabled ? 1 : 0
  role_id     = "vfbizTuningRehearsalObjectWriter"
  title       = "VFBiz tuning rehearsal object writer"
  description = "Create and verify synthetic tuning artifacts without list, update, overwrite or delete."
  permissions = [
    "storage.buckets.get",
    "storage.objects.create",
    "storage.objects.get",
  ]
}

resource "google_project_iam_custom_role" "tuning_rehearsal_object_reader" {
  count       = var.tuning_rehearsal_enabled ? 1 : 0
  role_id     = "vfbizTuningRehearsalObjectReader"
  title       = "VFBiz tuning rehearsal object reader"
  description = "Read only the exact synthetic train and validation objects granted on the rehearsal bucket."
  permissions = [
    "storage.buckets.get",
    "storage.objects.get",
  ]
}

resource "google_project_iam_custom_role" "tuning_rehearsal_baseline_predictor" {
  count       = var.tuning_rehearsal_enabled ? 1 : 0
  role_id     = "vfbizTuningRehearsalBaselinePredictor"
  title       = "VFBiz tuning rehearsal baseline predictor"
  description = "Invoke one pinned publisher-model endpoint for bounded synthetic evaluation."
  permissions = [
    "aiplatform.endpoints.predict",
  ]
}

resource "google_project_iam_custom_role" "tuning_rehearsal_job_operator" {
  count       = var.tuning_rehearsal_enabled ? 1 : 0
  role_id     = "vfbizTuningRehearsalJobOperator"
  title       = "VFBiz tuning rehearsal job operator"
  description = "Create, inspect and cancel a bounded tuning job without endpoint deployment authority."
  permissions = [
    "aiplatform.tuningJobs.cancel",
    "aiplatform.tuningJobs.create",
    "aiplatform.tuningJobs.get",
  ]
}

resource "google_storage_bucket_iam_member" "tuning_rehearsal_train_writer" {
  count = (
    var.tuning_rehearsal_enabled &&
    var.tuning_rehearsal_candidate_manifest_sha256 != ""
  ) ? 1 : 0
  bucket = google_storage_bucket.tuning_rehearsal[0].name
  role   = google_project_iam_custom_role.tuning_rehearsal_object_writer[0].id
  member = "serviceAccount:${google_service_account.tuning_rehearsal_upload[0].email}"

  condition {
    title       = "exact_synthetic_train_object"
    description = "Create and verify only the reviewed train JSONL object."
    expression = (
      "resource.name == \"projects/_/buckets/${google_storage_bucket.tuning_rehearsal[0].name}/objects/${local.tuning_candidate_prefix}/train.jsonl\""
    )
  }
}

resource "google_storage_bucket_iam_member" "tuning_rehearsal_validation_writer" {
  count = (
    var.tuning_rehearsal_enabled &&
    var.tuning_rehearsal_candidate_manifest_sha256 != ""
  ) ? 1 : 0
  bucket = google_storage_bucket.tuning_rehearsal[0].name
  role   = google_project_iam_custom_role.tuning_rehearsal_object_writer[0].id
  member = "serviceAccount:${google_service_account.tuning_rehearsal_upload[0].email}"

  condition {
    title       = "exact_synthetic_validation_object"
    description = "Create and verify only the reviewed validation JSONL object."
    expression = (
      "resource.name == \"projects/_/buckets/${google_storage_bucket.tuning_rehearsal[0].name}/objects/${local.tuning_candidate_prefix}/validation.jsonl\""
    )
  }
}

resource "google_storage_bucket_iam_member" "tuning_rehearsal_job_reader" {
  count  = var.tuning_rehearsal_enabled ? 1 : 0
  bucket = google_storage_bucket.tuning_rehearsal[0].name
  role   = google_project_iam_custom_role.tuning_rehearsal_object_reader[0].id
  member = "serviceAccount:${google_service_account.tuning_rehearsal_job[0].email}"
}

resource "google_project_iam_member" "tuning_rehearsal_baseline_predictor" {
  count   = var.tuning_rehearsal_enabled ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.tuning_rehearsal_baseline_predictor[0].id
  member  = "serviceAccount:${google_service_account.tuning_rehearsal_baseline[0].email}"
}

resource "google_project_iam_member" "tuning_rehearsal_job_operator" {
  count   = var.tuning_rehearsal_enabled ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.tuning_rehearsal_job_operator[0].id
  member  = "serviceAccount:${google_service_account.tuning_rehearsal_job[0].email}"
}

resource "google_service_account_iam_member" "tuning_rehearsal_upload_operator" {
  count              = local.tuning_operator_enabled ? 1 : 0
  service_account_id = google_service_account.tuning_rehearsal_upload[0].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = var.tuning_rehearsal_operator_member

  condition {
    title       = "expires_after_bounded_rehearsal"
    description = "Temporary keyless operator access for VFBIZ-0212."
    expression  = "request.time < timestamp(\"${var.tuning_rehearsal_operator_expires_at}\")"
  }
}

resource "google_service_account_iam_member" "tuning_rehearsal_baseline_operator" {
  count              = local.tuning_operator_enabled ? 1 : 0
  service_account_id = google_service_account.tuning_rehearsal_baseline[0].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = var.tuning_rehearsal_operator_member

  condition {
    title       = "expires_after_bounded_rehearsal"
    description = "Temporary keyless operator access for VFBIZ-0212."
    expression  = "request.time < timestamp(\"${var.tuning_rehearsal_operator_expires_at}\")"
  }
}

resource "google_service_account_iam_member" "tuning_rehearsal_job_operator" {
  count              = local.tuning_operator_enabled ? 1 : 0
  service_account_id = google_service_account.tuning_rehearsal_job[0].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = var.tuning_rehearsal_operator_member

  condition {
    title       = "expires_after_bounded_rehearsal"
    description = "Temporary keyless operator access for VFBIZ-0212."
    expression  = "request.time < timestamp(\"${var.tuning_rehearsal_operator_expires_at}\")"
  }
}

output "tuning_rehearsal_bucket" {
  value       = var.tuning_rehearsal_enabled ? google_storage_bucket.tuning_rehearsal[0].name : null
  description = "Private synthetic-only rehearsal bucket."
}

output "tuning_rehearsal_service_accounts" {
  value = var.tuning_rehearsal_enabled ? {
    upload   = google_service_account.tuning_rehearsal_upload[0].email
    baseline = google_service_account.tuning_rehearsal_baseline[0].email
    tuning   = google_service_account.tuning_rehearsal_job[0].email
  } : null
  description = "Separated keyless identities for upload, baseline prediction and tuning."
}
