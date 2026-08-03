output "intake_bucket" {
  value = google_storage_bucket.intake.name
}

output "derived_bucket" {
  value = google_storage_bucket.derived.name
}

output "ocr_output_bucket" {
  value = var.ocr_output_bucket_enabled ? google_storage_bucket.ocr_output[0].name : null
}

output "evidence_bucket" {
  value = google_storage_bucket.evidence.name
}

output "worker_service_account" {
  value = google_service_account.worker.email
}

output "worker_artifact_repository" {
  value = google_artifact_registry_repository.workers.name
}

output "worker_service_enabled" {
  value = local.worker_service_enabled
}

output "worker_dispatch_enabled" {
  value = local.worker_dispatch_enabled
}

output "reconciler_service_account" {
  value = google_service_account.reconciler.email
}

output "reconciler_service_enabled" {
  value = local.reconciler_service_enabled
}

output "reconciler_schedule_enabled" {
  value = local.reconciler_schedule_enabled
}

output "database_instance_connection_name" {
  value = var.database_foundation_enabled ? google_sql_database_instance.ai[0].connection_name : null
}

output "database_private_ip_address" {
  value = var.database_foundation_enabled ? google_sql_database_instance.ai[0].private_ip_address : null
}

output "database_bootstrap_secret_id" {
  value = var.database_foundation_enabled ? google_secret_manager_secret.database_bootstrap_url[0].secret_id : null
}

output "database_submitter_secret_id" {
  value = var.database_foundation_enabled ? google_secret_manager_secret.database_submitter_url[0].secret_id : null
}

output "database_reconciler_secret_id" {
  value = var.database_foundation_enabled ? google_secret_manager_secret.database_reconciler_url[0].secret_id : null
}

output "database_bootstrap_job_name" {
  value = var.database_bootstrap_enabled ? google_cloud_run_v2_job.database_bootstrap[0].name : null
}

output "database_credential_operator_service_account" {
  value = var.database_credential_operator_enabled ? google_service_account.database_credential_operator[0].email : null
}

output "database_credential_authority_object" {
  value = var.database_credential_operator_enabled ? local.database_credential_authority_name : null
}

output "database_credential_authority_generation" {
  value = var.database_credential_operator_enabled ? tostring(data.google_storage_bucket_object_content.database_credential_authority[0].generation) : null
}

output "intake_topic" {
  value = google_pubsub_topic.intake.id
}

output "worker_subscription" {
  value = google_pubsub_subscription.worker.id
}

output "ocr_processor" {
  value = google_document_ai_processor.ocr.name
}
