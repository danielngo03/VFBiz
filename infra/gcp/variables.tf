variable "project_id" {
  type        = string
  description = "Development GCP project ID from the operator packet."
}

variable "project_number" {
  type        = string
  description = "Development GCP project number from the operator packet."
}

variable "billing_account_id" {
  type        = string
  description = "Billing account ID used by the existing project budget."
}

variable "region" {
  type        = string
  description = "Single-region development placement."
  default     = "asia-southeast1"
}

variable "worker_image" {
  type        = string
  description = "Immutable Artifact Registry image digest; empty keeps Cloud Run disabled."
  default     = ""
}

variable "worker_database_url_secret_id" {
  type        = string
  description = "Existing Secret Manager secret ID containing the AI PostgreSQL URL; empty keeps Cloud Run disabled."
  default     = ""
}

variable "worker_database_url_secret_version" {
  type        = string
  description = "Exact numeric Secret Manager version for the AI PostgreSQL URL; empty keeps Cloud Run disabled."
  default     = ""

  validation {
    condition = (
      var.worker_database_url_secret_version == "" ||
      can(regex("^[1-9][0-9]*$", var.worker_database_url_secret_version))
    )
    error_message = "Worker database secret version must be empty or one positive numeric version."
  }
}

variable "worker_dispatch_enabled" {
  type        = bool
  description = "Attach authenticated Pub/Sub push to an already configured worker service."
  default     = false
}

variable "reconciler_database_url_secret_id" {
  type        = string
  description = "Existing Secret Manager secret ID for the restricted reconciliation PostgreSQL role."
  default     = ""
}

variable "reconciler_database_url_secret_version" {
  type        = string
  description = "Exact numeric version of the restricted reconciliation PostgreSQL secret."
  default     = ""

  validation {
    condition = (
      var.reconciler_database_url_secret_version == "" ||
      can(regex("^[1-9][0-9]*$", var.reconciler_database_url_secret_version))
    )
    error_message = "Reconciler database secret version must be empty or one positive numeric version."
  }
}

variable "reconciler_schedule_enabled" {
  type        = bool
  description = "Allow Cloud Scheduler to invoke the bounded reconciliation job every five minutes."
  default     = false
}

variable "synthetic_smoke_manifest" {
  type        = map(number)
  description = "Reviewed synthetic PDF SHA-256 to actual page-count map; empty keeps Cloud Run disabled."
  default     = {}

  validation {
    condition = alltrue([
      for digest, pages in var.synthetic_smoke_manifest :
      can(regex("^[a-f0-9]{64}$", digest)) && pages >= 1 && pages <= 500 && floor(pages) == pages
    ])
    error_message = "Synthetic smoke manifest keys must be SHA-256 digests with integer page counts from 1 to 500."
  }
}

variable "ingestion_activation_authority_sha256" {
  type        = string
  description = "SHA-256 of the external, content-free GCP ingestion activation packet."
  default     = ""

  validation {
    condition = (
      var.ingestion_activation_authority_sha256 == "" ||
      can(regex("^[a-f0-9]{64}$", var.ingestion_activation_authority_sha256))
    )
    error_message = "Ingestion activation authority must be empty or one lowercase SHA-256."
  }
}

variable "ingestion_activation_authority_generation" {
  type        = string
  description = "Exact positive GCS generation of the external activation packet."
  default     = ""

  validation {
    condition = (
      var.ingestion_activation_authority_generation == "" ||
      can(regex("^[1-9][0-9]*$", var.ingestion_activation_authority_generation))
    )
    error_message = "Ingestion activation authority generation must be empty or positive numeric."
  }
}

variable "ingestion_saved_plan_sha256" {
  type        = string
  description = "SHA-256 of the reviewed zero-replacement/zero-destruction activation plan."
  default     = ""

  validation {
    condition = (
      var.ingestion_saved_plan_sha256 == "" ||
      can(regex("^[a-f0-9]{64}$", var.ingestion_saved_plan_sha256))
    )
    error_message = "Ingestion saved plan identity must be empty or one lowercase SHA-256."
  }
}

