import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app.modules.datasets.application.evaluation.golden_rehearsal import (
    RehearsalBundle,
)
from app.modules.datasets.application.evaluation.golden_rehearsal_v3 import (
    build_rehearsal_bundle_v3,
    verify_rehearsal_bundle_v3,
)
from app.modules.datasets.domain import RegistryInvariantError
from app.modules.datasets.infrastructure.golden_rehearsal_v3_store import (
    LocalGoldenRehearsalV3Store,
)

GENERATOR_DIGEST = "b" * 64


def _validator() -> Draft202012Validator:
    schema_path = Path(__file__).resolve().parents[5] / "contracts/ai/evaluation-case.schema.json"
    return Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8")),
        format_checker=FormatChecker(),
    )


def test_v3_is_schema_valid_and_uses_exact_semantic_families() -> None:
    bundle = build_rehearsal_bundle_v3(generator_source_sha256=GENERATOR_DIGEST)

    assert bundle.manifest["family_count"] == 85
    assert len(bundle.cases) == 100
    validator = _validator()
    for case in bundle.cases:
        assert list(validator.iter_errors(case)) == []

    five_metre_families = {
        case["split_family_id"]
        for case in bundle.cases
        for claim in case["expected"]["required_claims"]
        if claim["text"].endswith(" là 5 mét.")
    }
    one_point_five_families = {
        case["split_family_id"]
        for case in bundle.cases
        for claim in case["expected"]["required_claims"]
        if claim["text"].endswith(" là 1,5 mét.")
    }
    assert five_metre_families == {
        "rehearsal-v3:family:synthetic-cable-length"
    }
    assert one_point_five_families == {
        "rehearsal-v3:family:synthetic-warning-distance"
    }


def test_v3_verifier_rejects_wrong_family_even_after_rehash() -> None:
    bundle = build_rehearsal_bundle_v3(generator_source_sha256=GENERATOR_DIGEST)
    cases = [json.loads(json.dumps(case)) for case in bundle.cases]
    target = next(
        case
        for case in cases
        if any(
            claim["text"].endswith(" là 1,5 mét.")
            for claim in case["expected"]["required_claims"]
        )
    )
    target["split_family_id"] = "rehearsal-v3:family:synthetic-cable-length"
    mutated = _rehash(bundle, cases)
    with pytest.raises(RegistryInvariantError, match="semantic family"):
        verify_rehearsal_bundle_v3(
            manifest_bytes=mutated.manifest_json,
            cases_bytes=mutated.cases_jsonl,
            expected_digest=mutated.bundle_digest,
        )


def test_v3_store_dispatches_semantic_verifier_before_write(tmp_path: Path) -> None:
    bundle = build_rehearsal_bundle_v3(generator_source_sha256=GENERATOR_DIGEST)
    cases = [json.loads(json.dumps(case)) for case in bundle.cases]
    del cases[0]["initial_context"]["evaluation_assertions"]["voice_dimensions"]
    mutated = _rehash(bundle, cases)
    store = LocalGoldenRehearsalV3Store(tmp_path / "v3")

    with pytest.raises(RegistryInvariantError, match="authority mismatch"):
        store.put(mutated)
    assert not (tmp_path / "v3" / mutated.bundle_digest).exists()


def test_v3_store_is_idempotent_and_verifies_persisted_semantics(
    tmp_path: Path,
) -> None:
    bundle = build_rehearsal_bundle_v3(generator_source_sha256=GENERATOR_DIGEST)
    store = LocalGoldenRehearsalV3Store(tmp_path / "v3")

    first = store.put(bundle)
    second = store.put(bundle)

    assert first == second
    assert store.verify(bundle.bundle_digest)["case_count"] == 100


def test_v3_no_evidence_cases_are_fully_specified_before_refusal() -> None:
    bundle = build_rehearsal_bundle_v3(generator_source_sha256=GENERATOR_DIGEST)
    cases = [
        case for case in bundle.cases if case["suite_id"] == "retrieval-no-evidence"
    ]

    for index in (0, 4, 5, 9, 11):
        assert cases[index]["expected"]["outcome"] == "refusal"
        assert cases[index]["expected"]["clarification_slots"] == []
        assert "NO_SOURCE" in cases[index]["conversation"][0]["content"]
    assert bundle.manifest["ambiguity_precedence"] == {
        "missing_lookup_identity": "clarification_required",
        "fully_specified_without_approved_evidence": "refusal",
        "tool_request_missing_required_argument": "clarification_required",
        "fully_specified_authorized_tool_request": "tool_proposal",
    }


def _rehash(bundle: RehearsalBundle, cases: list[dict[str, object]]) -> RehearsalBundle:
    cases_bytes = b"".join(_canonical_json(case) + b"\n" for case in cases)
    manifest = json.loads(bundle.manifest_json)
    manifest["cases_sha256"] = hashlib.sha256(cases_bytes).hexdigest()
    manifest["family_count"] = len({case["split_family_id"] for case in cases})
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_digest"}
    digest = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    manifest["bundle_digest"] = digest
    return RehearsalBundle(
        cases=tuple(cases),
        cases_jsonl=cases_bytes,
        manifest_json=_canonical_json(manifest) + b"\n",
        manifest=manifest,
        bundle_digest=digest,
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
