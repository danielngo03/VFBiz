from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.modules.datasets.application.evaluation.red_team_generator import (
    canonical_json,
    canonical_jsonl,
)
from app.modules.datasets.application.evaluation.red_team_verifier import (
    RedTeamCandidateBundle,
    verify_red_team_candidate_bundle,
)
from app.modules.datasets.domain import RegistryInvariantError
from app.modules.datasets.infrastructure.red_team_candidate_store import (
    build_current_red_team_candidate_bundle,
    verify_persisted_red_team_candidate,
    write_red_team_candidate_bundle,
)


def _verify(bundle: RedTeamCandidateBundle) -> None:
    current = build_current_red_team_candidate_bundle()
    verify_red_team_candidate_bundle(
        bundle,
        expected_generator_source_bytes=current.generator_source_bytes,
        expected_verifier_source_bytes=current.verifier_source_bytes,
    )


def _rows(bundle: RedTeamCandidateBundle) -> list[dict[str, object]]:
    return [json.loads(line) for line in bundle.rows_jsonl.decode("utf-8").splitlines()]


def test_candidate_is_fact_free_balanced_locked_and_non_releasable() -> None:
    first = build_current_red_team_candidate_bundle()
    second = build_current_red_team_candidate_bundle()

    assert first == second
    assert first.manifest["case_count"] == 200
    assert first.manifest["family_count"] == 40
    assert set(first.manifest["attack_class_counts"].values()) == {25}  # type: ignore[union-attr]
    assert first.manifest["semantic_equivalence_claimed"] is False
    assert first.manifest["independent_review_status"] == "pending"
    rows = _rows(first)
    assert len({row["case_id"] for row in rows}) == 200
    assert len({row["split_family_id"] for row in rows}) == 40
    assert all(
        row[field] is False
        for row in rows
        for field in (
            "human_adjudicated",
            "training_eligible",
            "upload_allowed",
            "release_eligible",
            "knowledge_eligible",
        )
    )
    report = json.loads(first.validation_report_json)
    assert report["exact_normalized_duplicate_count"] == 0
    assert report["cross_family_near_overlap_count"] == 0
    assert report["forbidden_content_match_count"] == 0
    assert report["deterministic_gate_passed"] is True


def test_verifier_rejects_row_tamper_even_after_manifest_resign() -> None:
    bundle = build_current_red_team_candidate_bundle()
    rows = _rows(bundle)
    rows[0]["text"] = "Nội dung đã bị thay đổi"
    rows_jsonl = canonical_jsonl(tuple(rows))
    manifest = bundle.manifest
    manifest["rows_sha256"] = __import__("hashlib").sha256(rows_jsonl).hexdigest()
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_digest"}
    resigned_digest = __import__("hashlib").sha256(canonical_json(unsigned)).hexdigest()
    manifest["bundle_digest"] = resigned_digest
    forged = replace(
        bundle,
        bundle_digest=resigned_digest,
        rows_jsonl=rows_jsonl,
        manifest_json=canonical_json(manifest),
    )

    with pytest.raises(RegistryInvariantError, match="deterministic projection"):
        _verify(forged)


def test_verifier_rejects_source_authority_resign() -> None:
    bundle = build_current_red_team_candidate_bundle()
    forged_source = bundle.generator_source_bytes + b"\n# forged\n"
    manifest = bundle.manifest
    manifest["generator_source_sha256"] = __import__("hashlib").sha256(
        forged_source
    ).hexdigest()
    unsigned = {key: value for key, value in manifest.items() if key != "bundle_digest"}
    resigned_digest = __import__("hashlib").sha256(canonical_json(unsigned)).hexdigest()
    manifest["bundle_digest"] = resigned_digest
    forged = replace(
        bundle,
        bundle_digest=resigned_digest,
        generator_source_bytes=forged_source,
        manifest_json=canonical_json(manifest),
    )

    with pytest.raises(RegistryInvariantError, match="authority digest"):
        _verify(forged)


def test_store_is_private_atomic_idempotent_and_replay_verified(tmp_path: Path) -> None:
    bundle = build_current_red_team_candidate_bundle()
    root = tmp_path / "red-team"
    first = write_red_team_candidate_bundle(bundle, root)
    second = write_red_team_candidate_bundle(bundle, root)

    assert first == second == root / bundle.bundle_digest
    assert list(first.rglob("*.jsonl")) == [first / "adversarial-cases.jsonl"]
    verify_persisted_red_team_candidate(first)
    assert (root.stat().st_mode & 0o777) == 0o700
    assert all(
        (path.stat().st_mode & 0o777) == 0o600
        for path in first.rglob("*")
        if path.is_file()
    )


def test_store_rejects_extra_file_and_symlink(tmp_path: Path) -> None:
    bundle = build_current_red_team_candidate_bundle()
    target = write_red_team_candidate_bundle(bundle, tmp_path / "red-team")
    extra = target / "extra.jsonl"
    extra.write_text("{}\n", encoding="utf-8")
    extra.chmod(0o600)
    with pytest.raises(RegistryInvariantError, match="file set"):
        verify_persisted_red_team_candidate(target)
    extra.unlink()
    symlink = target / "alias"
    symlink.symlink_to(target / "manifest.json")
    with pytest.raises(RegistryInvariantError, match="file set"):
        verify_persisted_red_team_candidate(target)


def test_store_rejects_permission_drift(tmp_path: Path) -> None:
    bundle = build_current_red_team_candidate_bundle()
    target = write_red_team_candidate_bundle(bundle, tmp_path / "red-team")
    (target / "manifest.json").chmod(0o644)
    with pytest.raises(RegistryInvariantError, match="permissions"):
        verify_persisted_red_team_candidate(target)
