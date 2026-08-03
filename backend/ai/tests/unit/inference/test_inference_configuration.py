import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.infrastructure.embedding_providers.configuration import (
    EmbeddingConfigurationError,
    build_embedding_provider,
)
from app.infrastructure.model_providers import (
    InferenceConfigurationError,
    build_model_mesh,
)
from app.modules.inference.application import (
    DeploymentPolicyDescriptor,
    GroundedAnswerPrompt,
    RetentionPolicy,
)
from app.platform.config import Settings


def test_openai_settings_require_secret_and_pinned_generation_model() -> None:
    with pytest.raises(ValidationError, match="generation_model"):
        Settings(
            _env_file=None,
            generation_provider="openai",
            openai_api_key="test-secret",
        )

    with pytest.raises(ValidationError, match="generation OpenAI capability"):
        Settings(
            _env_file=None,
            generation_provider="openai",
            generation_model="approved-model-2026-07-01",
            openai_generation_model_allowlist=("approved-model-2026-07-01",),
        )


def test_generation_and_embedding_provider_configuration_are_independent() -> None:
    settings = Settings(
        _env_file=None,
        generation_provider="openai",
        embedding_provider="disabled",
        generation_model="approved-model-2026-07-01",
        embedding_model="disabled",
        openai_api_key="test-secret",
        openai_generation_model_allowlist=("approved-model-2026-07-01",),
        openai_project_id="proj_test",
        openai_data_controls_approval_reference="approval-test-v1",
        openai_data_controls_approval_sha256="b" * 64,
        model_release_manifest_sha256="c" * 64,
    )
    assert settings.generation_provider == "openai"
    assert settings.embedding_provider == "disabled"


def test_openai_embedding_configuration_is_independent_from_generation() -> None:
    settings = Settings(
        _env_file=None,
        embedding_provider="openai",
        embedding_model="text-embedding-candidate-2026-07-01",
        embedding_dimension=3,
        embedding_input_microusd_per_million_tokens=20_000,
        openai_api_key="test-secret",
        openai_embedding_model_allowlist=("text-embedding-candidate-2026-07-01",),
        openai_project_id="proj_test",
        openai_data_controls_approval_reference="approval-test-v1",
        openai_data_controls_approval_sha256="b" * 64,
        model_release_manifest_sha256="c" * 64,
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
        base_url=settings.openai_base_url,
    )

    provider = build_embedding_provider(settings, client=client)

    assert provider is not None
    assert settings.generation_provider == "disabled"
    asyncio.run(client.aclose())


def test_generation_and_embedding_cannot_share_legacy_openai_authority() -> None:
    with pytest.raises(ValidationError, match="independent credentials"):
        Settings(
            _env_file=None,
            generation_provider="openai",
            generation_model="generation-v1",
            openai_generation_model_allowlist=("generation-v1",),
            embedding_provider="openai",
            embedding_model="embedding-v1",
            openai_embedding_model_allowlist=("embedding-v1",),
            openai_api_key="legacy-shared-secret",
            openai_project_id="legacy-project",
            openai_data_controls_approval_reference="approval-v1",
            openai_data_controls_approval_sha256="a" * 64,
        )


def test_generation_and_embedding_accept_separate_openai_authorities() -> None:
    settings = Settings(
        _env_file=None,
        generation_provider="openai",
        generation_model="generation-v1",
        openai_generation_model_allowlist=("generation-v1",),
        embedding_provider="openai",
        embedding_model="embedding-v1",
        openai_embedding_model_allowlist=("embedding-v1",),
        generation_openai_api_key="generation-secret",
        generation_openai_project_id="generation-project",
        generation_openai_approval_reference="generation-approval-v1",
        generation_openai_approval_sha256="a" * 64,
        generation_openai_base_url="https://api.openai.com/v1",
        generation_openai_retention_policy="zero_data_retention",
        embedding_openai_api_key="embedding-secret",
        embedding_openai_project_id="embedding-project",
        embedding_openai_approval_reference="embedding-approval-v1",
        embedding_openai_approval_sha256="b" * 64,
        embedding_openai_base_url="https://api.openai.com/v1",
        embedding_openai_retention_policy="zero_data_retention",
    )
    assert (
        settings.openai_capability("generation").project_id
        != settings.openai_capability("embedding").project_id
    )


def test_self_hosted_embedding_requires_loopback_or_https_endpoint() -> None:
    with pytest.raises(ValidationError, match="self_hosted_embedding_base_url"):
        Settings(
            _env_file=None,
            embedding_provider="self_hosted",
            embedding_model="self-hosted-candidate-v1",
            embedding_dimension=3,
            self_hosted_embedding_base_url="http://provider.internal:8080",
        )


