"""Deterministic cross-product contamination verification for Golden candidates."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Final

GLOBAL_CONTAMINATION_REQUIRED_PRODUCTS: Final[frozenset[str]] = frozenset(
    {"knowledge", "training", "red-team"}
)
GLOBAL_CONTAMINATION_ALGORITHM_REVISION: Final[str] = (
    "accent-folded-token-set-jaccard-v1"
)
GLOBAL_CONTAMINATION_SEMANTIC_THRESHOLD: Final[float] = 0.85
_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class ContaminationSourceEvidence:
    """Digest-bound proof for one independently parsed data-product source."""

    product: str
    source_id: str
    source_sha256: str
    extractor_id: str
    extractor_source_sha256: str
    surface_count: int


@dataclass(frozen=True, slots=True)
class ContaminationRecord:
    """One text surface tied to an exact governed source."""

    product: str
    source_id: str
    source_sha256: str
    record_id: str
    family_id: str
    text: str


def build_untrusted_contamination_projection(
    *,
    golden_records: tuple[ContaminationRecord, ...],
    comparison_records: tuple[ContaminationRecord, ...],
    source_evidence: tuple[ContaminationSourceEvidence, ...],
    algorithm_source_sha256: str,
    semantic_threshold: float = GLOBAL_CONTAMINATION_SEMANTIC_THRESHOLD,
    maximum_examples: int = 100,
) -> dict[str, object]:
    """Compare exact source-bound surfaces and fail closed on missing products."""

    _validate_inputs(
        golden_records=golden_records,
        comparison_records=comparison_records,
        source_evidence=source_evidence,
        algorithm_source_sha256=algorithm_source_sha256,
        semantic_threshold=semantic_threshold,
        maximum_examples=maximum_examples,
    )
    observed_products = frozenset(
        evidence.product for evidence in source_evidence if evidence.product != "golden"
    )
    missing_products = sorted(GLOBAL_CONTAMINATION_REQUIRED_PRODUCTS - observed_products)
    exact_examples: list[dict[str, object]] = []
    lexical_examples: list[dict[str, object]] = []
    exact_count = 0
    lexical_count = 0

    comparison = tuple(
        (record, _normalized_text(record.text), _token_set(record.text))
        for record in comparison_records
        if _normalized_text(record.text)
    )
    for golden in golden_records:
        normalized = _normalized_text(golden.text)
        tokens = _token_set(golden.text)
        if not normalized:
            continue
        for other, other_normalized, other_tokens in comparison:
            if normalized == other_normalized:
                exact_count += 1
                if len(exact_examples) < maximum_examples:
                    exact_examples.append(_match(golden, other, 1.0))
                continue
            similarity = _jaccard(tokens, other_tokens)
            if similarity >= semantic_threshold:
                lexical_count += 1
                if len(lexical_examples) < maximum_examples:
                    lexical_examples.append(_match(golden, other, similarity))

    overlap_found = exact_count > 0 or lexical_count > 0
    status = "failed" if overlap_found else "incomplete" if missing_products else "passed"
    source_projection = [
        {
            "product": evidence.product,
            "source_id": evidence.source_id,
            "source_sha256": evidence.source_sha256,
            "extractor_id": evidence.extractor_id,
            "extractor_source_sha256": evidence.extractor_source_sha256,
            "surface_count": evidence.surface_count,
        }
        for evidence in sorted(source_evidence, key=lambda item: item.source_id)
    ]
    projection: dict[str, object] = {
        "schema_revision": "global-contamination-report-v2",
        "authority_class": "untrusted-diagnostic",
        "status": status,
        "required_products": sorted(GLOBAL_CONTAMINATION_REQUIRED_PRODUCTS),
        "required_product_policy_sha256": _required_product_policy_digest(),
        "observed_products": sorted(observed_products),
        "missing_products": missing_products,
        "algorithm_revision": GLOBAL_CONTAMINATION_ALGORITHM_REVISION,
        "algorithm_source_sha256": algorithm_source_sha256,
        "similarity_method": "accent-insensitive lexical token-set Jaccard",
        "semantic_equivalence_claimed": False,
        "source_evidence": source_projection,
        "golden_surface_count": len(golden_records),
        "comparison_surface_count": len(comparison_records),
        "semantic_threshold": semantic_threshold,
        "exact_overlap_count": exact_count,
        "lexical_near_overlap_count": lexical_count,
        "exact_overlap_examples": exact_examples,
        "lexical_near_overlap_examples": lexical_examples,
        "exact_examples_truncated": exact_count > len(exact_examples),
        "lexical_examples_truncated": lexical_count > len(lexical_examples),
        "release_eligible": False,
    }
    projection["report_digest"] = compute_global_contamination_report_digest(projection)
    return projection


def compute_global_contamination_report_digest(report: dict[str, object]) -> str:
    projection = {key: value for key, value in report.items() if key != "report_digest"}
    canonical = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate_inputs(
    *,
    golden_records: tuple[ContaminationRecord, ...],
    comparison_records: tuple[ContaminationRecord, ...],
    source_evidence: tuple[ContaminationSourceEvidence, ...],
    algorithm_source_sha256: str,
    semantic_threshold: float,
    maximum_examples: int,
) -> None:
    if not golden_records:
        raise ValueError("golden_records must not be empty")
    if not source_evidence:
        raise ValueError("source_evidence must not be empty")
    if not 0.0 < semantic_threshold <= 1.0:
        raise ValueError("semantic_threshold must be in (0, 1]")
    if maximum_examples < 1:
        raise ValueError("maximum_examples must be positive")
    _validate_sha256(algorithm_source_sha256, "algorithm_source_sha256")
    if any(record.product != "golden" for record in golden_records):
        raise ValueError("golden_records must use product='golden'")
    if any(record.product == "golden" for record in comparison_records):
        raise ValueError("comparison_records cannot use product='golden'")

    evidence_by_source = {evidence.source_id: evidence for evidence in source_evidence}
    if len(evidence_by_source) != len(source_evidence):
        raise ValueError("source_evidence contains duplicate source_id")
    if not any(evidence.product == "golden" for evidence in source_evidence):
        raise ValueError("source_evidence must include a Golden source")
    for record in (*golden_records, *comparison_records):
        evidence = evidence_by_source.get(record.source_id)
        if evidence is None:
            raise ValueError("record is not bound to source evidence")
        if record.product != evidence.product or record.source_sha256 != evidence.source_sha256:
            raise ValueError("record product or digest differs from source evidence")
    observed_counts = Counter(record.source_id for record in (*golden_records, *comparison_records))
    for evidence in source_evidence:
        _validate_sha256(evidence.source_sha256, "source_sha256")
        _validate_sha256(evidence.extractor_source_sha256, "extractor_source_sha256")
        if evidence.surface_count < 1:
            raise ValueError("source evidence must bind at least one parsed surface")
        if evidence.surface_count != observed_counts[evidence.source_id]:
            raise ValueError("source evidence surface count does not match parsed records")


def _validate_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 value")


def _required_product_policy_digest() -> str:
    payload = json.dumps(
        {
            "policy_revision": "golden-cross-product-policy-v1",
            "required_products": sorted(GLOBAL_CONTAMINATION_REQUIRED_PRODUCTS),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalized_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(character for character in folded if not unicodedata.combining(character))
    return " ".join(_TOKEN_PATTERN.findall(ascii_text.replace("đ", "d")))


def _token_set(value: str) -> frozenset[str]:
    return frozenset(_normalized_text(value).split())


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _match(
    golden: ContaminationRecord,
    other: ContaminationRecord,
    similarity: float,
) -> dict[str, object]:
    return {
        "golden_record_id": golden.record_id,
        "golden_family_id": golden.family_id,
        "comparison_product": other.product,
        "comparison_record_id": other.record_id,
        "comparison_family_id": other.family_id,
        "similarity": round(similarity, 6),
    }


__all__ = [
    "ContaminationRecord",
    "ContaminationSourceEvidence",
    "GLOBAL_CONTAMINATION_ALGORITHM_REVISION",
    "GLOBAL_CONTAMINATION_REQUIRED_PRODUCTS",
    "GLOBAL_CONTAMINATION_SEMANTIC_THRESHOLD",
    "compute_global_contamination_report_digest",
]
