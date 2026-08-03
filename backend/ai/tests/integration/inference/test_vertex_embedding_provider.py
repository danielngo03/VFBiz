import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import httpx
import pytest

from app.infrastructure.embedding_providers.policy import EmbeddingAdapterPolicy
from app.infrastructure.embedding_providers.vertex_embedding import (
    VertexEmbeddingAdapter,
    VertexEmbeddingDeploymentDescriptor,
)
from app.modules.inference.application.embedding_ports import (
    EmbeddingBudget,
    EmbeddingFailure,
    EmbeddingFailureCode,
    EmbeddingInput,
    EmbeddingPurpose,
    EmbeddingRequest,
)

MODEL = "gemini-embedding-001"


class EventCancellation:
    def __init__(self) -> None:
        self.event = asyncio.Event()

    def is_set(self) -> bool:
        return self.event.is_set()

    async def wait(self) -> object:
        await self.event.wait()
        return None


def deployment(
    *,
    project_id: str = "vinfast-503003",
    location: str = "asia-southeast1",
    model_revision: str = MODEL,
) -> VertexEmbeddingDeploymentDescriptor:
    return VertexEmbeddingDeploymentDescriptor(
        project_id=project_id,
        location=location,
        model_revision=model_revision,
        profile="synthetic-smoke-only",
        retention_policy="standard",
        pricing_revision="vertex-pricing-2026-07-30",
        data_controls_approval_sha256="d" * 64,
    )


def policy(*, dimension: int = 3) -> EmbeddingAdapterPolicy:
    return EmbeddingAdapterPolicy(
        provider_id="vertex",
        model_revision=MODEL,
        output_dimension=dimension,
        max_items_per_request=1,
        max_input_bytes_per_request=4_096,
        max_input_tokens_per_request=1_024,
        input_microusd_per_million_tokens=1_000_000,
        fixed_request_cost_microusd=0,
        max_concurrency=2,
        max_response_bytes=16_384,
        max_output_elements=4_096,
        input_template_revision="vertex-embedding-v1",
        query_prefix="query: ",
        document_prefix="document: ",
    )


def request(
    adapter_policy: EmbeddingAdapterPolicy,
    *,
    max_cost: int = 10_000,
    cancellation: EventCancellation | None = None,
    deadline_seconds: float = 5,
) -> EmbeddingRequest:
    return EmbeddingRequest(
        inputs=(EmbeddingInput(index=0, text="synthetic value", estimated_tokens=3),),
        purpose=EmbeddingPurpose.RETRIEVAL_QUERY,
        expected_generation=adapter_policy.generation,
        deadline_at=datetime.now(UTC) + timedelta(seconds=deadline_seconds),
        budget=EmbeddingBudget(
            max_items=1,
            max_input_bytes=1_024,
            max_input_tokens=128,
            max_cost_microusd=max_cost,
        ),
        correlation_id="vertex-embedding-synthetic-1",
        cancellation=cancellation,
    )


def response(
    *,
    values: list[float] | None = None,
) -> dict[str, object]:
    return {
        "predictions": [
            {
                "embeddings": {
                    "values": [0.1, 0.2, 0.3] if values is None else values,
                    "statistics": {"token_count": 4, "truncated": False},
                }
            }
        ],
    }


def make_adapter(
    handler: httpx.AsyncBaseTransport,
    adapter_policy: EmbeddingAdapterPolicy,
) -> tuple[VertexEmbeddingAdapter, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=handler)

    async def token() -> str:
        return "test-adc-token"

    return (
        VertexEmbeddingAdapter(
            adapter_policy,
            deployment=deployment(),
            access_token_provider=token,
            client=client,
        ),
        client,
    )


@pytest.mark.asyncio
async def test_vertex_embedding_pins_region_model_task_and_dimension() -> None:
    adapter_policy = policy()
    observed: dict[str, object] = {}

    async def handler(provider_request: httpx.Request) -> httpx.Response:
        observed["url"] = str(provider_request.url)
        observed["authorization"] = provider_request.headers["authorization"]
        observed["payload"] = provider_request.content.decode()
        return httpx.Response(
            200,
            headers={"x-request-id": "embedding-request-1"},
            json=response(),
        )

    adapter, client = make_adapter(
        httpx.MockTransport(handler),
        adapter_policy,
    )
    result = await adapter.embed(request(adapter_policy))
    assert observed["url"] == (
        "https://asia-southeast1-aiplatform.googleapis.com/v1/"
        "projects/vinfast-503003/locations/asia-southeast1/"
        "publishers/google/models/gemini-embedding-001:predict"
    )
    assert observed["authorization"] == "Bearer test-adc-token"
    assert '"task_type":"RETRIEVAL_QUERY"' in str(observed["payload"])
    assert '"autoTruncate":false' in str(observed["payload"])
    assert '"outputDimensionality":3' in str(observed["payload"])
    assert result.vectors[0].values == (0.1, 0.2, 0.3)
    assert result.usage.input_tokens == 4
    assert result.incurred_cost_microusd == 4
    await client.aclose()