def test_self_hosted_embedding_requires_pinned_deployment_identity() -> None:
    with pytest.raises(ValidationError, match="fingerprints"):
        Settings(
            _env_file=None,
            embedding_provider="self_hosted",
            embedding_model="self-hosted-candidate-v1",
            embedding_dimension=3,
            self_hosted_embedding_base_url="http://127.0.0.1:8080",
        )


def test_self_hosted_embedding_builds_with_pinned_identity_without_generation() -> None:
    settings = Settings(
        _env_file=None,
        embedding_provider="self_hosted",
        embedding_model="self-hosted-candidate-v1",
        embedding_dimension=3,
        embedding_input_template_revision="embedding-input-v1",
        embedding_query_prefix="query: ",
        embedding_document_prefix="passage: ",
        self_hosted_embedding_base_url="http://127.0.0.1:8080",
        self_hosted_embedding_tokenizer_sha256="a" * 64,
        self_hosted_embedding_weights_sha256="b" * 64,
        self_hosted_embedding_deployment_sha256="c" * 64,
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
        base_url=settings.self_hosted_embedding_base_url,
    )

    provider = build_embedding_provider(settings, client=client)

    assert provider is not None
    assert settings.generation_provider == "disabled"
    asyncio.run(client.aclose())


def test_disabled_embedding_builds_no_provider_and_unknown_adapter_fails_closed() -> None:
    assert build_embedding_provider(Settings(_env_file=None)) is None
    settings = Settings(
        _env_file=None,
        embedding_provider="azure_openai",
        embedding_model="candidate-v1",
        embedding_dimension=3,
    )
    with pytest.raises(EmbeddingConfigurationError, match="no approved runtime adapter"):
        build_embedding_provider(settings)


def test_openai_settings_reject_non_loopback_cleartext_endpoint() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            _env_file=None,
            generation_provider="openai",
            generation_model="approved-model-2026-07-01",
            openai_api_key="test-secret",
            openai_generation_model_allowlist=("approved-model-2026-07-01",),
            openai_project_id="proj_test",
            openai_data_controls_approval_reference="approval-test-v1",
            openai_data_controls_approval_sha256="b" * 64,
            model_release_manifest_sha256="c" * 64,
            openai_base_url="http://provider.internal/v1",
        )


def test_openai_production_endpoint_is_pinned_to_official_origin() -> None:
    with pytest.raises(ValidationError, match="api.openai.com"):
        Settings(
            _env_file=None,
            environment="production",
            expose_docs=False,
            database_url="postgresql+asyncpg://vfbiz:vfbiz@db:5432/vfbiz_ai",
            redis_url="redis://redis:6379/2",
            gateway_jwks_url="https://api.internal.example/.well-known/jwks.json",
            gateway_jwks_allowed_origins=("https://api.internal.example",),
            response_signing_key_id="ai-response-current",
            response_signing_private_key_file="/run/secrets/ai-response-private.pem",
            generation_provider="openai",
            generation_model="approved-model-2026-07-01",
            openai_api_key="test-secret",
            openai_generation_model_allowlist=("approved-model-2026-07-01",),
            openai_project_id="proj_test",
            openai_data_controls_approval_reference="approval-test-v1",
            openai_data_controls_approval_sha256="b" * 64,
            model_release_manifest_sha256="c" * 64,
            openai_base_url="https://proxy.example/v1",
        )


def test_openai_production_requires_data_controls_and_pricing_approval() -> None:
    common: dict[str, object] = {
        "_env_file": None,
        "environment": "production",
        "expose_docs": False,
        "database_url": "postgresql+asyncpg://vfbiz:vfbiz@db:5432/vfbiz_ai",
        "redis_url": "redis://redis:6379/2",
        "gateway_jwks_url": "https://api.internal.example/.well-known/jwks.json",
        "gateway_jwks_allowed_origins": ("https://api.internal.example",),
        "response_signing_key_id": "ai-response-current",
        "response_signing_private_key_file": "/run/secrets/ai-response-private.pem",
        "generation_provider": "openai",
        "generation_model": "approved-model-2026-07-01",
        "openai_api_key": "test-secret",
        "openai_generation_model_allowlist": ("approved-model-2026-07-01",),
        "openai_project_id": "proj_test",
    }
    with pytest.raises(ValidationError, match="durable approval"):
        Settings(**common)

    common["openai_data_controls_approval_reference"] = "approval-test-v1"
    common["openai_data_controls_approval_sha256"] = "b" * 64
    common["model_release_manifest_sha256"] = "c" * 64
    with pytest.raises(ValidationError, match="token prices"):
        Settings(**common)


def test_disabled_mode_builds_empty_fail_closed_mesh() -> None:
    mesh = build_model_mesh(Settings(_env_file=None))
    assert mesh is not None


