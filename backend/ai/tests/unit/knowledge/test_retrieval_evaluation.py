from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.knowledge.application.retrieval_evaluation import (
    summarize_retrieval_benchmark,
    validate_vietnamese_bakeoff_authority,
    validate_vietnamese_bakeoff_coverage,
    validate_vietnamese_bakeoff_manifest,
)
from app.modules.knowledge.domain.retrieval_evaluation import (
    RetrievalBakeoffManifest,
    RetrievalBenchmarkObservation,
    RetrievalEvaluationCase,
    RetrievalSuiteAuthority,
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


def test_bakeoff_rejects_suite_without_required_outcome_classes() -> None:
    tags = (
        "diacritics",
        "no-diacritics",
        "typo",
        "slang",
        "code-switch",
        "vehicle-model",
        "numeric-policy",
        "ambiguous",
        "stale-source",
        "contradictory-source",
        "hard-negative",
        "refusal",
    )
    evidence_only = RetrievalEvaluationCase(
        case_id="vi-policy-001",
        query="VF 8 bảo hành pin bao lâu?",
        locale="vi-VN",
        expected_chunk_ids=(CHUNK_A,),
        tags=tags,
        source_approval_digest="a" * 64,
        split="held-out",
    )

    with pytest.raises(ValueError, match="at least one refusal case"):
        validate_vietnamese_bakeoff_coverage((evidence_only,))


def test_empty_metric_slices_fail_closed_instead_of_defaulting_to_perfect() -> None:
    refusal_only = RetrievalBenchmarkObservation(
        case_id="vi-unknown-001",
        expected_chunk_ids=(),
        retrieved_chunk_ids=(),
        expected_outcome="refusal",
        actual_outcome="refusal",
        citation_valid=True,
        latency_ms=42.0,
        normalized_cost=0.0,
    )

    summary = summarize_retrieval_benchmark((refusal_only,))

    assert summary.recall_at_5 == 0.0
    assert summary.recall_at_20 == 0.0
    assert summary.ndcg_at_10 == 0.0
    assert summary.mrr == 0.0


def test_observation_outcome_and_expected_chunks_must_agree() -> None:
    with pytest.raises(ValidationError, match="evidence observation"):
        RetrievalBenchmarkObservation(
            case_id="vi-policy-001",
            expected_chunk_ids=(),
            retrieved_chunk_ids=(),
            expected_outcome="evidence",
            actual_outcome="knowledge_unavailable",
            citation_valid=False,
            latency_ms=10.0,
            normalized_cost=0.0,
        )

    with pytest.raises(ValidationError, match="non-evidence observation"):
        RetrievalBenchmarkObservation(
            case_id="vi-unknown-001",
            expected_chunk_ids=(CHUNK_A,),
            retrieved_chunk_ids=(CHUNK_A,),
            expected_outcome="refusal",
            actual_outcome="evidence",
            citation_valid=True,
            latency_ms=10.0,
            normalized_cost=0.0,
        )


def _manifest_case(
    case_id: str,
    *,
    source_digest: str = "a" * 64,
) -> RetrievalEvaluationCase:
    return RetrievalEvaluationCase(
        case_id=case_id,
        query="Thông tin này có được cập nhật không?",
        locale="vi-VN",
        expected_chunk_ids=(CHUNK_A,),
        tags=("diacritics",),
        source_approval_digest=source_digest,
        split="held-out",
        expected_outcome="evidence",
    )


def test_bakeoff_manifest_locks_order_and_source_release() -> None:
    cases = (_manifest_case("vi-case-001"),)
    draft = RetrievalBakeoffManifest.model_construct(
        manifest_revision="retrieval-bakeoff-v1",
        suite_id="vietnamese-suite-v1",
        suite_digest="0" * 64,
        source_release_digest="a" * 64,
        index_generation_digest="b" * 64,
        evaluator_revision="retrieval-evaluator-v1",
        cases=cases,
    )
    manifest_payload = draft.model_dump()
    manifest_payload["suite_digest"] = draft.computed_suite_digest()
    manifest = RetrievalBakeoffManifest(**manifest_payload)

    assert manifest.computed_suite_digest() == manifest.suite_digest

    with pytest.raises(ValidationError, match="suite digest mismatch"):
        tampered_payload = manifest.model_dump()
        tampered_payload["suite_digest"] = "c" * 64
        RetrievalBakeoffManifest(**tampered_payload)

    tampered = RetrievalBakeoffManifest.model_construct(
        manifest_revision=manifest.manifest_revision,
        suite_id=manifest.suite_id,
        suite_digest="c" * 64,
        source_release_digest=manifest.source_release_digest,
        index_generation_digest=manifest.index_generation_digest,
        evaluator_revision=manifest.evaluator_revision,
        cases=manifest.cases,
    )
    with pytest.raises(ValidationError, match="suite digest mismatch"):
        validate_vietnamese_bakeoff_manifest(tampered)


def test_bakeoff_manifest_rejects_mixed_source_release() -> None:
    with pytest.raises(ValidationError, match="one source release"):
        RetrievalBakeoffManifest(
            manifest_revision="retrieval-bakeoff-v1",
            suite_id="vietnamese-suite-v1",
            suite_digest="a" * 64,
            source_release_digest="a" * 64,
            index_generation_digest="b" * 64,
            evaluator_revision="retrieval-evaluator-v1",
            cases=(_manifest_case("vi-case-001", source_digest="c" * 64),),
        )


def _manifest_with_required_coverage() -> RetrievalBakeoffManifest:
    tags = (
        "diacritics",
        "no-diacritics",
        "typo",
        "slang",
        "code-switch",
        "vehicle-model",
        "numeric-policy",
        "ambiguous",
        "stale-source",
        "contradictory-source",
        "hard-negative",
        "refusal",
    )
    cases = (
        RetrievalEvaluationCase(
            case_id="vi-approved-001",
            query="Tài liệu này có còn hiệu lực không?",
            locale="vi-VN",
            expected_chunk_ids=(CHUNK_A,),
            tags=tags,
            source_approval_digest="a" * 64,
            split="held-out",
        ),
        RetrievalEvaluationCase(
            case_id="vi-refusal-001",
            query="Hãy cho tôi một thông tin không có trong tài liệu.",
            locale="vi-VN",
            expected_chunk_ids=(),
            tags=("refusal",),
            source_approval_digest="a" * 64,
            split="held-out",
            expected_outcome="refusal",
        ),
    )
    draft = RetrievalBakeoffManifest.model_construct(
        manifest_revision="retrieval-bakeoff-v1",
        suite_id="vietnamese-suite-v1",
        suite_digest="0" * 64,
        source_release_digest="a" * 64,
        index_generation_digest="b" * 64,
        evaluator_revision="retrieval-evaluator-v1",
        cases=cases,
    )
    payload = draft.model_dump()
    payload["suite_digest"] = draft.computed_suite_digest()
    return RetrievalBakeoffManifest(**payload)


def _authority_for(manifest: RetrievalBakeoffManifest) -> RetrievalSuiteAuthority:
    return RetrievalSuiteAuthority.issue(
        suite_id=manifest.suite_id,
        suite_digest=manifest.suite_digest,
        source_release_digest=manifest.source_release_digest,
        index_generation_digest=manifest.index_generation_digest,
        evaluator_revision=manifest.evaluator_revision,
        provenance_digest="c" * 64,
        provenance_evidence_uri="evidence://retrieval-suite/provenance",
        data_owner_subject="data-owner",
        evaluator_subject="independent-evaluator",
        release_owner_subject="release-owner",
    )


def test_bakeoff_release_requires_external_authority_bound_to_every_revision() -> None:
    manifest = _manifest_with_required_coverage()
    authority = _authority_for(manifest)

    validate_vietnamese_bakeoff_authority(manifest, authority)

    mismatched = RetrievalSuiteAuthority.issue(
        suite_id=manifest.suite_id,
        suite_digest=manifest.suite_digest,
        source_release_digest=manifest.source_release_digest,
        index_generation_digest="d" * 64,
        evaluator_revision=manifest.evaluator_revision,
        provenance_digest="c" * 64,
        provenance_evidence_uri="evidence://retrieval-suite/provenance",
        data_owner_subject="data-owner",
        evaluator_subject="independent-evaluator",
        release_owner_subject="release-owner",
    )
    with pytest.raises(ValueError, match="AUTHORITY_BINDING_MISMATCH"):
        validate_vietnamese_bakeoff_authority(manifest, mismatched)


def test_bakeoff_manifest_integrity_alone_does_not_grant_release_authority() -> None:
    manifest = _manifest_with_required_coverage()
    with pytest.raises(TypeError):
        # The public validator intentionally requires the external record; a
        # manifest digest cannot be substituted for approval.
        validate_vietnamese_bakeoff_authority(manifest, None)  # type: ignore[arg-type]