@pytest.mark.asyncio
async def test_vertex_embedding_rejects_dimension_and_non_finite_values() -> None:
    adapter_policy = policy()
    responses = iter(
        (
            response(values=[0.1, 0.2]),
            response(values=[0.1, float("nan"), 0.3]),
        )
    )

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps(next(responses), allow_nan=True).encode(),
        )

    adapter, client = make_adapter(
        httpx.MockTransport(handler),
        adapter_policy,
    )
    expected = (
        EmbeddingFailureCode.DIMENSION_MISMATCH,
        EmbeddingFailureCode.NON_FINITE_VECTOR,
    )
    for code in expected:
        with pytest.raises(EmbeddingFailure) as caught:
            await adapter.embed(request(adapter_policy))
        assert caught.value.code is code
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("truncated", [True, None, "false"])
async def test_vertex_embedding_rejects_truncated_or_malformed_usage(
    truncated: object,
) -> None:
    adapter_policy = policy()
    payload = response()
    predictions = payload["predictions"]
    assert isinstance(predictions, list)
    prediction = cast("list[object]", predictions)[0]
    assert isinstance(prediction, dict)
    embeddings = cast("dict[str, object]", prediction)["embeddings"]
    assert isinstance(embeddings, dict)
    statistics = cast("dict[str, object]", embeddings)["statistics"]
    assert isinstance(statistics, dict)
    statistics["truncated"] = truncated
    adapter, client = make_adapter(
        httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
        adapter_policy,
    )
    with pytest.raises(EmbeddingFailure) as caught:
        await adapter.embed(request(adapter_policy))
    assert (
        caught.value.code
        is EmbeddingFailureCode.PROVIDER_INVALID_RESPONSE
    )
    await client.aclose()


def test_vertex_embedding_enforces_single_input_model_contract() -> None:
    with pytest.raises(ValueError, match="exactly one input"):
        VertexEmbeddingAdapter(
            replace(policy(), max_items_per_request=2),
            deployment=deployment(location="global"),
            access_token_provider=lambda: asyncio.sleep(0, result="token"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (403, EmbeddingFailureCode.PROVIDER_AUTHENTICATION_FAILED, False),
        (429, EmbeddingFailureCode.PROVIDER_RATE_LIMITED, True),
        (503, EmbeddingFailureCode.PROVIDER_UNAVAILABLE, True),
    ],
)
async def test_vertex_embedding_maps_provider_failures(
    status: int,
    code: EmbeddingFailureCode,
    retryable: bool,
) -> None:
    adapter_policy = policy()
    adapter, client = make_adapter(
        httpx.MockTransport(lambda _: httpx.Response(status)),
        adapter_policy,
    )
    with pytest.raises(EmbeddingFailure) as caught:
        await adapter.embed(request(adapter_policy))
    assert caught.value.code is code
    assert caught.value.retryable is retryable
    await client.aclose()


@pytest.mark.asyncio
async def test_vertex_embedding_cancels_auth_and_fails_preflight_budget() -> None:
    adapter_policy = policy()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def token() -> str:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return "unreachable"

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500))
    )
    adapter = VertexEmbeddingAdapter(
        adapter_policy,
        deployment=deployment(),
        access_token_provider=token,
        client=client,
    )
    task = asyncio.create_task(adapter.embed(request(adapter_policy)))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()
    await client.aclose()

    budget_adapter, budget_client = make_adapter(
        httpx.MockTransport(lambda _: httpx.Response(500)),
        adapter_policy,
    )
    with pytest.raises(EmbeddingFailure) as caught:
        await budget_adapter.embed(request(adapter_policy, max_cost=1))
    assert caught.value.code is EmbeddingFailureCode.COST_BUDGET_EXCEEDED
    await budget_client.aclose()


@pytest.mark.asyncio
async def test_vertex_embedding_normalizes_adc_failure() -> None:
    adapter_policy = policy()

    async def failed_token() -> str:
        raise RuntimeError("credential detail must not escape")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500))
    )
    adapter = VertexEmbeddingAdapter(
        adapter_policy,
        deployment=deployment(),
        access_token_provider=failed_token,
        client=client,
    )
    with pytest.raises(EmbeddingFailure) as caught:
        await adapter.embed(request(adapter_policy))
    assert (
        caught.value.code
        is EmbeddingFailureCode.PROVIDER_AUTHENTICATION_FAILED
    )
    assert "credential detail" not in str(caught.value)
    await client.aclose()


@pytest.mark.asyncio
async def test_vertex_embedding_cancels_inflight_transport() -> None:
    adapter_policy = policy()
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

    adapter, client = make_adapter(
        httpx.MockTransport(handler),
        adapter_policy,
    )
    task = asyncio.create_task(
        adapter.embed(
            request(adapter_policy, cancellation=cancellation)
        )
    )
    await started.wait()
    cancellation.event.set()
    with pytest.raises(EmbeddingFailure) as caught:
        await task
    assert caught.value.code is EmbeddingFailureCode.CANCELLED
    assert transport_cancelled.is_set()
    await client.aclose()


@pytest.mark.asyncio
async def test_vertex_embedding_times_out_inflight_transport() -> None:
    adapter_policy = policy()
    started = asyncio.Event()
    transport_cancelled = asyncio.Event()

    async def handler(_: httpx.Request) -> httpx.Response:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            transport_cancelled.set()
        return httpx.Response(500)

    adapter, client = make_adapter(
        httpx.MockTransport(handler),
        adapter_policy,
    )
    with pytest.raises(EmbeddingFailure) as caught:
        await adapter.embed(
            request(adapter_policy, deadline_seconds=0.05)
        )
    assert caught.value.code is EmbeddingFailureCode.DEADLINE_EXCEEDED
    assert started.is_set()
    assert transport_cancelled.is_set()
    await client.aclose()


def test_vertex_embedding_binds_model_to_reviewed_deployment() -> None:
    with pytest.raises(ValueError, match="deployment model"):
        VertexEmbeddingAdapter(
            policy(),
            deployment=deployment(model_revision="other-model"),
            access_token_provider=lambda: asyncio.sleep(0, result="token"),
        )
