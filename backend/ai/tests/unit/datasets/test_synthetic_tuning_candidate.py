from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest

from app.modules.datasets.application.curation.synthetic_tuning_candidate import (
    TrustedCandidateAuthority,
    count_words,
    digest,
    scenario_lock_digest,
    verify_candidate,
)
from app.modules.datasets.application.curation.synthetic_tuning_v4_authority import (
    VIVI_BEHAVIOR_SYNTHETIC_V4_AUTHORITY,
)
from app.modules.datasets.application.curation.synthetic_tuning_v4_generator import (
    build_v4_candidate,
)
from app.modules.datasets.infrastructure import synthetic_tuning_candidate_store
from app.modules.datasets.infrastructure.synthetic_tuning_candidate_store import (
    materialize_candidate_directory,
    verify_candidate_directory,
    verify_provider_exports,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_V3_CANDIDATE = (
    _REPOSITORY_ROOT / "local-data/ai-datasets/candidate/tuning/vivi-behavior-synthetic-v3"
)


def _candidate() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    response_structure_labels: dict[str, str] = {
        "behavior": "response_structure",
        "language": "vi",
        "risk_category": "low",
        "training_intent": "clear_response_structure",
    }
    pinned: dict[str, Any] = {
        "candidate_id": "vivi-behavior-synthetic-v4",
        "exports": ["gemini/train.jsonl", "gemini/validation.jsonl"],
        "generator_revision": "synthetic-behavior-composer-v4",
        "generator_identity": "vfbiz-synthetic-behavior-composer@4.0.0",
        "generator_source_sha256": "a" * 64,
        "verifier_revision": "synthetic-tuning-candidate-v2",
        "work_item": "VFBIZ-0214",
        "source": "synthetic",
        "seed_set_id": "synthetic-behavior-seeds-v4",
        "voice_rubric_sha256": "e" * 64,
        "domain_pack_sha256": "0" * 64,
        "system_instruction": (
            "Trả lời bằng tiếng Việt tự nhiên, ngắn gọn và minh bạch; "
            "không tự tạo dữ kiện hoặc hành động đã thực hiện."
        ),
        "behavior_labels": {"response_structure": response_structure_labels},
    }
    split_family_counts = {"train": 80, "validation": 20, "test": 20}
    families: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    def fixture_messages(
        *,
        family_id: str,
        family_number: int,
        split: str,
        variant: int,
    ) -> list[dict[str, str]]:
        record_id = f"{family_id}-v{variant}"
        context_width = {"train": 1, "validation": 3, "test": 6}[split]
        unique_context = " ".join(
            sha256(
                f"{family_number}:{variant}:{index}".encode()
            ).hexdigest()
            for index in range(context_width)
        )
        return [
            {
                "role": "user",
                "content": (
                    f"Hãy hỗ trợ mô phỏng {record_id} với "
                    f"ngữcảnh{family_number} biếnthể{variant} "
                    f"điểm{family_number}a điểm{variant}b {unique_context}."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    f"Hỗ trợ mốc{family_number} cách{variant} nhịp{family_number}c "
                    f"bước{variant}d: Mình sẽ trình bày {record_id} rõ ràng theo "
                    f"bước{variant}d {unique_context}."
                ),
            },
        ]

    family_number = 0
    for split, count in split_family_counts.items():
        for _ in range(count):
            family_number += 1
            family_id = f"family-{family_number:03d}"
            scenarios: list[dict[str, str]] = []
            for variant in range(1, 6):
                scenario_id = f"{family_id}-scenario-{variant}"
                messages = fixture_messages(
                    family_id=family_id,
                    family_number=family_number,
                    split=split,
                    variant=variant,
                )
                scenarios.append(
                    {
                        "scenario_digest": digest(
                            {
                                "assistant": messages[1]["content"],
                                "scenario_id": scenario_id,
                                "user": messages[0]["content"],
                            }
                        ),
                        "scenario_id": scenario_id,
                        "seed_digest": digest({"family_id": family_id, "variant": variant}),
                    }
                )
            families.append(
                {
                    "behavior": "response_structure",
                    "family_id": family_id,
                    "scenarios": scenarios,
                    "semantic_fingerprint": digest({"family": family_id, "split": split}),
                    "split": split,
                }
            )
    family_lock = {"candidate_id": pinned["candidate_id"], "families": families}
    pinned_digest = digest(pinned)
    lock_digest = digest(family_lock)
    for family in families:
        record_family_number = int(family["family_id"].removeprefix("family-"))
        for variant in range(1, 6):
            record_id = f"{family['family_id']}-v{variant}"
            messages = fixture_messages(
                family_id=family["family_id"],
                family_number=record_family_number,
                split=family["split"],
                variant=variant,
            )
            scenario = family["scenarios"][variant - 1]
            prompt_components = [f"prompt:{family['split']}:{record_id}"]
            response_components = [
                f"response-prefix:{family['split']}:{record_id}",
                f"response-bridge:{family['split']}:{record_id}",
                f"response-modifier:{family['split']}:{record_id}",
                f"response-tail:{family['split']}:{record_id}",
            ]
            lineage = {
                "candidate_id": pinned["candidate_id"],
                "work_item": "VFBIZ-0214",
                "generation_run_id": "vivi-behavior-synthetic-v4-run-001",
                "generator_identity": "vfbiz-synthetic-behavior-composer@4.0.0",
                "generator_source_sha256": "a" * 64,
                "pinned_revisions_sha256": pinned_digest,
                "family_lock_sha256": lock_digest,
                "seed_set_id": "synthetic-behavior-seeds-v4",
                "seed_digest": scenario["seed_digest"],
                "scenario_id": scenario["scenario_id"],
                "scenario_digest": scenario["scenario_digest"],
                "prompt_component_ids": prompt_components,
                "response_component_ids": response_components,
                "composition_digest": digest(
                    {
                        "messages": messages,
                        "prompt_component_ids": prompt_components,
                        "response_component_ids": response_components,
                    }
                ),
                "source_refs": [],
                "golden_or_heldout_seed_refs": [],
                "record_content_sha256": "",
            }
            record: dict[str, Any] = {
                "record_id": record_id,
                "family_id": family["family_id"],
                "split": family["split"],
                "human_adjudicated": False,
                "training_eligible": False,
                "release_eligible": False,
                "production_eligible": False,
                "provider_call_made": False,
                "upload_made": False,
                "source": "synthetic",
                "labels": response_structure_labels,
                "messages": messages,
                "response_constraints": {
                    "max_words": 60,
                    "max_questions": 0,
                    "required_phrases": ["Mình sẽ"],
                    "forbidden_phrases": ["đã được phê duyệt"],
                },
                "lineage": lineage,
            }
            projection = deepcopy(record)
            cast(dict[str, Any], projection["lineage"]).pop("record_content_sha256")
            lineage["record_content_sha256"] = digest(projection)
            records.append(record)
    return records, family_lock, pinned


def _authority(
    family_lock: dict[str, Any],
    pinned: dict[str, Any],
) -> TrustedCandidateAuthority:
    return TrustedCandidateAuthority(
        candidate_id="vivi-behavior-synthetic-v4",
        work_item="VFBIZ-0214",
        source="synthetic",
        verifier_revision="synthetic-tuning-candidate-v2",
        verifier_source_path=(
            "backend/ai/app/modules/datasets/application/curation/synthetic_tuning_candidate.py"
        ),
        verifier_source_sha256="b" * 64,
        text_quality_source_path=(
            "backend/ai/app/modules/datasets/application/curation/synthetic_text_quality.py"
        ),
        text_quality_source_sha256="1" * 64,
        store_source_path=(
            "backend/ai/app/modules/datasets/infrastructure/synthetic_tuning_candidate_store.py"
        ),
        store_source_sha256="c" * 64,
        voice_rubric_source_path=(
            "backend/ai/dataset-specs/evaluation/rubrics/vivi-text-voice-v1.json"
        ),
        voice_rubric_file_sha256="d" * 64,
        voice_rubric_semantic_sha256=str(pinned.get("voice_rubric_sha256", "e" * 64)),
        domain_pack_source_path=(
            "backend/ai/dataset-specs/evaluation/voice/vivi-text-domain-pack-v1.json"
        ),
        domain_pack_file_sha256="f" * 64,
        domain_pack_semantic_sha256=str(pinned.get("domain_pack_sha256", "0" * 64)),
        generator_identity="vfbiz-synthetic-behavior-composer@4.0.0",
        generator_source_path=(
            "backend/ai/app/modules/datasets/application/curation/synthetic_tuning_v4_generator.py"
        ),
        generator_source_sha256="a" * 64,
        seed_set_id="synthetic-behavior-seeds-v4",
        pinned_revisions_sha256=digest(pinned),
        family_lock_sha256=digest(family_lock),
        scenario_lock_sha256=scenario_lock_digest(family_lock),
        behavior_labels_sha256=digest(pinned["behavior_labels"]),
        governance_metadata_sha256="d" * 64,
        regression_source_bindings=(),
        allowed_exports=("gemini/train.jsonl", "gemini/validation.jsonl"),
        expected_record_count=600,
        expected_split_counts={"train": 400, "validation": 100, "test": 100},
    )


def _resign(record: dict[str, Any]) -> None:
    lineage = cast(dict[str, Any], record["lineage"])
    lineage["composition_digest"] = digest(
        {
            "messages": record["messages"],
            "prompt_component_ids": lineage["prompt_component_ids"],
            "response_component_ids": lineage["response_component_ids"],
        }
    )
    projection = deepcopy(record)
    cast(dict[str, Any], projection["lineage"]).pop("record_content_sha256")
    lineage["record_content_sha256"] = digest(projection)


def _rehash_directory(root: Path) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for relative in manifest["artifacts"]:
        manifest["artifacts"][relative] = sha256((root / relative).read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    no_upload_path = root / "reports" / "no-upload-decision.json"
    no_upload = json.loads(no_upload_path.read_text())
    no_upload["candidate_manifest_sha256"] = sha256(manifest_path.read_bytes()).hexdigest()
    no_upload.pop("packet_digest")
    no_upload["packet_digest"] = digest(no_upload)
    no_upload_path.write_text(
        json.dumps(no_upload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    checksums = [
        f"{sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    (root / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")


def _write_unqualified_candidate(
    root: Path,
    *,
    candidate: object,
    authority: TrustedCandidateAuthority,
) -> None:
    """Create a tamper-test fixture without exposing a production bypass."""

    root.mkdir(mode=0o700)
    writer = cast(
        Callable[[Path, object, TrustedCandidateAuthority], None],
        vars(synthetic_tuning_candidate_store)["_write_candidate_files"],
    )
    writer(root, candidate, authority)


def test_governed_synthetic_candidate_accepts_600_isolated_records() -> None:
    records, family_lock, pinned = _candidate()

    result = verify_candidate(
        records=records,
        family_lock=family_lock,
        pinned=pinned,
        authority=_authority(family_lock, pinned),
    )

    assert result.accepted
    assert result.record_count == 600
    assert result.split_counts == {"train": 400, "validation": 100, "test": 100}
    assert result.maximum_response_share == {
        "train": 0.0025,
        "validation": 0.01,
        "test": 0.01,
    }


def test_rejected_v3_cannot_pass_the_hardened_directory_gate() -> None:
    _records, family_lock, pinned = _candidate()
    result = verify_candidate_directory(
        _V3_CANDIDATE,
        authority=_authority(family_lock, pinned),
        repository_root=_REPOSITORY_ROOT,
    )

    assert not result.accepted
    assert "candidate authority metadata is incomplete" in result.errors
    assert result.record_count == 625
    assert result.split_counts == {"train": 400, "validation": 100, "test": 125}


def test_semantic_constraint_rejects_tamper_even_after_outer_hashes_are_rebuilt() -> None:
    records, family_lock, pinned = _candidate()
    target = records[-1]
    target["response_constraints"]["max_words"] = 15
    target["messages"][1]["content"] = " ".join(f"từ{index}" for index in range(1, 17))
    _resign(target)

    result = verify_candidate(
        records=records,
        family_lock=family_lock,
        pinned=pinned,
        authority=_authority(family_lock, pinned),
    )

    assert not result.accepted
    assert f"max words exceeded:{target['record_id']}" in result.errors


def test_family_lock_and_component_split_leakage_fail_closed() -> None:
    records, family_lock, pinned = _candidate()
    target = records[-1]
    target["family_id"] = records[0]["family_id"]
    target["lineage"]["prompt_component_ids"] = records[0]["lineage"]["prompt_component_ids"]
    _resign(target)

    result = verify_candidate(
        records=records,
        family_lock=family_lock,
        pinned=pinned,
        authority=_authority(family_lock, pinned),
    )

    assert not result.accepted
    assert any("family lock mismatch" in error for error in result.errors)
    assert "component split leakage:train:test" in result.errors


def test_generator_hash_tamper_is_rejected_even_when_record_is_resigned() -> None:
    records, family_lock, pinned = _candidate()
    target = records[0]
    target["lineage"]["generator_source_sha256"] = "f" * 64
    _resign(target)

    result = verify_candidate(
        records=records,
        family_lock=family_lock,
        pinned=pinned,
        authority=_authority(family_lock, pinned),
    )

    assert not result.accepted
    assert f"lineage authority mismatch:{target['record_id']}" in result.errors


def test_source_label_scenario_and_seed_tamper_cannot_be_self_resigned() -> None:
    records, family_lock, pinned = _candidate()
    target = records[0]
    target["source"] = "customer-conversation"
    target["labels"] = {}
    target["lineage"]["scenario_id"] = "replacement"
    target["lineage"]["scenario_digest"] = digest({"scenario": "replacement"})
    target["lineage"]["seed_digest"] = digest({"seed": "replacement"})
    _resign(target)

    result = verify_candidate(
        records=records,
        family_lock=family_lock,
        pinned=pinned,
        authority=_authority(family_lock, pinned),
    )

    assert not result.accepted
    assert any("source authority mismatch" in error for error in result.errors)
    assert any("label or family authority mismatch" in error for error in result.errors)
    assert any("lineage authority mismatch" in error for error in result.errors)


def test_message_and_scenario_resign_cannot_replace_locked_scenario() -> None:
    records, family_lock, pinned = _candidate()
    target = records[0]
    target["messages"][0]["content"] = "Một yêu cầu bị thay thế hoàn toàn."
    lineage = cast(dict[str, Any], target["lineage"])
    lineage["scenario_digest"] = digest(
        {
            "assistant": target["messages"][1]["content"],
            "scenario_id": lineage["scenario_id"],
            "user": target["messages"][0]["content"],
        }
    )
    _resign(target)

    result = verify_candidate(
        records=records,
        family_lock=family_lock,
        pinned=pinned,
        authority=_authority(family_lock, pinned),
    )

    assert not result.accepted
    assert f"lineage authority mismatch:{target['record_id']}" in result.errors


def test_coherent_full_resign_cannot_replace_external_authority() -> None:
    records, family_lock, pinned = _candidate()
    authority = _authority(family_lock, pinned)
    pinned["generator_identity"] = "attacker-controlled-generator@9.0.0"
    pinned["generator_source_sha256"] = "f" * 64
    pinned_digest = digest(pinned)
    for record in records:
        lineage = cast(dict[str, Any], record["lineage"])
        lineage["generator_identity"] = pinned["generator_identity"]
        lineage["generator_source_sha256"] = pinned["generator_source_sha256"]
        lineage["pinned_revisions_sha256"] = pinned_digest
        _resign(record)

    result = verify_candidate(
        records=records,
        family_lock=family_lock,
        pinned=pinned,
        authority=authority,
    )

    assert not result.accepted
    assert "candidate authority metadata is incomplete" in result.errors


def test_provider_exports_must_equal_reviewed_canonical_records(
    tmp_path: Path,
) -> None:
    records, _family_lock, pinned = _candidate()
    export_root = tmp_path / "candidate"
    (export_root / "gemini").mkdir(parents=True)
    system_instruction = cast(str, pinned["system_instruction"])
    for split in ("train", "validation"):
        rows: list[dict[str, Any]] = []
        for record in records:
            if record["split"] != split:
                continue
            messages = cast(list[dict[str, str]], record["messages"])
            rows.append(
                {
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": messages[0]["content"]}],
                        },
                        {
                            "role": "model",
                            "parts": [{"text": messages[1]["content"]}],
                        },
                    ],
                }
            )
        (export_root / "gemini" / f"{split}.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    assert verify_provider_exports(export_root, records, pinned) == []

    validation_path = export_root / "gemini" / "validation.jsonl"
    validation_rows = validation_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(validation_rows[0])
    tampered["contents"][1]["parts"][0]["text"] = '{"tool": "unsafe_unregistered_call"}'
    validation_rows[0] = json.dumps(tampered, ensure_ascii=False)
    validation_path.write_text("\n".join(validation_rows) + "\n", encoding="utf-8")

    errors = verify_provider_exports(export_root, records, pinned)

    assert "provider export divergence:validation:1" in errors
    assert "provider export safety finding:validation:1:ad-hoc-tool-call" in errors


def test_v4_materialization_rejects_text_quality_before_publish(tmp_path: Path) -> None:
    authority = VIVI_BEHAVIOR_SYNTHETIC_V4_AUTHORITY
    candidate = build_v4_candidate(generator_source_sha256=authority.generator_source_sha256)
    root = tmp_path / "vivi-behavior-synthetic-v4"

    with pytest.raises(ValueError, match="candidate failed verification"):
        materialize_candidate_directory(
            root,
            candidate=candidate,
            authority=authority,
            repository_root=_REPOSITORY_ROOT,
        )

    assert not root.exists()
    assert list(tmp_path.iterdir()) == []


def test_regression_semantics_and_exact_artifact_allowlist_fail_closed(
    tmp_path: Path,
) -> None:
    authority = VIVI_BEHAVIOR_SYNTHETIC_V4_AUTHORITY
    candidate = build_v4_candidate(generator_source_sha256=authority.generator_source_sha256)
    root = tmp_path / "vivi-behavior-synthetic-v4"
    _write_unqualified_candidate(
        root,
        candidate=candidate,
        authority=authority,
    )
    regression_path = root / "regressions" / "v2-word-limit-regressions.json"
    regression = json.loads(regression_path.read_text())
    regression["regressions"][0]["source_record_id"] = "forged-v2-record"
    regression["regressions"][0]["source_record_sha256"] = "f" * 64
    regression_path.write_text(
        json.dumps(regression, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "forged-approval.json").write_text(
        '{"decision":"approved"}\n',
        encoding="utf-8",
    )
    _rehash_directory(root)

    result = verify_candidate_directory(
        root,
        authority=authority,
        repository_root=_REPOSITORY_ROOT,
    )

    assert not result.accepted
    assert "candidate artifact allowlist mismatch" in result.errors
    assert "regression source binding mismatch:forged-v2-record" in result.errors


def test_directory_full_resign_still_fails_external_authority(
    tmp_path: Path,
) -> None:
    authority = VIVI_BEHAVIOR_SYNTHETIC_V4_AUTHORITY
    candidate = build_v4_candidate(generator_source_sha256=authority.generator_source_sha256)
    root = tmp_path / "vivi-behavior-synthetic-v4"
    _write_unqualified_candidate(
        root,
        candidate=candidate,
        authority=authority,
    )

    pinned_path = root / "revisions" / "pinned-revisions.json"
    pinned = json.loads(pinned_path.read_text(encoding="utf-8"))
    pinned["generator_identity"] = "attacker-controlled-generator@9.0.0"
    pinned_digest = digest(pinned)
    pinned_path.write_text(
        json.dumps(pinned, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for relative in (
        "canonical/train.jsonl",
        "canonical/validation.jsonl",
        "heldout/test.jsonl",
    ):
        path = root / relative
        records = [json.loads(line) for line in path.read_text().splitlines()]
        for record in records:
            lineage = record["lineage"]
            lineage["generator_identity"] = pinned["generator_identity"]
            lineage["pinned_revisions_sha256"] = pinned_digest
            _resign(record)
        path.write_text(
            "\n".join(
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                for record in records
            )
            + "\n",
            encoding="utf-8",
        )
        split = records[0]["split"]
        split_manifest_path = root / "manifests" / f"{split}.manifest.json"
        split_manifest = json.loads(split_manifest_path.read_text())
        split_manifest["record_digests"] = [
            record["lineage"]["record_content_sha256"] for record in records
        ]
        split_manifest_path.write_text(json.dumps(split_manifest, indent=2, sort_keys=True) + "\n")

    _rehash_directory(root)

    result = verify_candidate_directory(
        root,
        authority=authority,
        repository_root=_REPOSITORY_ROOT,
    )

    assert not result.accepted
    assert "candidate authority metadata is incomplete" in result.errors


def test_text_quality_implementation_is_bound_by_external_authority(
    tmp_path: Path,
) -> None:
    authority = VIVI_BEHAVIOR_SYNTHETIC_V4_AUTHORITY
    candidate = build_v4_candidate(generator_source_sha256=authority.generator_source_sha256)
    root = tmp_path / "vivi-behavior-synthetic-v4"
    _write_unqualified_candidate(
        root,
        candidate=candidate,
        authority=authority,
    )

    result = verify_candidate_directory(
        root,
        authority=replace(authority, text_quality_source_sha256="0" * 64),
        repository_root=_REPOSITORY_ROOT,
    )

    assert not result.accepted
    assert "trusted text-quality source digest mismatch" in result.errors


def test_vietnamese_word_count_is_deterministic() -> None:
    assert count_words("Mình đã nắm bối cảnh và sẽ trả lời thật ngắn gọn.") == 12
