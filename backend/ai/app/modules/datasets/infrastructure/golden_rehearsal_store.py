"""Private local storage adapter for synthetic Golden-grade rehearsal bundles."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

from app.modules.datasets.application.evaluation.golden_rehearsal import (
    RehearsalBundle,
    verify_rehearsal_bundle,
)
from app.modules.datasets.domain import RegistryInvariantError


class LocalGoldenRehearsalStore:
    """Write immutable rehearsal bundles under a content digest."""

    def __init__(self, root: Path) -> None:
        if root.is_symlink():
            raise RegistryInvariantError("rehearsal-store root cannot be a symlink")
        self._root = root.resolve()
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self._root.is_dir() or self._root.is_symlink():
            raise RegistryInvariantError("rehearsal-store root must be a directory")
        self._root.chmod(0o700)

    def put(self, bundle: RehearsalBundle) -> Path:
        target = self._target(bundle.bundle_digest)
        if target.exists():
            self.verify(bundle.bundle_digest)
            return target

        temporary = Path(tempfile.mkdtemp(prefix=".rehearsal-", dir=self._root))
        try:
            temporary.chmod(0o700)
            _write_private_file(temporary / "cases.jsonl", bundle.cases_jsonl)
            _write_private_file(temporary / "manifest.json", bundle.manifest_json)
            try:
                os.replace(temporary, target)
            except OSError:
                if not target.exists():
                    raise
                self.verify(bundle.bundle_digest)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
        self.verify(bundle.bundle_digest)
        return target

    def verify(self, bundle_digest: str) -> dict[str, object]:
        target = self._target(bundle_digest)
        if target.is_symlink() or not target.is_dir():
            raise RegistryInvariantError("rehearsal bundle directory is not trustworthy")
        manifest = target / "manifest.json"
        cases = target / "cases.jsonl"
        if manifest.is_symlink() or cases.is_symlink():
            raise RegistryInvariantError("rehearsal bundle cannot contain symlinks")
        if not manifest.is_file() or not cases.is_file():
            raise RegistryInvariantError("rehearsal bundle files must be regular files")
        if manifest.stat().st_size > 256 * 1024 or cases.stat().st_size > 10 * 1024 * 1024:
            raise RegistryInvariantError("rehearsal bundle exceeds local verification limits")
        if stat.S_IMODE(self._root.stat().st_mode) != 0o700:
            raise RegistryInvariantError("rehearsal-store root must remain private")
        if stat.S_IMODE(target.stat().st_mode) != 0o700:
            raise RegistryInvariantError("rehearsal bundle directory must remain private")
        if any(
            stat.S_IMODE(path.stat().st_mode) != 0o600
            for path in (manifest, cases)
            if path.exists()
        ):
            raise RegistryInvariantError("rehearsal bundle files must remain private")
        try:
            cases_bytes = cases.read_bytes()
            verified = verify_rehearsal_bundle(
                manifest_bytes=manifest.read_bytes(),
                cases_bytes=cases_bytes,
                expected_digest=bundle_digest,
            )
            _verify_case_policy(cases_bytes)
            return verified
        except OSError as error:
            raise RegistryInvariantError("rehearsal bundle is incomplete") from error

    def _target(self, bundle_digest: str) -> Path:
        if len(bundle_digest) != 64 or any(
            character not in "0123456789abcdef" for character in bundle_digest
        ):
            raise RegistryInvariantError("rehearsal bundle digest must be SHA-256 hex")
        target = self._root / bundle_digest
        if target.parent != self._root:
            raise RegistryInvariantError("rehearsal bundle path escapes storage root")
        return target


def _write_private_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _verify_case_policy(cases_bytes: bytes) -> None:
    try:
        cases = tuple(json.loads(line) for line in cases_bytes.splitlines() if line)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegistryInvariantError("rehearsal cases are unreadable") from error
    for case in cases:
        if (
            case.get("allowed_use") != "evaluation"
            or case.get("review", {}).get("status") != "pending"
            or case.get("lineage", {}).get("source_refs") != []
            or case.get("review", {}).get("adjudication_evidence") != []
        ):
            raise RegistryInvariantError(
                "rehearsal cases must remain pending, synthetic, and evaluation-only"
            )
