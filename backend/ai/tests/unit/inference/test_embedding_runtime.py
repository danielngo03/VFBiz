from datetime import UTC, datetime

import pytest

from app.modules.inference.application.embedding_ports import (
    EmbeddingGenerationIdentity,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingUsage,
    EmbeddingVector,
)
from app.modules.inference.application.embedding_runtime import (
    ConservativeByteTokenEstimator,
    EmbeddingRuntime,
    EmbeddingRuntimePolicy,
)


class RecordingProvider:
    def __init__(self) -> None:
        self.requests: list[EmbeddingRequest] = []
        self.closed = False

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self.requests.append(request)
        return EmbeddingResult(
            vectors=tuple(
                EmbeddingVector(index=item.index, values=(1.0, 0.0, 0.0)) for item in request.inputs
            ),
            usage=EmbeddingUsage(
                input_tokens=request.total_estimated_tokens,
                item_count=len(request.inputs),
                input_bytes=request.total_input_bytes,
            ),
            reserved_cost_microusd=1,
            incurred_cost_microusd=1,
            provider_id="recording",
            generation=request.expected_generation,
            provider_request_id="request-1",
            correlation_id=request.correlation_id,
        )

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_query_and_document_paths_share_one_release_pinned_runtime() -> None:
    provider = RecordingProvider()
    runtime = EmbeddingRuntime(
        provider=provider,
        token_estimator=ConservativeByteTokenEstimator(),
        policy=EmbeddingRuntimePolicy(
            generation=EmbeddingGenerationIdentity(
                model_revision="candidate-v1",
                tokenizer_revision="tokenizer-v1",
                weights_revision="weights-v1",
                dimension=3,
                pooling="mean",
                normalization="l2",
                input_template_revision="template-v1",
                query_template_sha256="a" * 64,
                document_template_sha256="b" * 64,
            ),
            timeout_seconds=5,
            max_items=8,
            max_input_bytes=4_096,
            max_input_tokens=4_096,
            max_cost_microusd=100,
        ),
        clock=lambda: datetime(2026, 7, 25, tzinfo=UTC),
    )

    query_vector = await runtime.embed_query("VF 8")
    document_vectors = await runtime.embed_documents(("Bảo hành", "Trạm sạc"))

    assert query_vector == (1.0, 0.0, 0.0)
    assert len(document_vectors) == 2
    assert provider.requests[0].purpose.value == "retrieval_query"
    assert provider.requests[1].purpose.value == "retrieval_document"
    assert {request.expected_model_revision for request in provider.requests} == {"candidate-v1"}
    assert {request.expected_dimension for request in provider.requests} == {3}

    await runtime.aclose()
    assert provider.closed is True
