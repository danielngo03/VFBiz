from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from app.modules.evaluation.application.voice_authority import ViViTextVoiceAuthority
from app.modules.evaluation.application.voice_calibration import (
    VoiceCalibrationError,
    build_voice_calibration_packet,
    verify_voice_calibration_packet,
)
from app.modules.evaluation.infrastructure.voice_calibration_store import (
    write_voice_calibration_bundle,
)

ROOT = Path(__file__).parents[2]
SPECIFICATION_ROOT = ROOT / "dataset-specs/evaluation"
REQUIRED_SLICES = {
    "diacritics-and-no-diacritics",
    "regional-language",
    "slang",
    "ambiguity",
    "refusal-and-handoff",
    "multi-turn",
    "high-risk-domain",
}


def _authority() -> ViViTextVoiceAuthority:
    return ViViTextVoiceAuthority.load(SPECIFICATION_ROOT)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _resign(manifest: dict[str, object]) -> bytes:
    basis = {key: value for key, value in manifest.items() if key != "bundle_digest"}
    digest = hashlib.sha256(_canonical(basis)).hexdigest()
    return _canonical({**basis, "bundle_digest": digest}) + b"\n"


def _resign_cases(
    bundle_manifest: dict[str, object], cases: list[dict[str, object]]
) -> tuple[bytes, bytes, str]:
    cases_bytes = b"".join(_canonical(case) + b"\n" for case in cases)
    manifest = deepcopy(bundle_manifest)
    manifest["cases_sha256"] = hashlib.sha256(cases_bytes).hexdigest()
    manifest_bytes = _resign(manifest)
    return manifest_bytes, cases_bytes, json.loads(manifest_bytes)["bundle_digest"]


def test_voice_calibration_packet_is_exact_pending_and_fact_free() -> None:
    authority = _authority()
    bundle = build_voice_calibration_packet(authority)

    verified = verify_voice_calibration_packet(
        authority=authority,
        manifest_bytes=bundle.manifest_json,
        cases_bytes=bundle.cases_jsonl,
        expected_bundle_digest=bundle.bundle_digest,
    )

    assert verified["case_count"] == 60
    assert verified["family_count"] == 12
    assert verified["current_adjudicated_cases"] == 0
    assert verified["status"] == "human-blocked"
    assert verified["golden"] is False
    assert verified["training_eligible"] is False
    assert verified["release_eligible"] is False
    assert verified["family_isolation_required"] is True
    assert verified["golden_overlap_maximum"] == 0
    assert verified["training_overlap_maximum"] == 0
    assert verified["required_human_roles"] == [
        "product-owner",
        "design-lead",
        "brand-content-owner",
        "legal-owner",
        "data-privacy-owner",
        "release-owner",
    ]
    assert verified["generator"]["generator_id"] == "vfbiz-voice-calibration-generator"
    assert verified["authority_binding"]["heldout_plan_revision"]
    assert verified["authority_binding"]["heldout_plan_semantic_digest"]
    assert len(bundle.cases) == 60
    assert len({case["case_id"] for case in bundle.cases}) == 60
    assert set(Counter(case["family_id"] for case in bundle.cases).values()) == {5}
    observed_slices = {slice_id for case in bundle.cases for slice_id in case["slices"]}
    assert REQUIRED_SLICES <= observed_slices
    assert all(case["source_refs"] == [] for case in bundle.cases)
    assert all(case["knowledge_snapshot"] is None for case in bundle.cases)
    assert all(case["review"]["status"] == "pending" for case in bundle.cases)
    assert all(case["review"]["human_label"] is None for case in bundle.cases)
    assert all(case["human_adjudicated"] is False for case in bundle.cases)
    assert all(case["golden_eligible"] is False for case in bundle.cases)
    assert all(case["training_eligible"] is False for case in bundle.cases)
    assert all(case["release_eligible"] is False for case in bundle.cases)
    assert all(case["public_serving_eligible"] is False for case in bundle.cases)
    style_cases = [case for case in bundle.cases if case["family_id"] == "12-voice-style-policy"]
    assert len(style_cases) == 5
    style_text = " ".join(
        turn["content"] for case in style_cases for turn in case["conversation"]
    ).casefold()
    assert all(term in style_text for term in ("vivi", "emoji", "câu đùa", "quảng cáo", "xưng hô"))
    assert all(case["conversation"][-1]["role"] == "assistant" for case in bundle.cases)


