"""Bounded structural scanner for inert quarantine payloads."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from typing import BinaryIO

from app.modules.datasets.application.source_intake.models import ScanEvidence

_MAX_NDJSON_LINE_BYTES = 16 * 1024 * 1024


class StructuralQuarantineScanner:
    def scan_stream(self, stream: BinaryIO, *, media_type: str, byte_size: int) -> ScanEvidence:
        return scan_quarantine_stream(stream, media_type=media_type, byte_size=byte_size)


def scan_quarantine_payload(content: bytes, *, media_type: str) -> ScanEvidence:
    return scan_quarantine_stream(BytesIO(content), media_type=media_type, byte_size=len(content))


def scan_quarantine_stream(stream: BinaryIO, *, media_type: str, byte_size: int) -> ScanEvidence:
    stream.seek(0)
    content = stream.read(min(byte_size, 8 * 1024 * 1024))
    stream.seek(max(0, byte_size - 4))
    tail = stream.read(4)
    stream.seek(0)
    reasons: list[str] = []
    executable = content.startswith((b"\x7fELF", b"MZ"))
    archive = content.startswith((b"PK\x03\x04", b"\x1f\x8b"))
    structural_valid = (
        _validate_ndjson_stream(stream, expected_bytes=byte_size)
        if media_type == "application/x-ndjson"
        else _validate_structure(
            content,
            media_type,
            complete=byte_size <= len(content),
            tail=tail,
        )
    )
    stream.seek(0)
    if executable:
        reasons.append("executable-content")
    if archive:
        reasons.append("archive-content-not-allowed")
    if not structural_valid:
        reasons.append("invalid-structure")
    secret_candidates, pii_candidates = _scan_markers_stream(
        stream,
        secret_markers=(
            b"-----begin private key-----",
            b"aws_secret_access_key",
            b"api_key=",
        ),
        pii_markers=(b"email", b"phone", b"address"),
    )
    if secret_candidates:
        reasons.append("secret-candidate")
    return ScanEvidence(
        scanner_revision="vivi-quarantine-structural-v1",
        observed_sha256=_hash_stream(stream),
        media_type=media_type,
        byte_size=byte_size,
        structural_valid=structural_valid,
        executable_content_detected=executable,
        archive_content_detected=archive,
        pii_candidate_count=pii_candidates,
        secret_candidate_count=secret_candidates,
        passed=not reasons,
        reasons=tuple(reasons),
    )


def _scan_markers_stream(
    stream: BinaryIO,
    *,
    secret_markers: tuple[bytes, ...],
    pii_markers: tuple[bytes, ...],
) -> tuple[int, int]:
    markers = secret_markers + pii_markers
    max_marker_bytes = max(map(len, markers))
    counts = {marker: 0 for marker in markers}
    carry = b""
    stream.seek(0)
    while chunk := stream.read(1024 * 1024):
        lowered = (carry + chunk).lower()
        carry_size = len(carry)
        for marker in markers:
            start = 0
            while (index := lowered.find(marker, start)) >= 0:
                if index + len(marker) > carry_size:
                    counts[marker] += 1
                start = index + len(marker)
        carry = lowered[-(max_marker_bytes - 1) :]
    stream.seek(0)
    return (
        sum(counts[marker] for marker in secret_markers),
        sum(counts[marker] for marker in pii_markers),
    )


def _validate_ndjson_stream(stream: BinaryIO, *, expected_bytes: int) -> bool:
    consumed = 0
    records = 0
    try:
        stream.seek(0)
        while True:
            line = stream.readline(_MAX_NDJSON_LINE_BYTES + 1)
            if not line:
                break
            consumed += len(line)
            if len(line) > _MAX_NDJSON_LINE_BYTES:
                return False
            if line.strip():
                json.loads(line)
                records += 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return consumed == expected_bytes and records > 0


def _validate_structure(
    content: bytes, media_type: str, *, complete: bool = True, tail: bytes = b""
) -> bool:
    try:
        if media_type == "application/json":
            if not complete:
                return False
            json.loads(content)
        elif media_type == "application/x-ndjson":
            for line in content.splitlines():
                if line.strip():
                    json.loads(line)
        elif media_type == "application/vnd.apache.parquet":
            ending = content[-4:] if complete else tail
            return len(content) >= 4 and content[:4] == b"PAR1" and ending == b"PAR1"
        elif media_type in {"text/csv", "text/tab-separated-values"}:
            content.decode("utf-8")
        else:
            return False
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return True


def _hash_stream(stream: BinaryIO) -> str:
    stream.seek(0)
    digest = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()
