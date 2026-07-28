from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import ijson  # pyright: ignore[reportMissingTypeStubs]
import pyarrow as pa  # pyright: ignore[reportMissingTypeStubs]
import pyarrow.parquet as pq  # pyright: ignore[reportMissingTypeStubs]

from app.modules.datasets.domain import RegistryInvariantError

_CHUNK_BYTES = 1024 * 1024
_MAX_TEXT_FIELD_BYTES = 4 * 1024 * 1024
_SECRET_PATTERNS = {
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "hugging-face-token": re.compile(rb"\bhf_[A-Za-z0-9]{20,}\b"),
    "openai-key": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "aws-access-key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
}
_PII_PATTERNS = {
    "email": re.compile(rb"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    "ipv4": re.compile(
        rb"\b(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
        rb"(?:\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)){3}\b"
    ),
}


@dataclass(frozen=True, slots=True)
class ArtifactInspectionReport:
    schema_version: int
    artifact_path: str
    artifact_sha256: str
    byte_size: int
    media_type: str
    record_count: int
    schema_sha256: str
    malformed_records: int
    secret_findings: Mapping[str, int]
    pii_candidates: Mapping[str, int]
    malware_engine: str
    malware_signature_revision: str | None
    malware_status: str
    malware_findings: int
    completed_at: str
    passed_for_candidate: bool
    blockers: tuple[str, ...]

    def canonical_payload(self) -> dict[str, object]:
        return asdict(self)


def inspect_artifact(path: Path, *, media_type: str) -> ArtifactInspectionReport:
    """Inspect an inert artifact without executing source-supplied code."""

    resolved = path.resolve(strict=True)
    if not resolved.is_file() or resolved.is_symlink():
        raise RegistryInvariantError("dataset inspection requires a regular non-symlink file")
    byte_size = resolved.stat().st_size
    artifact_sha256, secret_findings, pii_candidates = _scan_bytes(resolved)
    record_count, schema_sha256, malformed_records = _inspect_records(
        resolved, media_type=media_type
    )
    malware_engine, signature_revision, malware_status, malware_findings = _clamav_scan(resolved)
    blockers: list[str] = []
    if malformed_records:
        blockers.append("malformed-records")
    if sum(secret_findings.values()):
        blockers.append("secret-findings")
    if sum(pii_candidates.values()):
        blockers.append("pii-review-required")
    if malware_status != "passed":
        blockers.append("production-malware-scan-required")
    if malware_findings:
        blockers.append("malware-findings")
    return ArtifactInspectionReport(
        schema_version=1,
        artifact_path=str(resolved),
        artifact_sha256=artifact_sha256,
        byte_size=byte_size,
        media_type=media_type,
        record_count=record_count,
        schema_sha256=schema_sha256,
        malformed_records=malformed_records,
        secret_findings=secret_findings,
        pii_candidates=pii_candidates,
        malware_engine=malware_engine,
        malware_signature_revision=signature_revision,
        malware_status=malware_status,
        malware_findings=malware_findings,
        completed_at=datetime.now(UTC).isoformat(),
        passed_for_candidate=not blockers,
        blockers=tuple(blockers),
    )


def write_inspection_report(report: ArtifactInspectionReport, destination: Path) -> str:
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = json.dumps(
        report.canonical_payload(), ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8")
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    temporary.write_bytes(payload + b"\n")
    temporary.chmod(0o600)
    temporary.replace(destination)
    return hashlib.sha256(payload).hexdigest()


def _scan_bytes(path: Path) -> tuple[str, dict[str, int], dict[str, int]]:
    digest = hashlib.sha256()
    secrets = {name: 0 for name in _SECRET_PATTERNS}
    pii = {name: 0 for name in _PII_PATTERNS}
    overlap = b""
    max_pattern = 256
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_BYTES):
            digest.update(chunk)
            window = overlap + chunk
            for name, pattern in _SECRET_PATTERNS.items():
                secrets[name] += sum(
                    match.end() > len(overlap) for match in pattern.finditer(window)
                )
            for name, pattern in _PII_PATTERNS.items():
                pii[name] += sum(match.end() > len(overlap) for match in pattern.finditer(window))
            overlap = window[-max_pattern:]
    return digest.hexdigest(), secrets, pii


