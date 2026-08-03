import math
from collections.abc import Sequence

from app.modules.knowledge.domain.retrieval_evaluation import (
    RetrievalBakeoffManifest,
    RetrievalBenchmarkObservation,
    RetrievalBenchmarkSummary,
    RetrievalEvaluationCase,
    RetrievalSuiteAuthority,
)

REQUIRED_VIETNAMESE_BAKEOFF_TAGS = frozenset(
    {
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
    }
)


def validate_vietnamese_bakeoff_coverage(
    cases: Sequence[RetrievalEvaluationCase],
) -> None:
    """Fail closed when a release bake-off omits required language/risk slices."""

    typed_cases = tuple(cases)
    if not typed_cases:
        raise ValueError("retrieval bake-off requires typed held-out cases")
    case_ids = [case.case_id for case in typed_cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("retrieval bake-off case IDs must be unique")
    if any(case.locale != "vi-VN" for case in typed_cases):
        raise ValueError("Vietnamese bake-off only accepts vi-VN cases")
    observed_tags = {tag for case in typed_cases for tag in case.tags}
    missing = sorted(REQUIRED_VIETNAMESE_BAKEOFF_TAGS - observed_tags)
    if missing:
        raise ValueError(f"missing required coverage: {', '.join(missing)}")
    observed_outcomes = {case.expected_outcome for case in typed_cases}
    if "evidence" not in observed_outcomes:
        raise ValueError("retrieval bake-off requires at least one evidence case")
    if "refusal" not in observed_outcomes:
        raise ValueError("retrieval bake-off requires at least one refusal case")


def validate_vietnamese_bakeoff_manifest(
    manifest: RetrievalBakeoffManifest,
) -> None:
    """Validate language/risk coverage after the manifest digest is locked."""

    manifest.validate_integrity()
    validate_vietnamese_bakeoff_coverage(manifest.cases)


def validate_vietnamese_bakeoff_authority(
    manifest: RetrievalBakeoffManifest,
    authority: object,
) -> None:
    """Require an external, exact authority record before a suite can release.

    A valid manifest proves canonical integrity only. It does not prove source
    rights, held-out approval, or that the evaluator is allowed to release the
    result. Those claims must come from the separately persisted authority
    record and must bind every deployment-relevant revision.
    """

    if not isinstance(authority, RetrievalSuiteAuthority):
        raise TypeError("retrieval suite authority record is required")
    validate_vietnamese_bakeoff_manifest(manifest)
    if (
        authority.suite_id != manifest.suite_id
        or authority.suite_digest != manifest.suite_digest
        or authority.source_release_digest != manifest.source_release_digest
        or authority.index_generation_digest != manifest.index_generation_digest
        or authority.evaluator_revision != manifest.evaluator_revision
        or authority.authority_class != "approved-vietnamese-held-out"
        or not authority.held_out
    ):
        raise ValueError("RETRIEVAL_SUITE_AUTHORITY_BINDING_MISMATCH")


def summarize_retrieval_benchmark(
    observations: Sequence[RetrievalBenchmarkObservation],
) -> RetrievalBenchmarkSummary:
    """Calculate deterministic quality, latency and cost evidence for a bake-off."""

    if not observations:
        raise ValueError("retrieval benchmark requires at least one observation")
    evidence = tuple(item for item in observations if item.expected_chunk_ids)
    recall_at_5 = _mean(tuple(_recall(item, 5) for item in evidence), empty=0.0)
    recall_at_20 = _mean(tuple(_recall(item, 20) for item in evidence), empty=0.0)
    ndcg_at_10 = _mean(tuple(_ndcg(item, 10) for item in evidence), empty=0.0)
    mrr = _mean(tuple(_reciprocal_rank(item) for item in evidence), empty=0.0)
    refusal_cases = tuple(item for item in observations if item.expected_outcome == "refusal")
    reranked = tuple(item for item in evidence if item.baseline_retrieved_chunk_ids is not None)
    latencies = sorted(item.latency_ms for item in observations)
    total_latency_ms = sum(latencies)
    return RetrievalBenchmarkSummary(
        case_count=len(observations),
        recall_at_5=recall_at_5,
        recall_at_20=recall_at_20,
        ndcg_at_10=ndcg_at_10,
        reranker_ndcg_lift=_mean(
            tuple(
                _ndcg(item, 10)
                - _ndcg_for(
                    set(item.expected_chunk_ids),
                    item.baseline_retrieved_chunk_ids or (),
                    10,
                )
                for item in reranked
            ),
            empty=0.0,
        ),
        mrr=mrr,
        citation_correctness=_mean(
            tuple(1.0 if item.citation_valid else 0.0 for item in observations)
        ),
        refusal_correctness=_mean(
            tuple(1.0 if item.actual_outcome == "refusal" else 0.0 for item in refusal_cases),
            empty=0.0,
        ),
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        normalized_cost=sum(item.normalized_cost for item in observations),
        throughput_cases_per_second=(
            len(observations) * 1_000.0 / total_latency_ms if total_latency_ms > 0.0 else 0.0
        ),
    )


def _recall(observation: RetrievalBenchmarkObservation, limit: int) -> float:
    expected = set(observation.expected_chunk_ids)
    retrieved = set(observation.retrieved_chunk_ids[:limit])
    return len(expected & retrieved) / len(expected)


def _reciprocal_rank(observation: RetrievalBenchmarkObservation) -> float:
    expected = set(observation.expected_chunk_ids)
    return next(
        (
            1.0 / rank
            for rank, chunk_id in enumerate(observation.retrieved_chunk_ids, start=1)
            if chunk_id in expected
        ),
        0.0,
    )


def _ndcg(observation: RetrievalBenchmarkObservation, limit: int) -> float:
    return _ndcg_for(
        set(observation.expected_chunk_ids),
        observation.retrieved_chunk_ids,
        limit,
    )


def _ndcg_for(
    expected: set[object],
    retrieved: tuple[object, ...],
    limit: int,
) -> float:
    gains = tuple(1.0 if chunk_id in expected else 0.0 for chunk_id in retrieved[:limit])
    dcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))
    ideal_count = min(len(expected), limit)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / ideal if ideal else 0.0


def _mean(values: tuple[float, ...], *, empty: float = 0.0) -> float:
    return sum(values) / len(values) if values else empty


def _percentile(values: list[float], percentile: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction
