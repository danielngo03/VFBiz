"""Safe, inert archive extraction adapter."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from app.modules.datasets.domain import RegistryInvariantError

_CHUNK_BYTES = 1024 * 1024
_ALLOWED_SUFFIXES = {".json", ".jsonl", ".csv", ".parquet"}


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_entries: int = 10_000
    max_file_bytes: int = 512 * 1024 * 1024
    max_total_bytes: int = 2 * 1024 * 1024 * 1024
    max_compression_ratio: int = 100


@dataclass(frozen=True, slots=True)
class ExtractedArtifact:
    relative_path: str
    sha256: str
    byte_size: int


_DEFAULT_LIMITS = ArchiveLimits()


def extract_inert_zip(
    archive: Path,
    *,
    destination: Path,
    limits: ArchiveLimits = _DEFAULT_LIMITS,
) -> tuple[ExtractedArtifact, ...]:
    """Extract approved inert records while rejecting archive escape and bombs."""

    if archive.is_symlink():
        raise RegistryInvariantError("dataset archive must be a regular non-symlink file")
    source = archive.resolve(strict=True)
    if not source.is_file():
        raise RegistryInvariantError("dataset archive must be a regular non-symlink file")
    if destination.exists():
        raise RegistryInvariantError("archive destination must not already exist")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    try:
        with ZipFile(source) as zipped:
            entries = _validated_entries(zipped.infolist(), limits=limits)
            with tempfile.TemporaryDirectory(
                dir=destination.parent,
                prefix=f".{destination.name}-",
            ) as temporary_value:
                temporary = Path(temporary_value)
                temporary.chmod(0o700)
                artifacts = tuple(
                    _extract_entry(zipped, entry=entry, root=temporary) for entry in entries
                )
                os.replace(temporary, destination)
                destination.chmod(0o700)
                return artifacts
    except BadZipFile as error:
        raise RegistryInvariantError("dataset archive is not a valid ZIP file") from error


def _validated_entries(entries: list[ZipInfo], *, limits: ArchiveLimits) -> tuple[ZipInfo, ...]:
    files = [entry for entry in entries if not entry.is_dir()]
    if not files or len(files) > limits.max_entries:
        raise RegistryInvariantError("dataset archive entry count is outside policy")
    total = 0
    seen: set[str] = set()
    for entry in files:
        path = PurePosixPath(entry.filename)
        normalized = str(path)
        if path.is_absolute() or ".." in path.parts or normalized in seen:
            raise RegistryInvariantError("dataset archive contains an unsafe or duplicate path")
        seen.add(normalized)
        mode = entry.external_attr >> 16
        if stat.S_ISLNK(mode) or entry.flag_bits & 0x1:
            raise RegistryInvariantError("dataset archive cannot contain links or encrypted files")
        if path.suffix.lower() not in _ALLOWED_SUFFIXES:
            raise RegistryInvariantError("dataset archive contains an unsupported payload type")
        if entry.file_size < 0 or entry.file_size > limits.max_file_bytes:
            raise RegistryInvariantError("dataset archive entry exceeds the byte limit")
        if entry.file_size and (
            entry.compress_size <= 0
            or entry.file_size / entry.compress_size > limits.max_compression_ratio
        ):
            raise RegistryInvariantError("dataset archive exceeds the compression-ratio limit")
        total += entry.file_size
        if total > limits.max_total_bytes:
            raise RegistryInvariantError("dataset archive exceeds the total byte limit")
    return tuple(files)


def _extract_entry(zipped: ZipFile, *, entry: ZipInfo, root: Path) -> ExtractedArtifact:
    relative = PurePosixPath(entry.filename)
    target = root.joinpath(*relative.parts)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with zipped.open(entry, "r") as source, target.open("xb") as output:
        while chunk := source.read(_CHUNK_BYTES):
            size += len(chunk)
            if size > entry.file_size:
                raise RegistryInvariantError("dataset archive expanded beyond declared size")
            digest.update(chunk)
            output.write(chunk)
    if size != entry.file_size:
        raise RegistryInvariantError("dataset archive entry size does not match its manifest")
    target.chmod(0o600)
    return ExtractedArtifact(
        relative_path=str(relative),
        sha256=digest.hexdigest(),
        byte_size=size,
    )
