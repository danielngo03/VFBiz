import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.model_providers.semantic_classifier_http import (
    HttpSemanticRouteClassifier,
    SemanticClassifierHttpDeployment,
)
from app.modules.assistant.application import (
    GovernedSemanticSupervisor,
    SemanticClassifierBinding,
    SupervisorPort,
)
from app.modules.assistant.infrastructure.keyword_supervisor import KeywordSupervisor
from app.modules.governance.application import (
    SemanticClassifierBindingResolutionError,
    SemanticClassifierBindingResolver,
)
from app.modules.governance.domain import SemanticClassifierReleaseBinding
from app.modules.governance.infrastructure import (
    BoundedOpaqueArtifactDigestReader,
    BoundedSemanticClassifierEvidenceVerifier,
    JsonSchemaAuthorityValidator,
    PostgresSemanticClassifierBindingStore,
    PostgresTrustedReleaseRegistry,
)
from app.platform.config import Settings

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_BINDING_SCHEMA = (
    _REPOSITORY_ROOT
    / "contracts/ai/releases/semantic-classifier-binding.schema.json"
)
_OUTPUT_SCHEMA_PATH = (
    _REPOSITORY_ROOT
    / "contracts/ai/assistant/semantic-route-output.schema.json"
)
_OUTPUT_SCHEMA_REVISION = "semantic-route-output-v1"
_OUTPUT_SCHEMA = json.loads(_OUTPUT_SCHEMA_PATH.read_text(encoding="utf-8"))
if _OUTPUT_SCHEMA.get("x-vfbiz-revision") != _OUTPUT_SCHEMA_REVISION:
    raise RuntimeError("semantic route output contract revision mismatch")
_POLICIES = {
    "semantic-routing-policy-v1": {
        "revision": "semantic-routing-policy-v1",
        "semanticAcceptanceConfidence": 0.8,
        "semanticActivationBelow": 0.8,
    }
}
_LOGGER = logging.getLogger(__name__)


def _digest(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def semantic_routing_policy_sha256(revision: str) -> str | None:
    policy = _POLICIES.get(revision)
    return None if policy is None else _digest(policy)


def semantic_route_output_schema_sha256(revision: str) -> str | None:
    if revision != _OUTPUT_SCHEMA_REVISION:
        return None
    return _digest(_OUTPUT_SCHEMA)


@dataclass(slots=True)
class SemanticRoutingRuntime:
    resolver: SemanticClassifierBindingResolver
    deployment: SemanticClassifierHttpDeployment | None
    client: httpx.AsyncClient | None

    async def supervisor_for(
        self,
        *,
        activation_id: str,
        activation_envelope_sha256: str,
        assistant_profile: str,
        environment: str,
    ) -> SupervisorPort:
        deterministic = KeywordSupervisor()
        if self.deployment is None or self.client is None:
            return deterministic
        try:
            release_binding = await self.resolver.resolve(
                activation_id=activation_id,
                activation_envelope_sha256=activation_envelope_sha256,
                assistant_profile=assistant_profile,
                environment=environment,
            )
            binding = _map_binding(release_binding)
            classifier = HttpSemanticRouteClassifier(
                deployment=self.deployment,
                binding=binding,
                client=self.client,
            )
            return GovernedSemanticSupervisor(
                deterministic=deterministic,
                classifier=classifier,
                binding=binding,
            )
        except asyncio.CancelledError:
            raise
        except (SemanticClassifierBindingResolutionError, ValueError) as error:
            _LOGGER.warning(
                "semantic classifier unavailable; using deterministic routing",
                extra={"classifier_fallback_type": type(error).__name__},
            )
            return deterministic
        except Exception as error:
            _LOGGER.exception(
                "semantic classifier authority failed; using deterministic routing",
                extra={"classifier_fallback_type": type(error).__name__},
            )
            return deterministic

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()


def build_semantic_routing_runtime(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
) -> SemanticRoutingRuntime:
    registry = PostgresTrustedReleaseRegistry(sessions)
    schema = json.loads(_BINDING_SCHEMA.read_text(encoding="utf-8"))
    resolver = SemanticClassifierBindingResolver(
        store=PostgresSemanticClassifierBindingStore(
            sessions,
            schema_validator=JsonSchemaAuthorityValidator(schema),
        ),
        digest_reader=BoundedOpaqueArtifactDigestReader(
            registry=registry,
            timeout_seconds=2,
            max_concurrency=16,
        ),
        evidence_verifier=BoundedSemanticClassifierEvidenceVerifier(
            registry=registry,
            timeout_seconds=2,
            max_concurrency=16,
        ),
        freshness_fence=registry,
        clock=lambda: datetime.now(UTC),
        timeout_seconds=2,
        max_concurrency=16,
    )
    if settings.semantic_classifier_provider == "disabled":
        return SemanticRoutingRuntime(resolver=resolver, deployment=None, client=None)
    if (
        settings.semantic_classifier_endpoint is None
        or settings.semantic_classifier_artifact_ref is None
        or settings.semantic_classifier_artifact_sha256 is None
    ):
        return SemanticRoutingRuntime(resolver=resolver, deployment=None, client=None)
    client = httpx.AsyncClient(
        follow_redirects=False,
        trust_env=False,
        timeout=settings.semantic_classifier_timeout_seconds,
    )
    return SemanticRoutingRuntime(
        resolver=resolver,
        deployment=SemanticClassifierHttpDeployment(
            endpoint=settings.semantic_classifier_endpoint,
            artifact_ref=settings.semantic_classifier_artifact_ref,
            artifact_sha256=settings.semantic_classifier_artifact_sha256,
            api_token=(
                settings.semantic_classifier_api_token.get_secret_value()
                if settings.semantic_classifier_api_token is not None
                else None
            ),
            timeout_seconds=settings.semantic_classifier_timeout_seconds,
            max_request_bytes=settings.semantic_classifier_max_request_bytes,
            max_response_bytes=settings.semantic_classifier_max_response_bytes,
            max_concurrency=settings.semantic_classifier_max_concurrency,
        ),
        client=client,
    )


def _map_binding(
    release: SemanticClassifierReleaseBinding,
) -> SemanticClassifierBinding:
    policy = _POLICIES.get(release.routing_policy_revision)
    if (
        policy is None
        or semantic_routing_policy_sha256(release.routing_policy_revision)
        != release.routing_policy_sha256
        or semantic_route_output_schema_sha256(release.output_schema_revision)
        != release.output_schema_sha256
    ):
        raise ValueError("classifier code-owned policy or output schema mismatch")
    return SemanticClassifierBinding(
        binding_envelope_sha256=release.binding_envelope_sha256,
        classifier_artifact_ref=release.classifier_artifact_ref,
        artifact_sha256=release.classifier_artifact_sha256,
        classifier_revision=release.classifier_revision,
        evaluation_evidence_sha256=release.evaluation_evidence_sha256,
        output_schema_revision=release.output_schema_revision,
        threshold_policy_revision=release.routing_policy_revision,
        threshold_policy_sha256=release.routing_policy_sha256,
        semantic_acceptance_confidence=float(
            policy["semanticAcceptanceConfidence"]
        ),
        semantic_activation_below=float(policy["semanticActivationBelow"]),
    )
