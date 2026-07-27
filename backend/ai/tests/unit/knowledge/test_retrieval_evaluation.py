from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.knowledge.application.retrieval_evaluation import (
    summarize_retrieval_benchmark,
    validate_vietnamese_bakeoff_coverage,
)
from app.modules.knowledge.domain.retrieval_evaluation import (
    RetrievalBenchmarkObservation,
    RetrievalEvaluationCase,
)

CHUNK_A = UUID("00000000-0000-0000-0000-000000000001")
CHUNK_B = UUID("00000000-0000-0000-0000-000000000002")
CHUNK_C = UUID("00000000-0000-0000-0000-000000000003")


def test_vietnamese_case_requires_approved_provenance_and_held_out_split() -> None:
    with pytest.raises(ValidationError):
        RetrievalEvaluationCase.model_validate(
            {
                "case_id": "vi-policy-001",
                "query": "VF 8 bảo hành pin bao lâu?",
                "locale": "vi-VN",
                "expected_chunk_ids": (CHUNK_A,),
                "tags": ("numeric-policy",),
                "source_approval_digest": "a" * 64,
                "split": "training",
            }
        )


def test_summary_reports_quality_latency_cost_and_refusal_correctness() -> None:
    observations = (
        RetrievalBenchmarkObservation(
            case_id="vi-policy-001",
            expected_chunk_ids=(CHUNK_A, CHUNK_B),
            retrieved_chunk_ids=(CHUNK_A, CHUNK_C, CHUNK_B),
            baseline_retrieved_chunk_ids=(CHUNK_C, CHUNK_B, CHUNK_A),
            expected_outcome="evidence",
            actual_outcome="evidence",
            citation_valid=True,
            latency_ms=18.0,
            normalized_cost=0.00002,
        ),
        RetrievalBenchmarkObservation(
            case_id="vi-unknown-001",
            expected_chunk_ids=(),
            retrieved_chunk_ids=(),
            expected_outcome="refusal",
            actual_outcome="refusal",
            citation_valid=True,
            latency_ms=42.0,
            normalized_cost=0.0,
        ),
    )

    summary = summarize_retrieval_benchmark(observations)

    assert summary.case_count == 2
    assert summary.recall_at_5 == 1.0
    assert summary.recall_at_20 == 1.0
    assert summary.mrr == 1.0
    assert 0.9 < summary.ndcg_at_10 < 1.0
    assert summary.reranker_ndcg_lift > 0.0
    assert summary.citation_correctness == 1.0
    assert summary.refusal_correctness == 1.0
    assert summary.p50_latency_ms == 30.0
    assert summary.p95_latency_ms == 40.8
    assert summary.normalized_cost == 0.00002
    assert summary.throughput_cases_per_second == pytest.approx(33.333333, rel=1e-5)


def test_bakeoff_rejects_suite_missing_enterprise_vietnamese_risk_coverage() -> None:
    incomplete = RetrievalEvaluationCase(
        case_id="vi-policy-001",
        query="VF 8 bảo hành pin bao lâu?",
        locale="vi-VN",
        expected_chunk_ids=(CHUNK_A,),
        tags=("diacritics", "numeric-policy"),
        source_approval_digest="a" * 64,
        split="held-out",
    )

    with pytest.raises(ValueError, match="missing required coverage"):
        validate_vietnamese_bakeoff_coverage((incomplete,))
