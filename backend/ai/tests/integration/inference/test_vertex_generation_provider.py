import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.infrastructure.model_providers.vertex_generation import (
    VertexGenerationProvider,
)
from app.modules.inference.application import (
    DeploymentPolicyDescriptor,
    Evidence,
    GenerationOutcome,
    GenerationRequest,
    GroundedAnswerPrompt,
    InferenceBudget,
    InferenceFailure,
    InferenceFailureCode,
    RetentionPolicy,
)

MODEL = "gemini-2.5-flash-lite"
PROMPT = GroundedAnswerPrompt(revision="vertex-synthetic-smoke-v1")
POLICY = DeploymentPolicyDescriptor(
    revision="vertex-synthetic-smoke-v1",
    profile="synthetic-smoke-only",
    safety_tier="development-synthetic-v1",
    residency="asia-southeast1",
    retention=RetentionPolicy.STANDARD,
    schema_revision="grounded-answer-v2",
    model_release=MODEL,
    provider_project_id="vinfast-503003",
    provider_organization_id=None,
    data_controls_approval_reference="synthetic-only-no-release",
    data_controls_approval_sha256="a" * 64,
    release_manifest_sha256="b" * 64,
)
EVIDENCE = (
    Evidence(
        evidence_id="synthetic-1",
        source_uri="vfbiz://synthetic/smoke/revision-1/chunk-1",
        source_revision="sha256:" + "c" * 64,
        title="Synthetic arithmetic fixture",
        excerpt="The synthetic test value is four.",
        freshness="synthetic",
    ),
)


class EventCancellation:
    def __init__(self) -> None:
        self.event = asyncio.Event()

    @property
    def is_cancelled(self) -> bool:
        return self.event.is_set()

    async def wait(self) -> None:
        await self.event.wait()


def request(
    *,
    cancellation: EventCancellation | None = None,
    cost_budget: int = 10_000,
) -> GenerationRequest:
    return GenerationRequest(
        question="What is the synthetic test value?",
        evidence=EVIDENCE,
        budget=InferenceBudget(
            max_input_tokens=2_000,
            max_output_tokens=128,
            max_cost_microusd=cost_budget,
            max_attempts=1,
        ),
        deadline_at=datetime.now(UTC) + timedelta(seconds=5),
        required_policy=POLICY,
        correlation_id="vertex-synthetic-001",
        expected_prompt_revision=PROMPT.revision,
        expected_prompt_content_sha256=PROMPT.content_sha256,
        cancellation=cancellation,
    )


def provider_response(
    *,
    model: str = MODEL,
    outcome: str = "answered",
    answer: str | None = "The synthetic test value is four.",
    citation_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "responseId": "vertex-response-1",
        "modelVersion": model,
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "outcome": outcome,
                                    "answer": answer,
                                    "citation_ids": (
                                        ["synthetic-1"]
                                        if citation_ids is None
                                        else citation_ids
                                    ),
                                }
                            )
                        }
                    ],
                },
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 80,
            "candidatesTokenCount": 20,
            "cachedContentTokenCount": 0,
            "thoughtsTokenCount": 0,
        },
    }


def make_provider(
    handler: httpx.AsyncBaseTransport,
    **overrides: object,
) -> tuple[VertexGenerationProvider, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=handler)

    async def token() -> str:
        return "test-adc-token"

    kwargs: dict[str, object] = {
        "deployment_id": "vertex-synthetic-primary",
        "project_id": "vinfast-503003",
        "location": "asia-southeast1",
        "model_revision": MODEL,
        "model_allowlist": (MODEL,),
        "prompt": PROMPT,
        "policy": POLICY,
        "access_token_provider": token,
        "client": client,
        "input_microusd_per_million_tokens": 1_000_000,
        "output_microusd_per_million_tokens": 2_000_000,
    }
    kwargs.update(overrides)
    return VertexGenerationProvider(**kwargs), client  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_vertex_generation_is_region_pinned_and_structured() -> None:
    observed: dict[str, object] = {}

    async def handler(provider_request: httpx.Request) -> httpx.Response:
        observed["url"] = str(provider_request.url)
        observed["authorization"] = provider_request.headers["authorization"]
        observed["payload"] = json.loads(provider_request.content)
        return httpx.Response(
            200,
            headers={"x-request-id": "request-1"},
            json=provider_response(),
        )

    adapter, client = make_provider(httpx.MockTransport(handler))
    result = await adapter.generate_response(request())

    assert observed["url"] == (
        "https://asia-southeast1-aiplatform.googleapis.com/v1/"
        "projects/vinfast-503003/locations/asia-southeast1/"
        "publishers/google/models/gemini-2.5-flash-lite:generateContent"
    )
    assert observed["authorization"] == "Bearer test-adc-token"
    payload = observed["payload"]
    assert isinstance(payload, dict)
    assert payload["generationConfig"]["candidateCount"] == 1
    assert payload["generationConfig"]["temperature"] == 0
    assert payload["generationConfig"]["maxOutputTokens"] == 128
    assert "safety_identifier" not in json.dumps(payload)
    assert result.outcome is GenerationOutcome.ANSWERED
    assert result.model_revision == MODEL
    assert result.citations[0].evidence_id == "synthetic-1"
    assert result.estimated_cost_microusd == 120
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (403, InferenceFailureCode.PROVIDER_AUTHENTICATION_FAILED, False),
        (429, InferenceFailureCode.PROVIDER_RATE_LIMITED, True),
        (503, InferenceFailureCode.PROVIDER_UNAVAILABLE, True),
    ],
)
async def test_vertex_generation_maps_provider_failures(
    status: int,
    code: InferenceFailureCode,
    retryable: bool,
) -> None:
    adapter, client = make_provider(
        httpx.MockTransport(lambda _: httpx.Response(status))
    )
    with pytest.raises(InferenceFailure) as caught:
        await adapter.generate_response(request())
    assert caught.value.code is code
    assert caught.value.retryable is retryable
    await client.aclose()


