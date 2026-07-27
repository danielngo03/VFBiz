from datetime import UTC, datetime, timedelta

import pytest

from app.modules.inference.application.embedding_ports import (
    EmbeddingBudget,
    EmbeddingGenerationIdentity,
    EmbeddingInput,
    EmbeddingPurpose,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingUsage,
    EmbeddingVector,
)

NOW = datetime(2026, 7, 25, tzinfo=UTC)


def generation() -> EmbeddingGenerationIdentity:
    return EmbeddingGenerationIdentity(
        model_revision="candidate-embed-v1",
        tokenizer_revision="tokenizer-v1",
        weights_revision="weights-v1",
        dimension=3,
        pooling="mean",
        normalization="l2",
        input_template_revision="template-v1",
        query_template_sha256="a" * 64,
        document_template_sha256="b" * 64,
    )


def test_embedding_request_rejects_duplicate_indices_and_local_budget_overrun() -> None:
    budget = EmbeddingBudget(
        max_items=2,
        max_input_bytes=32,
        max_input_tokens=10,
        max_cost_microusd=100,
    )

    with pytest.raises(ValueError, match="indices must be contiguous"):
        EmbeddingRequest(
            inputs=(
                EmbeddingInput(index=0, text="VF 8", estimated_tokens=2),
                EmbeddingInput(index=0, text="VF 9", estimated_tokens=2),
            ),
            purpose=EmbeddingPurpose.RETRIEVAL_DOCUMENT,
            expected_generation=generation(),
            deadline_at=NOW + timedelta(seconds=5),
            budget=budget,
            correlation_id="embedding-contract-1",
        )

    with pytest.raises(ValueError, match="input token budget"):
        EmbeddingRequest(
            inputs=(EmbeddingInput(index=0, text="VF 8", estimated_tokens=11),),
            purpose=EmbeddingPurpose.RETRIEVAL_QUERY,
            expected_generation=generation(),
            deadline_at=NOW + timedelta(seconds=5),
            budget=budget,
            correlation_id="embedding-contract-2",
        )


def test_embedding_request_keeps_query_and_document_purposes_explicit() -> None:
    request = EmbeddingRequest(
        inputs=(EmbeddingInput(index=0, text="Chính sách bảo hành", estimated_tokens=4),),
        purpose=EmbeddingPurpose.RETRIEVAL_QUERY,
        expected_generation=generation(),
        deadline_at=NOW + timedelta(seconds=5),
        budget=EmbeddingBudget(
            max_items=1,
            max_input_bytes=128,
            max_input_tokens=8,
            max_cost_microusd=100,
        ),
        correlation_id="embedding-contract-3",
    )

    assert request.purpose is EmbeddingPurpose.RETRIEVAL_QUERY
    assert request.total_estimated_tokens == 4


def test_embedding_result_enforces_vector_and_usage_invariants() -> None:
    with pytest.raises(ValueError, match="indices"):
        EmbeddingResult(
            vectors=(EmbeddingVector(index=1, values=(1.0, 0.0, 0.0)),),
            usage=EmbeddingUsage(input_tokens=2, item_count=1, input_bytes=4),
            reserved_cost_microusd=2,
            incurred_cost_microusd=2,
            provider_id="candidate",
            generation=generation(),
            provider_request_id="request-1",
            correlation_id="correlation-1",
        )

    with pytest.raises(ValueError, match="item count"):
        EmbeddingResult(
            vectors=(EmbeddingVector(index=0, values=(1.0, 0.0, 0.0)),),
            usage=EmbeddingUsage(input_tokens=2, item_count=2, input_bytes=4),
            reserved_cost_microusd=2,
            incurred_cost_microusd=None,
            provider_id="candidate",
            generation=generation(),
            provider_request_id="request-1",
            correlation_id="correlation-1",
        )
