# This imported project-scoped grant is intentionally retained during the
# inactive foundation-only stage so that the foundation plan is zero-destroy.
# It must be removed by a later reviewed plan before worker service activation;
# the custom submit-only role in main.tf is the replacement authority.
resource "google_project_iam_member" "worker_document_ai_api_user" {
  project = var.project_id
  role    = "roles/documentai.apiUser"
  member  = "serviceAccount:${google_service_account.worker.email}"
}