def test_voice_calibration_packet_is_deterministic() -> None:
    authority = _authority()
    first = build_voice_calibration_packet(authority)
    second = build_voice_calibration_packet(authority)

    assert first.cases_jsonl == second.cases_jsonl
    assert first.manifest_json == second.manifest_json
    assert first.bundle_digest == second.bundle_digest


def test_voice_calibration_packet_store_is_private_and_idempotent(tmp_path: Path) -> None:
    authority = _authority()
    bundle = build_voice_calibration_packet(authority)

    target = write_voice_calibration_bundle(
        bundle=bundle,
        authority=authority,
        root=tmp_path / "review-evidence",
    )

    assert target == write_voice_calibration_bundle(
        bundle=bundle,
        authority=authority,
        root=tmp_path / "review-evidence",
    )
    assert target.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in target.iterdir())


def test_voice_calibration_store_rejects_permissions_and_unbound_files(
    tmp_path: Path,
) -> None:
    authority = _authority()
    bundle = build_voice_calibration_packet(authority)
    root = tmp_path / "review-evidence"
    target = write_voice_calibration_bundle(bundle=bundle, authority=authority, root=root)
    target.chmod(0o755)
    with pytest.raises(ValueError, match="permissions"):
        write_voice_calibration_bundle(bundle=bundle, authority=authority, root=root)
    target.chmod(0o700)
    extra = target / "unbound.txt"
    extra.write_text("not evidence", encoding="utf-8")
    extra.chmod(0o600)
    with pytest.raises(ValueError, match="unbound"):
        write_voice_calibration_bundle(bundle=bundle, authority=authority, root=root)


def test_voice_calibration_rejects_resigned_human_role_weakening() -> None:
    authority = _authority()
    bundle = build_voice_calibration_packet(authority)
    manifest = deepcopy(dict(bundle.manifest))
    manifest["required_human_roles"] = []
    manifest_bytes = _resign(manifest)
    resigned_digest = json.loads(manifest_bytes)["bundle_digest"]

    with pytest.raises(VoiceCalibrationError, match="manifest policy mismatch"):
        verify_voice_calibration_packet(
            authority=authority,
            manifest_bytes=manifest_bytes,
            cases_bytes=bundle.cases_jsonl,
            expected_bundle_digest=resigned_digest,
        )


def test_voice_calibration_packet_rejects_case_tamper() -> None:
    authority = _authority()
    bundle = build_voice_calibration_packet(authority)
    tampered = bundle.cases_jsonl.replace(
        "hỏi lại".encode(),
        "đoán giúp".encode(),
        1,
    )

    with pytest.raises(VoiceCalibrationError, match="cases digest mismatch"):
        verify_voice_calibration_packet(
            authority=authority,
            manifest_bytes=bundle.manifest_json,
            cases_bytes=tampered,
            expected_bundle_digest=bundle.bundle_digest,
        )


def test_voice_calibration_packet_rejects_full_resign_promotion() -> None:
    authority = _authority()
    bundle = build_voice_calibration_packet(authority)
    manifest = deepcopy(dict(bundle.manifest))
    manifest["training_eligible"] = True
    resigned_manifest = _resign(manifest)
    resigned_digest = json.loads(resigned_manifest)["bundle_digest"]

    with pytest.raises(VoiceCalibrationError, match="manifest digest mismatch"):
        verify_voice_calibration_packet(
            authority=authority,
            manifest_bytes=resigned_manifest,
            cases_bytes=bundle.cases_jsonl,
            expected_bundle_digest=bundle.bundle_digest,
        )
    with pytest.raises(VoiceCalibrationError, match="not release isolated"):
        verify_voice_calibration_packet(
            authority=authority,
            manifest_bytes=resigned_manifest,
            cases_bytes=bundle.cases_jsonl,
            expected_bundle_digest=resigned_digest,
        )


