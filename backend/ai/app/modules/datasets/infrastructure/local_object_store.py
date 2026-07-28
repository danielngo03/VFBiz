from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import BinaryIO

from app.modules.datasets.application.ports import StoredObject
from app.modules.datasets.domain import RegistryInvariantError, TrustZone


class LocalContentAddressedObjectStore:
    """Local development adapter with production-equivalent path invariants."""

    _CHUNK_BYTES = 1024 * 1024

    def __init__(self, root: Path) -> None:
        if root.is_symlink():
            raise RegistryInvariantError("object-store root cannot be a symlink")
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._root.chmod(0o700)

    def put_stream(
        self,
        *,
        zone: TrustZone,
        stream: BinaryIO,
        media_type: str,
        max_bytes: int,
    ) -> StoredObject:
        if max_bytes <= 0:
            raise RegistryInvariantError("object maximum size must be positive")
        suffix = _safe_suffix(media_type)
        zone_root = (self._root / zone.value).resolve()
        _assert_contained(self._root, zone_root)
        zone_root.mkdir(parents=True, exist_ok=True)
        zone_root.chmod(0o700)
        digest = hashlib.sha256()
        size = 0
        descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=zone_root)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                while chunk := stream.read(self._CHUNK_BYTES):
                    size += len(chunk)
                    if size > max_bytes:
                        raise RegistryInvariantError("object exceeds configured byte limit")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            sha256 = digest.hexdigest()
            destination = (zone_root / sha256[:2] / f"{sha256}{suffix}").resolve()
            _assert_contained(zone_root, destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.parent.chmod(0o700)
            if destination.exists():
                if (
                    destination.is_symlink()
                    or not destination.is_file()
                    or _hash_file(destination) != sha256
                ):
                    raise RegistryInvariantError("content-addressed destination is not trustworthy")
                temporary.unlink()
            else:
                os.replace(temporary, destination)
            destination.chmod(0o600)
            relative = destination.relative_to(self._root).as_posix()
            return StoredObject(uri=f"file://{relative}", sha256=sha256, byte_size=size)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def path_for_test(self, stored: StoredObject) -> Path:
        candidate = (self._root / stored.uri.removeprefix("file://")).resolve()
        _assert_contained(self._root, candidate)
        return candidate


def _safe_suffix(media_type: str) -> str:
    return {
        "application/json": ".json",
        "application/x-ndjson": ".jsonl",
        "text/csv": ".csv",
        "application/vnd.apache.parquet": ".parquet",
    }.get(media_type, ".bin")


def _assert_contained(parent: Path, child: Path) -> None:
    if child != parent and parent not in child.parents:
        raise RegistryInvariantError("object path escapes the configured trust zone")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