variable "ingestion_rollback_image_sha256" {
  type        = string
  description = "SHA-256 digest of the reviewed rollback worker image."
  default     = ""

  validation {
    condition = (
      var.ingestion_rollback_image_sha256 == "" ||
      can(regex("^[a-f0-9]{64}$", var.ingestion_rollback_image_sha256))
    )
    error_message = "Ingestion rollback image identity must be empty or one lowercase SHA-256."
  }
}

variable "ingestion_risk_disposition_sha256" {
  type        = string
  description = "SHA-256 of the named development risk disposition for project-scoped Document AI permissions."
  default     = ""

  validation {
    condition = (
      var.ingestion_risk_disposition_sha256 == "" ||
      can(regex("^[a-f0-9]{64}$", var.ingestion_risk_disposition_sha256))
    )
    error_message = "Ingestion risk disposition identity must be empty or one lowercase SHA-256."
  }
}

variable "ingestion_risk_disposition_reference" {
  type        = string
  description = "Content-free evidence/decision URI for the named development risk disposition."
  default     = ""

  validation {
    condition = (
      var.ingestion_risk_disposition_reference == "" ||
      can(regex(
        "^(evidence|decision)://[A-Za-z0-9._:/-]{1,255}$",
        var.ingestion_risk_disposition_reference,
      ))
    )
    error_message = "Ingestion risk disposition reference must be empty or an evidence:// or decision:// URI."
  }
}

variable "document_ai_processor_revision" {
  type        = string
  description = "Exact Document AI processor version pinned by the worker."
  default     = "pretrained-ocr-v2.1.1-2025-01-31"
}

variable "document_ai_processor_id" {
  type        = string
  description = "Existing OCR processor ID, without project/location prefix."
}

variable "budget_amount_vnd" {
  type        = number
  description = "Development alert budget in VND. Alerts are not hard spend limits."
  default     = 4000000
}

variable "enable_derived_output_expiry" {
  type        = bool
  description = "Enable irreversible short-lived derived OCR cleanup only after an explicit Data Owner retention decision."
  default     = false
}

variable "ocr_output_bucket_enabled" {
  type        = bool
  description = "Retain the dedicated Document AI OCR-output bucket; enable explicitly before workload activation and keep true for later disable/rollback cycles."
  default     = false
}

variable "database_foundation_enabled" {
  type        = bool
  description = "Create the private development PostgreSQL/VPC foundation and empty database secret containers."
  default     = false
}

variable "database_bootstrap_enabled" {
  type        = bool
  description = "Create a manual one-shot private database migration and restricted-identity bootstrap job."
  default     = false
}

variable "database_bootstrap_image" {
  type        = string
  description = "Immutable digest of the dedicated migration and database-identity bootstrap image."
  default     = ""

  validation {
    condition = (
      var.database_bootstrap_image == "" ||
      can(regex(
        "^asia-southeast1-docker\\.pkg\\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/[a-z][a-z0-9-]{0,61}[a-z0-9]/[a-z0-9][a-z0-9._/-]{0,126}@sha256:[a-f0-9]{64}$",
        var.database_bootstrap_image,
      ))
    )
    error_message = "The database bootstrap image must be empty or an immutable asia-southeast1 Artifact Registry digest."
  }
}

variable "database_bootstrap_authority_digest" {
  type        = string
  description = "SHA-256 of the externally reviewed one-shot database bootstrap operator packet."
  default     = ""

  validation {
    condition = (
      var.database_bootstrap_authority_digest == "" ||
      can(regex("^[a-f0-9]{64}$", var.database_bootstrap_authority_digest))
    )
    error_message = "The database bootstrap authority digest must be empty or a lowercase SHA-256."
  }
}

variable "database_bootstrap_url_secret_version" {
  type        = string
  description = "Exact numeric version of the private database administrator URL used only by the bootstrap job."
  default     = ""

  validation {
    condition = (
      var.database_bootstrap_url_secret_version == "" ||
      can(regex("^[1-9][0-9]*$", var.database_bootstrap_url_secret_version))
    )
    error_message = "The database bootstrap secret version must be empty or a positive numeric Secret Manager version."
  }
}

