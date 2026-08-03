import pytest
from pydantic import ValidationError

from app.platform.config.settings import Settings


def test_development_settings_are_typed() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
        redis_url="redis://localhost:6379/2",
    )

    assert settings.environment == "development"
    assert settings.generation_provider == "disabled"
    assert settings.embedding_provider == "disabled"
    assert settings.internal_api_prefix == "/internal/v1"


def test_evaluation_database_roles_require_distinct_complete_credentials() -> None:
    with pytest.raises(ValidationError, match="runner, sealer"):
        Settings(
            _env_file=None,
            evaluation_runner_database_url=(
                "postgresql+asyncpg://runner:test@localhost/vfbiz_ai"
            ),
        )

    with pytest.raises(ValidationError, match="distinct login roles"):
        Settings(
            _env_file=None,
            evaluation_runner_database_url=(
                "postgresql+asyncpg://shared:test@localhost/vfbiz_ai"
            ),
            evaluation_sealer_database_url=(
                "postgresql+asyncpg://shared:test@localhost/vfbiz_ai"
            ),
            evaluation_definition_reader_database_url=(
                "postgresql+asyncpg://reader:test@localhost/vfbiz_ai"
            ),
        )

    settings = Settings(
        _env_file=None,
        evaluation_runner_database_url=(
            "postgresql+asyncpg://runner:test@localhost/vfbiz_ai"
        ),
        evaluation_sealer_database_url=(
            "postgresql+asyncpg://sealer:test@localhost/vfbiz_ai"
        ),
        evaluation_definition_reader_database_url=(
            "postgresql+asyncpg://reader:test@localhost/vfbiz_ai"
        ),
    )
    assert settings.evaluation_runner_database_url is not None


def test_semantic_classifier_requires_pinned_deployment_identity() -> None:
    with pytest.raises(ValidationError, match="pinned artifact identity"):
        Settings(
            _env_file=None,
            semantic_classifier_provider="http",
            semantic_classifier_endpoint="http://127.0.0.1:8090/v1/route",
        )


def test_semantic_classifier_rejects_unapproved_remote_origin() -> None:
    with pytest.raises(ValidationError, match="explicitly allowed"):
        Settings(
            _env_file=None,
            semantic_classifier_provider="http",
            semantic_classifier_endpoint=(
                "https://classifier.internal.example/v1/route"
            ),
            semantic_classifier_artifact_ref="classifier://vivi/router/v1",
            semantic_classifier_artifact_sha256="a" * 64,
        )


def test_semantic_classifier_accepts_pinned_allowlisted_deployment() -> None:
    settings = Settings(
        _env_file=None,
        semantic_classifier_provider="http",
        semantic_classifier_endpoint=(
            "https://classifier.internal.example/v1/route"
        ),
        semantic_classifier_allowed_origins=(
            "https://classifier.internal.example",
        ),
        semantic_classifier_artifact_ref="classifier://vivi/router/v1",
        semantic_classifier_artifact_sha256="a" * 64,
    )

    assert settings.semantic_classifier_provider == "http"


def test_staging_requires_database_and_redis() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None, environment="staging", expose_docs=False)


def test_enabled_generation_provider_requires_pinned_model() -> None:
    with pytest.raises(ValidationError, match="generation_model"):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
            redis_url="redis://localhost:6379/2",
            generation_provider="openai",
        )


def test_documentation_cannot_be_exposed_in_production() -> None:
    with pytest.raises(ValidationError, match="expose_docs"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
            redis_url="redis://localhost:6379/2",
            expose_docs=True,
        )


def _gcp_knowledge_settings(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "_env_file": None,
        "database_url": "postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
        "knowledge_ingestion_profile": "gcp",
        "knowledge_gcp_project_id": "vinfast-503003",
        "knowledge_gcp_location": "asia-southeast1",
        "knowledge_gcp_document_processor_id": "processor-1",
        "knowledge_gcp_document_processor_revision": "pretrained-ocr-v2.1.1-2025-01-31",
        "knowledge_gcp_input_buckets": ("vinfast-503003-intake-dev",),
        "knowledge_gcp_staging_bucket": "vinfast-503003-derived-dev",
        "knowledge_gcp_output_bucket": "vinfast-503003-ocr-output-dev",
        "knowledge_gcp_pubsub_subscription": "worker-sub",
        "knowledge_gcp_pubsub_dead_letter_topic": "dead-letter",
        "knowledge_gcp_synthetic_smoke_manifest": {"a" * 64: 1},
    }
    values.update(overrides)
    return values


def test_gcp_ingestion_requires_distinct_staging_and_output_buckets() -> None:
    settings = Settings(**_gcp_knowledge_settings())
    assert settings.knowledge_gcp_staging_bucket != settings.knowledge_gcp_output_bucket

    with pytest.raises(ValidationError, match="staging and output buckets must be distinct"):
        Settings(
            **_gcp_knowledge_settings(
                knowledge_gcp_output_bucket="vinfast-503003-derived-dev",
            )
        )


def test_gcp_ingestion_rejects_data_plane_bucket_reuse() -> None:
    with pytest.raises(ValidationError, match="staging bucket must not be an input bucket"):
        Settings(
            **_gcp_knowledge_settings(
                knowledge_gcp_input_buckets=("vinfast-503003-derived-dev",),
            )
        )

    with pytest.raises(ValidationError, match="output bucket must not be an input bucket"):
        Settings(
            **_gcp_knowledge_settings(
                knowledge_gcp_input_buckets=("vinfast-503003-ocr-output-dev",),
            )
        )


def test_staging_requires_https_allowlisted_jwks_origin() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            _env_file=None,
            environment="staging",
            database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
            redis_url="redis://localhost:6379/2",
            expose_docs=False,
        )

    with pytest.raises(ValidationError, match="allowed_origins"):
        Settings(
            _env_file=None,
            environment="staging",
            database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
            redis_url="redis://localhost:6379/2",
            expose_docs=False,
            gateway_jwks_url="https://api.internal.example/.well-known/jwks.json",
        )

    settings = Settings(
        _env_file=None,
        environment="staging",
        database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
        redis_url="redis://localhost:6379/2",
        expose_docs=False,
        gateway_jwks_url="https://api.internal.example/.well-known/jwks.json",
        gateway_jwks_allowed_origins=("https://api.internal.example",),
        response_signing_key_id="ai-response-current",
        response_signing_private_key_file="/run/secrets/ai-response-private.pem",
    )
    assert settings.gateway_jwks_url.startswith("https://")
