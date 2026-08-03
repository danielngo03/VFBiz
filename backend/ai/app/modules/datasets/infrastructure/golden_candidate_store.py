"""Private, atomic filesystem store for governed Golden candidate packets."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from app.modules.datasets.application.evaluation.golden_candidate import (
    GoldenCandidateBundle,
    verify_golden_candidate_bundle,
)
from app.modules.datasets.domain import RegistryInvariantError


def write_golden_candidate_bundle(bundle: GoldenCandidateBundle, root: Path) -> Path:
    """Atomically persist one verified, content-addressed candidate packet."""

    authority_value = bundle.manifest.get("authority_digests")
    authority = (
        {
            key: str(value)
            for key, value in cast(Mapping[str, object], authority_value).items()
        }
        if isinstance(authority_value, Mapping)
        else {}
    )
    verify_golden_candidate_bundle(
        bundle=bundle,
        expected_taxonomy_sha256=str(bundle.manifest.get("taxonomy_sha256", "")),
        expected_authority_sha256=authority,
        expected_generator_source_sha256=str(
            bundle.manifest.get("generator_source_sha256", "")
        ),
    )
    target = root / bundle.bundle_digest
    files = _bundle_files(bundle)
    if target.exists():
        _verify_persisted_bundle(target, files)
        return target

    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    temporary = Path(tempfile.mkdtemp(prefix=".golden-candidate-", dir=root))
    try:
        for relative, payload in files.items():
            path = temporary / relative
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes(payload)
            path.chmod(0o600)
        checksums = "".join(
            f"{hashlib.sha256(payload).hexdigest()}  {relative}\n"
            for relative, payload in sorted(files.items())
        ).encode("ascii")
        checksum_path = temporary / "SHA256SUMS"
        checksum_path.write_bytes(checksums)
        checksum_path.chmod(0o600)
        for directory in (temporary, temporary / "authority"):
            directory.chmod(0o700)
        os.replace(temporary, target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return target


def _bundle_files(bundle: GoldenCandidateBundle) -> dict[str, bytes]:
    return {
        "authority/authority-snapshot.json": bundle.authority_snapshot_json,
        "authority/generator.py": bundle.generator_source_bytes,
        "cases.jsonl": bundle.cases_jsonl,
        "family-lock.json": bundle.family_lock_json,
        "fingerprint-report.json": bundle.fingerprint_report_json,
        "manifest.json": bundle.manifest_json,
    }


def _verify_persisted_bundle(target: Path, expected: Mapping[str, bytes]) -> None:
    if not target.is_dir() or target.is_symlink():
        raise RegistryInvariantError("persisted Golden candidate target is unsafe")
    for relative, payload in expected.items():
        path = target / relative
        if not path.is_file() or path.is_symlink() or path.read_bytes() != payload:
            raise RegistryInvariantError("persisted Golden candidate differs from bundle")
    checksum_path = target / "SHA256SUMS"
    expected_sums = "".join(
        f"{hashlib.sha256(payload).hexdigest()}  {relative}\n"
        for relative, payload in sorted(expected.items())
    ).encode("ascii")
    if (
        not checksum_path.is_file()
        or checksum_path.is_symlink()
        or checksum_path.read_bytes() != expected_sums
    ):
        raise RegistryInvariantError("persisted Golden candidate checksums are invalid")


__all__ = ["write_golden_candidate_bundle"]