def test_voice_calibration_packet_rejects_reorder_even_after_resign() -> None:
    authority = _authority()
    bundle = build_voice_calibration_packet(authority)
    lines = bundle.cases_jsonl.splitlines()
    reordered = b"\n".join(reversed(lines)) + b"\n"
    manifest = deepcopy(dict(bundle.manifest))
    manifest["cases_sha256"] = hashlib.sha256(reordered).hexdigest()
    resigned_manifest = _resign(manifest)
    resigned_digest = json.loads(resigned_manifest)["bundle_digest"]

    with pytest.raises(VoiceCalibrationError, match="canonical authority"):
        verify_voice_calibration_packet(
            authority=authority,
            manifest_bytes=resigned_manifest,
            cases_bytes=reordered,
            expected_bundle_digest=resigned_digest,
        )


def test_voice_calibration_packet_rejects_semantic_swap_after_full_resign() -> None:
    authority = _authority()
    bundle = build_voice_calibration_packet(authority)
    cases = [deepcopy(dict(case)) for case in bundle.cases]
    first = cases[0]
    first["conversation"] = [
        {"role": "user", "content": "Giá VinFast được bịa đặt là 123 triệu đồng."}
    ]
    basis = {key: value for key, value in first.items() if key != "case_digest"}
    first["case_digest"] = f"sha256:{hashlib.sha256(_canonical(basis)).hexdigest()}"
    manifest_bytes, cases_bytes, resigned_digest = _resign_cases(dict(bundle.manifest), cases)

    with pytest.raises(VoiceCalibrationError, match="canonical authority"):
        verify_voice_calibration_packet(
            authority=authority,
            manifest_bytes=manifest_bytes,
            cases_bytes=cases_bytes,
            expected_bundle_digest=resigned_digest,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("family_isolation_required", False),
        ("golden_overlap_maximum", 1),
        ("training_overlap_maximum", 1),
    ],
)
def test_voice_calibration_packet_rejects_resigned_isolation_policy(
    field: str, value: object
) -> None:
    authority = _authority()
    bundle = build_voice_calibration_packet(authority)
    manifest = deepcopy(dict(bundle.manifest))
    manifest[field] = value
    manifest_bytes = _resign(manifest)
    resigned_digest = json.loads(manifest_bytes)["bundle_digest"]

    with pytest.raises(VoiceCalibrationError, match="manifest policy mismatch"):
        verify_voice_calibration_packet(
            authority=authority,
            manifest_bytes=manifest_bytes,
            cases_bytes=bundle.cases_jsonl,
            expected_bundle_digest=resigned_digest,
        )


def test_voice_calibration_packet_rejects_governed_split_overlap() -> None:
    authority = _authority()
    bundle = build_voice_calibration_packet(authority)
    first_digest = str(bundle.cases[0]["case_digest"])

    with pytest.raises(VoiceCalibrationError, match="overlaps a governed split"):
        verify_voice_calibration_packet(
            authority=authority,
            manifest_bytes=bundle.manifest_json,
            cases_bytes=bundle.cases_jsonl,
            expected_bundle_digest=bundle.bundle_digest,
            forbidden_case_digests=frozenset({first_digest}),
        )


def test_voice_calibration_packet_rejects_family_and_semantic_overlap() -> None:
    authority = _authority()
    bundle = build_voice_calibration_packet(authority)
    first_family = str(bundle.cases[0]["split_family_id"])
    first_semantic = str(bundle.cases[0]["semantic_fingerprint"])

    with pytest.raises(VoiceCalibrationError, match="family overlaps"):
        verify_voice_calibration_packet(
            authority=authority,
            manifest_bytes=bundle.manifest_json,
            cases_bytes=bundle.cases_jsonl,
            expected_bundle_digest=bundle.bundle_digest,
            forbidden_split_family_ids=frozenset({first_family}),
        )
    with pytest.raises(VoiceCalibrationError, match="semantics overlap"):
        verify_voice_calibration_packet(
            authority=authority,
            manifest_bytes=bundle.manifest_json,
            cases_bytes=bundle.cases_jsonl,
            expected_bundle_digest=bundle.bundle_digest,
            forbidden_semantic_fingerprints=frozenset({first_semantic}),
        )
