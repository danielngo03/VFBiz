import base64
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any, Protocol, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app.modules.datasets.application.evaluation.golden_candidate import (
    EXPECTED_DISTRIBUTION,
    GoldenCandidateBundle,
    build_golden_candidate_bundle,
    build_golden_candidate_fingerprint_report,
    verify_golden_candidate_bundle,
)
from app.modules.datasets.domain import RegistryInvariantError
from app.modules.datasets.infrastructure.golden_candidate_store import (
    write_golden_candidate_bundle,
)

ROOT = Path(__file__).resolve().parents[5]
TAXONOMY_PATH = (
    ROOT / "backend/ai/dataset-specs/evaluation/taxonomies/customer-assistant-golden-v1.json"
)
SCHEMA_PATH = ROOT / "contracts/ai/evaluation-case.schema.json"
GENERATOR_SOURCE_BYTES = b"synthetic unit-test generator source"
GENERATOR_DIGEST = hashlib.sha256(GENERATOR_SOURCE_BYTES).hexdigest()
AUTHORITY_PATHS = {
    "suite": ROOT
    / "backend/ai/dataset-specs/evaluation/suites/customer-assistant-golden-v1-candidate.json",
    "golden_rubric": ROOT
    / "backend/ai/dataset-specs/evaluation/rubrics/customer-assistant-golden-v1.json",
    "voice_rubric": ROOT / "backend/ai/dataset-specs/evaluation/rubrics/vivi-text-voice-v1.json",
    "voice_domain_pack": ROOT
    / "backend/ai/dataset-specs/evaluation/voice/vivi-text-domain-pack-v1.json",
    "voice_board_policy": ROOT
    / "backend/ai/dataset-specs/evaluation/voice/vivi-text-board-policy-v1.json",
    "voice_calibration_plan": ROOT
    / "backend/ai/dataset-specs/evaluation/voice/vivi-text-calibration-plan-v1.json",
    "voice_heldout_plan": ROOT
    / "backend/ai/dataset-specs/evaluation/voice/vivi-text-heldout-plan-v1.json",
}


class _SchemaValidator(Protocol):
    def validate(self, instance: object) -> None: ...


def _build() -> GoldenCandidateBundle:
    return build_golden_candidate_bundle(
        taxonomy_bytes=TAXONOMY_PATH.read_bytes(),
        authority_documents={key: path.read_bytes() for key, path in AUTHORITY_PATHS.items()},
        generator_source_bytes=GENERATOR_SOURCE_BYTES,
    )


def _authority_digests() -> dict[str, str]:
    return {
        key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in AUTHORITY_PATHS.items()
    }


def test_candidate_is_deterministic_schema_valid_and_exactly_distributed() -> None:
    first = _build()
    second = _build()

    assert first == second
    assert len(first.cases) == 1000
    assert first.manifest["suite_counts"] == EXPECTED_DISTRIBUTION
    assert first.manifest["family_count"] == 100
    assert (
        first.manifest["taxonomy_sha256"] == hashlib.sha256(TAXONOMY_PATH.read_bytes()).hexdigest()
    )
    validator = cast(
        _SchemaValidator,
        Draft202012Validator(
            json.loads(SCHEMA_PATH.read_text(encoding="utf-8")),
            format_checker=FormatChecker(),
        ),
    )
    for case in first.cases:
        validator.validate(case)


def test_candidate_is_fact_free_pending_and_permanently_training_excluded() -> None:
    bundle = _build()

    assert bundle.manifest["human_adjudicated"] is False
    assert bundle.manifest["training_eligible"] is False
    assert bundle.manifest["upload_allowed"] is False
    assert bundle.manifest["release_eligible"] is False
    assert bundle.manifest["approval_evidence"] == []
    assert all(case["expected"]["outcome"] != "answer" for case in bundle.cases)
    assert all(case["expected"]["required_claims"] == [] for case in bundle.cases)
    assert all(case["knowledge_snapshot"] is None for case in bundle.cases)
    assert all(case["review"]["status"] == "pending" for case in bundle.cases)
    assert all(
        case["initial_context"]["candidate_controls"]
        == {
            "human_adjudicated": False,
            "training_eligible": False,
            "upload_allowed": False,
            "release_eligible": False,
        }
        for case in bundle.cases
    )