def _inspect_records(path: Path, *, media_type: str) -> tuple[int, str, int]:
    if media_type == "application/vnd.apache.parquet":
        return _inspect_parquet(path)
    if media_type == "application/x-ndjson":
        return _inspect_ndjson(path)
    if media_type == "application/json":
        return _inspect_json(path)
    raise RegistryInvariantError(f"unsupported inspection media type: {media_type}")


def _inspect_parquet(path: Path) -> tuple[int, str, int]:
    parquet = cast(Any, pq).ParquetFile(path)
    schema = parquet.schema_arrow
    schema_digest = hashlib.sha256(str(schema).encode("utf-8")).hexdigest()
    rows = 0
    malformed = 0
    for batch in parquet.iter_batches(batch_size=2_048):
        rows += int(batch.num_rows)
        malformed += _oversized_text_values(batch)
    metadata_rows = int(parquet.metadata.num_rows)
    if rows != metadata_rows:
        malformed += abs(rows - metadata_rows)
    return rows, schema_digest, malformed


def _oversized_text_values(batch: Any) -> int:
    invalid = 0
    arrow_types = cast(Any, pa).types
    for column in batch.columns:
        if arrow_types.is_string(column.type) or arrow_types.is_large_string(column.type):
            for value in cast(list[object | None], column.to_pylist()):
                if isinstance(value, str) and len(value.encode("utf-8")) > _MAX_TEXT_FIELD_BYTES:
                    invalid += 1
    return invalid


def _inspect_ndjson(path: Path) -> tuple[int, str, int]:
    rows = 0
    malformed = 0
    keys: set[str] = set()
    with path.open("rb") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                item = cast(object, json.loads(line))
            except json.JSONDecodeError:
                malformed += 1
                continue
            rows += 1
            if isinstance(item, dict):
                keys.update(str(key) for key in cast(dict[object, object], item))
    return rows, _schema_digest(keys), malformed


def _inspect_json(path: Path) -> tuple[int, str, int]:
    prefix = path.read_bytes()[:4_096].lstrip()
    if not prefix:
        return 0, _schema_digest(set()), 1
    with path.open("rb") as stream:
        if prefix.startswith(b"["):
            return _inspect_json_records(cast(Any, ijson).items(stream, "item"))
        if b'"data"' in prefix:
            return _inspect_json_records(cast(Any, ijson).items(stream, "data.item"))
    return _inspect_ndjson(path)


def _inspect_json_records(records: Iterable[Any]) -> tuple[int, str, int]:
    rows = 0
    malformed = 0
    keys: set[str] = set()
    for item in records:
        rows += 1
        if not isinstance(item, dict):
            malformed += 1
            continue
        keys.update(str(key) for key in cast(dict[object, object], item))
    return rows, _schema_digest(keys), malformed


def _schema_digest(keys: set[str]) -> str:
    return hashlib.sha256(
        json.dumps(sorted(keys), separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _clamav_scan(path: Path) -> tuple[str, str | None, str, int]:
    executable = shutil.which("clamscan")
    if executable is None:
        return "clamav", None, "unavailable", 0
    database_value = os.environ.get("VFBIZ_AI_DATASET_CLAMAV_DATABASE")
    if not database_value:
        return "clamav", None, "unavailable", 0
    database = Path(database_value).expanduser().resolve()
    signatures = tuple(database.glob("*.cvd")) + tuple(database.glob("*.cld"))
    if not database.is_dir() or not signatures:
        return "clamav", None, "unavailable", 0
    newest_signature = max(item.stat().st_mtime for item in signatures)
    signature_age_seconds = datetime.now(UTC).timestamp() - newest_signature
    if signature_age_seconds > 48 * 60 * 60:
        return "clamav", None, "stale-signatures", 0
    version = subprocess.run(  # noqa: S603 - resolved executable, argument vector only
        [executable, f"--database={database}", "--version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    completed = subprocess.run(  # noqa: S603 - resolved executable, argument vector only
        [
            executable,
            f"--database={database}",
            "--no-summary",
            "--infected",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=max(60, min(3_600, path.stat().st_size // 250_000)),
    )
    if completed.returncode == 0:
        return "clamav", version, "passed", 0
    if completed.returncode == 1:
        return "clamav", version, "failed", 1
    return "clamav", version, "error", 0
