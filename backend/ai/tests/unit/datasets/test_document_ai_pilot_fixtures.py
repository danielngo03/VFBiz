from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.build_document_ai_pilot_fixtures import DEFAULT_FONT, build


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def test_pilot_pdfs_are_deterministic_private_and_fact_free(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_manifest = build(first, font_path=DEFAULT_FONT)
    second_manifest = build(second, font_path=DEFAULT_FONT)

    assert first_manifest == second_manifest
    assert _tree_digest(first) == _tree_digest(second)
    assert first_manifest["cloud_ocr_performed"] is False
    assert first_manifest["human_adjudicated"] is False
    assert first_manifest["release_eligible"] is False
    assert first_manifest["training_eligible"] is False
    assert first_manifest["upload_allowed"] is False
    assert {fixture["mode"] for fixture in first_manifest["fixtures"]} == {
        "image-only",
        "mixed-page",
        "native-text",
    }

    for path in first.rglob("*"):
        expected_mode = 0o700 if path.is_dir() else 0o600
        assert path.stat().st_mode & 0o777 == expected_mode
    for pdf in (first / "pdfs").glob("*.pdf"):
        assert pdf.read_bytes().startswith(b"%PDF-1.7")
        assert pdf.read_bytes().rstrip().endswith(b"%%EOF")

    manifest = json.loads((first / "manifest.json").read_text())
    assert manifest == first_manifest


def test_pilot_builder_rejects_unexpected_or_linked_output(tmp_path: Path) -> None:
    unexpected_root = tmp_path / "unexpected"
    unexpected_root.mkdir()
    (unexpected_root / "foreign.txt").write_text("not part of the packet")
    with pytest.raises(ValueError, match="unexpected paths"):
        build(unexpected_root, font_path=DEFAULT_FONT)

    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    (linked_root / "pdfs").symlink_to(unexpected_root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        build(linked_root, font_path=DEFAULT_FONT)

    hardlink_root = tmp_path / "hardlink"
    hardlink_root.mkdir()
    source = hardlink_root / "manifest.json"
    source.write_text("{}")
    os.link(source, hardlink_root / "checksums.sha256")
    with pytest.raises(ValueError, match="linked file"):
        build(hardlink_root, font_path=DEFAULT_FONT)


def test_pilot_builder_rejects_unapproved_font_bytes(tmp_path: Path) -> None:
    font = tmp_path / "unapproved.ttf"
    font.write_bytes(DEFAULT_FONT.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="approved open-license"):
        build(tmp_path / "output", font_path=font)
