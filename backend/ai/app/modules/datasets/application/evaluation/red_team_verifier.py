"""Independent deterministic verifier for synthetic red-team candidates."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Final, cast

from app.modules.datasets.application.evaluation.red_team_generator import (
    DATASET_ID,
    GENERATOR_REVISION,
    SCHEMA_REVISION,
    VARIANTS_PER_FAMILY,
    build_family_lock,
    canonical_json,
    canonical_jsonl,
    locked_red_team_families,
    render_red_team_rows,
    sha256,
)
from app.modules.datasets.domain import RegistryInvariantError

MINIMUM_CASE_COUNT: Final[int] = 200
NEAR_DUPLICATE_THRESHOLD: Final[float] = 0.85
_REQUIRED_FALSE_FLAGS: Final[tuple[str, ...]] = (
    "human_adjudicated",
    "training_eligible",
    "upload_allowed",
    "release_eligible",
    "knowledge_eligible",
)
_FORBIDDEN_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b(?:https?://|www\.)", re.IGNORECASE),
    re.compile(r"\b\d{8,}\b"),
    re.compile(r"\b(?:vinfast|vivi)\b", re.IGNORECASE),
    re.compile(r"\b(?:hotline|đường dây nóng)\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:đồng|vnd|usd|triệu|tỷ)\b", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class RedTeamCandidateBundle:
    bundle_digest: str
    rows_jsonl: bytes
    family_lock_json: bytes
    validation_report_json: bytes
    manifest_json: bytes
    generator_source_bytes: bytes
    verifier_source_bytes: bytes

    @property
    def manifest(self) -> dict[str, object]:
        return _parse_object(self.manifest_json)


def build_red_team_candidate_bundle(
    *, generator_source_bytes: bytes, verifier_source_bytes: bytes
) -> RedTeamCandidateBundle:
    if not generator_source_bytes or not verifier_source_bytes:
        raise RegistryInvariantError("red-team authority source snapshot is empty")
    family_lock = build_family_lock()
    family_lock_json = canonical_json(family_lock)
    rows = render_red_team_rows(family_lock_sha256=sha256(family_lock_json))
    rows_jsonl = canonical_jsonl(rows)
    report = _build_validation_report(rows)
    report_json = canonical_json(report)
    unsigned_manifest: dict[str, object] = {
        "schema_revision": SCHEMA_REVISION,
        "dataset_id": DATASET_ID,
        "status": "candidate",
        "allowed_use": "red-team-evaluation-only",
        "restricted_access_required": True,
        "generator_revision": GENERATOR_REVISION,
        "generator_source_sha256": sha256(generator_source_bytes),
        "verifier_revision": "vfbiz-red-team-verifier-v1",
        "verifier_source_sha256": sha256(verifier_source_bytes),
        "synthetic_source_revision": "fact-free-adversarial-patterns-v1",
        "synthetic_source_sha256": sha256(_synthetic_source_projection()),
        "case_count": len(rows),
        "family_count": len(locked_red_team_families()),
        "variants_per_family": VARIANTS_PER_FAMILY,
        "attack_class_counts": dict(
            sorted(Counter(str(row["attack_class"]) for row in rows).items())
        ),
        "rows_sha256": sha256(rows_jsonl),
        "family_lock_sha256": sha256(family_lock_json),
        "validation_report_sha256": sha256(report_json),
        "human_adjudicated": False,
        "training_eligible": False,
        "upload_allowed": False,
        "release_eligible": False,
        "knowledge_eligible": False,
        "semantic_equivalence_claimed": False,
        "provider_calls": 0,
        "approval_evidence": [],
        "independent_review_status": "pending",
    }
    bundle_digest = sha256(canonical_json(unsigned_manifest))
    manifest = {**unsigned_manifest, "bundle_digest": bundle_digest}
    bundle = RedTeamCandidateBundle(
        bundle_digest=bundle_digest,
        rows_jsonl=rows_jsonl,
        family_lock_json=family_lock_json,
        validation_report_json=report_json,
        manifest_json=canonical_json(manifest),
        generator_source_bytes=generator_source_bytes,
        verifier_source_bytes=verifier_source_bytes,
    )
    verify_red_team_candidate_bundle(
        bundle,
        expected_generator_source_bytes=generator_source_bytes,
        expected_verifier_source_bytes=verifier_source_bytes,
    )
    return bundle


def verify_red_team_candidate_bundle(
    bundle: RedTeamCandidateBundle,
    *,
    expected_generator_source_bytes: bytes,
    expected_verifier_source_bytes: bytes,
) -> None:
    manifest = bundle.manifest
    rows = _parse_rows(bundle.rows_jsonl)
    family_lock = _parse_object(bundle.family_lock_json)
    report = _parse_object(bundle.validation_report_json)
    expected_hashes = {
        "rows_sha256": sha256(bundle.rows_jsonl),
        "family_lock_sha256": sha256(bundle.family_lock_json),
        "validation_report_sha256": sha256(bundle.validation_report_json),
        "generator_source_sha256": sha256(expected_generator_source_bytes),
        "verifier_source_sha256": sha256(expected_verifier_source_bytes),
        "synthetic_source_sha256": sha256(_synthetic_source_projection()),
    }
    if any(manifest.get(key) != value for key, value in expected_hashes.items()):
        raise RegistryInvariantError("red-team candidate authority digest mismatch")
    if (
        bundle.generator_source_bytes != expected_generator_source_bytes
        or bundle.verifier_source_bytes != expected_verifier_source_bytes
    ):
        raise RegistryInvariantError("red-team candidate source snapshot mismatch")
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_digest"}
    if (
        manifest.get("bundle_digest") != sha256(canonical_json(unsigned))
        or bundle.bundle_digest != manifest.get("bundle_digest")
    ):
        raise RegistryInvariantError("red-team candidate bundle digest mismatch")
    _verify_manifest_policy(manifest)

    expected_lock = build_family_lock()
    if family_lock != expected_lock:
        raise RegistryInvariantError("red-team family lock differs from authority")
    expected_rows = render_red_team_rows(
        family_lock_sha256=sha256(bundle.family_lock_json)
    )
    if rows != expected_rows:
        raise RegistryInvariantError("red-team rows differ from deterministic projection")
    expected_report = _build_validation_report(rows)
    if report != expected_report:
        raise RegistryInvariantError("red-team validation report mismatch")
    _verify_rows(rows, manifest)


def _verify_manifest_policy(manifest: dict[str, object]) -> None:
    if (
        manifest.get("schema_revision") != SCHEMA_REVISION
        or manifest.get("dataset_id") != DATASET_ID
        or manifest.get("status") != "candidate"
        or manifest.get("allowed_use") != "red-team-evaluation-only"
        or manifest.get("restricted_access_required") is not True
        or manifest.get("case_count") != 200
        or manifest.get("family_count") != 40
        or manifest.get("variants_per_family") != VARIANTS_PER_FAMILY
        or manifest.get("semantic_equivalence_claimed") is not False
        or manifest.get("provider_calls") != 0
        or manifest.get("approval_evidence") != []
        or manifest.get("independent_review_status") != "pending"
        or any(manifest.get(flag) is not False for flag in _REQUIRED_FALSE_FLAGS)
    ):
        raise RegistryInvariantError("red-team candidate manifest policy mismatch")


def _verify_rows(
    rows: tuple[dict[str, object], ...], manifest: dict[str, object]
) -> None:
    required = {
        "case_id",
        "split_family_id",
        "attack_class",
        "text",
        "expected_disposition",
        "typed_failure",
        "family_lock_sha256",
        *_REQUIRED_FALSE_FLAGS,
    }
    if len(rows) < MINIMUM_CASE_COUNT or len(rows) != 200:
        raise RegistryInvariantError("red-team candidate case count mismatch")
    if any(set(row) != required for row in rows):
        raise RegistryInvariantError("red-team candidate row schema mismatch")
    if len({str(row["case_id"]) for row in rows}) != len(rows):
        raise RegistryInvariantError("red-team candidate case identifiers collide")
    if any(row.get(flag) is not False for row in rows for flag in _REQUIRED_FALSE_FLAGS):
        raise RegistryInvariantError("red-team candidate row policy mismatch")
    if any(
        row.get("family_lock_sha256") != manifest.get("family_lock_sha256")
        for row in rows
    ):
        raise RegistryInvariantError("red-team candidate family lock binding mismatch")
    if any(
        pattern.search(str(row["text"])) for row in rows for pattern in _FORBIDDEN_PATTERNS
    ):
        raise RegistryInvariantError("red-team candidate contains forbidden content")
    counts = Counter(str(row["attack_class"]) for row in rows)
    if counts != Counter({spec[0]: 25 for spec in _class_specs()}):
        raise RegistryInvariantError("red-team candidate attack distribution mismatch")
    if manifest.get("attack_class_counts") != dict(sorted(counts.items())):
        raise RegistryInvariantError("red-team manifest distribution mismatch")


def _build_validation_report(
    rows: tuple[dict[str, object], ...]
) -> dict[str, object]:
    normalized = [_normalize(str(row["text"])) for row in rows]
    exact_duplicates = len(normalized) - len(set(normalized))
    near_examples: list[dict[str, object]] = []
    near_count = 0
    token_sets = [frozenset(text.split()) for text in normalized]
    for left_index, left in enumerate(rows):
        for right_index in range(left_index + 1, len(rows)):
            right = rows[right_index]
            if left["split_family_id"] == right["split_family_id"]:
                continue
            union = token_sets[left_index] | token_sets[right_index]
            score = (
                len(token_sets[left_index] & token_sets[right_index]) / len(union)
                if union
                else 1.0
            )
            if score < NEAR_DUPLICATE_THRESHOLD:
                continue
            near_count += 1
            if len(near_examples) < 20:
                near_examples.append(
                    {
                        "left_case_id": left["case_id"],
                        "right_case_id": right["case_id"],
                        "token_jaccard": round(score, 6),
                    }
                )
    return {
        "schema_revision": "red-team-validation-report-v1",
        "case_count": len(rows),
        "family_count": len({row["split_family_id"] for row in rows}),
        "attack_class_counts": dict(
            sorted(Counter(str(row["attack_class"]) for row in rows).items())
        ),
        "exact_normalized_duplicate_count": exact_duplicates,
        "cross_family_token_jaccard_threshold": NEAR_DUPLICATE_THRESHOLD,
        "cross_family_near_overlap_count": near_count,
        "cross_family_near_overlap_examples": near_examples,
        "forbidden_content_match_count": sum(
            1
            for row in rows
            if any(pattern.search(str(row["text"])) for pattern in _FORBIDDEN_PATTERNS)
        ),
        "semantic_equivalence_claimed": False,
        "deterministic_gate_passed": exact_duplicates == 0 and near_count == 0,
    }


def _synthetic_source_projection() -> bytes:
    return canonical_json(
        {
            "source_revision": "fact-free-adversarial-patterns-v1",
            "family_lock": build_family_lock(),
            "provider_calls": 0,
            "external_sources": [],
            "vinfast_facts": [],
        }
    )


def _class_specs() -> tuple[tuple[str, str, str, tuple[str, ...]], ...]:
    families = locked_red_team_families()
    grouped: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    for family in families:
        disposition, failure, contexts = grouped.get(
            family.attack_class, (family.expected_disposition, family.typed_failure, ())
        )
        grouped[family.attack_class] = (disposition, failure, (*contexts, family.context))
    return tuple(
        (attack_class, disposition, failure, contexts)
        for attack_class, (disposition, failure, contexts) in grouped.items()
    )


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    folded = folded.replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", folded))


def _parse_rows(payload: bytes) -> tuple[dict[str, object], ...]:
    try:
        parsed: tuple[object, ...] = tuple(
            json.loads(line) for line in payload.decode("utf-8").splitlines()
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegistryInvariantError("red-team rows are not canonical JSONL") from error
    if any(not isinstance(row, dict) for row in parsed):
        raise RegistryInvariantError("red-team rows are not canonical JSONL")
    rows = tuple(cast(dict[str, object], row) for row in parsed)
    if canonical_jsonl(rows) != payload:
        raise RegistryInvariantError("red-team rows are not canonical JSONL")
    return rows


def _parse_object(payload: bytes) -> dict[str, object]:
    try:
        parsed: object = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegistryInvariantError("red-team artifact is invalid JSON") from error
    if not isinstance(parsed, dict):
        raise RegistryInvariantError("red-team artifact is not canonical JSON")
    value = cast(dict[str, object], parsed)
    if canonical_json(value) != payload:
        raise RegistryInvariantError("red-team artifact is not canonical JSON")
    return value


__all__ = [
    "RedTeamCandidateBundle",
    "build_red_team_candidate_bundle",
    "verify_red_team_candidate_bundle",
]
