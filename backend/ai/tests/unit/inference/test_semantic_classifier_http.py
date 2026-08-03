import json

import httpx
import pytest
from pydantic import ValidationError

from app.infrastructure.model_providers.semantic_classifier_http import (
    HttpSemanticRouteClassifier,
    SemanticClassifierHttpDeployment,
)
from app.modules.assistant.application import SemanticClassifierBinding

_BINDING = SemanticClassifierBinding(
    binding_envelope_sha256="d" * 64,
    classifier_artifact_ref="classifier://vivi/router/v1",
    artifact_sha256="a" * 64,
    classifier_revision="vivi-router-v1",
    evaluation_evidence_sha256="b" * 64,
    output_schema_revision="semantic-route-output-v1",
    threshold_policy_revision="semantic-routing-policy-v1",
    threshold_policy_sha256="c" * 64,
    semantic_acceptance_confidence=0.8,
    semantic_activation_below=0.8,
)


def deployment(**overrides: object) -> SemanticClassifierHttpDeployment:
    values: dict[str, object] = {
        "endpoint": "https://classifier.internal.example/v1/route",
        "artifact_ref": _BINDING.classifier_artifact_ref,
        "artifact_sha256": _BINDING.artifact_sha256,
        "api_token": None,
        "timeout_seconds": 1,
        "max_request_bytes": 32_768,
        "max_response_bytes": 16_384,
        "max_concurrency": 2,
    }
    values.update(overrides)
    return SemanticClassifierHttpDeployment(**values)  # type: ignore[arg-type]


def valid_response(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "abuseSignals": [],
        "bindingEnvelopeSha256": _BINDING.binding_envelope_sha256,
        "confidence": 0.93,
        "intent": "financing_question",
        "missingSlots": [],
        "multiIntent": False,
        "outOfDomain": False,
        "requiredSlots": [],
    }
    document.update(overrides)
    return document


@pytest.mark.asyncio
async def test_classifier_sends_only_opaque_context_and_requires_binding() -> None:
    captured: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.headers["x-vfbiz-binding-sha256"] == "d" * 64
        return httpx.Response(200, json=valid_response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        classifier = HttpSemanticRouteClassifier(
            deployment=deployment(),
            binding=_BINDING,
            client=client,
        )
        prediction = await classifier.classify(
            message="Mỗi tháng khoảng bao nhiêu?",
            global_entities=(),
            previous_task=None,
        )

    assert captured["globalEntities"] == []
    assert prediction.decision.intent == "financing_question"
    assert prediction.decision.routing_source == "semantic"
    assert prediction.binding == _BINDING


@pytest.mark.asyncio
async def test_classifier_rejects_extra_or_coerced_response_fields() -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=valid_response(confidence="0.93", unexpected="value"),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        classifier = HttpSemanticRouteClassifier(
            deployment=deployment(),
            binding=_BINDING,
            client=client,
        )
        with pytest.raises(ValidationError):
            await classifier.classify(
                message="Tôi cần tư vấn",
                global_entities=(),
                previous_task=None,
            )


@pytest.mark.asyncio
async def test_classifier_rejects_response_from_another_binding() -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=valid_response(bindingEnvelopeSha256="e" * 64),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        classifier = HttpSemanticRouteClassifier(
            deployment=deployment(),
            binding=_BINDING,
            client=client,
        )
        with pytest.raises(ValueError, match="binding mismatch"):
            await classifier.classify(
                message="Tôi cần tư vấn",
                global_entities=(),
                previous_task=None,
            )


@pytest.mark.asyncio
async def test_classifier_stops_reading_an_oversized_response() -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{" + (b"x" * 2_048) + b"}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        classifier = HttpSemanticRouteClassifier(
            deployment=deployment(max_response_bytes=1_024),
            binding=_BINDING,
            client=client,
        )
        with pytest.raises(ValueError, match="release budget"):
            await classifier.classify(
                message="Tôi cần tư vấn",
                global_entities=(),
                previous_task=None,
            )


@pytest.mark.asyncio
async def test_classifier_rejects_deployment_not_pinned_by_release() -> None:
    async with httpx.AsyncClient(trust_env=False) as client:
        with pytest.raises(ValueError, match="does not match release binding"):
            HttpSemanticRouteClassifier(
                deployment=deployment(artifact_sha256="f" * 64),
                binding=_BINDING,
                client=client,
            )
