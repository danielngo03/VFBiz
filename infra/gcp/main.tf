locals {
  iam_contract           = jsondecode(file("${path.module}/iam-contract.json"))
  intake_bucket          = "${var.project_id}-intake-dev"
  derived_bucket         = "${var.project_id}-derived-dev"
  ocr_output_bucket      = "${var.project_id}-ocr-output-dev"
  ocr_output_bucket_name = var.ocr_output_bucket_enabled ? google_storage_bucket.ocr_output[0].name : ""
  evidence_bucket        = "${var.project_id}-evidence-dev"
  worker_sa              = "vfbiz-ai-dev-worker"
  push_sa                = "vfbiz-ai-dev-push"
  reconciler_sa          = "vfbiz-ai-dev-reconciler"
  scheduler_sa           = "vfbiz-ai-dev-scheduler"
  intake_topic           = "vinfast-document-intake-dev"
  dead_letter_topic      = "vinfast-document-intake-dlq-dev"
  worker_sub             = "vinfast-document-worker-dev"
  worker_repository      = "vfbiz-ai-workers-dev"
  ingestion_activation_packet_ready = (
    can(regex("^[a-f0-9]{64}$", var.ingestion_activation_authority_sha256)) &&
    can(regex("^[1-9][0-9]*$", var.ingestion_activation_authority_generation)) &&
    can(regex("^[a-f0-9]{64}$", var.ingestion_saved_plan_sha256)) &&
    can(regex("^[a-f0-9]{64}$", var.ingestion_rollback_image_sha256)) &&
    can(regex("^[a-f0-9]{64}$", var.ingestion_risk_disposition_sha256)) &&
    can(regex(
      "^(evidence|decision)://[A-Za-z0-9._:/-]{1,255}$",
      var.ingestion_risk_disposition_reference,
    ))
  )
  pubsub_service_agent = "service-${var.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  worker_database_secret_id = (
    var.database_foundation_enabled
    ? local.database_submitter_secret_id
    : var.worker_database_url_secret_id
  )
  reconciler_database_secret_id = (
    var.database_foundation_enabled
    ? local.database_reconciler_secret_id
    : var.reconciler_database_url_secret_id
  )
  worker_service_enabled = (
    var.database_foundation_enabled &&
    var.worker_image != "" &&
    local.worker_database_secret_id != "" &&
    var.worker_database_url_secret_version != "" &&
    length(var.synthetic_smoke_manifest) > 0 &&
    local.ingestion_activation_packet_ready
  )
  worker_dispatch_enabled = local.worker_service_enabled && var.worker_dispatch_enabled
  reconciler_service_enabled = (
    var.database_foundation_enabled &&
    var.worker_image != "" &&
    local.reconciler_database_secret_id != "" &&
    var.reconciler_database_url_secret_version != "" &&
    length(var.synthetic_smoke_manifest) > 0 &&
    local.ingestion_activation_packet_ready
  )
  reconciler_schedule_enabled = (
    local.reconciler_service_enabled && var.reconciler_schedule_enabled
  )

  required_project_services = setunion(
    toset([
      "aiplatform.googleapis.com",
      "artifactregistry.googleapis.com",
      "cloudscheduler.googleapis.com",
      "documentai.googleapis.com",
      "iam.googleapis.com",
      "pubsub.googleapis.com",
      "run.googleapis.com",
      "secretmanager.googleapis.com",
      "storage.googleapis.com",
    ]),
    var.database_foundation_enabled ? toset([
      "compute.googleapis.com",
      "servicenetworking.googleapis.com",
      "sqladmin.googleapis.com",
    ]) : toset([]),
  )
}

