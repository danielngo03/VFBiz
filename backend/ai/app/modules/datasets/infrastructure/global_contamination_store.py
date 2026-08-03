"""Atomic local evidence store for global contamination reports."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from app.modules.datasets.application.evaluation.global_contamination import (
    compute_global_contamination_report_digest,
)
from app.modules.datasets.infrastructure.global_contamination_builder import (
    verify_governed_global_contamination_report,
)


def write_global_contamination_report(
    *, report: Mapping[str, object], root: Path, repository_root: Path
) -> Path:
    """Persist one canonical report by its verified content digest."""

    digest = report.get("report_digest")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("report_digest must be a SHA-256 value")
    if compute_global_contamination_report_digest(dict(report)) != digest:
        raise ValueError("report_digest does not match canonical report content")
    verify_governed_global_contamination_report(
        report=dict(report), repository_root=repository_root
    )
    canonical = json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    target = root / f"{digest}.json"
    if target.exists():
        if target.is_symlink() or target.read_bytes() != canonical:
            raise ValueError("persisted contamination report differs from evidence")
        return target
    descriptor, temporary_name = tempfile.mkstemp(prefix=".contamination-", dir=root)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


__all__ = ["write_global_contamination_report"]
