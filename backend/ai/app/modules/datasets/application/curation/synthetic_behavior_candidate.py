"""Fail-closed qualification manifest loader for synthetic behavior candidates.

Candidate data is versioned in governed manifests.  Runtime code remains
version-neutral and accepts a candidate only when an external authority pins
the exact canonical manifest digest and every governed input digest.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from app.modules.datasets.application.curation.synthetic_tuning_candidate import (
    digest,
)

_SHA256_KEYS = frozenset(
    {
        "domain_pack_sha256",
        "family_lock_sha256",
        "literal_source_pack_sha256",
        "policy_sha256",
        "rubric_sha256",
        "scenario_lock_sha256",
        "schema_sha256",
        "taxonomy_sha256",
    }
)
_AUTHORITY_SOURCE_KEYS = frozenset(
    {
        "allowed_artifacts_sha256",
        "composer_source_sha256",
        "store_source_sha256",
        "text_quality_source_sha256",
        "verifier_source_sha256",
    }
)
_FALSE_FLAGS = frozenset(
    {
        "human_adjudicated",
        "provider_dispatch_allowed",
        "release_eligible",
        "training_eligible",
        "upload_allowed",
    }
)
_BEHAVIORS = frozenset(
    {
        "citation_transparency",
        "clarification",
        "concise_structure",
        "refusal_handoff",
        "state_transparency",
    }
)
_SPLITS = frozenset({"train", "validation", "test"})
_MANIFEST_KEYS = frozenset(
    {
        "behavior_counts",
        "behavior_family_counts",
        "candidate_id",
        "families",
        "family_count",
        "family_split_counts",
        "flags",
        "input_digests",
        "purpose",
        "record_count",
        "schema_version",
        "split_counts",
        "work_item",
    }
)
_AUTHORITY_KEYS = frozenset(
    {
        "candidate_id",
        "input_digests",
        "manifest_sha256",
        "source_digests",
        "work_item",
    }
)
_FAMILY_KEYS = frozenset({"behavior", "family_id", "record_count", "split"})


@dataclass(frozen=True, slots=True)
class FamilyAllocation:
    family_id: str
    behavior: str
    split: str
    record_count: int


@dataclass(frozen=True, slots=True)
class QualificationManifest:
    candidate_id: str
    work_item: str
    families: tuple[FamilyAllocation, ...]
    manifest_sha256: str
    input_digests: Mapping[str, str]


def load_qualification_manifest(
    manifest_document: Mapping[str, Any],
    authority_document: Mapping[str, Any],
    *,
    trusted_authority_sha256: str,
    observed_input_digests: Mapping[str, Any],
    observed_source_digests: Mapping[str, Any],
) -> QualificationManifest:
    """Load one exact candidate contract or raise without partial acceptance."""

    _require_exact_keys(manifest_document, _MANIFEST_KEYS, "manifest")
    _require_exact_keys(authority_document, _AUTHORITY_KEYS, "authority")

    manifest_digest = digest(manifest_document)
    authority_digest = digest(authority_document)
    if (
        not _is_sha256(trusted_authority_sha256)
        or authority_digest != trusted_authority_sha256
    ):
        raise ValueError("trusted authority digest mismatch")
    candidate_id = _required_text(manifest_document, "candidate_id")
    work_item = _required_text(manifest_document, "work_item")
    _require_exact_integer(manifest_document, "schema_version", 1)
    if manifest_document.get("purpose") != "behavior-sft-candidate-review-only":
        raise ValueError("qualification purpose is not allowed")
    if authority_document.get("candidate_id") != candidate_id:
        raise ValueError("authority candidate mismatch")
    if authority_document.get("work_item") != work_item:
        raise ValueError("authority work item mismatch")
    if authority_document.get("manifest_sha256") != manifest_digest:
        raise ValueError("authority manifest digest mismatch")

    input_digests = _digest_map(
        manifest_document.get("input_digests"),
        expected_keys=_SHA256_KEYS,
        label="manifest input digests",
    )
    authority_input_digests = _digest_map(
        authority_document.get("input_digests"),
        expected_keys=_SHA256_KEYS,
        label="authority input digests",
    )
    if input_digests != authority_input_digests:
        raise ValueError("authority input digest mismatch")
    observed_inputs = _digest_map(
        observed_input_digests,
        expected_keys=_SHA256_KEYS,
        label="observed input digests",
    )
    if observed_inputs != input_digests:
        raise ValueError("observed input digest mismatch")
    authority_source_digests = _digest_map(
        authority_document.get("source_digests"),
        expected_keys=_AUTHORITY_SOURCE_KEYS,
        label="authority source digests",
    )
    observed_sources = _digest_map(
        observed_source_digests,
        expected_keys=_AUTHORITY_SOURCE_KEYS,
        label="observed source digests",
    )
    if observed_sources != authority_source_digests:
        raise ValueError("observed source digest mismatch")
    _require_false_flags(manifest_document.get("flags"))

    families = _load_families(manifest_document.get("families"))
    _verify_allocation(manifest_document, families)
    return QualificationManifest(
        candidate_id=candidate_id,
        work_item=work_item,
        families=families,
        manifest_sha256=manifest_digest,
        input_digests=MappingProxyType(input_digests),
    )


def _load_families(value: object) -> tuple[FamilyAllocation, ...]:
    if not isinstance(value, list):
        raise ValueError("families must be a list")
    families: list[FamilyAllocation] = []
    seen: set[str] = set()
    for raw_family in cast(list[object], value):
        if not isinstance(raw_family, dict):
            raise ValueError("family must be an object")
        family = cast(dict[str, Any], raw_family)
        _require_exact_keys(family, _FAMILY_KEYS, "family")
        family_id = _required_text(family, "family_id")
        behavior = _required_text(family, "behavior")
        split = _required_text(family, "split")
        record_count = family.get("record_count")
        if family_id in seen:
            raise ValueError("family id is duplicated")
        if behavior not in _BEHAVIORS:
            raise ValueError("family behavior is unsupported")
        if split not in _SPLITS:
            raise ValueError("family split is unsupported")
        if type(record_count) is not int or record_count != 25:
            raise ValueError("family record count must be the integer 25")
        seen.add(family_id)
        families.append(
            FamilyAllocation(
                family_id=family_id,
                behavior=behavior,
                split=split,
                record_count=record_count,
            )
        )
    return tuple(families)


def _verify_allocation(
    manifest: Mapping[str, Any],
    families: Sequence[FamilyAllocation],
) -> None:
    _require_exact_integer(manifest, "record_count", 625)
    _require_exact_integer(manifest, "family_count", 25)
    split_counts = Counter[str]()
    family_split_counts = Counter[str]()
    behavior_counts = Counter[str]()
    behavior_family_counts = Counter[tuple[str, str]]()
    for family in families:
        split_counts[family.split] += family.record_count
        family_split_counts[family.split] += 1
        behavior_counts[family.behavior] += family.record_count
        behavior_family_counts[(family.behavior, family.split)] += 1
    expected_split_counts = {"test": 125, "train": 400, "validation": 100}
    expected_family_splits = {"test": 5, "train": 16, "validation": 4}
    expected_behaviors = {behavior: 125 for behavior in sorted(_BEHAVIORS)}
    expected_behavior_families = {
        "citation_transparency": {"test": 1, "train": 3, "validation": 1},
        "clarification": {"test": 1, "train": 3, "validation": 1},
        "concise_structure": {"test": 1, "train": 4, "validation": 0},
        "refusal_handoff": {"test": 1, "train": 3, "validation": 1},
        "state_transparency": {"test": 1, "train": 3, "validation": 1},
    }
    observed_behavior_families = {
        behavior: {
            split: behavior_family_counts[(behavior, split)]
            for split in sorted(_SPLITS)
        }
        for behavior in sorted(_BEHAVIORS)
    }
    if dict(split_counts) != expected_split_counts:
        raise ValueError("record split allocation mismatch")
    if dict(family_split_counts) != expected_family_splits:
        raise ValueError("family split allocation mismatch")
    if dict(behavior_counts) != expected_behaviors:
        raise ValueError("behavior allocation mismatch")
    if observed_behavior_families != expected_behavior_families:
        raise ValueError("behavior family allocation mismatch")
    _require_exact_count_map(
        manifest.get("split_counts"),
        expected_split_counts,
        "declared record split counts",
    )
    _require_exact_count_map(
        manifest.get("family_split_counts"),
        expected_family_splits,
        "declared family split counts",
    )
    _require_exact_count_map(
        manifest.get("behavior_counts"),
        expected_behaviors,
        "declared behavior counts",
    )
    _require_exact_nested_count_map(
        manifest.get("behavior_family_counts"),
        expected_behavior_families,
        "declared behavior family counts",
    )


def _require_false_flags(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("qualification flags must be an object")
    flags = cast(dict[str, Any], value)
    _require_exact_keys(flags, _FALSE_FLAGS, "qualification flags")
    if any(flags[key] is not False for key in _FALSE_FLAGS):
        raise ValueError("qualification eligibility must remain false")


def _digest_map(
    value: object,
    *,
    expected_keys: frozenset[str],
    label: str,
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    digests = cast(dict[str, Any], value)
    _require_exact_keys(digests, expected_keys, label)
    if any(
        not isinstance(digests[key], str)
        or len(digests[key]) != 64
        or any(character not in "0123456789abcdef" for character in digests[key])
        for key in expected_keys
    ):
        raise ValueError(f"{label} contains an invalid digest")
    return {key: cast(str, digests[key]) for key in sorted(expected_keys)}


def _required_text(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty")
    return value


def _require_exact_integer(
    document: Mapping[str, Any],
    key: str,
    expected: int,
) -> None:
    value = document.get(key)
    if type(value) is not int or value != expected:
        raise ValueError(f"{key} must be the integer {expected}")


def _require_exact_count_map(
    value: object,
    expected: Mapping[str, int],
    label: str,
) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    counts = cast(dict[str, Any], value)
    if frozenset(counts) != frozenset(expected):
        raise ValueError(f"{label} fields mismatch")
    if any(
        type(counts[key]) is not int or counts[key] != expected[key]
        for key in expected
    ):
        raise ValueError(f"{label} mismatch")


def _require_exact_nested_count_map(
    value: object,
    expected: Mapping[str, Mapping[str, int]],
    label: str,
) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    counts = cast(dict[str, Any], value)
    if frozenset(counts) != frozenset(expected):
        raise ValueError(f"{label} fields mismatch")
    for key, expected_counts in expected.items():
        _require_exact_count_map(counts[key], expected_counts, f"{label}:{key}")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_exact_keys(
    document: Mapping[str, Any],
    expected: frozenset[str],
    label: str,
) -> None:
    if frozenset(document) != expected:
        raise ValueError(f"{label} fields mismatch")
