from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from app.modules.datasets.domain import RegistryInvariantError
from app.modules.datasets.infrastructure.formats.safe_archive import (
    ArchiveLimits,
    extract_inert_zip,
)


def _archive(path: Path, entries: dict[str, bytes]) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as zipped:
        for name, payload in entries.items():
            zipped.writestr(name, payload)


def test_extracts_only_inert_supported_records_with_private_permissions(tmp_path: Path) -> None:
    archive = tmp_path / "dataset.zip"
    _archive(archive, {"suite/train.jsonl": b'{"question":"xin chao"}\n'})

    result = extract_inert_zip(archive, destination=tmp_path / "extracted")

    target = tmp_path / "extracted" / "suite" / "train.jsonl"
    assert result[0].relative_path == "suite/train.jsonl"
    assert result[0].byte_size == target.stat().st_size
    assert target.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "name",
    ["../escape.json", "/absolute.json", "payload.py"],
)
def test_rejects_unsafe_or_executable_paths(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "dataset.zip"
    _archive(archive, {name: b"{}"})

    with pytest.raises(RegistryInvariantError):
        extract_inert_zip(archive, destination=tmp_path / "extracted")


def test_rejects_symlink_and_archive_bomb_ratio(tmp_path: Path) -> None:
    symlink_archive = tmp_path / "symlink.zip"
    with ZipFile(symlink_archive, "w") as zipped:
        entry = ZipInfo("link.json")
        entry.external_attr = 0o120777 << 16
        zipped.writestr(entry, b"target")
    with pytest.raises(RegistryInvariantError, match="links"):
        extract_inert_zip(symlink_archive, destination=tmp_path / "symlink-output")

    bomb_archive = tmp_path / "bomb.zip"
    _archive(bomb_archive, {"records.json": b"0" * 20_000})
    with pytest.raises(RegistryInvariantError, match="compression-ratio"):
        extract_inert_zip(
            bomb_archive,
            destination=tmp_path / "bomb-output",
            limits=ArchiveLimits(max_compression_ratio=1),
        )


def test_rejects_symlinked_source_archive(tmp_path: Path) -> None:
    archive = tmp_path / "dataset.zip"
    _archive(archive, {"records.json": b"{}"})
    link = tmp_path / "dataset-link.zip"
    link.symlink_to(archive)

    with pytest.raises(RegistryInvariantError, match="non-symlink"):
        extract_inert_zip(link, destination=tmp_path / "extracted")
