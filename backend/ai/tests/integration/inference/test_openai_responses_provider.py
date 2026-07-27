import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.infrastructure.model_providers import OpenAIResponsesProvider
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

MODEL = "approved-model-2026-07-01"
PROMPT = GroundedAnswerPrompt(revision="customer-grounded-v1")
POLICY = DeploymentPolicyDescriptor(
    revision="customer-grounded-v1",
    profile="customer-grounded-v1",
    safety_tier="customer-factual-v1",
    residency="global",
    retention=RetentionPolicy.STANDARD,
    schema_revision="grounded-answer-v2",
    model_release=MODEL,
    provider_project_id="proj_test",
    provider_organization_id="org_test",
    data_controls_approval_reference="approval-test-v1",
    data_controls_approval_sha256="b" * 64,
    release_manifest_sha256="c" * 64,
)
EVIDENCE = (
    Evidence(
        evidence_id="ev-1",
        source_uri="vfbiz://knowledge/source-1/revision-1/chunk-1",
        source_revision="revision-1",
        title="Approved policy",
        excerpt="The approved warranty period is five years.",
        freshness="current",
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


def generation_request(
    *,
    cancellation: EventCancellation | None = None,
    input_budget: int = 2_000,
) -> GenerationRequest:
    return GenerationRequest(
        question="What is the warranty period?",
        evidence=EVIDENCE,
        budget=InferenceBudget(
            max_input_tokens=input_budget,
            max_output_tokens=200,
            max_cost_microusd=10_000,
            max_attempts=2,
        ),
        deadline_at=datetime.now(UTC) + timedelta(seconds=5),
        required_policy=POLICY,
        correlation_id="corr-test-001",
        expected_prompt_revision=PROMPT.revision,
        expected_prompt_content_sha256=PROMPT.content_sha256,
        safety_identifier="a" * 64,
        cancellation=cancellation,
    )


def make_provider(
    handler: httpx.AsyncBaseTransport,
    **overrides: object,
) -> tuple[OpenAIResponsesProvider, httpx.AsyncClient]:
    client = httpx.AsyncClient(
        transport=handler,
        base_url="https://api.openai.test/v1/",
    )
    kwargs: dict[str, object] = {
        "deployment_id": "openai-test-primary",
        "api_key": "test-only-key",
        "project_id": "proj_test",
        "organization_id": "org_test",
        "model_revision": MODEL,
        "model_allowlist": (MODEL,),
        "prompt": PROMPT,
        "policy": POLICY,
        "client": client,
        "input_microusd_per_million_tokens": 1_000_000,
        "output_microusd_per_million_tokens": 2_000_000,
    }
    kwargs.update(overrides)
    return OpenAIResponsesProvider(**kwargs), client  # type: ignore[arg-type]


def provider_response(
    *,
    outcome: str = "answered",
    answer: str | None = "The approved warranty period is five years.",
    citation_ids: list[str] | None = None,
    model: str = MODEL,
    response_id: str = "resp_test",
) -> dict[str, object]:
    return {
        "id": response_id,
        "status": "completed",
        "model": model,
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {
                                "outcome": outcome,
                                "answer": answer,
                                "citation_ids": (
                                    ["ev-1"] if citation_ids is None else citation_ids
                                ),
                            }
                        ),
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": 80,
            "output_tokens": 20,
            "input_tokens_details": {"cached_tokens": 40},
            "output_tokens_details": {"reasoning_tokens": 5},
        },
    }


@pytest.mark.asyncio
async def test_openai_adapter_uses_strict_bounded_responses_contract() -> None:
    observed: dict[str, object] = {}

    async def handler(request_message: httpx.Request) -> httpx.Response:
        observed["authorization"] = request_message.headers["authorization"]
        observed["host"] = request_message.url.host
        observed["project"] = request_message.headers["openai-project"]
        observed["organization"] = request_message.headers["openai-organization"]
        observed["path"] = request_message.url.path
        observed["payload"] = json.loads(request_message.content)
        return httpx.Response(
            200,
            headers={"x-request-id": "req_test"},
            json=provider_response(),
        )

    adapter, client = make_provider(httpx.MockTransport(handler))
    result = await adapter.generate_response(generation_request())

    payload = observed["payload"]
    assert isinstance(payload, dict)
    assert payload["store"] is False
    assert payload["safety_identifier"] == "a" * 64
    assert payload["parallel_tool_calls"] is False
    assert payload["truncation"] == "disabled"
    assert "reasoning" not in payload
    assert payload["text"]["format"]["strict"] is True
    assert payload["metadata"]["prompt_content_sha256"] == PROMPT.content_sha256
    assert observed["authorization"] == "Bearer test-only-key"
    assert observed["host"] == "api.openai.com"
    assert observed["project"] == "proj_test"
    assert observed["organization"] == "org_test"
    assert result.deployment_policy.provider_project_id == "proj_test"
    assert observed["path"] == "/v1/responses"
    assert result.outcome is GenerationOutcome.ANSWERED
    assert result.citations[0].evidence_id == "ev-1"
    assert result.model_revision == MODEL
    assert result.prompt_content_sha256 == PROMPT.content_sha256
    assert len(result.evidence_digest) == 64
    assert result.correlation_id == "corr-test-001"
    assert result.estimated_cost_microusd == 120
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_adapter_maps_invalid_result_metadata_to_typed_failure() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=provider_response(response_id=""))

    adapter, client = make_provider(httpx.MockTransport(handler))
    with pytest.raises(InferenceFailure) as caught:
        await adapter.generate_response(generation_request())
    assert caught.value.code is InferenceFailureCode.PROVIDER_INVALID_RESPONSE
    await client.aclose()