def test_candidate_rows_do_not_share_mutable_review_or_voice_state() -> None:
    bundle = _build()
    first = bundle.cases[0]
    second = bundle.cases[1]

    first["review"]["adjudication_evidence"].append("invalid-local-mutation")
    first["initial_context"]["evaluation_assertions"]["voice_dimensions"].append(
        "invalid-local-mutation"
    )

    assert second["review"]["adjudication_evidence"] == []
    assert (
        "invalid-local-mutation"
        not in second["initial_context"]["evaluation_assertions"]["voice_dimensions"]
    )


def test_family_lock_and_fingerprint_report_cover_every_case_without_overlap_claim() -> None:
    bundle = _build()
    family_lock = json.loads(bundle.family_lock_json)
    report = json.loads(bundle.fingerprint_report_json)

    assert len(family_lock["families"]) == 100
    assert {item["variant_count"] for item in family_lock["families"]} == {10}
    assert family_lock["split"] == "held-out-candidate"
    assert report["record_count"] == 1000
    assert report["unique_fingerprint_count"] == 1000
    assert report["unique_input_fingerprint_count"] == 1000
    assert report["exact_input_duplicate_count"] == 0
    assert report["conflicting_outcome_input_count"] == 0
    assert report["declared_training_corpus_fingerprints"] == []
    assert report["declared_training_overlap_count"] == 0
    assert report["global_registry_verification_status"] == ("pending-independent-verification")
    assert report["semantic_overlap_verification_status"] == "token-jaccard-complete"
    diversity = report["diversity"]
    assert diversity["max_normalized_five_token_prefix_share"] <= 0.02
    assert diversity["prefix_threshold_passed"] is True
    assert diversity["max_template_pattern_share"] == 0.001
    assert diversity["max_template_pattern_share_threshold"] == 0.02
    assert diversity["template_concentration_passed"] is True
    assert diversity["template_concentration_status"] == "deterministic-gate-passed"
    assert diversity["cross_family_token_jaccard_threshold"] == 0.85
    assert diversity["cross_family_near_duplicate_count"] == 0
    assert diversity["cross_family_near_duplicate_gate_passed"] is True
    assert diversity["cross_family_near_duplicate_examples"] == []


def test_candidate_suites_exercise_behavioral_inputs_and_typed_state() -> None:
    cases = _build().cases
    voice = [case for case in cases if case["suite_id"] == "vietnamese-register-vivi-recovery"]
    routing = [case for case in cases if case["suite_id"] == "routing-retrieval-typo-no-diacritics"]
    resilience = [
        case for case in cases if case["suite_id"] == "cancellation-replay-staleness-resilience"
    ]
    ambiguity = [case for case in cases if case["suite_id"] == "ambiguity-clarification-multi-turn"]
    security = [
        case for case in cases if case["suite_id"] == "pii-acl-tool-authorization-prompt-injection"
    ]
    tool_allow = [
        case
        for case in security
        if case["expected"]["tool"]
        and case["expected"]["tool"]["authorization_decision"] == "allow"
    ]
    tool_denied = [
        case
        for case in security
        if case["expected"]["tool"] and case["expected"]["tool"]["authorization_decision"] == "deny"
    ]

    assert len(voice) == 160
    assert {case["expected"]["outcome"] for case in voice} == {
        "clarification_required",
        "handoff_recommended",
        "refusal",
    }
    assert all(
        "khách hàng" not in turn["content"].casefold()
        for case in voice
        for turn in case["conversation"]
        if turn["role"] == "user"
    )
    assert len(routing) == 100
    assert all(
        turn["content"].isascii()
        for case in routing
        for turn in case["conversation"]
        if turn["role"] == "user"
    )
    assert {case["expected"]["outcome"] for case in routing} == {
        "clarification_required",
        "refusal",
        "handoff_recommended",
        "tool_proposal",
    }
    assert {case["initial_context"]["routing_expectation"]["decision"] for case in routing} == {
        "clarification",
        "retrieval-refusal",
        "safety-handoff",
        "proposal",
        "human-handoff",
    }
    assert len({case["initial_context"]["routing_expectation"]["intent"] for case in routing}) == 10
    assert all(
        phrase not in turn["content"].casefold()
        for case in routing
        for turn in case["conversation"]
        for phrase in ("hoi lai", "dung tu doan", "hay lam ro", "xac nhan tuyen")
    )
    assert len(resilience) == 120
    assert len({case["initial_context"]["runtime_state"]["kind"] for case in resilience}) == 12
    assert (
        len(
            {
                json.dumps(case["expected"]["state_assertions"]["required_delta"], sort_keys=True)
                for case in resilience
            }
        )
        == 12
    )
    assert (
        len({case["expected"]["state_assertions"]["forbidden_paths"][-1] for case in resilience})
        == 12
    )
    assert len(tool_allow) == 30
    assert all(
        case["initial_context"]["verified_identity"]["object_relations"] == ["self"]
        and case["initial_context"]["execution_authority"] == "proposal-only"
        and case["initial_context"]["authorization_request"]["required_capability"]
        in case["initial_context"]["verified_identity"]["capabilities"]
        and case["expected"]["tool"]["typed_error"] is None
        and case["expected"]["state_assertions"]["required_delta"]
        == {"proposal_status": "pending_confirmation", "side_effect_committed": False}
        for case in tool_allow
    )
    assert len(tool_denied) == 40
    assert {case["expected"]["tool"]["typed_error"] for case in tool_denied} == {
        "capability_missing",
        "realm_not_allowed",
        "object_relation_mismatch",
    }
    assert all(
        case["initial_context"]["verified_identity"]["subject"].startswith("synthetic-customer-")
        and case["initial_context"]["authorization_request"]["decision"] == "deny"
        and case["expected"]["state_assertions"]["required_delta"]["proposal_status"] == "rejected"
        and case["expected"]["state_assertions"]["required_delta"]["side_effect_committed"] is False
        for case in tool_denied
    )
    assert all(
        case["expected"]["reason_code"] == "missing_context_requires_clarification"
        and len(case["conversation"]) == 3
        and case["expected"]["clarification_slots"]
        for case in ambiguity
    )
    assert len({tuple(case["expected"]["clarification_slots"]) for case in ambiguity}) == 16


