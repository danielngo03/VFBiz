import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.infrastructure.embedding_providers import (
    EmbeddingAdapterPolicy,
    OpenAIEmbeddingAdapter,
    TeiDeploymentIdentity,
    TeiEmbeddingAdapter,
)
from app.modules.inference.application.embedding_ports import (
    EmbeddingBudget,
    EmbeddingFailure,
    EmbeddingFailureCode,
    EmbeddingInput,
    EmbeddingPurpose,
    EmbeddingRequest,
)


def request(
    *,
    model: str = "candidate-embed-v1",
    dimension: int = 3,
    cancellation: asyncio.Event | None = None,
) -> EmbeddingRequest:
    adapter_policy = policy(model=model)
    return EmbeddingRequest(
        inputs=(
            EmbeddingInput(index=0, text="VF 8 bảo hành", estimated_tokens=4),
            EmbeddingInput(index=1, text="Trạm sạc", estimated_tokens=3),
        ),
        purpose=EmbeddingPurpose.RETRIEVAL_DOCUMENT,
        expected_generation=replace(adapter_policy.generation, dimension=dimension),
        deadline_at=datetime.now(UTC) + timedelta(seconds=5),
        budget=EmbeddingBudget(
            max_items=2,
            max_input_bytes=1_024,
            max_input_tokens=64,
            max_cost_microusd=100,
        ),
        correlation_id="embedding-adapter-test",
        cancellation=cancellation,
    )


def policy(
    *,
    model: str = "candidate-embed-v1",
    dimension: int = 3,
    circuit_failure_threshold: int = 3,
):
    return EmbeddingAdapterPolicy(
        provider_id="managed-candidate",
        model_revision=model,
        output_dimension=dimension,
        max_items_per_request=8,
        max_input_bytes_per_request=4_096,
        max_input_tokens_per_request=100,
        input_microusd_per_million_tokens=1_000_000,
        fixed_request_cost_microusd=0,
        max_concurrency=2,
        circuit_failure_threshold=circuit_failure_threshold,
        circuit_recovery_seconds=30,
        max_response_bytes=16_384,
        max_output_elements=1_024,
        input_template_revision="embedding-input-v1",
        query_prefix="query: ",
        document_prefix="passage: ",
        tokenizer_revision=("a" * 64 if model == "self-hosted-embed-v1" else "provider-managed"),
        weights_revision=("b" * 64 if model == "self-hosted-embed-v1" else "provider-managed"),
    )


def tei_identity() -> TeiDeploymentIdentity:
    return TeiDeploymentIdentity(
        model_revision="self-hosted-embed-v1",
        tokenizer_sha256="a" * 64,
        weights_sha256="b" * 64,
        input_template_revision="embedding-input-v1",
        deployment_sha256="c" * 64,
    )


def tei_info_payload() -> dict[str, str]:
    identity = tei_identity()
    return {
        "model_revision": identity.model_revision,
        "tokenizer_sha256": identity.tokenizer_sha256,
        "weights_sha256": identity.weights_sha256,
        "input_template_revision": identity.input_template_revision,
        "deployment_sha256": identity.deployment_sha256,
    }


