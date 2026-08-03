from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.modules.datasets.application.curation.synthetic_behavior_candidate import (
    load_qualification_manifest,
)
from app.modules.datasets.application.curation.synthetic_tuning_candidate import (
    digest,
)

_BEHAVIORS = (
    "concise_structure",
    "clarification",
    "refusal_handoff",
    "citation_transparency",
    "state_transparency",
)


def _documents() -> tuple[dict[str, Any], dict[str, Any]]:
    split_layout = {
        "train": (
            ("concise_structure", 4),
            ("clarification", 3),
            ("refusal_handoff", 3),
            ("citation_transparency", 3),
            ("state_transparency", 3),
        ),
        "validation": (
            ("clarification", 1),
            ("refusal_handoff", 1),
            ("citation_transparency", 1),
            ("state_transparency", 1),
        ),
        "test": tuple((behavior, 1) for behavior in _BEHAVIORS),
    }
    families: list[dict[str, object]] = []
    index = 0
    for split, behavior_counts in split_layout.items():
        for behavior, count in behavior_counts:
            for _ in range(count):
                families.append(
                    {
                        "behavior": behavior,
                        "family_id": f"family-{index + 1:02d}",
                        "record_count": 25,
                        "split": split,
                    }
                )
                index += 1
    input_digests = {
        "domain_pack_sha256": "1" * 64,
        "family_lock_sha256": "2" * 64,
        "literal_source_pack_sha256": "3" * 64,
        "policy_sha256": "4" * 64,
        "rubric_sha256": "5" * 64,
        "scenario_lock_sha256": "6" * 64,
        "schema_sha256": "7" * 64,
        "taxonomy_sha256": "8" * 64,
    }
    manifest: dict[str, Any] = {
        "behavior_counts": {behavior: 125 for behavior in sorted(_BEHAVIORS)},
        "behavior_family_counts": {
            "citation_transparency": {"test": 1, "train": 3, "validation": 1},
            "clarification": {"test": 1, "train": 3, "validation": 1},
            "concise_structure": {"test": 1, "train": 4, "validation": 0},
            "refusal_handoff": {"test": 1, "train": 3, "validation": 1},
            "state_transparency": {"test": 1, "train": 3, "validation": 1},
        },
        "candidate_id": "vivi-behavior-synthetic-v5",
        "families": families,
        "family_count": 25,
        "family_split_counts": {"test": 5, "train": 16, "validation": 4},
        "flags": {
            "human_adjudicated": False,
            "provider_dispatch_allowed": False,
            "release_eligible": False,
            "training_eligible": False,
            "upload_allowed": False,
        },
        "input_digests": input_digests,
        "purpose": "behavior-sft-candidate-review-only",
        "record_count": 625,
        "schema_version": 1,
        "split_counts": {"test": 125, "train": 400, "validation": 100},
        "work_item": "VFBIZ-0214",
    }
    authority: dict[str, Any] = {
        "candidate_id": manifest["candidate_id"],
        "input_digests": deepcopy(input_digests),
        "manifest_sha256": digest(manifest),
        "source_digests": {
            "allowed_artifacts_sha256": "9" * 64,
            "composer_source_sha256": "a" * 64,
            "store_source_sha256": "b" * 64,
            "text_quality_source_sha256": "c" * 64,
            "verifier_source_sha256": "d" * 64,
        },
        "work_item": manifest["work_item"],
    }
    return manifest, authority


def _load(
    manifest: dict[str, Any],
    authority: dict[str, Any],
):
    return load_qualification_manifest(
        manifest,
        authority,
        trusted_authority_sha256=digest(authority),
        observed_input_digests=deepcopy(authority["input_digests"]),
        observed_source_digests=deepcopy(authority["source_digests"]),
    )


def test_loads_exact_external_authority_bound_allocation() -> None:
    manifest, authority = _documents()

    result = _load(manifest, authority)

    assert result.candidate_id == "vivi-behavior-synthetic-v5"
    assert len(result.families) == 25
    assert result.manifest_sha256 == digest(manifest)


def test_candidate_cannot_self_resign_external_authority() -> None:
    manifest, authority = _documents()
    trusted_authority_sha256 = digest(authority)
    manifest["candidate_id"] = "candidate-self-issued"
    manifest["work_item"] = "VFBIZ-SELF"
    manifest["input_digests"] = {
        key: "e" * 64 for key in manifest["input_digests"]
    }
    authority["candidate_id"] = manifest["candidate_id"]
    authority["work_item"] = manifest["work_item"]
    authority["input_digests"] = deepcopy(manifest["input_digests"])
    authority["source_digests"] = {
        key: "f" * 64 for key in authority["source_digests"]
    }
    authority["manifest_sha256"] = digest(manifest)

    with pytest.raises(ValueError, match="trusted authority digest mismatch"):
        load_qualification_manifest(
            manifest,
            authority,
            trusted_authority_sha256=trusted_authority_sha256,
            observed_input_digests=authority["input_digests"],
            observed_source_digests=authority["source_digests"],
        )


def test_eligibility_flags_fail_closed() -> None:
    manifest, authority = _documents()
    manifest["flags"]["training_eligible"] = True
    authority["manifest_sha256"] = digest(manifest)

    with pytest.raises(ValueError, match="eligibility must remain false"):
        _load(manifest, authority)


def test_authority_digest_divergence_fails_closed() -> None:
    manifest, authority = _documents()
    authority["input_digests"]["policy_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="authority input digest mismatch"):
        _load(manifest, authority)


def test_family_split_allocation_cannot_be_relabelled() -> None:
    manifest, authority = _documents()
    manifest["families"][0]["split"] = "test"
    authority["manifest_sha256"] = digest(manifest)

    with pytest.raises(ValueError, match="record split allocation mismatch"):
        _load(manifest, authority)


def test_unknown_candidate_fields_fail_closed() -> None:
    manifest, authority = _documents()
    manifest["authority_override"] = authority
    authority["manifest_sha256"] = digest(manifest)

    with pytest.raises(ValueError, match="manifest fields mismatch"):
        _load(manifest, authority)


def test_observed_artifact_digest_divergence_fails_closed() -> None:
    manifest, authority = _documents()
    observed_sources = deepcopy(authority["source_digests"])
    observed_sources["text_quality_source_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="observed source digest mismatch"):
        load_qualification_manifest(
            manifest,
            authority,
            trusted_authority_sha256=digest(authority),
            observed_input_digests=authority["input_digests"],
            observed_source_digests=observed_sources,
        )


def test_loaded_digest_map_is_immutable() -> None:
    manifest, authority = _documents()
    result = _load(manifest, authority)

    with pytest.raises(TypeError):
        result.input_digests["policy_sha256"] = "0" * 64  # type: ignore[index]


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("schema_version",), True),
        (("families", 0, "record_count"), True),
        (("behavior_family_counts", "clarification", "test"), True),
    ),
)
def test_boolean_counts_are_not_integers(
    path: tuple[str | int, ...],
    value: bool,
) -> None:
    manifest, authority = _documents()
    target: Any = manifest
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    authority["manifest_sha256"] = digest(manifest)

    with pytest.raises(ValueError, match="integer|count"):
        _load(manifest, authority)