def test_token_jaccard_report_detects_cross_family_near_duplicate() -> None:
    bundle = _build()
    cases = [json.loads(json.dumps(case)) for case in bundle.cases]
    cases[10]["conversation"] = json.loads(json.dumps(cases[0]["conversation"]))
    cases[10]["conversation"][0]["content"] += " riêng"

    report = build_golden_candidate_fingerprint_report(tuple(cases))

    assert report["diversity"]["cross_family_near_duplicate_count"] >= 1
    assert report["diversity"]["cross_family_near_duplicate_gate_passed"] is False
    with pytest.raises(RegistryInvariantError, match="diversity policy"):
        verify_golden_candidate_bundle(
            bundle=_resign(bundle, cases=cases),
            expected_taxonomy_sha256=bundle.manifest["taxonomy_sha256"],
            expected_authority_sha256=_authority_digests(),
            expected_generator_source_sha256=GENERATOR_DIGEST,
        )


def test_authority_snapshot_contains_exact_reproducible_inputs() -> None:
    bundle = _build()
    snapshot = json.loads(bundle.authority_snapshot_json)
    expected = {"taxonomy": TAXONOMY_PATH.read_bytes()} | {
        key: path.read_bytes() for key, path in AUTHORITY_PATHS.items()
    }

    assert bundle.generator_source_bytes == GENERATOR_SOURCE_BYTES
    for key, payload in expected.items():
        entry = snapshot["documents"][key]
        assert base64.b64decode(entry["content_base64"], validate=True) == payload
        assert entry["sha256"] == hashlib.sha256(payload).hexdigest()
    assert bundle.manifest["rubric_revision"] == "customer-assistant-golden-v1"
    assert bundle.manifest["authority_digests"] == _authority_digests()


def test_verifier_rejects_fully_resigned_semantic_authority_mutations() -> None:
    bundle = _build()
    mutations: list[GoldenCandidateBundle] = []

    label_cases = [json.loads(json.dumps(case)) for case in bundle.cases]
    label_cases[0]["expected"]["outcome"] = "clarification_required"
    label_cases[0]["expected"]["reason_code"] = "attacker_relabel"
    mutations.append(_resign(bundle, cases=label_cases))

    rubric_cases = [json.loads(json.dumps(case)) for case in bundle.cases]
    rubric_cases[0]["rubric_revision"] = "attacker-rubric"
    mutations.append(_resign(bundle, cases=rubric_cases))

    provenance_cases = [json.loads(json.dumps(case)) for case in bundle.cases]
    provenance_cases[0]["initial_context"]["candidate_provenance"]["authority_set_sha256"] = (
        "a" * 64
    )
    mutations.append(_resign(bundle, cases=provenance_cases))

    for mutated in mutations:
        with pytest.raises(RegistryInvariantError, match="semantic projection"):
            verify_golden_candidate_bundle(
                bundle=mutated,
                expected_taxonomy_sha256=bundle.manifest["taxonomy_sha256"],
                expected_authority_sha256=_authority_digests(),
                expected_generator_source_sha256=GENERATOR_DIGEST,
            )