def test_openai_adapter_requires_policy_organization_match() -> None:
    with pytest.raises(ValueError, match="organization"):
        make_provider(
            httpx.MockTransport(lambda _: httpx.Response(500)),
            organization_id="org_other",
        )


@pytest.mark.asyncio
async def test_insufficient_evidence_is_typed_and_needs_no_citation() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=provider_response(
                outcome="insufficient_evidence",
                answer=None,
                citation_ids=[],
            ),
        )

    adapter, client = make_provider(httpx.MockTransport(handler))
    result = await adapter.generate_response(generation_request())
    assert result.outcome is GenerationOutcome.INSUFFICIENT_EVIDENCE
    assert result.answer is None
    assert result.citations == ()
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_adapter_rejects_unknown_citation_and_model_mismatch() -> None:
    responses = iter(
        (
            provider_response(citation_ids=["invented"]),
            provider_response(model="unapproved-model"),
        )
    )

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    adapter, client = make_provider(httpx.MockTransport(handler))
    with pytest.raises(InferenceFailure) as citation_failure:
        await adapter.generate_response(generation_request())
    assert (
        citation_failure.value.code
        is InferenceFailureCode.PROVIDER_INVALID_RESPONSE
    )
    with pytest.raises(InferenceFailure) as model_failure:
        await adapter.generate_response(generation_request())
    assert model_failure.value.code is InferenceFailureCode.MODEL_REVISION_MISMATCH
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_adapter_rejects_million_character_response() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 1_000_000)

    adapter, client = make_provider(
        httpx.MockTransport(handler),
        max_response_bytes=8_192,
    )
    with pytest.raises(InferenceFailure) as caught:
        await adapter.generate_response(generation_request())
    assert caught.value.code is InferenceFailureCode.RESPONSE_TOO_LARGE
    await client.aclose()


@pytest.mark.asyncio
async def test_injected_client_cannot_redirect_credentials_to_another_origin() -> None:
    observed_hosts: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed_hosts.append(request.url.host)
        return httpx.Response(
            307,
            headers={"location": "https://evil.example/collect"},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://evil-client-default.example/v1/",
        follow_redirects=True,
    )
    adapter = OpenAIResponsesProvider(
        deployment_id="openai-test-primary",
        api_key="test-only-key",
        project_id="proj_test",
        organization_id="org_test",
        model_revision=MODEL,
        model_allowlist=(MODEL,),
        prompt=PROMPT,
        policy=POLICY,
        base_url="https://api.openai.com/v1",
        client=client,
    )
    with pytest.raises(InferenceFailure) as caught:
        await adapter.generate_response(generation_request())
    assert caught.value.code is InferenceFailureCode.PROVIDER_REJECTED_REQUEST
    assert observed_hosts == ["api.openai.com"]
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_adapter_maps_rate_limit_without_provider_detail() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "sensitive detail"}})

    adapter, client = make_provider(httpx.MockTransport(handler))
    with pytest.raises(InferenceFailure) as caught:
        await adapter.generate_response(generation_request())
    assert caught.value.code is InferenceFailureCode.PROVIDER_RATE_LIMITED
    assert caught.value.retryable is True
    assert "sensitive detail" not in str(caught.value)
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_adapter_cancels_in_flight_http_request() -> None:
    started = asyncio.Event()

    async def handler(_: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.Event().wait()
        return httpx.Response(200, json=provider_response())

    cancellation = EventCancellation()
    adapter, client = make_provider(httpx.MockTransport(handler))
    task = asyncio.create_task(
        adapter.generate_response(generation_request(cancellation=cancellation))
    )
    await started.wait()
    cancellation.event.set()
    with pytest.raises(InferenceFailure) as caught:
        await task
    assert caught.value.code is InferenceFailureCode.CANCELLED
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_adapter_enforces_deadline_and_aborts_transport() -> None:
    aborted = asyncio.Event()

    async def handler(_: httpx.Request) -> httpx.Response:
        try:
            await asyncio.Event().wait()
        finally:
            aborted.set()
        return httpx.Response(200, json=provider_response())

    adapter, client = make_provider(
        httpx.MockTransport(handler),
        request_timeout_seconds=0.01,
    )
    with pytest.raises(InferenceFailure) as caught:
        await adapter.generate_response(generation_request())
    assert caught.value.code is InferenceFailureCode.DEADLINE_EXCEEDED
    await asyncio.wait_for(aborted.wait(), timeout=1)
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_adapter_rejects_input_before_network_call() -> None:
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=provider_response())

    adapter, client = make_provider(httpx.MockTransport(handler))
    with pytest.raises(InferenceFailure) as caught:
        await adapter.generate_response(generation_request(input_budget=1))
    assert caught.value.code is InferenceFailureCode.INPUT_BUDGET_EXCEEDED
    assert called is False
    await client.aclose()


def test_adapter_has_no_legacy_generate_bypass() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=provider_response())

    adapter, _ = make_provider(httpx.MockTransport(handler))
    assert not hasattr(adapter, "generate")


@pytest.mark.asyncio
async def test_openai_adapter_bulkhead_bounds_concurrent_requests() -> None:
    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        async with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.01)
        async with lock:
            active -= 1
        return httpx.Response(
            200,
            json=provider_response(
                outcome="insufficient_evidence",
                answer=None,
                citation_ids=[],
            ),
        )

    adapter, client = make_provider(
        httpx.MockTransport(handler),
        max_concurrency=2,
    )
    await asyncio.gather(
        *(adapter.generate_response(generation_request()) for _ in range(10))
    )
    assert peak == 2
    await client.aclose()
