locals {
  database_bootstrap_service_account = "vfbiz-ai-dev-db-bootstrap"
}

resource "terraform_data" "database_bootstrap_gate" {
  count = var.database_bootstrap_enabled ? 1 : 0

  lifecycle {
    precondition {
      condition = (
        var.database_foundation_enabled &&
        can(regex("@sha256:[a-f0-9]{64}$", var.database_bootstrap_image)) &&
        can(regex("^[a-f0-9]{64}$", var.database_bootstrap_authority_digest)) &&
        can(regex("^[1-9][0-9]*$", var.database_bootstrap_url_secret_version))
      )
      error_message = "Database bootstrap requires the private foundation, an immutable bootstrap-capable image and a positive numeric administrator secret version."
    }
  }
}

resource "google_service_account" "database_bootstrap" {
  count = var.database_bootstrap_enabled ? 1 : 0

  account_id   = local.database_bootstrap_service_account
  display_name = "VFBiz AI development database bootstrap"
}

resource "google_project_iam_custom_role" "database_secret_version_publisher" {
  count = var.database_bootstrap_enabled ? 1 : 0

  role_id     = "vfbizAiDatabaseSecretVersionPublisher"
  title       = "VFBiz AI database secret version publisher"
  description = "Inspect exact runtime secret containers and add or disable versions without reading payloads."
  permissions = [
    "secretmanager.secrets.get",
    "secretmanager.versions.add",
    "secretmanager.versions.disable",
  ]
}

resource "google_secret_manager_secret_iam_member" "database_bootstrap_admin_reader" {
  count = var.database_bootstrap_enabled ? 1 : 0

  project   = var.project_id
  secret_id = google_secret_manager_secret.database_bootstrap_url[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.database_bootstrap[0].email}"
}

resource "google_secret_manager_secret_iam_member" "database_bootstrap_submitter_publisher" {
  count = var.database_bootstrap_enabled ? 1 : 0

  project   = var.project_id
  secret_id = google_secret_manager_secret.database_submitter_url[0].secret_id
  role      = google_project_iam_custom_role.database_secret_version_publisher[0].id
  member    = "serviceAccount:${google_service_account.database_bootstrap[0].email}"
}

resource "google_secret_manager_secret_iam_member" "database_bootstrap_reconciler_publisher" {
  count = var.database_bootstrap_enabled ? 1 : 0

  project   = var.project_id
  secret_id = google_secret_manager_secret.database_reconciler_url[0].secret_id
  role      = google_project_iam_custom_role.database_secret_version_publisher[0].id
  member    = "serviceAccount:${google_service_account.database_bootstrap[0].email}"
}

resource "google_cloud_run_v2_job" "database_bootstrap" {
  count               = var.database_bootstrap_enabled ? 1 : 0
  name                = "vfbiz-ai-database-bootstrap-dev"
  location            = var.region
  deletion_protection = true

  template {
    template {
      service_account = google_service_account.database_bootstrap[0].email
      timeout         = "600s"
      max_retries     = 0

      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.database[0].name
          subnetwork = google_compute_subnetwork.cloud_run_database[0].name
          tags       = ["vfbiz-ai-database-bootstrap"]
        }
      }

      containers {
        image   = var.database_bootstrap_image
        command = ["/usr/bin/python3.14"]
        args = [
          "-m",
          "scripts.bootstrap_document_ai_database",
        ]

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }

        env {
          name  = "VFBIZ_AI_ENVIRONMENT"
          value = "development"
        }
        env {
          name  = "VFBIZ_AI_DATABASE_BOOTSTRAP_APPLY"
          value = "true"
        }
        env {
          name  = "VFBIZ_AI_GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "VFBIZ_AI_DATABASE_SUBMITTER_SECRET_ID"
          value = google_secret_manager_secret.database_submitter_url[0].secret_id
        }
        env {
          name  = "VFBIZ_AI_DATABASE_RECONCILER_SECRET_ID"
          value = google_secret_manager_secret.database_reconciler_url[0].secret_id
        }
        env {
          name  = "VFBIZ_AI_DATABASE_BOOTSTRAP_AUTHORITY_DIGEST"
          value = var.database_bootstrap_authority_digest
        }
        env {
          name = "VFBIZ_AI_DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_bootstrap_url[0].secret_id
              version = var.database_bootstrap_url_secret_version
            }
          }
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition = (
        var.database_foundation_enabled &&
        can(regex("@sha256:[a-f0-9]{64}$", var.database_bootstrap_image)) &&
        can(regex("^[a-f0-9]{64}$", var.database_bootstrap_authority_digest)) &&
        can(regex("^[1-9][0-9]*$", var.database_bootstrap_url_secret_version))
      )
      error_message = "Database bootstrap job prerequisites are incomplete."
    }
  }

  depends_on = [
    google_project_service.required,
    google_secret_manager_secret_iam_member.database_bootstrap_admin_reader,
    google_secret_manager_secret_iam_member.database_bootstrap_reconciler_publisher,
    google_secret_manager_secret_iam_member.database_bootstrap_submitter_publisher,
    terraform_data.database_bootstrap_gate,
  ]
}