def test_verifier_rejects_resigned_family_and_authority_snapshot_tamper() -> None:
    bundle = _build()
    family_lock = json.loads(bundle.family_lock_json)
    family_lock["families"][0]["suite_id"] = "attacker-suite"
    with pytest.raises(RegistryInvariantError, match="family lock authority"):
        verify_golden_candidate_bundle(
            bundle=_resign(bundle, family_lock=family_lock),
            expected_taxonomy_sha256=bundle.manifest["taxonomy_sha256"],
            expected_authority_sha256=_authority_digests(),
            expected_generator_source_sha256=GENERATOR_DIGEST,
        )

    snapshot = json.loads(bundle.authority_snapshot_json)
    snapshot["documents"]["voice_rubric"]["content_base64"] = base64.b64encode(b"{}").decode(
        "ascii"
    )
    with pytest.raises(RegistryInvariantError, match="authority snapshot digest"):
        verify_golden_candidate_bundle(
            bundle=_resign(bundle, authority_snapshot=snapshot),
            expected_taxonomy_sha256=bundle.manifest["taxonomy_sha256"],
            expected_authority_sha256=_authority_digests(),
            expected_generator_source_sha256=GENERATOR_DIGEST,
        )

    with pytest.raises(RegistryInvariantError, match="external authority"):
        verify_golden_candidate_bundle(
            bundle=_resign(bundle, generator_source_bytes=b"attacker source"),
            expected_taxonomy_sha256=bundle.manifest["taxonomy_sha256"],
            expected_authority_sha256=_authority_digests(),
            expected_generator_source_sha256=GENERATOR_DIGEST,
        )


def test_verifier_rejects_resigned_accent_insensitive_conflicting_input() -> None:
    bundle = _build()
    cases = [json.loads(json.dumps(case)) for case in bundle.cases]
    cases[240]["conversation"] = [
        {
            "role": turn["role"],
            "content": "".join(
                character
                for character in unicodedata.normalize("NFKD", turn["content"])
                if not unicodedata.combining(character)
            ),
        }
        for turn in cases[0]["conversation"]
    ]
    assert cases[240]["expected"]["outcome"] != cases[0]["expected"]["outcome"]
    cases_jsonl = b"".join(_canonical_json(case) + b"\n" for case in cases)
    fingerprint_report_json = (
        _canonical_json(build_golden_candidate_fingerprint_report(tuple(cases))) + b"\n"
    )
    manifest = json.loads(bundle.manifest_json)
    manifest["cases_sha256"] = hashlib.sha256(cases_jsonl).hexdigest()
    manifest["fingerprint_report_sha256"] = hashlib.sha256(fingerprint_report_json).hexdigest()
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_digest"}
    digest = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    manifest["bundle_digest"] = digest
    mutated = GoldenCandidateBundle(
        cases=tuple(cases),
        cases_jsonl=cases_jsonl,
        family_lock_json=bundle.family_lock_json,
        fingerprint_report_json=fingerprint_report_json,
        authority_snapshot_json=bundle.authority_snapshot_json,
        generator_source_bytes=bundle.generator_source_bytes,
        manifest_json=_canonical_json(manifest) + b"\n",
        manifest=manifest,
        bundle_digest=digest,
    )

    with pytest.raises(RegistryInvariantError, match="input collision"):
        verify_golden_candidate_bundle(
            bundle=mutated,
            expected_taxonomy_sha256=bundle.manifest["taxonomy_sha256"],
            expected_authority_sha256=_authority_digests(),
            expected_generator_source_sha256=GENERATOR_DIGEST,
        )


