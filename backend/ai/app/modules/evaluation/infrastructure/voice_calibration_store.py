"""Private atomic store for ViVi voice calibration review packets."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from app.modules.evaluation.application.voice_authority import ViViTextVoiceAuthority
from app.modules.evaluation.application.voice_calibration import (
    VoiceCalibrationBundle,
    verify_voice_calibration_packet,
)


def write_voice_calibration_bundle(
    *,
    bundle: VoiceCalibrationBundle,
    authority: ViViTextVoiceAuthority,
    root: Path,
) -> Path:
    """Verify and atomically persist one immutable human-blocked packet."""

    verify_voice_calibration_packet(
        authority=authority,
        manifest_bytes=bundle.manifest_json,
        cases_bytes=bundle.cases_jsonl,
        expected_bundle_digest=bundle.bundle_digest,
    )
    files = {
        "cases.jsonl": bundle.cases_jsonl,
        "manifest.json": bundle.manifest_json,
    }
    target = root / bundle.bundle_digest
    if target.exists():
        _verify_existing(target, files)
        return target
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    temporary = Path(tempfile.mkdtemp(prefix=".voice-calibration-", dir=root))
    try:
        for name, payload in files.items():
            path = temporary / name
            path.write_bytes(payload)
            path.chmod(0o600)
        checksums = "".join(
            f"{hashlib.sha256(payload).hexdigest()}  {name}\n"
            for name, payload in sorted(files.items())
        ).encode("ascii")
        checksum_path = temporary / "SHA256SUMS"
        checksum_path.write_bytes(checksums)
        checksum_path.chmod(0o600)
        temporary.chmod(0o700)
        os.replace(temporary, target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return target


def _verify_existing(target: Path, files: dict[str, bytes]) -> None:
    if not target.is_dir() or target.is_symlink():
        raise ValueError("voice calibration target is unsafe")
    if target.stat().st_mode & 0o777 != 0o700:
        raise ValueError("voice calibration directory permissions are invalid")
    if {path.name for path in target.iterdir()} != {*files, "SHA256SUMS"}:
        raise ValueError("voice calibration target contains unbound files")
    for name, payload in files.items():
        path = target / name
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_mode & 0o777 != 0o600
            or path.read_bytes() != payload
        ):
            raise ValueError("voice calibration packet differs from existing evidence")
    expected = "".join(
        f"{hashlib.sha256(payload).hexdigest()}  {name}\n"
        for name, payload in sorted(files.items())
    ).encode("ascii")
    checksum_path = target / "SHA256SUMS"
    if (
        not checksum_path.is_file()
        or checksum_path.is_symlink()
        or checksum_path.stat().st_mode & 0o777 != 0o600
        or checksum_path.read_bytes() != expected
    ):
        raise ValueError("voice calibration checksums are invalid")


__all__ = ["write_voice_calibration_bundle"]
