# VFBIZ-0199 retires the imported legacy worker IAM bindings. The authenticated
# push identity is distinct from the OCR worker, and worker storage access is
# limited to the custom get-only/create-and-get roles declared in main.tf.

variable "vertex_smoke_operator_principal" {
  type        = string
  description = "Private user principal allowed to impersonate the development smoke identity; supplied only at plan/apply time."
  sensitive   = true
  default     = ""

  validation {
    condition = (
      var.vertex_smoke_operator_principal == "" ||
      can(regex("^user:[^[:space:]@]+@[^[:space:]@]+$", var.vertex_smoke_operator_principal))
    )
    error_message = "The smoke operator must be empty or one explicit user principal."
  }
}

resource "google_service_account" "vertex_smoke" {
  account_id   = "vfbiz-vertex-smoke"
  display_name = "VFBiz Vertex synthetic smoke identity"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_project_iam_custom_role" "vertex_smoke_predictor" {
  role_id     = "vfbizVertexSmokePredictor"
  title       = "VFBiz Vertex synthetic smoke predictor"
  description = "Invoke one online Vertex prediction without dataset, tuning, pipeline, deployment, model upload or batch authority."
  permissions = ["aiplatform.endpoints.predict"]

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_project_iam_member" "vertex_smoke_predictor" {
  project = var.project_id
  role    = google_project_iam_custom_role.vertex_smoke_predictor.id
  member  = "serviceAccount:${google_service_account.vertex_smoke.email}"
}

resource "google_project_iam_custom_role" "vertex_smoke_witness_writer" {
  role_id     = "vfbizVertexSmokeWitnessWriter"
  title       = "VFBiz Vertex smoke witness writer"
  description = "Inspect the evidence bucket retention policy and create an immutable dispatch witness without read, update, list or delete authority."
  permissions = [
    "storage.buckets.get",
    "storage.objects.create",
  ]

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "vertex_smoke_witness_writer" {
  bucket = google_storage_bucket.evidence.name
  role   = google_project_iam_custom_role.vertex_smoke_witness_writer.id
  member = "serviceAccount:${google_service_account.vertex_smoke.email}"
}

resource "google_service_account_iam_member" "vertex_smoke_operator" {
  count = var.vertex_smoke_operator_principal == "" ? 0 : 1

  service_account_id = google_service_account.vertex_smoke.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = var.vertex_smoke_operator_principal
}

output "vertex_smoke_service_account" {
  value = google_service_account.vertex_smoke.email
}

output "vertex_smoke_prediction_role" {
  value = google_project_iam_custom_role.vertex_smoke_predictor.name
}