variable "database_credential_operator_enabled" {
  type        = bool
  description = "Create the default-off, keyless identity for one externally authorized administrator credential bootstrap."
  default     = false
}

variable "database_credential_operator_principal" {
  type        = string
  description = "Exact private user or service-account IAM member allowed to impersonate the one-time credential operator."
  sensitive   = true
  default     = ""

  validation {
    condition = (
      var.database_credential_operator_principal == "" ||
      can(regex("^(user|serviceAccount):[^@[:space:]]+@[^@[:space:]]+$", var.database_credential_operator_principal))
    )
    error_message = "Credential operator principal must be empty or one exact user/serviceAccount IAM member."
  }
}

variable "database_credential_authority_sha256" {
  type        = string
  description = "SHA-256 of the externally issued canonical credential authority packet."
  default     = ""

  validation {
    condition = (
      var.database_credential_authority_sha256 == "" ||
      can(regex("^[a-f0-9]{64}$", var.database_credential_authority_sha256))
    )
    error_message = "Credential authority SHA-256 must be empty or one lowercase digest."
  }
}

variable "database_credential_authority_generation" {
  type        = string
  description = "Exact positive GCS generation of the externally issued credential authority packet."
  default     = ""

  validation {
    condition = (
      var.database_credential_authority_generation == "" ||
      can(regex("^[1-9][0-9]*$", var.database_credential_authority_generation))
    )
    error_message = "Credential authority generation must be empty or one positive integer."
  }
}

variable "tuning_rehearsal_enabled" {
  type        = bool
  description = "Create the isolated synthetic-only tuning rehearsal data plane."
  default     = false
}

variable "tuning_rehearsal_region" {
  type        = string
  description = "Explicit US region for the synthetic-only tuning rehearsal."
  default     = "us-central1"

  validation {
    condition     = var.tuning_rehearsal_region == "us-central1"
    error_message = "The reviewed synthetic rehearsal currently pins us-central1."
  }
}

variable "tuning_rehearsal_operator_member" {
  type        = string
  description = "Optional private IAM member allowed to impersonate the rehearsal identity; keep empty in committed configuration."
  default     = ""

  validation {
    condition = (
      var.tuning_rehearsal_operator_member == "" ||
      can(regex(
        "^(user:[^@[:space:]]+@[^@[:space:]]+|serviceAccount:[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9-]{4,28}[a-z0-9]\\.iam\\.gserviceaccount\\.com)$",
        var.tuning_rehearsal_operator_member,
      ))
    )
    error_message = "Operator member must be empty or one exact user/serviceAccount email IAM member."
  }
}

variable "tuning_rehearsal_operator_expires_at" {
  type        = string
  description = "RFC3339 expiry for the temporary rehearsal impersonation grant."
  default     = ""

  validation {
    condition = (
      var.tuning_rehearsal_operator_expires_at == "" ||
      (
        can(timecmp(var.tuning_rehearsal_operator_expires_at, timestamp())) &&
        timecmp(var.tuning_rehearsal_operator_expires_at, timestamp()) > 0 &&
        timecmp(
          var.tuning_rehearsal_operator_expires_at,
          timeadd(timestamp(), "24h"),
        ) <= 0
      )
    )
    error_message = "Operator expiry must be empty or a future RFC3339 timestamp no more than 24 hours away."
  }
}

variable "tuning_rehearsal_candidate_manifest_sha256" {
  type        = string
  description = "Reviewed synthetic candidate manifest digest used to scope create-only object IAM."
  default     = ""

  validation {
    condition = (
      var.tuning_rehearsal_candidate_manifest_sha256 == "" ||
      can(regex("^[a-f0-9]{64}$", var.tuning_rehearsal_candidate_manifest_sha256))
    )
    error_message = "Candidate manifest identity must be empty or one SHA-256 digest."
  }
}

variable "labels" {
  type        = map(string)
  description = "Non-sensitive resource labels."
  default = {
    environment = "development"
    owner       = "vfbiz-ai"
    provenance  = "managed-pipeline"
  }
}
