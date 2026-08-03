from datetime import UTC, datetime

import httpx

from app.infrastructure.embedding_providers.openai import OpenAIEmbeddingAdapter
from app.infrastructure.embedding_providers.policy import (
    EmbeddingAdapterPolicy,
    TeiDeploymentIdentity,
)
from app.infrastructure.embedding_providers.tei import TeiEmbeddingAdapter
from app.infrastructure.embedding_providers.vertex_embedding import (
    VertexEmbeddingAdapter,
    VertexEmbeddingDeploymentDescriptor,
)
from app.infrastructure.model_providers.vertex_auth import (
    AccessTokenProvider,
    ApplicationDefaultVertexTokenProvider,
)
from app.modules.inference.application.embedding_ports import (
    EmbeddingGenerationIdentity,
    EmbeddingProvider,
)
from app.modules.inference.application.embedding_runtime import (
    ConservativeByteTokenEstimator,
    EmbeddingRuntime,
    EmbeddingRuntimePolicy,
)
from app.platform.config import Settings


class EmbeddingConfigurationError(RuntimeError):
    """Raised when an enabled embedding provider cannot be composed safely."""


def embedding_generation_for_settings(
    settings: Settings,
) -> EmbeddingGenerationIdentity | None:
    if settings.embedding_provider == "disabled":
        return None
    return _policy_for(settings).generation


def build_embedding_runtime(
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
    vertex_access_token_provider: AccessTokenProvider | None = None,
) -> EmbeddingRuntime | None:
    provider = build_embedding_provider(
        settings,
        client=client,
        vertex_access_token_provider=vertex_access_token_provider,
    )
    if provider is None:
        return None
    policy = _policy_for(settings)
    maximum_cost = (
        (
            settings.embedding_max_input_tokens_per_request
            * settings.embedding_input_microusd_per_million_tokens
            + 999_999
        )
        // 1_000_000
    ) + settings.embedding_fixed_request_cost_microusd
    return EmbeddingRuntime(
        provider=provider,
        token_estimator=ConservativeByteTokenEstimator(),
        policy=EmbeddingRuntimePolicy(
            generation=policy.generation,
            timeout_seconds=settings.request_timeout_seconds,
            max_items=settings.embedding_max_items_per_request,
            max_input_bytes=settings.embedding_max_input_bytes_per_request,
            max_input_tokens=settings.embedding_max_input_tokens_per_request,
            max_cost_microusd=max(1, maximum_cost),
        ),
        clock=lambda: datetime.now(UTC),
    )


def _policy_for(settings: Settings) -> EmbeddingAdapterPolicy:
    return EmbeddingAdapterPolicy(
        provider_id=settings.embedding_provider,
        model_revision=settings.embedding_model,
        output_dimension=settings.embedding_dimension,
        max_items_per_request=settings.embedding_max_items_per_request,
        max_input_bytes_per_request=settings.embedding_max_input_bytes_per_request,
        max_input_tokens_per_request=settings.embedding_max_input_tokens_per_request,
        input_microusd_per_million_tokens=(
            settings.embedding_input_microusd_per_million_tokens
        ),
        fixed_request_cost_microusd=settings.embedding_fixed_request_cost_microusd,
        max_concurrency=settings.embedding_max_concurrency,
        max_response_bytes=settings.embedding_max_response_bytes,
        max_output_elements=settings.embedding_max_output_elements,
        input_template_revision=settings.embedding_input_template_revision,
        query_prefix=settings.embedding_query_prefix,
        document_prefix=settings.embedding_document_prefix,
        tokenizer_revision=(
            settings.self_hosted_embedding_tokenizer_sha256
            if settings.embedding_provider == "self_hosted"
            and settings.self_hosted_embedding_tokenizer_sha256 is not None
            else f"provider-managed:{settings.embedding_model}"
        ),
        weights_revision=(
            settings.self_hosted_embedding_weights_sha256
            if settings.embedding_provider == "self_hosted"
            and settings.self_hosted_embedding_weights_sha256 is not None
            else f"provider-managed:{settings.embedding_model}"
        ),
        circuit_failure_threshold=settings.embedding_circuit_failure_threshold,
        circuit_recovery_seconds=settings.embedding_circuit_recovery_seconds,
    )


def build_embedding_provider(
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
    vertex_access_token_provider: AccessTokenProvider | None = None,
) -> EmbeddingProvider | None:
    if settings.embedding_provider == "disabled":
        return None

    policy = _policy_for(settings)

    if settings.embedding_provider == "openai":
        identity = settings.openai_capability("embedding")
        if (
            identity.api_key is None
            or identity.project_id is None
            or identity.approval_reference is None
            or identity.approval_sha256 is None
        ):
            raise EmbeddingConfigurationError(
                "OpenAI embedding credentials or approval evidence are unavailable"
            )
        resolved_client = client or httpx.AsyncClient(
            base_url=identity.base_url,
            timeout=settings.request_timeout_seconds,
            follow_redirects=False,
            # Provider egress is an approved deployment boundary. Do not let
            # ambient HTTP_PROXY/HTTPS_PROXY variables silently redirect
            # customer evidence or provider credentials.
            trust_env=False,
        )
        return OpenAIEmbeddingAdapter(
            policy,
            client=resolved_client,
            api_key=identity.api_key.get_secret_value(),
            project_id=identity.project_id,
            organization_id=identity.organization_id,
            owns_client=client is None,
        )

    if settings.embedding_provider == "self_hosted":
        if (
            settings.self_hosted_embedding_tokenizer_sha256 is None
            or settings.self_hosted_embedding_weights_sha256 is None
            or settings.self_hosted_embedding_deployment_sha256 is None
        ):
            raise EmbeddingConfigurationError(
                "self-hosted embedding deployment identity is unavailable"
            )
        resolved_client = client or httpx.AsyncClient(
            base_url=settings.self_hosted_embedding_base_url,
            timeout=settings.request_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )
        return TeiEmbeddingAdapter(
            policy,
            client=resolved_client,
            expected_identity=TeiDeploymentIdentity(
                model_revision=settings.embedding_model,
                tokenizer_sha256=settings.self_hosted_embedding_tokenizer_sha256,
                weights_sha256=settings.self_hosted_embedding_weights_sha256,
                input_template_revision=settings.embedding_input_template_revision,
                deployment_sha256=settings.self_hosted_embedding_deployment_sha256,
            ),
            api_token=(
                settings.self_hosted_embedding_api_token.get_secret_value()
                if settings.self_hosted_embedding_api_token is not None
                else None
            ),
            owns_client=client is None,
        )

    if settings.embedding_provider == "vertex":
        identity = settings.vertex_capability("embedding")
        if (
            identity.project_id is None
            or identity.location is None
            or identity.approval_sha256 is None
            or identity.pricing_revision is None
        ):
            raise EmbeddingConfigurationError(
                "Vertex embedding deployment identity or approval evidence is unavailable"
            )
        token_provider = vertex_access_token_provider or ApplicationDefaultVertexTokenProvider()
        return VertexEmbeddingAdapter(
            policy,
            deployment=VertexEmbeddingDeploymentDescriptor(
                project_id=identity.project_id,
                location=identity.location,
                model_revision=settings.embedding_model,
                profile=settings.model_policy_profile,
                retention_policy=identity.retention_policy,
                pricing_revision=identity.pricing_revision,
                data_controls_approval_sha256=identity.approval_sha256,
            ),
            access_token_provider=token_provider,
            client=client,
            owns_client=client is None,
        )

    raise EmbeddingConfigurationError(
        f"embedding provider {settings.embedding_provider!r} has no approved runtime adapter"
    )