resource "google_project_service" "required" {
  for_each = local.required_project_services

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "intake" {
  name                        = local.intake_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = var.labels

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_artifact_registry_repository" "workers" {
  location      = var.region
  repository_id = local.worker_repository
  description   = "Immutable VFBiz AI development worker images"
  format        = "DOCKER"
  labels        = var.labels

  # Keep cleanup observable but non-destructive until deployed and rollback
  # image digests are protected by a reviewed retention policy.
  cleanup_policy_dry_run = true

  cleanup_policies {
    id     = "delete-untagged-after-seven-days"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s"
    }
  }

  cleanup_policies {
    id     = "keep-ten-recent-images"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket" "derived" {
  name                        = local.derived_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = var.labels

  versioning {
    enabled = true
  }

  # Worker-staged Document AI input objects are retained during development
  # until the retention gate opens; the worker intentionally has no delete
  # authority. Raw Document AI output is stored in the dedicated OCR bucket
  # below, so this bucket is never the reconciler's list boundary.
  soft_delete_policy {
    retention_duration_seconds = var.enable_derived_output_expiry ? 0 : 604800
  }

  dynamic "lifecycle_rule" {
    for_each = var.enable_derived_output_expiry ? [1] : []
    content {
      condition {
        age        = 7
        with_state = "LIVE"
      }
      action {
        type = "Delete"
      }
    }
  }

  dynamic "lifecycle_rule" {
    for_each = var.enable_derived_output_expiry ? [1] : []
    content {
      condition {
        days_since_noncurrent_time = 1
        with_state                 = "ARCHIVED"
      }
      action {
        type = "Delete"
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket" "ocr_output" {
  count                       = var.ocr_output_bucket_enabled ? 1 : 0
  name                        = local.ocr_output_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = var.labels

  versioning {
    enabled = true
  }

  # Keep Document AI's raw OCR output in a bucket dedicated to the
  # reconciler.  Bucket-level list permission is therefore bounded by the
  # resource boundary; no prefix-based list condition is relied upon.
  soft_delete_policy {
    retention_duration_seconds = var.enable_derived_output_expiry ? 0 : 604800
  }

  dynamic "lifecycle_rule" {
    for_each = var.enable_derived_output_expiry ? [1] : []
    content {
      condition {
        age        = 7
        with_state = "LIVE"
      }
      action {
        type = "Delete"
      }
    }
  }

  dynamic "lifecycle_rule" {
    for_each = var.enable_derived_output_expiry ? [1] : []
    content {
      condition {
        days_since_noncurrent_time = 1
        with_state                 = "ARCHIVED"
      }
      action {
        type = "Delete"
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket" "evidence" {
  name                        = local.evidence_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = var.labels

  versioning {
    enabled = true
  }

  # A smoke manifest is valid for at most one hour. Retaining its external
  # dispatch witness for a full day prevents delete-and-recreate replay even
  # if the local sealed ledger and anchor are both lost.
  retention_policy {
    retention_period = 86400
    is_locked        = false
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_service_account" "worker" {
  account_id   = local.worker_sa
  display_name = "VFBiz AI development worker"
}

resource "google_service_account" "push" {
  account_id   = local.push_sa
  display_name = "VFBiz AI development Pub/Sub push identity"
}

resource "google_service_account" "reconciler" {
  account_id   = local.reconciler_sa
  display_name = "VFBiz AI development Document AI reconciler"
}

resource "google_service_account" "scheduler" {
  account_id   = local.scheduler_sa
  display_name = "VFBiz AI development reconciliation scheduler"
}

resource "google_project_iam_custom_role" "worker_object_reader" {
  role_id     = "vfbizAiObjectReader"
  title       = "VFBiz AI object reader"
  description = "Read one explicitly addressed GCS object without list or mutation rights."
  permissions = ["storage.objects.get"]
}

resource "google_project_iam_custom_role" "worker_staging_writer" {
  role_id     = "vfbizAiStagingWriter"
  title       = "VFBiz AI staging writer"
  description = "Create and verify derived OCR objects without update or delete rights."
  permissions = ["storage.objects.create", "storage.objects.get"]
}

resource "google_project_iam_custom_role" "reconciler_output_reader" {
  role_id     = "vfbizAiReconcilerOutputReader"
  title       = "VFBiz AI reconciler output reader"
  description = "List and read exact Document AI output objects in the dedicated OCR bucket."
  permissions = local.iam_contract.reconciler_derived_output_reader
}

resource "google_project_iam_custom_role" "worker_document_ai_submitter" {
  role_id     = "vfbizAiDocumentSubmitter"
  title       = "VFBiz AI Document AI batch submitter"
  description = "Submit one processor-version-scoped asynchronous OCR batch."
  permissions = local.iam_contract.worker_document_ai_submitter
}

resource "google_project_iam_custom_role" "reconciler_document_ai_operation_reader" {
  role_id     = "vfbizAiDocumentOperationReader"
  title       = "VFBiz AI Document AI operation reader"
  description = "Read legacy Document AI operation state without submit or review rights."
  permissions = local.iam_contract.reconciler_document_ai_operation_reader
}

resource "google_storage_bucket_iam_member" "worker_intake_reader" {
  count  = local.worker_service_enabled ? 1 : 0
  bucket = google_storage_bucket.intake.name
  role   = google_project_iam_custom_role.worker_object_reader.id
  member = "serviceAccount:${google_service_account.worker.email}"

  condition {
    title       = "content-addressed-intake-only"
    description = "Worker may read only immutable content-addressed intake objects."
    expression  = "resource.name.startsWith('projects/_/buckets/${local.intake_bucket}/objects/sha256/')"
  }
}

resource "google_storage_bucket_iam_member" "worker_derived_writer" {
  count  = local.worker_service_enabled ? 1 : 0
  bucket = google_storage_bucket.derived.name
  role   = google_project_iam_custom_role.worker_staging_writer.id
  member = "serviceAccount:${google_service_account.worker.email}"

  condition {
    title       = "document-ai-input-prefix-only"
    description = "Worker may create/read only its generation-pinned Document AI input prefix."
    expression  = "resource.name.startsWith('projects/_/buckets/${local.derived_bucket}/objects/document-ai-input/')"
  }
}

resource "google_storage_bucket_iam_member" "reconciler_derived_reader" {
  count  = local.reconciler_service_enabled && var.ocr_output_bucket_enabled ? 1 : 0
  bucket = google_storage_bucket.ocr_output[0].name
  role   = google_project_iam_custom_role.reconciler_output_reader.id
  member = "serviceAccount:${google_service_account.reconciler.email}"
}

resource "google_project_iam_member" "worker_document_ai_submitter" {
  count   = local.worker_service_enabled ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.worker_document_ai_submitter.id
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "reconciler_document_ai_operation_reader" {
  count   = local.reconciler_service_enabled ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reconciler_document_ai_operation_reader.id
  member  = "serviceAccount:${google_service_account.reconciler.email}"
}

resource "google_pubsub_topic_iam_member" "worker_structured_dead_letter_publisher" {
  topic  = google_pubsub_topic.dead_letter.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_secret_manager_secret_iam_member" "worker_database_reader" {
  count     = local.worker_service_enabled ? 1 : 0
  project   = var.project_id
  secret_id = local.worker_database_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_secret_manager_secret_iam_member" "reconciler_database_reader" {
  count     = local.reconciler_service_enabled ? 1 : 0
  project   = var.project_id
  secret_id = local.reconciler_database_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.reconciler.email}"
}

resource "google_pubsub_topic" "intake" {
  name   = local.intake_topic
  labels = var.labels
}

resource "google_pubsub_topic" "dead_letter" {
  name                       = local.dead_letter_topic
  message_retention_duration = "1209600s"
  labels                     = var.labels
}

resource "google_pubsub_subscription" "worker" {
  name                       = local.worker_sub
  topic                      = google_pubsub_topic.intake.id
  ack_deadline_seconds       = 300
  message_retention_duration = "604800s"
  labels                     = var.labels

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }

  dynamic "push_config" {
    for_each = local.worker_dispatch_enabled ? [1] : []
    content {
      push_endpoint = "${google_cloud_run_v2_service.worker[0].uri}/internal/v1/knowledge/gcp-intake/pubsub"
      oidc_token {
        service_account_email = google_service_account.push.email
        audience              = google_cloud_run_v2_service.worker[0].uri
      }
    }
  }

  lifecycle {
    precondition {
      condition     = !var.worker_dispatch_enabled || local.worker_service_enabled
      error_message = "Pub/Sub dispatch cannot be enabled before the immutable worker service prerequisites are complete."
    }
  }
}

resource "google_pubsub_subscription_iam_member" "service_agent_forwarder" {
  subscription = google_pubsub_subscription.worker.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${local.pubsub_service_agent}"
}

resource "google_pubsub_topic_iam_member" "service_agent_dead_letter_publisher" {
  topic  = google_pubsub_topic.dead_letter.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${local.pubsub_service_agent}"
}

resource "google_service_account_iam_member" "pubsub_oidc_token_creator" {
  service_account_id = google_service_account.push.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${local.pubsub_service_agent}"
}

resource "google_document_ai_processor" "ocr" {
  location        = var.region
  display_name    = "VFBiz VinFast OCR development"
  type            = "OCR_PROCESSOR"
  deletion_policy = "ABANDON"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_billing_budget" "development" {
  billing_account = var.billing_account_id
  display_name    = "VFBiz AI development monthly guardrail"

  amount {
    specified_amount {
      currency_code = "VND"
      units         = tostring(var.budget_amount_vnd)
    }
  }

  budget_filter {
    projects = ["projects/${var.project_number}"]
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.75
  }

  threshold_rules {
    threshold_percent = 0.9
  }

  threshold_rules {
    threshold_percent = 1.0
  }

}

resource "google_cloud_run_v2_service" "worker" {
  count               = local.worker_service_enabled ? 1 : 0
  name                = "vfbiz-ai-document-worker-dev"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = true

  template {
    service_account                  = google_service_account.worker.email
    max_instance_request_concurrency = 1
    timeout                          = "300s"
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.database[0].name
        subnetwork = google_compute_subnetwork.cloud_run_database[0].name
        tags       = ["vfbiz-ai-document-worker"]
      }
    }
    containers {
      image = var.worker_image
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
      env {
        name  = "VFBIZ_AI_ENVIRONMENT"
        value = "development"
      }
      env {
        name  = "VFBIZ_AI_EXPOSE_DOCS"
        value = "false"
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_INGESTION_PROFILE"
        value = "gcp"
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_LOCATION"
        value = var.region
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_DOCUMENT_PROCESSOR_ID"
        value = var.document_ai_processor_id
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_DOCUMENT_PROCESSOR_REVISION"
        value = var.document_ai_processor_revision
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_INPUT_BUCKETS"
        value = jsonencode([google_storage_bucket.intake.name])
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_OUTPUT_BUCKET"
        value = local.ocr_output_bucket_name
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_STAGING_BUCKET"
        value = google_storage_bucket.derived.name
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_DAILY_PAGE_BUDGET"
        value = "500"
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_MAX_OUTPUT_OBJECTS"
        value = "20"
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_MAX_OUTPUT_OBJECT_BYTES"
        value = "16777216"
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_MAX_OUTPUT_TOTAL_BYTES"
        value = "134217728"
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_MAX_EXTRACTED_TEXT_BYTES"
        value = "33554432"
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_RECONCILIATION_DEADLINE_SECONDS"
        value = "180"
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_SYNTHETIC_SMOKE_MANIFEST"
        value = jsonencode(var.synthetic_smoke_manifest)
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_PUBSUB_SUBSCRIPTION"
        value = "projects/${var.project_id}/subscriptions/${local.worker_sub}"
      }
      env {
        name  = "VFBIZ_AI_KNOWLEDGE_GCP_PUBSUB_DEAD_LETTER_TOPIC"
        value = google_pubsub_topic.dead_letter.id
      }
      env {
        name = "VFBIZ_AI_DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = local.worker_database_secret_id
            version = var.worker_database_url_secret_version
          }
        }
      }
      startup_probe {
        failure_threshold     = 3
        initial_delay_seconds = 1
        period_seconds        = 3
        timeout_seconds       = 2
        http_get {
          path = "/healthz"
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition     = !local.worker_service_enabled || var.ocr_output_bucket_enabled
      error_message = "Worker activation requires the explicitly retained dedicated OCR output bucket."
    }
    precondition {
      condition = (
        !local.worker_service_enabled || (
          can(regex("@sha256:[a-f0-9]{64}$", var.worker_image)) &&
          local.worker_database_secret_id != "" &&
          can(regex("^[1-9][0-9]*$", var.worker_database_url_secret_version)) &&
          length(var.synthetic_smoke_manifest) > 0
        )
      )
      error_message = "Worker deployment requires an immutable image digest, numeric database secret version and reviewed synthetic manifest."
    }
    precondition {
      condition = (
        local.worker_database_secret_id == "" ||
        local.reconciler_database_secret_id == "" ||
        local.worker_database_secret_id != local.reconciler_database_secret_id
      )
      error_message = "Worker and reconciler must use distinct Secret Manager IDs backed by distinct PostgreSQL login roles."
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_service_iam_member" "worker_invoker" {
  count    = local.worker_dispatch_enabled ? 1 : 0
  name     = google_cloud_run_v2_service.worker[0].name
  location = google_cloud_run_v2_service.worker[0].location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.push.email}"
}

resource "google_cloud_run_v2_job" "reconciler" {
  count               = local.reconciler_service_enabled ? 1 : 0
  name                = "vfbiz-ai-document-reconciler-dev"
  location            = var.region
  deletion_protection = true

  template {
    template {
      service_account = google_service_account.reconciler.email
      timeout         = "300s"
      max_retries     = 0
      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.database[0].name
          subnetwork = google_compute_subnetwork.cloud_run_database[0].name
          tags       = ["vfbiz-ai-document-reconciler"]
        }
      }

      containers {
        image   = var.worker_image
        command = ["/usr/bin/python3.14"]
        args = [
          "-m",
          "app.modules.knowledge.presentation.gcp_reconcile_job",
        ]

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }

        env {
          name  = "VFBIZ_AI_ENVIRONMENT"
          value = "development"
        }
        env {
          name  = "VFBIZ_AI_EXPOSE_DOCS"
          value = "false"
        }
        env {
          name  = "VFBIZ_AI_KNOWLEDGE_INGESTION_PROFILE"
          value = "gcp"
        }
        env {
          name  = "VFBIZ_AI_KNOWLEDGE_GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "VFBIZ_AI_KNOWLEDGE_GCP_LOCATION"
          value = var.region
        }
        env {
          name  = "VFBIZ_AI_KNOWLEDGE_GCP_DOCUMENT_PROCESSOR_ID"
          value = var.document_ai_processor_id
        }
        env {
          name  = "VFBIZ_AI_KNOWLEDGE_GCP_DOCUMENT_PROCESSOR_REVISION"
          value = var.document_ai_processor_revision
        }
        env {
          name  = "VFBIZ_AI_KNOWLEDGE_GCP_INPUT_BUCKETS"
          value = jsonencode([google_storage_bucket.intake.name])
        }
        env {
          name  = "VFBIZ_AI_KNOWLEDGE_GCP_OUTPUT_BUCKET"
          value = local.ocr_output_bucket_name
        }
        env {
          name  = "VFBIZ_AI_KNOWLEDGE_GCP_STAGING_BUCKET"
          value = google_storage_bucket.derived.name
        }
        env {
          name  = "VFBIZ_AI_KNOWLEDGE_GCP_SYNTHETIC_SMOKE_MANIFEST"
          value = jsonencode(var.synthetic_smoke_manifest)
        }
        env {
          name  = "VFBIZ_AI_KNOWLEDGE_GCP_PUBSUB_SUBSCRIPTION"
          value = "projects/${var.project_id}/subscriptions/${local.worker_sub}"
        }
        env {
          name  = "VFBIZ_AI_KNOWLEDGE_GCP_PUBSUB_DEAD_LETTER_TOPIC"
          value = google_pubsub_topic.dead_letter.id
        }
        env {
          name  = "VFBIZ_AI_KNOWLEDGE_GCP_RECONCILIATION_DEADLINE_SECONDS"
          value = "180"
        }
        env {
          name = "VFBIZ_AI_DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = local.reconciler_database_secret_id
              version = var.reconciler_database_url_secret_version
            }
          }
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition     = !local.reconciler_service_enabled || var.ocr_output_bucket_enabled
      error_message = "Reconciler activation requires the explicitly retained dedicated OCR output bucket."
    }
    precondition {
      condition = (
        !local.reconciler_service_enabled || (
          can(regex("@sha256:[a-f0-9]{64}$", var.worker_image)) &&
          local.reconciler_database_secret_id != "" &&
          can(regex("^[1-9][0-9]*$", var.reconciler_database_url_secret_version)) &&
          length(var.synthetic_smoke_manifest) > 0
        )
      )
      error_message = "Reconciliation job requires an immutable image, restricted numeric secret version and reviewed synthetic manifest."
    }
    precondition {
      condition = (
        local.worker_database_secret_id == "" ||
        local.reconciler_database_secret_id == "" ||
        local.worker_database_secret_id != local.reconciler_database_secret_id
      )
      error_message = "Worker and reconciler must use distinct Secret Manager IDs backed by distinct PostgreSQL login roles."
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_reconciler_invoker" {
  count    = local.reconciler_schedule_enabled ? 1 : 0
  name     = google_cloud_run_v2_job.reconciler[0].name
  location = google_cloud_run_v2_job.reconciler[0].location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "reconciler" {
  count       = local.reconciler_schedule_enabled ? 1 : 0
  name        = "vfbiz-ai-document-reconciler-dev"
  description = "Run one bounded content-free Document AI reconciliation batch."
  region      = var.region
  schedule    = "*/5 * * * *"
  time_zone   = "Etc/UTC"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.reconciler[0].name}:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  retry_config {
    retry_count = 0
  }

  lifecycle {
    precondition {
      condition     = !var.reconciler_schedule_enabled || local.reconciler_service_enabled
      error_message = "Reconciliation schedule cannot be enabled before the job prerequisites are complete."
    }
  }

  depends_on = [
    google_cloud_run_v2_job_iam_member.scheduler_reconciler_invoker,
    google_project_service.required,
  ]
}