@pytest.mark.asyncio
async def test_openai_adapter_preserves_index_and_records_normalized_usage() -> None:
    def handler(provider_request: httpx.Request) -> httpx.Response:
        assert provider_request.headers["authorization"] == "Bearer test-secret"
        assert provider_request.headers["openai-project"] == "project-test"
        return httpx.Response(
            200,
            headers={"x-request-id": "req-managed-1"},
            json={
                "object": "list",
                "model": "candidate-embed-v1",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [1.0, 0.0, 0.0]},
                    {"object": "embedding", "index": 1, "embedding": [0.0, 1.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 7, "total_tokens": 7},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    ) as client:
        adapter = OpenAIEmbeddingAdapter(
            policy(),
            client=client,
            api_key="test-secret",
            project_id="project-test",
        )
        result = await adapter.embed(request())

    assert tuple(vector.index for vector in result.vectors) == (0, 1)
    assert result.usage.input_tokens == 7
    assert result.reserved_cost_microusd == 25
    assert result.incurred_cost_microusd == 7
    assert result.provider_request_id == "req-managed-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "failure_code"),
    [
        (
            {
                "model": "candidate-embed-v1",
                "data": [
                    {"index": 1, "embedding": [1.0, 0.0, 0.0]},
                    {"index": 0, "embedding": [0.0, 1.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 7, "total_tokens": 7},
            },
            EmbeddingFailureCode.RESPONSE_ORDER_MISMATCH,
        ),
        (
            {
                "model": "candidate-embed-v1",
                "data": [
                    {"index": 0, "embedding": [1.0, 0.0]},
                    {"index": 1, "embedding": [0.0, 1.0]},
                ],
                "usage": {"prompt_tokens": 7, "total_tokens": 7},
            },
            EmbeddingFailureCode.DIMENSION_MISMATCH,
        ),
    ],
)
async def test_openai_adapter_fails_closed_on_malformed_vector_contract(
    payload: dict[str, object],
    failure_code: EmbeddingFailureCode,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
        base_url="https://api.openai.com/v1",
    ) as client:
        adapter = OpenAIEmbeddingAdapter(
            policy(),
            client=client,
            api_key="test-secret",
            project_id="project-test",
        )
        with pytest.raises(EmbeddingFailure) as captured:
            await adapter.embed(request())

    assert captured.value.code is failure_code


@pytest.mark.asyncio
async def test_managed_adapter_maps_rate_limit_without_retrying_itself() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"retry-after": "2"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    ) as client:
        adapter = OpenAIEmbeddingAdapter(
            policy(),
            client=client,
            api_key="test-secret",
            project_id="project-test",
        )
        with pytest.raises(EmbeddingFailure) as captured:
            await adapter.embed(request())

    assert captured.value.code is EmbeddingFailureCode.PROVIDER_RATE_LIMITED
    assert captured.value.retryable is True
    assert calls == 1


@pytest.mark.asyncio
async def test_tei_adapter_uses_same_contract_without_provider_credentials() -> None:
    observed_inputs: list[str] = []

    def handler(provider_request: httpx.Request) -> httpx.Response:
        if provider_request.url.path == "/info":
            return httpx.Response(200, json=tei_info_payload())
        payload = json.loads(provider_request.content)
        observed_inputs.extend(payload["inputs"])
        return httpx.Response(
            200,
            headers={
                "x-request-id": "req-tei-1",
                "x-vfbiz-embedding-deployment-sha256": "c" * 64,
            },
            json=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://127.0.0.1:8080",
    ) as client:
        adapter = TeiEmbeddingAdapter(
            policy(model="self-hosted-embed-v1"),
            client=client,
            expected_identity=tei_identity(),
        )
        result = await adapter.embed(request(model="self-hosted-embed-v1"))

    assert result.model_revision == "self-hosted-embed-v1"
    assert result.usage.input_tokens == 25
    assert result.reserved_cost_microusd == 25
    assert result.incurred_cost_microusd is None
    assert observed_inputs == ["passage: VF 8 bảo hành", "passage: Trạm sạc"]


@pytest.mark.asyncio
async def test_adapter_honors_cancellation_before_network_io() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    cancellation = asyncio.Event()
    cancellation.set()
    cancelled_request = request(cancellation=cancellation)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    ) as client:
        adapter = OpenAIEmbeddingAdapter(
            policy(),
            client=client,
            api_key="test-secret",
            project_id="project-test",
        )
        with pytest.raises(EmbeddingFailure) as captured:
            await adapter.embed(cancelled_request)

    assert captured.value.code is EmbeddingFailureCode.CANCELLED
    assert calls == 0


@pytest.mark.asyncio
async def test_adapter_cancels_inflight_network_io_at_caller_deadline() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    timed_request = EmbeddingRequest(
        inputs=(EmbeddingInput(index=0, text="VF 8", estimated_tokens=2),),
        purpose=EmbeddingPurpose.RETRIEVAL_QUERY,
        expected_generation=policy().generation,
        deadline_at=datetime.now(UTC) + timedelta(milliseconds=10),
        budget=EmbeddingBudget(
            max_items=1,
            max_input_bytes=128,
            max_input_tokens=16,
            max_cost_microusd=100,
        ),
        correlation_id="embedding-timeout-test",
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    ) as client:
        adapter = OpenAIEmbeddingAdapter(
            policy(),
            client=client,
            api_key="test-secret",
            project_id="project-test",
        )
        with pytest.raises(EmbeddingFailure) as captured:
            await adapter.embed(timed_request)

    assert captured.value.code is EmbeddingFailureCode.DEADLINE_EXCEEDED


def test_managed_adapter_rejects_missing_credentials_before_runtime() -> None:
    async_client = httpx.AsyncClient(
        base_url="https://api.openai.com/v1",
        trust_env=False,
    )
    try:
        with pytest.raises(ValueError, match="credentials"):
            OpenAIEmbeddingAdapter(
                policy(),
                client=async_client,
                api_key="",
                project_id="project-test",
            )
    finally:
        asyncio.run(async_client.aclose())


