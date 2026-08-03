import hashlib
import json
from collections import defaultdict
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app.modules.datasets.application.evaluation.golden_rehearsal_v2 import (
    REHEARSAL_V2_GENERATOR_REVISION,
    build_rehearsal_bundle_v2,
    verify_rehearsal_bundle_v2,
)
from app.modules.datasets.domain import RegistryInvariantError

GENERATOR_DIGEST = "a" * 64


def _validator() -> Draft202012Validator:
    schema_path = Path(__file__).resolve().parents[5] / "contracts/ai/evaluation-case.schema.json"
    return Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8")),
        format_checker=FormatChecker(),
    )


def test_v2_is_deterministic_schema_valid_and_authority_bound() -> None:
    first = build_rehearsal_bundle_v2(generator_source_sha256=GENERATOR_DIGEST)
    second = build_rehearsal_bundle_v2(generator_source_sha256=GENERATOR_DIGEST)

    assert first == second
    assert len(first.cases) == 100
    assert first.manifest["generator_source_sha256"] == GENERATOR_DIGEST
    assert set(first.manifest["authority_bindings"]) == {
        "suite_candidate",
        "voice_rubric",
        "voice_domain_pack",
        "voice_board_policy",
    }
    assert all(
        binding["file_sha256"] and binding["semantic_digest"]
        for binding in first.manifest["authority_bindings"].values()
    )
    assert first.manifest["governance"]["human_approval_evidence"] == []
    assert first.manifest["governance"]["independent_review_evidence"] == []

    validator = _validator()
    for case in first.cases:
        assert list(validator.iter_errors(case)) == []


def test_v2_groups_semantic_variants_in_shared_families() -> None:
    cases = build_rehearsal_bundle_v2(generator_source_sha256=GENERATOR_DIGEST).cases
    families_by_value: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        for claim in case["expected"]["required_claims"]:
            for marker in (
                "42 phút",
                "25 phần trăm",
                "12 phút",
                "5 mét",
                "15 phút",
                "30 ngày",
                "2 ngôn ngữ",
                "320 ki-lô-gam",
                "1,5 mét",
                "20 phút",
                "10 phút",
                "16 trang",
            ):
                if marker in claim["text"]:
                    families_by_value[marker].add(case["split_family_id"])

    assert len(families_by_value) == 12
    assert all(len(families) == 1 for families in families_by_value.values())
    assert len({case["split_family_id"] for case in cases}) < len(cases)


def test_v2_clarification_tool_and_state_precedence_is_explicit() -> None:
    cases = build_rehearsal_bundle_v2(generator_source_sha256=GENERATOR_DIGEST).cases
    no_evidence = [case for case in cases if case["suite_id"] == "retrieval-no-evidence"]
    tool_cases = [case for case in cases if case["suite_id"] == "tool-authorization"]
    state_cases = [case for case in cases if case["suite_id"] == "state-resilience"]

    assert no_evidence[0]["expected"]["outcome"] == "clarification_required"
    assert no_evidence[9]["expected"]["clarification_slots"] == [
        "vehicle_model",
        "vehicle_variant",
    ]
    assert no_evidence[11]["expected"]["clarification_slots"] == [
        "part_name",
        "vehicle_model",
    ]
    for case in tool_cases:
        tool = case["expected"]["tool"]
        if tool["authorization_decision"] == "allow":
            assert tool["arguments"]
            assert case["expected"]["outcome"] == "tool_proposal"
    for case in state_cases:
        delta = case["expected"]["state_assertions"]["required_delta"]
        assert delta["task.status"] in {
            "cancelled",
            "failed_safely",
            "reconciliation_required",
        }
        assert delta["task.reason_code"]


def test_v2_verifier_rejects_self_consistent_semantic_substitution() -> None:
    bundle = build_rehearsal_bundle_v2(generator_source_sha256=GENERATOR_DIGEST)
    cases = [json.loads(json.dumps(case)) for case in bundle.cases]
    cases[0]["allowed_use"] = "training"
    cases[0]["review"]["status"] = "adjudicated"
    cases[0]["lineage"]["source_refs"] = ["unauthorized:source"]
    cases_bytes = b"".join(_canonical_json(case) + b"\n" for case in cases)
    manifest = json.loads(bundle.manifest_json)
    manifest["cases_sha256"] = hashlib.sha256(cases_bytes).hexdigest()
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_digest"}
    substituted_digest = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    manifest["bundle_digest"] = substituted_digest

    with pytest.raises(RegistryInvariantError, match="evaluation-only"):
        verify_rehearsal_bundle_v2(
            manifest_bytes=_canonical_json(manifest) + b"\n",
            cases_bytes=cases_bytes,
            expected_digest=substituted_digest,
        )


def test_v2_verifier_requires_trusted_expected_digest() -> None:
    bundle = build_rehearsal_bundle_v2(generator_source_sha256=GENERATOR_DIGEST)
    with pytest.raises(RegistryInvariantError, match="SHA-256"):
        verify_rehearsal_bundle_v2(
            manifest_bytes=bundle.manifest_json,
            cases_bytes=bundle.cases_jsonl,
            expected_digest="",
        )


def test_v2_remains_pending_evaluation_only_and_voice_asserted() -> None:
    bundle = build_rehearsal_bundle_v2(generator_source_sha256=GENERATOR_DIGEST)

    assert bundle.manifest["golden"] is False
    assert bundle.manifest["human_adjudicated"] is False
    assert bundle.manifest["training_eligible"] is False
    assert bundle.manifest["release_eligible"] is False
    assert bundle.manifest["public_serving_eligible"] is False
    for case in bundle.cases:
        assert case["allowed_use"] == "evaluation"
        assert case["review"]["status"] == "pending"
        assert case["lineage"] == {
            "seed_refs": [f"synthetic:{REHEARSAL_V2_GENERATOR_REVISION}"],
            "source_refs": [],
        }
        assert len(case["initial_context"]["evaluation_assertions"]["voice_dimensions"]) == 5


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