def test_openai_mode_builds_mesh_without_calling_network() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        generation_provider="openai",
        generation_model="approved-model-2026-07-01",
        openai_api_key="test-secret",
        openai_generation_model_allowlist=("approved-model-2026-07-01",),
        openai_project_id="proj_test",
        openai_data_controls_approval_reference="approval-test-v1",
        openai_data_controls_approval_sha256="b" * 64,
        model_release_manifest_sha256="c" * 64,
        openai_base_url="http://127.0.0.1:9999/v1",
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
        base_url=settings.openai_base_url,
    )
    policy = DeploymentPolicyDescriptor(
        revision="release-gate-v3",
        profile=settings.model_policy_profile,
        safety_tier=settings.model_safety_tier,
        residency=settings.model_residency,
        retention=RetentionPolicy.STANDARD,
        schema_revision=settings.structured_schema_revision,
        model_release=settings.generation_model,
        provider_project_id="proj_test",
        provider_organization_id=None,
        data_controls_approval_reference="approval-test-v1",
        data_controls_approval_sha256="b" * 64,
        release_manifest_sha256="c" * 64,
    )
    mesh = build_model_mesh(
        settings,
        client=client,
        policy=policy,
        prompt=GroundedAnswerPrompt(revision=settings.prompt_revision),
    )
    assert mesh is not None
    assert "test-secret" not in repr(settings)


def test_unimplemented_provider_fails_closed() -> None:
    settings = Settings(
        _env_file=None,
        generation_provider="self_hosted",
        generation_model="approved-model-2026-07-01",
    )
    with pytest.raises(InferenceConfigurationError, match="no approved runtime adapter"):
        build_model_mesh(settings)


def _vertex_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "test",
        "generation_provider": "vertex",
        "generation_model": "gemini-3.5-flash",
        "vertex_project_id": "vinfast-503003",
        "vertex_location": "asia-southeast1",
        "model_residency": "asia-southeast1",
        "vertex_generation_model_allowlist": ("gemini-3.5-flash",),
        "vertex_data_controls_approval_reference": "vertex-data-approval-v1",
        "vertex_data_controls_approval_sha256": "b" * 64,
        "vertex_pricing_revision": "vertex-pricing-2026-08-01",
        "input_microusd_per_million_tokens": 1,
        "output_microusd_per_million_tokens": 1,
    }
    values.update(overrides)
    return Settings(**values)


def test_vertex_settings_require_release_bound_identity_and_pricing() -> None:
    with pytest.raises(ValidationError, match="data-control approval"):
        _vertex_settings(vertex_data_controls_approval_reference=None)
    with pytest.raises(ValidationError, match="allowlist"):
        _vertex_settings(vertex_generation_model_allowlist=())
    with pytest.raises(ValidationError, match="token prices"):
        _vertex_settings(input_microusd_per_million_tokens=0)
    with pytest.raises(ValidationError, match="model_residency"):
        _vertex_settings(model_residency="global")


def test_vertex_generation_factory_is_composed_without_provider_call() -> None:
    settings = _vertex_settings()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
    )

    async def token() -> str:
        return "test-adc-token"

    policy = DeploymentPolicyDescriptor(
        revision="release-gate-v3",
        profile=settings.model_policy_profile,
        safety_tier=settings.model_safety_tier,
        residency="asia-southeast1",
        retention=RetentionPolicy.STANDARD,
        schema_revision=settings.structured_schema_revision,
        model_release="gemini-3.5-flash",
        provider_project_id="vinfast-503003",
        provider_organization_id=None,
        data_controls_approval_reference="vertex-data-approval-v1",
        data_controls_approval_sha256="b" * 64,
        release_manifest_sha256="c" * 64,
    )
    mesh = build_model_mesh(
        settings,
        client=client,
        policy=policy,
        prompt=GroundedAnswerPrompt(revision=settings.prompt_revision),
        vertex_access_token_provider=token,
    )
    assert mesh is not None
    assert "test-adc-token" not in repr(settings)
    asyncio.run(client.aclose())


def test_vertex_embedding_factory_is_composed_without_provider_call() -> None:
    settings = _vertex_settings(
        generation_provider="disabled",
        generation_model="disabled",
        embedding_provider="vertex",
        embedding_model="gemini-embedding-001",
        embedding_dimension=768,
        embedding_max_items_per_request=1,
        vertex_generation_model_allowlist=(),
        vertex_embedding_model_allowlist=("gemini-embedding-001",),
        embedding_input_microusd_per_million_tokens=1,
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
    )

    async def token() -> str:
        return "test-adc-token"

    from app.infrastructure.embedding_providers.configuration import (
        build_embedding_provider,
    )

    provider = build_embedding_provider(
        settings,
        client=client,
        vertex_access_token_provider=token,
    )
    assert provider is not None
    asyncio.run(provider.aclose())