@pytest.mark.asyncio
async def test_embedding_circuit_is_local_to_each_adapter() -> None:
    failing_calls = 0
    healthy_calls = 0

    def failing_handler(_: httpx.Request) -> httpx.Response:
        nonlocal failing_calls
        failing_calls += 1
        return httpx.Response(503)

    def healthy_handler(_: httpx.Request) -> httpx.Response:
        nonlocal healthy_calls
        healthy_calls += 1
        return httpx.Response(
            200,
            json={
                "model": "candidate-embed-v1",
                "data": [
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 7, "total_tokens": 7},
            },
        )

    async with (
        httpx.AsyncClient(
            transport=httpx.MockTransport(failing_handler),
            base_url="https://api.openai.com/v1",
        ) as failing_client,
        httpx.AsyncClient(
            transport=httpx.MockTransport(healthy_handler),
            base_url="https://api.openai.com/v1",
        ) as healthy_client,
    ):
        failing = OpenAIEmbeddingAdapter(
            policy(circuit_failure_threshold=1),
            client=failing_client,
            api_key="test-secret",
            project_id="project-test",
        )
        healthy = OpenAIEmbeddingAdapter(
            policy(circuit_failure_threshold=1),
            client=healthy_client,
            api_key="test-secret",
            project_id="project-test",
        )
        with pytest.raises(EmbeddingFailure):
            await failing.embed(request())
        with pytest.raises(EmbeddingFailure) as opened:
            await failing.embed(request())
        result = await healthy.embed(request())

    assert opened.value.code is EmbeddingFailureCode.CIRCUIT_OPEN
    assert failing_calls == 1
    assert healthy_calls == 1
    assert len(result.vectors) == 2


@pytest.mark.asyncio
async def test_rate_limit_does_not_poison_provider_health_circuit() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    ) as client:
        adapter = OpenAIEmbeddingAdapter(
            policy(circuit_failure_threshold=1),
            client=client,
            api_key="test-secret",
            project_id="project-test",
        )
        for _ in range(2):
            with pytest.raises(EmbeddingFailure) as captured:
                await adapter.embed(request())
            assert captured.value.code is EmbeddingFailureCode.PROVIDER_RATE_LIMITED

    assert calls == 2


@pytest.mark.asyncio
async def test_transport_timeouts_open_provider_health_circuit() -> None:
    calls = 0

    def handler(provider_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("simulated", request=provider_request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    ) as client:
        adapter = OpenAIEmbeddingAdapter(
            policy(circuit_failure_threshold=2),
            client=client,
            api_key="test-secret",
            project_id="project-test",
        )
        for _ in range(2):
            with pytest.raises(EmbeddingFailure) as captured:
                await adapter.embed(request())
            assert captured.value.code is EmbeddingFailureCode.DEADLINE_EXCEEDED
        with pytest.raises(EmbeddingFailure) as opened:
            await adapter.embed(request())

    assert opened.value.code is EmbeddingFailureCode.CIRCUIT_OPEN
    assert calls == 2


@pytest.mark.asyncio
async def test_unexpected_transport_exception_does_not_strand_circuit_probe() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("simulated adapter fault")
        return httpx.Response(
            200,
            json={
                "model": "candidate-embed-v1",
                "data": [
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 7, "total_tokens": 7},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    ) as client:
        adapter = OpenAIEmbeddingAdapter(
            policy(circuit_failure_threshold=1),
            client=client,
            api_key="test-secret",
            project_id="project-test",
        )
        with pytest.raises(EmbeddingFailure) as first:
            await adapter.embed(request())
        result = await adapter.embed(request())

    assert first.value.code is EmbeddingFailureCode.PROVIDER_ADAPTER_FAILURE
    assert len(result.vectors) == 2


@pytest.mark.asyncio
async def test_tei_fails_closed_when_deployment_fingerprint_changes() -> None:
    mismatched = tei_info_payload()
    mismatched["weights_sha256"] = "d" * 64

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=mismatched)),
        base_url="http://127.0.0.1:8080",
    ) as client:
        adapter = TeiEmbeddingAdapter(
            policy(model="self-hosted-embed-v1"),
            client=client,
            expected_identity=tei_identity(),
        )
        with pytest.raises(EmbeddingFailure) as captured:
            await adapter.embed(request(model="self-hosted-embed-v1"))

    assert captured.value.code is EmbeddingFailureCode.MODEL_REVISION_MISMATCH


@pytest.mark.asyncio
async def test_tei_rejects_mixed_replica_response_identity() -> None:
    def handler(provider_request: httpx.Request) -> httpx.Response:
        if provider_request.url.path == "/info":
            return httpx.Response(200, json=tei_info_payload())
        return httpx.Response(
            200,
            headers={"x-vfbiz-embedding-deployment-sha256": "d" * 64},
            json=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://127.0.0.1:8080",
    ) as client:
        adapter = TeiEmbeddingAdapter(
            policy(model="self-hosted-embed-v1"),
            client=client,
            expected_identity=tei_identity(),
        )
        with pytest.raises(EmbeddingFailure) as captured:
            await adapter.embed(request(model="self-hosted-embed-v1"))

    assert captured.value.code is EmbeddingFailureCode.MODEL_REVISION_MISMATCH


