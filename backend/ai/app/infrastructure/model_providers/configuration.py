import json
from hashlib import sha256

import httpx

from app.infrastructure.model_providers.openai_responses import OpenAIResponsesProvider
from app.modules.inference.application import (
    ClaimSupportValidator,
    DeploymentPolicyDescriptor,
    DeploymentRoute,
    FailClosedClaimSupportValidator,
    GroundedAnswerPrompt,
    ModelMesh,
)
from app.platform.config import Settings


class InferenceConfigurationError(RuntimeError):
    """Raised when an enabled provider has no approved runtime adapter."""


def model_deployment_sha256_for_settings(settings: Settings) -> str:
    """Fingerprint the non-secret generation deployment identity.

    Credentials are intentionally excluded: rotation must not change model
    semantics, while provider/project/origin/model/policy/cost controls must.
    """
    identity = settings.openai_capability("generation")
    payload = {
        "provider": settings.generation_provider,
        "modelRevision": settings.generation_model,
        "providerOrigin": identity.base_url.rstrip("/"),
        "projectId": identity.project_id,
        "organizationId": identity.organization_id,
        "retention": identity.retention_policy,
        "modelAllowlist": sorted(settings.openai_generation_model_allowlist),
        "maxInputTokens": settings.max_input_tokens,
        "maxOutputTokens": settings.max_output_tokens,
        "maxResponseBytes": settings.max_response_bytes,
        "inputMicrousdPerMillionTokens": (
            settings.input_microusd_per_million_tokens
        ),
        "outputMicrousdPerMillionTokens": (
            settings.output_microusd_per_million_tokens
        ),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode()).hexdigest()


def build_model_mesh(
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
    policy: DeploymentPolicyDescriptor | None = None,
    prompt: GroundedAnswerPrompt | None = None,
    claim_support_validator: ClaimSupportValidator | None = None,
) -> ModelMesh:
    if settings.generation_provider == "disabled":
        return ModelMesh(
            (),
            claim_support_validator=(
                claim_support_validator or FailClosedClaimSupportValidator()
            ),
        )
    if settings.generation_provider != "openai":
        raise InferenceConfigurationError(
            "generation provider "
            f"{settings.generation_provider!r} has no approved runtime adapter"
        )
    if policy is None:
        raise InferenceConfigurationError(
            "an authority-resolved deployment policy is required"
        )
    identity = settings.openai_capability("generation")
    if identity.api_key is None:
        raise InferenceConfigurationError("OpenAI credentials are unavailable")
    if (
        identity.project_id is None
        or identity.approval_reference is None
        or identity.approval_sha256 is None
    ):
        raise InferenceConfigurationError("OpenAI approval evidence is unavailable")

    resolved_policy = policy
    deployment = OpenAIResponsesProvider(
        deployment_id=(
            f"openai:{settings.generation_model}:{settings.model_policy_profile}"
        ),
        api_key=identity.api_key.get_secret_value(),
        project_id=identity.project_id,
        organization_id=identity.organization_id,
        model_revision=settings.generation_model,
        model_allowlist=settings.openai_generation_model_allowlist,
        prompt=prompt or GroundedAnswerPrompt(revision=settings.prompt_revision),
        policy=resolved_policy,
        base_url=identity.base_url,
        request_timeout_seconds=settings.request_timeout_seconds,
        max_input_tokens=settings.max_input_tokens,
        max_output_tokens=settings.max_output_tokens,
        max_response_bytes=settings.max_response_bytes,
        max_concurrency=settings.max_provider_concurrency,
        input_microusd_per_million_tokens=(
            settings.input_microusd_per_million_tokens
        ),
        output_microusd_per_million_tokens=(
            settings.output_microusd_per_million_tokens
        ),
        client=client,
    )
    return ModelMesh(
        (DeploymentRoute(deployment=deployment, priority=100),),
        claim_support_validator=(
            claim_support_validator or FailClosedClaimSupportValidator()
        ),
    )