@pytest.mark.asyncio
async def test_vertex_generation_rejects_model_and_citation_mismatch() -> None:
    responses = iter(
        (
            provider_response(model="gemini-unapproved"),
            provider_response(citation_ids=["outside-request"]),
        )
    )

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    adapter, client = make_provider(httpx.MockTransport(handler))
    with pytest.raises(InferenceFailure) as model_failure:
        await adapter.generate_response(request())
    assert model_failure.value.code is InferenceFailureCode.MODEL_REVISION_MISMATCH
    with pytest.raises(InferenceFailure) as citation_failure:
        await adapter.generate_response(request())
    assert (
        citation_failure.value.code
        is InferenceFailureCode.PROVIDER_INVALID_RESPONSE
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_vertex_generation_cancels_token_work() -> None:
    cancellation = EventCancellation()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def token() -> str:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return "unreachable"

    adapter, client = make_provider(
        httpx.MockTransport(lambda _: httpx.Response(500)),
        access_token_provider=token,
    )
    task = asyncio.create_task(
        adapter.generate_response(request(cancellation=cancellation))
    )
    await started.wait()
    cancellation.event.set()
    with pytest.raises(InferenceFailure) as caught:
        await task
    assert caught.value.code is InferenceFailureCode.CANCELLED
    assert cancelled.is_set()
    await client.aclose()


@pytest.mark.asyncio
async def test_vertex_generation_fails_closed_on_cost_and_invalid_output() -> None:
    transport_calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        return httpx.Response(200, json=provider_response())

    adapter, client = make_provider(
        httpx.MockTransport(handler)
    )
    with pytest.raises(InferenceFailure) as cost_failure:
        await adapter.generate_response(request(cost_budget=1))
    assert cost_failure.value.code is InferenceFailureCode.COST_BUDGET_EXCEEDED
    assert cost_failure.value.incurred_cost_microusd == 0
    assert transport_calls == 0
    await client.aclose()

    invalid, invalid_client = make_provider(
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"modelVersion": MODEL, "candidates": []},
            )
        )
    )
    with pytest.raises(InferenceFailure) as parse_failure:
        await invalid.generate_response(request())
    assert (
        parse_failure.value.code
        is InferenceFailureCode.PROVIDER_INVALID_RESPONSE
    )
    await invalid_client.aclose()


def test_vertex_generation_binds_location_to_policy() -> None:
    with pytest.raises(ValueError, match="location"):
        make_provider(
            httpx.MockTransport(lambda _: httpx.Response(500)),
            location="us-central1",
        )


def test_vertex_generation_rejects_missing_live_pricing() -> None:
    with pytest.raises(ValueError, match="prices"):
        make_provider(
            httpx.MockTransport(lambda _: httpx.Response(500)),
            input_microusd_per_million_tokens=0,
        )


@pytest.mark.asyncio
async def test_vertex_generation_cancels_inflight_transport() -> None:
    cancellation = EventCancellation()
    started = asyncio.Event()
    transport_cancelled = asyncio.Event()

    async def handler(_: httpx.Request) -> httpx.Response:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            transport_cancelled.set()
        return httpx.Response(500)

    adapter, client = make_provider(httpx.MockTransport(handler))
    task = asyncio.create_task(
        adapter.generate_response(request(cancellation=cancellation))
    )
    await started.wait()
    cancellation.event.set()
    with pytest.raises(InferenceFailure) as caught:
        await task
    assert caught.value.code is InferenceFailureCode.CANCELLED
    assert caught.value.incurred_cost_microusd is None
    assert transport_cancelled.is_set()
    await client.aclose()
