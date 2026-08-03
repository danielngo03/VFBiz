import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
IAM_CONTRACT = ROOT / "infra/gcp/iam-contract.json"
GCP_ADAPTER = ROOT / "backend/ai/app/modules/knowledge/infrastructure/gcp_cloud_ingestion.py"
GCP_IAC = ROOT / "infra/gcp/main.tf"
GCP_LEGACY_TRANSITION = ROOT / "infra/gcp/legacy_transition.tf"
GCP_DATABASE_FOUNDATION = ROOT / "infra/gcp/database_foundation.tf"
GCP_DATABASE_BOOTSTRAP = ROOT / "infra/gcp/database_bootstrap.tf"
GCP_VARIABLES = ROOT / "infra/gcp/variables.tf"
GCP_WORKER_DOCKERFILE = ROOT / "backend/ai/ops/gcp-intake-worker/Dockerfile"
GCP_DATABASE_BOOTSTRAP_DOCKERFILE = (
    ROOT / "backend/ai/ops/gcp-database-bootstrap/Dockerfile"
)


def test_document_ai_output_listing_has_exact_reconciler_iam_contract() -> None:
    contract = json.loads(IAM_CONTRACT.read_text(encoding="utf-8"))

    assert contract == {
        "schema_revision": "vfbiz-gcp-iam-contract-v1",
        "reconciler_derived_output_reader": [
            "storage.objects.get",
            "storage.objects.list",
        ],
        "worker_document_ai_submitter": [
            "documentai.processorVersions.processBatch",
        ],
        "reconciler_document_ai_operation_reader": [
            "documentai.operations.getLegacy",
        ],
    }

    adapter = GCP_ADAPTER.read_text(encoding="utf-8")
    assert '"https://storage.googleapis.com/storage/v1/b/"' in adapter
    assert 'f"{quote(self._output_bucket, safe=\'\')}/o"' in adapter

    iac = GCP_IAC.read_text(encoding="utf-8")
    assert "permissions = local.iam_contract.reconciler_derived_output_reader" in iac
    assert "role   = google_project_iam_custom_role.reconciler_output_reader.id" in iac
    reconciler_binding = iac.split(
        'resource "google_storage_bucket_iam_member" "reconciler_derived_reader"',
        maxsplit=1,
    )[1].split("}", maxsplit=1)[0]
    assert (
        "count  = local.reconciler_service_enabled && var.ocr_output_bucket_enabled ? 1 : 0"
        in reconciler_binding
    )


def test_document_ai_workloads_have_disjoint_least_privilege_roles() -> None:
    iac = GCP_IAC.read_text(encoding="utf-8")

    assert "permissions = local.iam_contract.worker_document_ai_submitter" in iac
    assert (
        "permissions = local.iam_contract.reconciler_document_ai_operation_reader"
        in iac
    )
    assert 'role    = "roles/documentai.apiUser"' not in iac
    assert "count   = local.worker_service_enabled ? 1 : 0" in iac
    assert "count   = local.reconciler_service_enabled ? 1 : 0" in iac
    assert iac.count("count  = local.worker_service_enabled ? 1 : 0") >= 2


def test_gcs_workload_bindings_are_prefix_scoped() -> None:
    iac = GCP_IAC.read_text(encoding="utf-8")

    def resource_section(name: str) -> str:
        marker = f'resource "google_storage_bucket_iam_member" "{name}"'
        return iac.split(marker, maxsplit=1)[1].split("\nresource ", maxsplit=1)[0]

    intake = resource_section("worker_intake_reader")
    derived_writer = resource_section("worker_derived_writer")
    reconciler = resource_section("reconciler_derived_reader")

    assert "content-addressed-intake-only" in intake
    assert "objects/sha256/" in intake
    assert "document-ai-input-prefix-only" in derived_writer
    assert "objects/document-ai-input/" in derived_writer
    assert "google_storage_bucket.ocr_output[0].name" in reconciler
    assert (
        "count  = local.reconciler_service_enabled && var.ocr_output_bucket_enabled ? 1 : 0"
        in reconciler
    )
    assert "document-ai-output-prefix-only" not in reconciler
    assert "objects/document-ai/jobs/" not in reconciler


def test_document_ai_output_has_a_dedicated_bucket_boundary() -> None:
    iac = GCP_IAC.read_text(encoding="utf-8")

    assert 'ocr_output_bucket      = "${var.project_id}-ocr-output-dev"' in iac
    variables = (ROOT / "infra/gcp/variables.tf").read_text(encoding="utf-8")
    assert 'variable "ocr_output_bucket_enabled"' in variables
    assert "default     = false" in (
        variables.split('variable "ocr_output_bucket_enabled"', maxsplit=1)[1]
        .split("}", maxsplit=1)[0]
    )
    output_bucket = iac.split(
        'resource "google_storage_bucket" "ocr_output"', maxsplit=1
    )[1].split('resource "google_storage_bucket" "evidence"', maxsplit=1)[0]
    assert "count                       = var.ocr_output_bucket_enabled ? 1 : 0" in output_bucket
    assert "uniform_bucket_level_access = true" in output_bucket
    assert 'public_access_prevention    = "enforced"' in output_bucket
    assert "prevent_destroy = true" in output_bucket
    assert 'name  = "VFBIZ_AI_KNOWLEDGE_GCP_STAGING_BUCKET"' in iac
    assert 'name  = "VFBIZ_AI_KNOWLEDGE_GCP_OUTPUT_BUCKET"' in iac


def test_cloud_workloads_require_distinct_database_secrets() -> None:
    iac = GCP_IAC.read_text(encoding="utf-8")

    condition = "local.worker_database_secret_id != local.reconciler_database_secret_id"
    assert iac.count(condition) == 2
    assert "cleanup_policy_dry_run = true" in iac


def test_cloud_workloads_require_content_free_activation_packet() -> None:
    iac = GCP_IAC.read_text(encoding="utf-8")
    variables = GCP_VARIABLES.read_text(encoding="utf-8")

    required_fields = (
        "ingestion_activation_authority_sha256",
        "ingestion_activation_authority_generation",
        "ingestion_saved_plan_sha256",
        "ingestion_rollback_image_sha256",
        "ingestion_risk_disposition_sha256",
        "ingestion_risk_disposition_reference",
    )
    for field in required_fields:
        assert f'variable "{field}"' in variables
        assert f"var.{field}" in iac
    assert "local.ingestion_activation_packet_ready" in iac
    assert "length(var.synthetic_smoke_manifest) > 0 &&" in iac
    assert 'ingestion_activation_authority_generation = ""' in (
        ROOT / "infra/gcp/terraform.tfvars.example"
    ).read_text(encoding="utf-8")


def test_database_foundation_is_private_protected_and_default_off() -> None:
    variables = GCP_VARIABLES.read_text(encoding="utf-8")
    foundation = GCP_DATABASE_FOUNDATION.read_text(encoding="utf-8")

    variable = variables.split(
        'variable "database_foundation_enabled"', maxsplit=1
    )[1].split("}", maxsplit=1)[0]
    assert "default     = false" in variable
    assert foundation.count(
        "count = var.database_foundation_enabled ? 1 : 0"
    ) == 10
    assert 'database_version    = "POSTGRES_17"' in foundation
    assert 'tier                        = "db-f1-micro"' in foundation
    assert 'availability_type           = "ZONAL"' in foundation
    assert "disk_size                   = 20" in foundation
    assert "disk_autoresize             = false" in foundation
    assert "ipv4_enabled                                  = false" in foundation
    assert 'ssl_mode                                      = "ENCRYPTED_ONLY"' in foundation
    assert foundation.count("deletion_protection = true") == 4
    assert foundation.count("prevent_destroy = true") == 9
    assert "google_sql_user" not in foundation
    assert "google_secret_manager_secret_version" not in foundation
    assert "auto {}" not in foundation
    assert foundation.count("user_managed {") == 3
    assert foundation.count("location = var.region") == 3


