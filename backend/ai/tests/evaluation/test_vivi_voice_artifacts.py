import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.modules.datasets.application.evaluation.golden_smoke import to_contract_candidate
from app.modules.datasets.domain.golden import build_smoke_candidates
from app.modules.evaluation.application.voice_authority import (
    ViViTextVoiceAuthority,
    VoiceAuthorityError,
)

ROOT = Path(__file__).parents[2]
RUBRIC_PATH = ROOT / "dataset-specs/evaluation/rubrics/vivi-text-voice-v1.json"
SUITE_PATH = ROOT / "dataset-specs/evaluation/suites/customer-assistant-golden-v1-candidate.json"
DOMAIN_PATH = ROOT / "dataset-specs/evaluation/voice/vivi-text-domain-pack-v1.json"
BOARD_PATH = ROOT / "dataset-specs/evaluation/voice/vivi-text-board-policy-v1.json"


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_golden_suite_pins_candidate_voice_revisions() -> None:
    rubric = _read(RUBRIC_PATH)
    suite = _read(SUITE_PATH)
    domain = _read(DOMAIN_PATH)
    board = _read(BOARD_PATH)

    assert suite["rubric_revision"] == "customer-assistant-golden-v1"
    assert suite["voice_profile_revision"] == rubric["rubric_id"]
    assert suite["voice_domain_pack_revision"] == domain["domain_pack_id"]
    assert suite["voice_board_policy_revision"] == board["board_policy_id"]
    assert rubric["status"] == "candidate"
    assert board["status"] == "human-blocked"

    # The suite binds exact content, while keeping the digest fields out of the
    # hashed basis so an operator cannot silently swap an artifact revision.
    suite_basis = {
        key: value
        for key, value in suite.items()
        if key != "voice_suite_semantic_digest"
    }
    assert _digest(suite_basis) == suite.get("voice_suite_semantic_digest")

    for artifact in (rubric, domain, board):
        artifact_basis = {
            key: value for key, value in artifact.items() if key != "semantic_digest"
        }
        assert _digest(artifact_basis) == artifact["semantic_digest"]


def test_smoke_candidate_uses_the_bound_voice_rubric() -> None:
    case = build_smoke_candidates(
        namespace=__import__("uuid").uuid4(),
        seed_revision="test-vivi-voice",
    )[0]
    candidate = to_contract_candidate(case)
    assert candidate["rubric_revision"] == "vivi-text-voice-v1"


def test_voice_authority_loads_exact_bindings_and_remains_human_blocked() -> None:
    authority = ViViTextVoiceAuthority.load(ROOT / "dataset-specs/evaluation")

    authority.assert_case_revision("vivi-text-voice-v1")
    assert authority.release_blocked is True
    assert authority.calibration_plan["target_cases"] == 60
    assert authority.heldout_plan["target_cases"] == 120
    assert authority.calibration_plan["current_adjudicated_cases"] == 0
    assert authority.heldout_plan["current_adjudicated_cases"] == 0


def test_voice_authority_rejects_tampered_artifact(tmp_path: Path) -> None:
    specification_root = tmp_path / "evaluation"
    shutil.copytree(ROOT / "dataset-specs/evaluation", specification_root)
    rubric_path = specification_root / "rubrics/vivi-text-voice-v1.json"
    rubric = _read(rubric_path)
    rubric["status"] = "approved"
    rubric_path.write_text(json.dumps(rubric), encoding="utf-8")

    with pytest.raises(VoiceAuthorityError, match="digest mismatch"):
        ViViTextVoiceAuthority.load(specification_root)


def test_voice_authority_rejects_coherently_resigned_artifact(tmp_path: Path) -> None:
    specification_root = tmp_path / "evaluation"
    shutil.copytree(ROOT / "dataset-specs/evaluation", specification_root)
    rubric_path = specification_root / "rubrics/vivi-text-voice-v1.json"
    rubric = _read(rubric_path)
    rubric["description"] = "coherently resigned replacement"
    basis = {key: value for key, value in rubric.items() if key != "semantic_digest"}
    rubric["semantic_digest"] = _digest(basis)
    rubric_path.write_text(json.dumps(rubric), encoding="utf-8")

    with pytest.raises(VoiceAuthorityError, match="not trusted"):
        ViViTextVoiceAuthority.load(specification_root)


def test_voice_authority_rejects_unknown_case_revision() -> None:
    authority = ViViTextVoiceAuthority.load(ROOT / "dataset-specs/evaluation")

    with pytest.raises(VoiceAuthorityError, match="unknown voice revision"):
        authority.assert_case_revision("vivi-text-voice-v0")
