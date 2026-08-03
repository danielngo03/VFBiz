import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app.modules.datasets.application.evaluation.golden_rehearsal import (
    REHEARSAL_RUBRIC_REVISION,
    build_rehearsal_bundle,
    verify_rehearsal_bundle,
)
from app.modules.datasets.domain import RegistryInvariantError


def _validator() -> Draft202012Validator:
    schema_path = Path(__file__).resolve().parents[5] / "contracts/ai/evaluation-case.schema.json"
    return Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8")),
        format_checker=FormatChecker(),
    )


def test_rehearsal_is_deterministic_schema_valid_and_never_golden() -> None:
    first = build_rehearsal_bundle()
    second = build_rehearsal_bundle()

    assert first == second
    assert len(first.cases) == 100
    assert first.manifest["case_count"] == 100
    assert first.manifest["golden"] is False
    assert first.manifest["human_adjudicated"] is False
    assert first.manifest["training_eligible"] is False
    assert first.manifest["release_eligible"] is False
    assert first.manifest["public_serving_eligible"] is False
    assert first.manifest["provider_calls"] == 0

    validator = _validator()
    for case in first.cases:
        assert list(validator.iter_errors(case)) == []
        assert case["allowed_use"] == "evaluation"
        assert case["review"] == {
            "status": "pending",
            "human_label": None,
            "reviewer_role": None,
            "adjudication_evidence": [],
        }
        assert case["rubric_revision"] == REHEARSAL_RUBRIC_REVISION
        assert case["lineage"]["source_refs"] == []


def test_rehearsal_covers_expected_suites_risks_locales_and_outcomes() -> None:
    bundle = build_rehearsal_bundle()

    assert bundle.manifest["suite_counts"] == {
        "factual-citation": 25,
        "handoff": 3,
        "intent-ood-clarification": 12,
        "multi-turn-context": 12,
        "retrieval-no-evidence": 15,
        "safety-legal-privacy": 12,
        "state-resilience": 8,
        "tool-authorization": 10,
        "vietnamese-robustness": 3,
    }
    assert {case["locale"] for case in bundle.cases} >= {
        "vi-VN",
        "vi-Latn-no-diacritics",
        "mixed",
    }
    assert {case["risk_domain"] for case in bundle.cases} >= {
        "general",
        "pricing",
        "safety",
        "legal",
        "privacy",
        "authorization",
        "prompt-injection",
        "resilience",
    }
    assert {case["expected"]["outcome"] for case in bundle.cases} >= {
        "answer",
        "clarification_required",
        "refusal",
        "handoff_recommended",
        "tool_proposal",
        "cancelled",
        "failed_safely",
    }


def test_factual_cases_are_synthetic_cited_and_nonfactual_cases_do_not_claim() -> None:
    cases = build_rehearsal_bundle().cases

    for case in cases:
        expected = case["expected"]
        if expected["outcome"] == "answer":
            assert case["knowledge_snapshot"] is not None
            assert expected["required_claims"]
            assert all(
                claim["text"].startswith("Trong namespace SYNTHETIC_VF_REHEARSAL,")
                for claim in expected["required_claims"]
            )
            assert {
                "citation-membership",
                "revision-coherence",
                "claim-grounding",
            }.issubset(case["hard_gates"])
        else:
            assert expected["required_claims"] == []
            assert case["knowledge_snapshot"] is None


def test_tool_cases_propose_only_and_never_claim_execution() -> None:
    cases = [
        case
        for case in build_rehearsal_bundle().cases
        if case["suite_id"] == "tool-authorization"
    ]

    assert len(cases) == 10
    assert {case["expected"]["tool"]["authorization_decision"] for case in cases} == {
        "allow",
        "deny",
    }
    for case in cases:
        assert case["initial_context"]["execution_authority"] == "proposal-only"
        assert case["expected"]["state_assertions"]["required_delta"] == {}
        assert "tool-authorization" in case["hard_gates"]


def test_bundle_bytes_are_tamper_evident() -> None:
    bundle = build_rehearsal_bundle()

    verified = verify_rehearsal_bundle(
        manifest_bytes=bundle.manifest_json,
        cases_bytes=bundle.cases_jsonl,
        expected_digest=bundle.bundle_digest,
    )
    assert verified["case_count"] == 100

    with pytest.raises(RegistryInvariantError, match="digest mismatch"):
        verify_rehearsal_bundle(
            manifest_bytes=bundle.manifest_json,
            cases_bytes=bundle.cases_jsonl + b"{}\n",
            expected_digest=bundle.bundle_digest,
        )
