"""Private atomic filesystem store for governed red-team candidate packets."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

from app.modules.datasets.application.evaluation.red_team_verifier import (
    RedTeamCandidateBundle,
    build_red_team_candidate_bundle,
    verify_red_team_candidate_bundle,
)
from app.modules.datasets.domain import RegistryInvariantError


def write_red_team_candidate_bundle(
    bundle: RedTeamCandidateBundle, root: Path
) -> Path:
    """Verify and atomically persist a content-addressed restricted packet."""

    generator_source, verifier_source = _authority_sources()
    verify_red_team_candidate_bundle(
        bundle,
        expected_generator_source_bytes=generator_source,
        expected_verifier_source_bytes=verifier_source,
    )
    _ensure_safe_root(root)
    files = _bundle_files(bundle)
    target = root / bundle.bundle_digest
    if target.exists() or target.is_symlink():
        _verify_persisted_bundle(target, files)
        return target

    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    temporary = Path(tempfile.mkdtemp(prefix=".red-team-candidate-", dir=root))
    try:
        for relative, payload in files.items():
            path = temporary / relative
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes(payload)
            path.chmod(0o600)
        checksums = _checksum_bytes(files)
        checksum_path = temporary / "SHA256SUMS"
        checksum_path.write_bytes(checksums)
        checksum_path.chmod(0o600)
        for directory in (temporary, temporary / "authority"):
            directory.chmod(0o700)
        os.replace(temporary, target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    _verify_persisted_bundle(target, files)
    return target


def verify_persisted_red_team_candidate(target: Path) -> None:
    """Replay byte, checksum, permission and file-set verification from disk."""

    if not target.is_dir() or target.is_symlink():
        raise RegistryInvariantError("persisted red-team candidate target is unsafe")
    manifest_path = target / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RegistryInvariantError("persisted red-team candidate manifest is missing")
    expected_files = {
        "adversarial-cases.jsonl",
        "authority/generator.py",
        "authority/verifier.py",
        "family-lock.json",
        "manifest.json",
        "validation-report.json",
    }
    _verify_file_set(target, expected_files)
    files = {
        relative: (target / relative).read_bytes() for relative in expected_files
    }
    _verify_checksums(target, files)
    bundle = RedTeamCandidateBundle(
        bundle_digest=target.name,
        rows_jsonl=files["adversarial-cases.jsonl"],
        family_lock_json=files["family-lock.json"],
        validation_report_json=files["validation-report.json"],
        manifest_json=files["manifest.json"],
        generator_source_bytes=files["authority/generator.py"],
        verifier_source_bytes=files["authority/verifier.py"],
    )
    generator_source, verifier_source = _authority_sources()
    verify_red_team_candidate_bundle(
        bundle,
        expected_generator_source_bytes=generator_source,
        expected_verifier_source_bytes=verifier_source,
    )
    _verify_permissions(target)


def build_current_red_team_candidate_bundle() -> RedTeamCandidateBundle:
    """Build a candidate against the repository-owned source authority."""

    generator_source, verifier_source = _authority_sources()
    return build_red_team_candidate_bundle(
        generator_source_bytes=generator_source,
        verifier_source_bytes=verifier_source,
    )


def _bundle_files(bundle: RedTeamCandidateBundle) -> dict[str, bytes]:
    return {
        "adversarial-cases.jsonl": bundle.rows_jsonl,
        "authority/generator.py": bundle.generator_source_bytes,
        "authority/verifier.py": bundle.verifier_source_bytes,
        "family-lock.json": bundle.family_lock_json,
        "manifest.json": bundle.manifest_json,
        "validation-report.json": bundle.validation_report_json,
    }


def _verify_persisted_bundle(target: Path, expected: Mapping[str, bytes]) -> None:
    if not target.is_dir() or target.is_symlink():
        raise RegistryInvariantError("persisted red-team candidate target is unsafe")
    _verify_file_set(target, set(expected))
    for relative, payload in expected.items():
        path = target / relative
        if not path.is_file() or path.is_symlink() or path.read_bytes() != payload:
            raise RegistryInvariantError("persisted red-team candidate differs from bundle")
    _verify_checksums(target, expected)
    _verify_permissions(target)


def _verify_file_set(target: Path, expected_files: set[str]) -> None:
    actual_files = {
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_files != expected_files | {"SHA256SUMS"}:
        raise RegistryInvariantError("persisted red-team candidate file set mismatch")


def _verify_checksums(target: Path, files: Mapping[str, bytes]) -> None:
    checksum_path = target / "SHA256SUMS"
    if (
        not checksum_path.is_file()
        or checksum_path.is_symlink()
        or checksum_path.read_bytes() != _checksum_bytes(files)
    ):
        raise RegistryInvariantError("persisted red-team candidate checksums are invalid")


def _checksum_bytes(files: Mapping[str, bytes]) -> bytes:
    return "".join(
        f"{hashlib.sha256(payload).hexdigest()}  {relative}\n"
        for relative, payload in sorted(files.items())
    ).encode("ascii")


def _verify_permissions(target: Path) -> None:
    directories = [target, *(path for path in target.rglob("*") if path.is_dir())]
    files = [path for path in target.rglob("*") if path.is_file()]
    if any((path.stat().st_mode & 0o777) != 0o700 for path in directories):
        raise RegistryInvariantError("red-team candidate directory permissions are unsafe")
    if any((path.stat().st_mode & 0o777) != 0o600 for path in files):
        raise RegistryInvariantError("red-team candidate file permissions are unsafe")


def _ensure_safe_root(root: Path) -> None:
    if root.exists() and (not root.is_dir() or root.is_symlink()):
        raise RegistryInvariantError("red-team candidate root is unsafe")


def _authority_sources() -> tuple[bytes, bytes]:
    evaluation_root = Path(__file__).parents[1] / "application" / "evaluation"
    return (
        (evaluation_root / "red_team_generator.py").read_bytes(),
        (evaluation_root / "red_team_verifier.py").read_bytes(),
    )


__all__ = [
    "build_current_red_team_candidate_bundle",
    "verify_persisted_red_team_candidate",
    "write_red_team_candidate_bundle",
]
