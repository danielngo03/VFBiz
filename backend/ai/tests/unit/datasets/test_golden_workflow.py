import json
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app.modules.datasets.application import to_contract_candidate
from app.modules.datasets.domain import (
    GoldenCase,
    GoldenState,
    GoldenSuite,
    RegistryInvariantError,
    build_smoke_candidates,
    select_releasable_cases,
)

NAMESPACE = UUID("ac83f8b2-7fd4-4cb1-868a-f9b70ad30276")


def test_smoke_pack_is_deterministic_evaluation_only_and_balanced() -> None:
    first = build_smoke_candidates(namespace=NAMESPACE, seed_revision="vivi-golden-v2-smoke-v1")
    second = build_smoke_candidates(namespace=NAMESPACE, seed_revision="vivi-golden-v2-smoke-v1")
    assert first == second
    assert len(first) == 100
    assert len({case.case_id for case in first}) == 100
    assert len({case.split_family_id for case in first}) == 100
    assert {case.allowed_use for case in first} == {"evaluation"}

    schema_path = Path(__file__).resolve().parents[5] / "contracts/ai/evaluation-case.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    contract_cases = tuple(to_contract_candidate(case) for case in first)
    assert len(contract_cases) == 100
    for contract_case in contract_cases:
        assert list(validator.iter_errors(contract_case)) == []


def test_annotation_requires_three_independent_human_roles() -> None:
    candidate = build_smoke_candidates(
        namespace=NAMESPACE, seed_revision="vivi-golden-v2-smoke-v1"
    )[0]
    annotated = candidate.annotate(actor_ref="sme:author", evidence_sha256="a" * 64)
    with pytest.raises(RegistryInvariantError, match="cannot review"):
        annotated.review(actor_ref="sme:author", evidence_sha256="b" * 64)
    reviewed = annotated.review(actor_ref="quality:reviewer", evidence_sha256="b" * 64)
    with pytest.raises(RegistryInvariantError, match="independent"):
        reviewed.adjudicate(actor_ref="quality:reviewer", evidence_sha256="c" * 64)
    adjudicated = reviewed.adjudicate(actor_ref="data-owner:adjudicator", evidence_sha256="c" * 64)
    assert adjudicated.state is GoldenState.ADJUDICATED


def test_release_rejects_unreviewed_or_contaminated_cases() -> None:
    candidates = build_smoke_candidates(
        namespace=NAMESPACE, seed_revision="vivi-golden-v2-smoke-v1"
    )
    with pytest.raises(RegistryInvariantError, match="adjudicated"):
        select_releasable_cases(candidates)

    adjudicated = tuple(
        case.annotate(actor_ref="sme:author", evidence_sha256="a" * 64)
        .review(actor_ref="quality:reviewer", evidence_sha256="b" * 64)
        .adjudicate(actor_ref="data-owner:adjudicator", evidence_sha256="c" * 64)
        for case in candidates[:2]
    )
    duplicate = replace(
        adjudicated[1],
        contamination_fingerprint=adjudicated[0].contamination_fingerprint,
    )
    with pytest.raises(RegistryInvariantError, match="contamination"):
        select_releasable_cases((adjudicated[0], duplicate))
    assert len(select_releasable_cases(adjudicated)) == 2


def test_forged_adjudicated_case_is_rejected() -> None:
    with pytest.raises(RegistryInvariantError, match="author evidence"):
        GoldenCase(
            case_id=NAMESPACE,
            suite=GoldenSuite.FACTUAL_CITATION,
            split_family_id="forged-family",
            contamination_fingerprint="a" * 64,
            state=GoldenState.ADJUDICATED,
        )
