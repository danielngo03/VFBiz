from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app.modules.datasets.domain import RegistryInvariantError
from app.modules.datasets.infrastructure.scanners.artifact_inspection import (
    inspect_artifact,
    write_inspection_report,
)

_MEDIA_TYPES = {
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".parquet": "application/vnd.apache.parquet",
}


@dataclass(frozen=True, slots=True)
class LocalScanSummary:
    artifact_count: int
    byte_size: int
    record_count: int
    candidate_pass_count: int
    blocked_count: int
    manifest_sha256: str


def scan_local_downloads(*, download_root: Path, report_root: Path) -> LocalScanSummary:
    root = download_root.resolve(strict=True)
    if root.is_symlink() or not root.is_dir():
        raise RegistryInvariantError("download root must be a non-symlink directory")
    report_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    total_bytes = 0
    total_records = 0
    passed = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if _is_hugging_face_transport_metadata(relative):
            # `hf download --local-dir` writes resumable transport metadata here.
            # It is not source payload and must never enter lineage or record counts.
            continue
        media_type = _MEDIA_TYPES.get(path.suffix.lower())
        if media_type is None:
            raise RegistryInvariantError(f"unsupported downloaded artifact: {path}")
        report = inspect_artifact(path, media_type=media_type)
        report_path = report_root / relative.parent / f"{relative.name}.inspection.json"
        report_digest = write_inspection_report(report, report_path)
        total_bytes += report.byte_size
        total_records += report.record_count
        passed += int(report.passed_for_candidate)
        entries.append(
            {
                "artifact_path": str(relative),
                "artifact_sha256": report.artifact_sha256,
                "byte_size": report.byte_size,
                "record_count": report.record_count,
                "report_path": str(report_path.relative_to(report_root)),
                "report_sha256": report_digest,
                "passed_for_candidate": report.passed_for_candidate,
                "blockers": list(report.blockers),
            }
        )
    manifest = {
        "schema_version": 1,
        # Evidence must be portable and must not disclose the operator's
        # machine path. The caller identity and source rights live in the
        # separate governed receipt, not in this content inspection report.
        "download_root": "local-downloads",
        "artifacts": entries,
    }
    canonical = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest_sha256 = hashlib.sha256(canonical).hexdigest()
    manifest["manifest_sha256"] = manifest_sha256
    manifest_path = report_root / "inspection-manifest.json"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(manifest_path)
    return LocalScanSummary(
        artifact_count=len(entries),
        byte_size=total_bytes,
        record_count=total_records,
        candidate_pass_count=passed,
        blocked_count=len(entries) - passed,
        manifest_sha256=manifest_sha256,
    )


def _is_hugging_face_transport_metadata(relative: Path) -> bool:
    parts = relative.parts
    return any(
        parts[index : index + 2] == (".cache", "huggingface")
        for index in range(len(parts) - 1)
    )