@pytest.mark.asyncio
async def test_adapter_closes_only_client_it_owns() -> None:
    injected = httpx.AsyncClient(base_url="https://api.openai.com/v1", trust_env=False)
    owned = httpx.AsyncClient(base_url="https://api.openai.com/v1", trust_env=False)
    injected_adapter = OpenAIEmbeddingAdapter(
        policy(),
        client=injected,
        api_key="test-secret",
        project_id="project-test",
    )
    owned_adapter = OpenAIEmbeddingAdapter(
        policy(),
        client=owned,
        api_key="test-secret",
        project_id="project-test",
        owns_client=True,
    )

    await injected_adapter.aclose()
    await owned_adapter.aclose()

    assert injected.is_closed is False
    assert owned.is_closed is True
    await injected.aclose()


@pytest.mark.asyncio
async def test_cancellation_while_waiting_for_bulkhead_never_starts_network() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return httpx.Response(
            200,
            json={
                "model": "candidate-embed-v1",
                "data": [
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 7, "total_tokens": 7},
            },
        )

    constrained_policy = replace(policy(), max_concurrency=1)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    ) as client:
        adapter = OpenAIEmbeddingAdapter(
            constrained_policy,
            client=client,
            api_key="test-secret",
            project_id="project-test",
        )
        first = asyncio.create_task(adapter.embed(request()))
        await entered.wait()
        cancellation = asyncio.Event()
        second = asyncio.create_task(adapter.embed(request(cancellation=cancellation)))
        await asyncio.sleep(0)
        cancellation.set()
        with pytest.raises(EmbeddingFailure) as captured:
            await second
        release.set()
        await first

    assert captured.value.code is EmbeddingFailureCode.CANCELLED
    assert calls == 1


@pytest.mark.asyncio
async def test_outer_task_cancellation_propagates_to_network_operation() -> None:
    entered = asyncio.Event()
    provider_cancelled = asyncio.Event()

    async def handler(_: httpx.Request) -> httpx.Response:
        entered.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            provider_cancelled.set()
            raise
        return httpx.Response(500)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    ) as client:
        adapter = OpenAIEmbeddingAdapter(
            policy(),
            client=client,
            api_key="test-secret",
            project_id="project-test",
        )
        task = asyncio.create_task(adapter.embed(request()))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert provider_cancelled.is_set()


@pytest.mark.asyncio
async def test_adapter_rejects_provider_body_above_memory_ceiling() -> None:
    limited = EmbeddingAdapterPolicy(
        provider_id="managed-candidate",
        model_revision="candidate-embed-v1",
        output_dimension=3,
        max_items_per_request=8,
        max_input_bytes_per_request=4_096,
        max_input_tokens_per_request=100,
        input_microusd_per_million_tokens=1_000_000,
        fixed_request_cost_microusd=0,
        max_concurrency=2,
        max_response_bytes=128,
        max_output_elements=1_024,
        input_template_revision="embedding-input-v1",
        query_prefix="query: ",
        document_prefix="passage: ",
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=b"{" + b"x" * 512 + b"}")
        ),
        base_url="https://api.openai.com/v1",
    ) as client:
        adapter = OpenAIEmbeddingAdapter(
            limited,
            client=client,
            api_key="test-secret",
            project_id="project-test",
        )
        with pytest.raises(EmbeddingFailure) as captured:
            await adapter.embed(request())

    assert captured.value.code is EmbeddingFailureCode.RESPONSE_TOO_LARGE


@pytest.mark.asyncio
async def test_adapter_accounts_for_purpose_prefix_before_network_and_cost() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    constrained = replace(policy(), document_prefix="x" * 32)
    limited_request = replace(
        request(),
        budget=EmbeddingBudget(
            max_items=2,
            max_input_bytes=1_024,
            max_input_tokens=32,
            max_cost_microusd=1_000,
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    ) as client:
        adapter = OpenAIEmbeddingAdapter(
            constrained,
            client=client,
            api_key="test-secret",
            project_id="project-test",
        )
        limited_request = replace(
            limited_request,
            expected_generation=constrained.generation,
        )
        with pytest.raises(EmbeddingFailure) as captured:
            await adapter.embed(limited_request)

    assert captured.value.code is EmbeddingFailureCode.INPUT_BUDGET_EXCEEDED
    assert calls == 0