def test_verifier_rejects_resigned_case_policy_mutation() -> None:
    bundle = _build()
    cases = [json.loads(json.dumps(case)) for case in bundle.cases]
    cases[0]["initial_context"]["candidate_controls"]["training_eligible"] = True
    cases_jsonl = b"".join(_canonical_json(case) + b"\n" for case in cases)
    manifest = json.loads(bundle.manifest_json)
    manifest["cases_sha256"] = hashlib.sha256(cases_jsonl).hexdigest()
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_digest"}
    digest = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    manifest["bundle_digest"] = digest
    mutated = GoldenCandidateBundle(
        cases=tuple(cases),
        cases_jsonl=cases_jsonl,
        family_lock_json=bundle.family_lock_json,
        fingerprint_report_json=bundle.fingerprint_report_json,
        authority_snapshot_json=bundle.authority_snapshot_json,
        generator_source_bytes=bundle.generator_source_bytes,
        manifest_json=_canonical_json(manifest) + b"\n",
        manifest=manifest,
        bundle_digest=digest,
    )

    with pytest.raises(RegistryInvariantError):
        verify_golden_candidate_bundle(
            bundle=mutated,
            expected_taxonomy_sha256=bundle.manifest["taxonomy_sha256"],
            expected_authority_sha256=_authority_digests(),
            expected_generator_source_sha256=GENERATOR_DIGEST,
        )


def test_writer_is_atomic_private_reproducible_and_idempotent(tmp_path: Path) -> None:
    bundle = _build()
    root = tmp_path / "candidate"

    first = write_golden_candidate_bundle(bundle, root)
    second = write_golden_candidate_bundle(bundle, root)

    assert first == second == root / bundle.bundle_digest
    assert (first / "authority/generator.py").read_bytes() == GENERATOR_SOURCE_BYTES
    assert (first / "authority/authority-snapshot.json").read_bytes() == (
        bundle.authority_snapshot_json
    )
    assert (first.stat().st_mode & 0o777) == 0o700
    for path in first.rglob("*"):
        expected_mode = 0o700 if path.is_dir() else 0o600
        assert (path.stat().st_mode & 0o777) == expected_mode


def test_writer_rejects_existing_content_address_conflict(tmp_path: Path) -> None:
    bundle = _build()
    target = write_golden_candidate_bundle(bundle, tmp_path)
    (target / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(RegistryInvariantError, match="differs from bundle"):
        write_golden_candidate_bundle(bundle, tmp_path)


def _resign(
    bundle: GoldenCandidateBundle,
    *,
    cases: list[dict[str, Any]] | None = None,
    family_lock: dict[str, Any] | None = None,
    authority_snapshot: dict[str, Any] | None = None,
    generator_source_bytes: bytes | None = None,
) -> GoldenCandidateBundle:
    case_values = tuple(
        cases if cases is not None else [json.loads(json.dumps(case)) for case in bundle.cases]
    )
    cases_jsonl = b"".join(_canonical_json(case) + b"\n" for case in case_values)
    family_lock_json = (
        _canonical_json(family_lock) + b"\n" if family_lock is not None else bundle.family_lock_json
    )
    fingerprint_report_json = (
        _canonical_json(build_golden_candidate_fingerprint_report(case_values)) + b"\n"
    )
    authority_snapshot_json = (
        _canonical_json(authority_snapshot) + b"\n"
        if authority_snapshot is not None
        else bundle.authority_snapshot_json
    )
    source_bytes = generator_source_bytes or bundle.generator_source_bytes
    manifest = json.loads(bundle.manifest_json)
    manifest.update(
        {
            "cases_sha256": hashlib.sha256(cases_jsonl).hexdigest(),
            "family_lock_sha256": hashlib.sha256(family_lock_json).hexdigest(),
            "fingerprint_report_sha256": hashlib.sha256(fingerprint_report_json).hexdigest(),
            "authority_snapshot_sha256": hashlib.sha256(authority_snapshot_json).hexdigest(),
            "generator_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "generator_source_bytes": len(source_bytes),
        }
    )
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_digest"}
    digest = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    manifest["bundle_digest"] = digest
    return GoldenCandidateBundle(
        cases=case_values,
        cases_jsonl=cases_jsonl,
        family_lock_json=family_lock_json,
        fingerprint_report_json=fingerprint_report_json,
        authority_snapshot_json=authority_snapshot_json,
        generator_source_bytes=source_bytes,
        manifest_json=_canonical_json(manifest) + b"\n",
        manifest=manifest,
        bundle_digest=digest,
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
