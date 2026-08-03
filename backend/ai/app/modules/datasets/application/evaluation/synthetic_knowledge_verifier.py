"""Independent reconstruction verifier for synthetic knowledge candidates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Final, cast

from app.modules.datasets.application.evaluation.synthetic_knowledge_authority import (
    AUTHORITY_REVISION,
    GENERATOR_SOURCE_SHA256,
    VERIFIER_SOURCE_SHA256,
)
from app.modules.datasets.application.evaluation.synthetic_knowledge_candidate import (
    DATASET_ID,
    GENERATOR_REVISION,
    SCHEMA_REVISION,
    build_document_lock,
    canonical_json,
    canonical_jsonl,
    render_knowledge_rows,
    sha256,
)
from app.modules.datasets.domain import RegistryInvariantError

VERIFIER_REVISION: Final[str] = "vfbiz-synthetic-knowledge-verifier-v1"
_FORBIDDEN: Final[re.Pattern[str]] = re.compile(
    r"vinfast|vivi|https?://|\b(?:giá|bảo hành|khuyến mại|hotline)\b|"
    r"\b\d{8,}\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SyntheticKnowledgeCandidateBundle:
    bundle_digest: str
    rows_jsonl: bytes
    document_lock_json: bytes
    validation_report_json: bytes
    manifest_json: bytes
    generator_source_bytes: bytes
    verifier_source_bytes: bytes


def build_synthetic_knowledge_candidate_bundle(
    *, generator_source_bytes: bytes, verifier_source_bytes: bytes
) -> SyntheticKnowledgeCandidateBundle:
    _validate_authority_sources(generator_source_bytes, verifier_source_bytes)
    document_lock_json = canonical_json(build_document_lock())
    document_lock_sha256 = sha256(document_lock_json)
    rows = render_knowledge_rows(document_lock_sha256=document_lock_sha256)
    rows_jsonl = canonical_jsonl(rows)
    validation_report = _validate_rows(rows, document_lock_sha256)
    validation_report_json = canonical_json(validation_report)
    manifest_basis: dict[str, object] = {
        "schema_revision": SCHEMA_REVISION,
        "dataset_id": DATASET_ID,
        "status": "restricted-synthetic-candidate",
        "purpose": "knowledge-ingestion-and-fingerprint-qualification-only",
        "generator_revision": GENERATOR_REVISION,
        "verifier_revision": VERIFIER_REVISION,
        "authority_revision": AUTHORITY_REVISION,
        "generator_source_sha256": sha256(generator_source_bytes),
        "verifier_source_sha256": sha256(verifier_source_bytes),
        "document_lock_sha256": document_lock_sha256,
        "rows_sha256": sha256(rows_jsonl),
        "validation_report_sha256": sha256(validation_report_json),
        "document_count": 3,
        "record_count": len(rows),
        "raw_pdf_included": False,
        "cloud_ocr_performed": False,
        "human_adjudicated": False,
        "training_eligible": False,
        "upload_allowed": False,
        "release_eligible": False,
    }
    bundle_digest = sha256(canonical_json(manifest_basis))
    manifest_json = canonical_json({**manifest_basis, "bundle_digest": bundle_digest})
    return SyntheticKnowledgeCandidateBundle(
        bundle_digest=bundle_digest,
        rows_jsonl=rows_jsonl,
        document_lock_json=document_lock_json,
        validation_report_json=validation_report_json,
        manifest_json=manifest_json,
        generator_source_bytes=generator_source_bytes,
        verifier_source_bytes=verifier_source_bytes,
    )


def verify_synthetic_knowledge_candidate_bundle(
    bundle: SyntheticKnowledgeCandidateBundle,
) -> None:
    """Verify against pinned authority, never caller-declared authority."""

    expected = build_synthetic_knowledge_candidate_bundle(
        generator_source_bytes=bundle.generator_source_bytes,
        verifier_source_bytes=bundle.verifier_source_bytes,
    )
    if bundle != expected:
        raise RegistryInvariantError(
            "synthetic knowledge candidate differs from repository authority"
        )


def _validate_authority_sources(generator_source: bytes, verifier_source: bytes) -> None:
    if sha256(generator_source) != GENERATOR_SOURCE_SHA256:
        raise RegistryInvariantError("synthetic knowledge generator authority mismatch")
    if sha256(verifier_source) != VERIFIER_SOURCE_SHA256:
        raise RegistryInvariantError("synthetic knowledge verifier authority mismatch")


def _validate_rows(
    rows: tuple[dict[str, object], ...], document_lock_sha256: str
) -> dict[str, object]:
    if len(rows) != 12:
        raise RegistryInvariantError("synthetic knowledge candidate must contain 12 rows")
    if len({str(row["record_id"]) for row in rows}) != len(rows):
        raise RegistryInvariantError("synthetic knowledge record IDs must be unique")
    if len({str(row["text"]).casefold() for row in rows}) != len(rows):
        raise RegistryInvariantError("synthetic knowledge text must be unique")
    for row in rows:
        text = str(row.get("text", ""))
        if not text or _FORBIDDEN.search(text):
            raise RegistryInvariantError("synthetic knowledge contains forbidden content")
        if row.get("page_text_sha256") != sha256(text.encode("utf-8")):
            raise RegistryInvariantError("synthetic knowledge page digest mismatch")
        if any(
            row.get(field) is not False
            for field in (
                "human_adjudicated",
                "training_eligible",
                "upload_allowed",
                "release_eligible",
            )
        ):
            raise RegistryInvariantError("synthetic knowledge eligibility is unsafe")
        citation = _mapping(row.get("citation"), "citation")
        lineage = _mapping(row.get("lineage"), "lineage")
        if (
            citation.get("document_id") != row.get("document_id")
            or citation.get("page") != row.get("page_start")
            or citation.get("source_sha256") != row.get("source_sha256")
            or row.get("page_start") != row.get("page_end")
        ):
            raise RegistryInvariantError("synthetic knowledge citation mismatch")
        if (
            lineage.get("origin") != "synthetic-qualification"
            or lineage.get("extraction_method") != "synthetic-fixture"
            or lineage.get("cloud_ocr_performed") is not False
            or lineage.get("document_lock_sha256") != document_lock_sha256
        ):
            raise RegistryInvariantError("synthetic knowledge lineage mismatch")
    return {
        "schema_revision": "synthetic-knowledge-validation-v1",
        "status": "passed-technical-restricted",
        "record_count": len(rows),
        "document_count": len({str(row["document_id"]) for row in rows}),
        "unique_record_count": len({str(row["record_id"]) for row in rows}),
        "unique_text_count": len({str(row["text"]).casefold() for row in rows}),
        "forbidden_content_match_count": 0,
        "citation_complete_count": len(rows),
        "release_eligible": False,
    }


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RegistryInvariantError(f"synthetic knowledge {field} must be an object")
    return cast(dict[str, object], value)


def parse_synthetic_knowledge_rows(payload: bytes) -> tuple[dict[str, object], ...]:
    try:
        rows = tuple(json.loads(line) for line in payload.decode("utf-8").splitlines())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegistryInvariantError("synthetic knowledge rows are unreadable") from error
    if not all(isinstance(row, dict) for row in rows):
        raise RegistryInvariantError("synthetic knowledge rows must be objects")
    return cast(tuple[dict[str, object], ...], rows)


__all__ = [
    "SyntheticKnowledgeCandidateBundle",
    "build_synthetic_knowledge_candidate_bundle",
    "parse_synthetic_knowledge_rows",
    "verify_synthetic_knowledge_candidate_bundle",
]
