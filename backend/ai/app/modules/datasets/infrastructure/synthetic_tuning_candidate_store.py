"""Filesystem adapter for a governed synthetic tuning candidate."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from app.modules.datasets.application.curation.synthetic_tuning_candidate import (
    CandidateVerification,
    TrustedCandidateAuthority,
    canonical_json,
    count_words,
    digest,
    safety_findings,
    verify_candidate,
)
from app.modules.datasets.application.curation.synthetic_tuning_v4_generator import (
    GeneratedCandidate,
)

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SPLITS = ("train", "validation", "test")
_EXPECTED_FILES = frozenset(
    {
        "SHA256SUMS",
        "canonical/train.jsonl",
        "canonical/validation.jsonl",
        "family-lock.json",
        "gemini/train.jsonl",
        "gemini/validation.jsonl",
        "heldout/test.jsonl",
        "manifest.json",
        "manifests/test.manifest.json",
        "manifests/train.manifest.json",
        "manifests/validation.manifest.json",
        "regressions/v2-word-limit-regressions.json",
        "reports/no-upload-decision.json",
        "revisions/pinned-revisions.json",
    }
)
_MANIFEST_ARTIFACTS = _EXPECTED_FILES - {
    "SHA256SUMS",
    "manifest.json",
    "reports/no-upload-decision.json",
}
_GOVERNANCE_METADATA: dict[str, object] = {
    "accountable_role": "data-owner",
    "allowed_use": "behavior-sft-candidate-review-only",
    "approval_status": "unapproved",
    "classification": "synthetic-no-production-data",
    "deletion_policy": "delete-provider-copy-on-rejection",
    "purpose": "evaluate-non-factual-assistant-behavior",
    "retention_status": "pending-human-decision",
    "rights_basis": "internally-generated-synthetic",
    "source_provenance": "deterministic-repository-generator",
}


def materialize_candidate_directory(
    root: Path,
    *,
    candidate: GeneratedCandidate,
    authority: TrustedCandidateAuthority,
    repository_root: Path,
) -> CandidateVerification:
    """Atomically materialize one immutable candidate, or verify an existing one."""

    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise ValueError("candidate path must be an existing directory")
        return verify_candidate_directory(
            root,
            authority=authority,
            repository_root=repository_root,
        )
    root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{root.name}.", dir=root.parent))
    os.chmod(temporary, 0o700)
    try:
        _write_candidate_files(temporary, candidate, authority)
        verification = verify_candidate_directory(
            temporary,
            authority=authority,
            repository_root=repository_root,
        )
        if not verification.accepted:
            raise ValueError("candidate failed verification: " + "; ".join(verification.errors))
        temporary.rename(root)
        return verification
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def verify_candidate_directory(
    root: Path,
    *,
    authority: TrustedCandidateAuthority,
    repository_root: Path,
) -> CandidateVerification:
    family_lock = _load_json(root / "family-lock.json")
    pinned = _load_json(root / "revisions" / "pinned-revisions.json")
    records: list[dict[str, Any]] = []
    for split in _SPLITS:
        relative = "heldout/test.jsonl" if split == "test" else f"canonical/{split}.jsonl"
        records.extend(_load_jsonl(root / relative))
    result = verify_candidate(
        records=records,
        family_lock=family_lock,
        pinned=pinned,
        authority=authority,
    )
    directory_errors = _verify_directory_artifacts(
        root,
        records,
        pinned,
        authority,
    )
    source_errors = _verify_trusted_sources(authority, repository_root)
    return CandidateVerification(
        candidate_id=result.candidate_id,
        record_count=result.record_count,
        split_counts=result.split_counts,
        unique_composition_ratio=result.unique_composition_ratio,
        maximum_response_share=result.maximum_response_share,
        errors=tuple(sorted(set((*result.errors, *directory_errors, *source_errors)))),
    )


def _load_json(path: Path) -> dict[str, Any]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, Any], value)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value: object = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"expected JSON object: {path}:{line_number}")
        records.append(cast(dict[str, Any], value))
    return records


def _write_candidate_files(
    root: Path,
    candidate: GeneratedCandidate,
    authority: TrustedCandidateAuthority,
) -> None:
    for relative in (
        "canonical",
        "gemini",
        "heldout",
        "manifests",
        "regressions",
        "reports",
        "revisions",
    ):
        directory = root / relative
        directory.mkdir(mode=0o700)
    records_by_split = {
        split: [record for record in candidate.records if record.get("split") == split]
        for split in _SPLITS
    }
    _write_json(root / "family-lock.json", candidate.family_lock)
    _write_json(
        root / "revisions" / "pinned-revisions.json",
        candidate.pinned_revisions,
    )
    _write_json(
        root / "regressions" / "v2-word-limit-regressions.json",
        candidate.regression_manifest,
    )
    for split in _SPLITS:
        records = records_by_split[split]
        relative = (
            Path("heldout/test.jsonl") if split == "test" else Path(f"canonical/{split}.jsonl")
        )
        _write_jsonl(root / relative, records)
        _write_json(
            root / "manifests" / f"{split}.manifest.json",
            {
                "record_count": len(records),
                "record_digests": [
                    cast(dict[str, Any], record["lineage"])["record_content_sha256"]
                    for record in records
                ],
                "split": split,
            },
        )
    system_instruction = cast(str, candidate.pinned_revisions["system_instruction"])
    for split in ("train", "validation"):
        _write_jsonl(
            root / "gemini" / f"{split}.jsonl",
            [_provider_row(record, system_instruction) for record in records_by_split[split]],
        )

    artifact_paths = sorted(
        item.relative_to(root).as_posix() for item in root.rglob("*") if item.is_file()
    )
    artifacts = {
        relative: sha256((root / relative).read_bytes()).hexdigest() for relative in artifact_paths
    }
    manifest = {
        "artifacts": artifacts,
        "authority_digest": authority.authority_digest,
        "candidate_id": candidate.pinned_revisions["candidate_id"],
        "external_dispatch_witness": {"status": "absent"},
        "governance_metadata": _GOVERNANCE_METADATA,
        "production_eligible": False,
        "provider_dispatch_allowed": False,
        "record_count": len(candidate.records),
        "release_eligible": False,
        "training_eligible": False,
        "upload_made": False,
    }
    _write_json(root / "manifest.json", manifest)
    no_upload: dict[str, Any] = {
        "cancellation_control": "not-provisioned",
        "candidate_manifest_sha256": sha256((root / "manifest.json").read_bytes()).hexdigest(),
        "decision": "no-upload",
        "endpoint_cleanup_control": "not-provisioned",
        "external_dispatch_witness_status": "absent",
        "kill_switch_control": "not-provisioned",
        "provider_call_made": False,
        "retention_control": "pending-human-decision",
        "upload_made": False,
    }
    no_upload["packet_digest"] = digest(no_upload)
    _write_json(root / "reports" / "no-upload-decision.json", no_upload)

    checksums: list[str] = []
    for item in sorted(root.rglob("*")):
        if item.is_file() and item.name != "SHA256SUMS":
            relative = item.relative_to(root).as_posix()
            checksums.append(f"{sha256(item.read_bytes()).hexdigest()}  {relative}")
    _write_text(root / "SHA256SUMS", "\n".join(checksums) + "\n")


def _write_json(path: Path, value: object) -> None:
    _write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: Sequence[object]) -> None:
    _write_text(path, "\n".join(canonical_json(row) for row in rows) + "\n")


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    os.chmod(path, 0o600)


def _verify_directory_artifacts(
    root: Path,
    records: Sequence[dict[str, Any]],
    pinned: dict[str, Any],
    authority: TrustedCandidateAuthority,
) -> list[str]:
    errors: list[str] = []
    listed: dict[str, str] = {}
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            errors.append("invalid SHA256SUMS line")
            continue
        observed_digest, relative = parts
        candidate = Path(relative)
        if (
            not _SHA256.fullmatch(observed_digest)
            or candidate.is_absolute()
            or ".." in candidate.parts
            or relative in listed
        ):
            errors.append(f"invalid checksum identity:{relative}")
            continue
        listed[relative] = observed_digest
        target = root / candidate
        if not target.is_file() or sha256(target.read_bytes()).hexdigest() != observed_digest:
            errors.append(f"checksum mismatch:{relative}")
    actual = {item.relative_to(root).as_posix() for item in root.rglob("*") if item.is_file()}
    if set(listed) != actual - {"SHA256SUMS"}:
        errors.append("SHA256SUMS completeness mismatch")
    if actual != set(_EXPECTED_FILES):
        errors.append("candidate artifact allowlist mismatch")

    manifest = _load_json(root / "manifest.json")
    if (
        manifest.get("record_count") != len(records)
        or manifest.get("authority_digest") != authority.authority_digest
        or digest(manifest.get("governance_metadata")) != authority.governance_metadata_sha256
        or manifest.get("governance_metadata") != _GOVERNANCE_METADATA
        or manifest.get("external_dispatch_witness") != {"status": "absent"}
        or manifest.get("provider_dispatch_allowed") is not False
        or manifest.get("upload_made") is not False
        or manifest.get("training_eligible") is not False
        or manifest.get("release_eligible") is not False
        or manifest.get("production_eligible") is not False
    ):
        errors.append("manifest eligibility or count mismatch")
    artifacts_value = manifest.get("artifacts")
    artifacts = cast(dict[str, Any], artifacts_value) if isinstance(artifacts_value, dict) else {}
    if set(artifacts) != set(_MANIFEST_ARTIFACTS):
        errors.append("manifest artifact allowlist mismatch")
    for relative, expected in artifacts.items():
        target = root / relative
        if (
            not isinstance(expected, str)
            or not target.is_file()
            or sha256(target.read_bytes()).hexdigest() != expected
        ):
            errors.append(f"manifest artifact mismatch:{relative}")

    records_by_split = {
        split: [record for record in records if record.get("split") == split] for split in _SPLITS
    }
    for split in _SPLITS:
        split_manifest = _load_json(root / "manifests" / f"{split}.manifest.json")
        expected_digests = [
            cast(dict[str, Any], record["lineage"])["record_content_sha256"]
            for record in records_by_split[split]
        ]
        if (
            split_manifest.get("record_count") != len(expected_digests)
            or split_manifest.get("record_digests") != expected_digests
        ):
            errors.append(f"split manifest mismatch:{split}")
    if (root / "gemini" / "test.jsonl").exists():
        errors.append("heldout Gemini export is forbidden")
    errors.extend(verify_provider_exports(root, records, pinned))
    errors.extend(_verify_regression_manifest(root, records, authority))

    no_upload = _load_json(root / "reports" / "no-upload-decision.json")
    observed_packet_digest = no_upload.pop("packet_digest", None)
    if (
        observed_packet_digest != digest(no_upload)
        or no_upload.get("decision") != "no-upload"
        or no_upload.get("external_dispatch_witness_status") != "absent"
        or no_upload.get("provider_call_made") is not False
        or no_upload.get("upload_made") is not False
        or no_upload.get("candidate_manifest_sha256")
        != sha256((root / "manifest.json").read_bytes()).hexdigest()
        or no_upload.get("retention_control") != "pending-human-decision"
        or no_upload.get("cancellation_control") != "not-provisioned"
        or no_upload.get("endpoint_cleanup_control") != "not-provisioned"
        or no_upload.get("kill_switch_control") != "not-provisioned"
    ):
        errors.append("no-upload packet mismatch")
    return errors


def _verify_regression_manifest(
    root: Path,
    records: Sequence[dict[str, Any]],
    authority: TrustedCandidateAuthority,
) -> list[str]:
    errors: list[str] = []
    try:
        manifest = _load_json(root / "regressions" / "v2-word-limit-regressions.json")
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return ["regression manifest is missing or invalid"]
    raw_regressions = manifest.get("regressions")
    regressions = cast(list[object], raw_regressions) if isinstance(raw_regressions, list) else []
    expected_sources = {
        record_id: (record_sha256, word_count)
        for record_id, record_sha256, word_count in authority.regression_source_bindings
    }
    records_by_id = {str(record.get("record_id")): record for record in records}
    observed_sources: set[str] = set()
    if (
        manifest.get("source_candidate") != "vivi-behavior-synthetic-v2"
        or manifest.get("target_candidate") != authority.candidate_id
        or len(regressions) != len(expected_sources)
    ):
        errors.append("regression manifest identity mismatch")
    for raw_regression in regressions:
        if not isinstance(raw_regression, dict):
            errors.append("regression entry is invalid")
            continue
        regression = cast(dict[str, Any], raw_regression)
        source_id = str(regression.get("source_record_id", ""))
        source = expected_sources.get(source_id)
        replacement_id = str(regression.get("replacement_record_id", ""))
        replacement = records_by_id.get(replacement_id)
        observed_sources.add(source_id)
        if (
            source is None
            or regression.get("source_record_sha256") != source[0]
            or regression.get("source_word_count") != source[1]
            or source[1] <= 15
            or regression.get("requirement") != "assistant-response-max-15-words"
            or replacement is None
        ):
            errors.append(f"regression source binding mismatch:{source_id}")
            continue
        messages = cast(list[dict[str, Any]], replacement.get("messages", []))
        lineage = cast(dict[str, Any], replacement.get("lineage", {}))
        replacement_word_count = (
            count_words(str(messages[1].get("content", ""))) if len(messages) == 2 else -1
        )
        if (
            regression.get("replacement_record_sha256") != lineage.get("record_content_sha256")
            or regression.get("replacement_word_count") != replacement_word_count
            or replacement_word_count > 15
        ):
            errors.append(f"regression replacement mismatch:{source_id}")
    if observed_sources != set(expected_sources):
        errors.append("regression source set mismatch")
    return errors


def verify_provider_exports(
    root: Path,
    records: Sequence[dict[str, Any]],
    pinned: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    system_instruction = pinned.get("system_instruction")
    if not isinstance(system_instruction, str) or not system_instruction.strip():
        return ["provider system instruction is missing"]
    if safety_findings(system_instruction):
        errors.append("provider system instruction failed safety scan")

    for split in ("train", "validation"):
        path = root / "gemini" / f"{split}.jsonl"
        try:
            observed = _load_jsonl(path)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            errors.append(f"provider export is missing or invalid:{split}")
            continue
        canonical_records = [record for record in records if record.get("split") == split]
        expected = [_provider_row(record, system_instruction) for record in canonical_records]
        if len(observed) != len(expected):
            errors.append(f"provider export row count mismatch:{split}")
        for index, (actual_row, expected_row) in enumerate(
            zip(observed, expected, strict=False),
            1,
        ):
            if canonical_json(actual_row) != canonical_json(expected_row):
                errors.append(f"provider export divergence:{split}:{index}")
            for text in _provider_text(actual_row):
                for finding in safety_findings(text):
                    errors.append(f"provider export safety finding:{split}:{index}:{finding}")
    return errors


def _provider_row(
    record: dict[str, Any],
    system_instruction: str,
) -> dict[str, Any]:
    messages_value = record.get("messages")
    messages = cast(list[dict[str, Any]], messages_value)
    return {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [
            {"role": "user", "parts": [{"text": messages[0]["content"]}]},
            {"role": "model", "parts": [{"text": messages[1]["content"]}]},
        ],
    }


def _provider_text(row: dict[str, Any]) -> tuple[str, ...]:
    texts: list[str] = []
    system_value = row.get("systemInstruction")
    if isinstance(system_value, dict):
        system = cast(dict[str, Any], system_value)
        parts = system.get("parts")
        if isinstance(parts, list):
            for part_value in cast(list[object], parts):
                if not isinstance(part_value, dict):
                    continue
                part = cast(dict[str, Any], part_value)
                texts.append(str(part.get("text", "")))
    contents_value = row.get("contents")
    if isinstance(contents_value, list):
        for content_value in cast(list[object], contents_value):
            if not isinstance(content_value, dict):
                continue
            content = cast(dict[str, Any], content_value)
            parts = content.get("parts")
            if isinstance(parts, list):
                for part_value in cast(list[object], parts):
                    if not isinstance(part_value, dict):
                        continue
                    part = cast(dict[str, Any], part_value)
                    texts.append(str(part.get("text", "")))
    return tuple(texts)


def _verify_trusted_sources(
    authority: TrustedCandidateAuthority,
    repository_root: Path,
) -> list[str]:
    errors: list[str] = []
    root = repository_root.resolve()
    for label, relative, expected, semantic_digest in (
        (
            "verifier",
            authority.verifier_source_path,
            authority.verifier_source_sha256,
            None,
        ),
        (
            "text-quality",
            authority.text_quality_source_path,
            authority.text_quality_source_sha256,
            None,
        ),
        (
            "generator",
            authority.generator_source_path,
            authority.generator_source_sha256,
            None,
        ),
        (
            "store",
            authority.store_source_path,
            authority.store_source_sha256,
            None,
        ),
        (
            "voice-rubric",
            authority.voice_rubric_source_path,
            authority.voice_rubric_file_sha256,
            authority.voice_rubric_semantic_sha256,
        ),
        (
            "domain-pack",
            authority.domain_pack_source_path,
            authority.domain_pack_file_sha256,
            authority.domain_pack_semantic_sha256,
        ),
    ):
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            errors.append(f"trusted {label} source path is invalid")
            continue
        target = (root / candidate).resolve()
        if target != root and root not in target.parents:
            errors.append(f"trusted {label} source escapes repository")
            continue
        if (
            not _SHA256.fullmatch(expected)
            or not target.is_file()
            or sha256(target.read_bytes()).hexdigest() != expected
        ):
            errors.append(f"trusted {label} source digest mismatch")
            continue
        if semantic_digest is not None:
            try:
                document = _load_json(target)
            except (ValueError, json.JSONDecodeError):
                errors.append(f"trusted {label} semantic document is invalid")
                continue
            if document.get("semantic_digest") != semantic_digest:
                errors.append(f"trusted {label} semantic digest mismatch")
    return errors
