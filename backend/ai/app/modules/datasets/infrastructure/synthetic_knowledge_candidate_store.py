"""Atomic restricted store for synthetic knowledge qualification packets."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

from app.modules.datasets.application.evaluation.synthetic_knowledge_verifier import (
    SyntheticKnowledgeCandidateBundle,
    build_synthetic_knowledge_candidate_bundle,
    verify_synthetic_knowledge_candidate_bundle,
)
from app.modules.datasets.domain import RegistryInvariantError


def build_current_synthetic_knowledge_candidate() -> SyntheticKnowledgeCandidateBundle:
    generator_source, verifier_source = _authority_sources()
    return build_synthetic_knowledge_candidate_bundle(
        generator_source_bytes=generator_source,
        verifier_source_bytes=verifier_source,
    )


def write_synthetic_knowledge_candidate(
    bundle: SyntheticKnowledgeCandidateBundle, root: Path
) -> Path:
    verify_synthetic_knowledge_candidate_bundle(bundle)
    _ensure_safe_root(root)
    files = _bundle_files(bundle)
    target = root / bundle.bundle_digest
    if target.exists() or target.is_symlink():
        _verify_persisted(target, files)
        return target

    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    temporary = Path(tempfile.mkdtemp(prefix=".synthetic-knowledge-", dir=root))
    try:
        for relative, payload in files.items():
            path = temporary / relative
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes(payload)
            path.chmod(0o600)
        checksum_path = temporary / "SHA256SUMS"
        checksum_path.write_bytes(_checksum_bytes(files))
        checksum_path.chmod(0o600)
        for directory in (temporary, temporary / "authority"):
            directory.chmod(0o700)
        os.replace(temporary, target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    _verify_persisted(target, files)
    return target


def verify_persisted_synthetic_knowledge_candidate(target: Path) -> None:
    if not target.is_dir() or target.is_symlink():
        raise RegistryInvariantError("persisted synthetic knowledge target is unsafe")
    expected_files = {
        "authority/generator.py",
        "authority/verifier.py",
        "document-lock.json",
        "manifest.json",
        "records.jsonl",
        "validation-report.json",
    }
    _verify_file_set(target, expected_files)
    files = {
        relative: (target / relative).read_bytes() for relative in expected_files
    }
    _verify_checksums(target, files)
    bundle = SyntheticKnowledgeCandidateBundle(
        bundle_digest=target.name,
        rows_jsonl=files["records.jsonl"],
        document_lock_json=files["document-lock.json"],
        validation_report_json=files["validation-report.json"],
        manifest_json=files["manifest.json"],
        generator_source_bytes=files["authority/generator.py"],
        verifier_source_bytes=files["authority/verifier.py"],
    )
    verify_synthetic_knowledge_candidate_bundle(bundle)
    _verify_permissions(target)


def _bundle_files(bundle: SyntheticKnowledgeCandidateBundle) -> dict[str, bytes]:
    return {
        "authority/generator.py": bundle.generator_source_bytes,
        "authority/verifier.py": bundle.verifier_source_bytes,
        "document-lock.json": bundle.document_lock_json,
        "manifest.json": bundle.manifest_json,
        "records.jsonl": bundle.rows_jsonl,
        "validation-report.json": bundle.validation_report_json,
    }


def _verify_persisted(target: Path, expected: Mapping[str, bytes]) -> None:
    if not target.is_dir() or target.is_symlink():
        raise RegistryInvariantError("persisted synthetic knowledge target is unsafe")
    _verify_file_set(target, set(expected))
    for relative, payload in expected.items():
        path = target / relative
        if not path.is_file() or path.is_symlink() or path.read_bytes() != payload:
            raise RegistryInvariantError("persisted synthetic knowledge packet differs")
    _verify_checksums(target, expected)
    _verify_permissions(target)


def _verify_file_set(target: Path, expected: set[str]) -> None:
    actual: set[str] = set()
    directories: set[str] = set()
    for path in target.rglob("*"):
        relative = path.relative_to(target).as_posix()
        if path.is_symlink():
            raise RegistryInvariantError("synthetic knowledge packet contains a symlink")
        metadata = path.lstat()
        if path.is_dir():
            directories.add(relative)
        elif path.is_file():
            if metadata.st_nlink != 1:
                raise RegistryInvariantError(
                    "synthetic knowledge packet contains a linked file"
                )
            actual.add(relative)
        else:
            raise RegistryInvariantError(
                "synthetic knowledge packet contains a non-regular entry"
            )
    if actual != expected | {"SHA256SUMS"}:
        raise RegistryInvariantError("synthetic knowledge file set mismatch")
    if directories != {"authority"}:
        raise RegistryInvariantError("synthetic knowledge directory set mismatch")


def _verify_checksums(target: Path, files: Mapping[str, bytes]) -> None:
    checksum_path = target / "SHA256SUMS"
    if (
        not checksum_path.is_file()
        or checksum_path.is_symlink()
        or checksum_path.read_bytes() != _checksum_bytes(files)
    ):
        raise RegistryInvariantError("synthetic knowledge checksums are invalid")


def _checksum_bytes(files: Mapping[str, bytes]) -> bytes:
    return "".join(
        f"{hashlib.sha256(payload).hexdigest()}  {relative}\n"
        for relative, payload in sorted(files.items())
    ).encode("ascii")


def _verify_permissions(target: Path) -> None:
    directories = [target, *(path for path in target.rglob("*") if path.is_dir())]
    files = [path for path in target.rglob("*") if path.is_file()]
    if any((path.stat().st_mode & 0o777) != 0o700 for path in directories):
        raise RegistryInvariantError("synthetic knowledge directory permissions are unsafe")
    if any((path.stat().st_mode & 0o777) != 0o600 for path in files):
        raise RegistryInvariantError("synthetic knowledge file permissions are unsafe")


def _ensure_safe_root(root: Path) -> None:
    if root.exists() and (not root.is_dir() or root.is_symlink()):
        raise RegistryInvariantError("synthetic knowledge root is unsafe")


def _authority_sources() -> tuple[bytes, bytes]:
    evaluation_root = Path(__file__).parents[1] / "application" / "evaluation"
    return (
        (evaluation_root / "synthetic_knowledge_candidate.py").read_bytes(),
        (evaluation_root / "synthetic_knowledge_verifier.py").read_bytes(),
    )


__all__ = [
    "build_current_synthetic_knowledge_candidate",
    "verify_persisted_synthetic_knowledge_candidate",
    "write_synthetic_knowledge_candidate",
]