def test_cloud_run_database_access_uses_direct_vpc_and_exact_reconciler_binary() -> None:
    iac = GCP_IAC.read_text(encoding="utf-8")
    bootstrap = GCP_DATABASE_BOOTSTRAP.read_text(encoding="utf-8")

    assert iac.count('egress = "PRIVATE_RANGES_ONLY"') == 2
    assert iac.count("network    = google_compute_network.database[0].name") == 2
    assert iac.count(
        "subnetwork = google_compute_subnetwork.cloud_run_database[0].name"
    ) == 2
    assert 'command = ["/usr/bin/python3.14"]' in iac
    assert 'command = ["python"]' not in iac
    assert 'egress = "PRIVATE_RANGES_ONLY"' in bootstrap


def test_database_bootstrap_is_manual_least_privilege_and_default_off() -> None:
    variables = GCP_VARIABLES.read_text(encoding="utf-8")
    bootstrap = GCP_DATABASE_BOOTSTRAP.read_text(encoding="utf-8")
    worker_dockerfile = GCP_WORKER_DOCKERFILE.read_text(encoding="utf-8")
    bootstrap_dockerfile = GCP_DATABASE_BOOTSTRAP_DOCKERFILE.read_text(
        encoding="utf-8"
    )

    enabled_variable = variables.split(
        'variable "database_bootstrap_enabled"', maxsplit=1
    )[1].split("}", maxsplit=1)[0]
    assert "default     = false" in enabled_variable
    assert "secretmanager.secrets.get" in bootstrap
    assert "secretmanager.versions.add" in bootstrap
    assert "secretmanager.versions.disable" in bootstrap
    assert "secretmanager.versions.access" not in bootstrap
    assert "secretmanager.secrets.delete" not in bootstrap
    assert bootstrap.count(
        'role      = google_project_iam_custom_role.database_secret_version_publisher[0].id'
    ) == 2
    assert 'role      = "roles/secretmanager.secretAccessor"' in bootstrap
    assert "max_retries     = 0" in bootstrap
    assert "google_cloud_run_v2_job_iam_member" not in bootstrap
    assert "google_cloud_scheduler_job" not in bootstrap
    assert '"scripts.bootstrap_document_ai_database"' in bootstrap
    assert "var.database_bootstrap_image" in bootstrap
    assert "COPY scripts/__init__.py" in bootstrap_dockerfile
    assert "scripts/bootstrap_document_ai_database.py" in bootstrap_dockerfile
    assert "--group gcp-bootstrap" in bootstrap_dockerfile
    assert "scripts/bootstrap_document_ai_database.py" not in worker_dockerfile


def test_development_derived_lifecycle_separates_live_and_noncurrent_objects() -> None:
    iac = GCP_IAC.read_text(encoding="utf-8")
    derived = iac.split('resource "google_storage_bucket" "derived"', maxsplit=1)[
        1
    ].split('resource "google_storage_bucket" "ocr_output"', maxsplit=1)[0]

    assert "var.enable_derived_output_expiry ? 0 : 604800" in derived
    assert derived.count(
        "for_each = var.enable_derived_output_expiry ? [1] : []"
    ) == 2
    assert 'age        = 7\n        with_state = "LIVE"' in derived
    assert (
        'days_since_noncurrent_time = 1\n        with_state                 = "ARCHIVED"'
        in derived
    )


def test_legacy_document_ai_grant_is_retained_only_as_transition_evidence() -> None:
    legacy = GCP_LEGACY_TRANSITION.read_text(encoding="utf-8")

    assert legacy.count('resource "google_project_iam_member"') == 1
    assert '"worker_document_ai_api_user"' in legacy
    assert 'role    = "roles/documentai.apiUser"' in legacy
    assert "must be removed by a later reviewed plan before worker service activation" in legacy
