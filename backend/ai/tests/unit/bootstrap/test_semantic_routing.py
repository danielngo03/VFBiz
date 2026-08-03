from types import SimpleNamespace
from typing import cast

import httpx
import pytest

from app.bootstrap.semantic_routing import (
    SemanticRoutingRuntime,
    semantic_route_output_schema_sha256,
    semantic_routing_policy_sha256,
)
from app.infrastructure.model_providers.semantic_classifier_http import (
    SemanticClassifierHttpDeployment,
)
from app.modules.assistant.application import GovernedSemanticSupervisor
from app.modules.assistant.infrastructure.keyword_supervisor import KeywordSupervisor
from app.modules.governance.application import (
    SemanticClassifierBindingResolutionError,
    SemanticClassifierBindingResolver,
)
from app.modules.governance.domain import SemanticClassifierReleaseBinding


class FixedResolver:
    def __init__(self, result: object) -> None:
        self.result = result

    async def resolve(self, **_kwargs: object) -> SemanticClassifierReleaseBinding:
        if isinstance(self.result, Exception):
            raise self.result
        return cast(SemanticClassifierReleaseBinding, self.result)


def release_binding(**overrides: object) -> SemanticClassifierReleaseBinding:
    values: dict[str, object] = {
        "binding_envelope_sha256": "d" * 64,
        "classifier_artifact_ref": "classifier://vivi/router/v1",
        "classifier_artifact_sha256": "a" * 64,
        "classifier_revision": "vivi-router-v1",
        "evaluation_evidence_sha256": "b" * 64,
        "output_schema_revision": "semantic-route-output-v1",
        "output_schema_sha256": semantic_route_output_schema_sha256(
            "semantic-route-output-v1"
        ),
        "routing_policy_revision": "semantic-routing-policy-v1",
        "routing_policy_sha256": semantic_routing_policy_sha256(
            "semantic-routing-policy-v1"
        ),
    }
    values.update(overrides)
    return cast(SemanticClassifierReleaseBinding, SimpleNamespace(**values))


def deployment() -> SemanticClassifierHttpDeployment:
    return SemanticClassifierHttpDeployment(
        endpoint="https://classifier.internal.example/v1/route",
        artifact_ref="classifier://vivi/router/v1",
        artifact_sha256="a" * 64,
        api_token=None,
        timeout_seconds=1,
        max_request_bytes=32_768,
        max_response_bytes=16_384,
        max_concurrency=2,
    )


@pytest.mark.asyncio
async def test_disabled_deployment_stays_deterministic() -> None:
    runtime = SemanticRoutingRuntime(
        resolver=cast(
            SemanticClassifierBindingResolver,
            FixedResolver(AssertionError("resolver must not be called")),
        ),
        deployment=None,
        client=None,
    )

    supervisor = await runtime.supervisor_for(
        activation_id="activation-1",
        activation_envelope_sha256="e" * 64,
        assistant_profile="customer-assistant",
        environment="staging",
    )

    assert isinstance(supervisor, KeywordSupervisor)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        SemanticClassifierBindingResolutionError("CLASSIFIER_BINDING_EXPIRED"),
        RuntimeError("database unavailable"),
    ],
)
async def test_authority_failure_falls_back_fail_closed(failure: Exception) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(500)
        ),
        trust_env=False,
    ) as client:
        runtime = SemanticRoutingRuntime(
            resolver=cast(
                SemanticClassifierBindingResolver,
                FixedResolver(failure),
            ),
            deployment=deployment(),
            client=client,
        )
        supervisor = await runtime.supervisor_for(
            activation_id="activation-1",
            activation_envelope_sha256="e" * 64,
            assistant_profile="customer-assistant",
            environment="staging",
        )

    assert isinstance(supervisor, KeywordSupervisor)


@pytest.mark.asyncio
async def test_matching_active_binding_composes_governed_supervisor() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(500)
        ),
        trust_env=False,
    ) as client:
        runtime = SemanticRoutingRuntime(
            resolver=cast(
                SemanticClassifierBindingResolver,
                FixedResolver(release_binding()),
            ),
            deployment=deployment(),
            client=client,
        )
        supervisor = await runtime.supervisor_for(
            activation_id="activation-1",
            activation_envelope_sha256="e" * 64,
            assistant_profile="customer-assistant",
            environment="staging",
        )

    assert isinstance(supervisor, GovernedSemanticSupervisor)


@pytest.mark.asyncio
async def test_code_policy_digest_mismatch_stays_deterministic() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(500)
        ),
        trust_env=False,
    ) as client:
        runtime = SemanticRoutingRuntime(
            resolver=cast(
                SemanticClassifierBindingResolver,
                FixedResolver(release_binding(routing_policy_sha256="f" * 64)),
            ),
            deployment=deployment(),
            client=client,
        )
        supervisor = await runtime.supervisor_for(
            activation_id="activation-1",
            activation_envelope_sha256="e" * 64,
            assistant_profile="customer-assistant",
            environment="staging",
        )

    assert isinstance(supervisor, KeywordSupervisor)
