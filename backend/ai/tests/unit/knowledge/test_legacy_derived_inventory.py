from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.datasets.domain import RegistryInvariantError
from scripts.inventory_legacy_derived import inventory_legacy_derived

SOURCE = "a" * 64
PIPELINE = "b" * 64


def _write_page(
    root: Path,
    *,
    number: int = 1,
    source: str = SOURCE,
    payload_source: str | None = None,
) -> None:
    page = root / source / PIPELINE / "pages" / f"{number:06d}.json"
    page.parent.mkdir(parents=True)
    page.write_text(
        json.dumps(
            {
                "source_sha256": payload_source or source,
                "pipeline_digest": PIPELINE,
                "page_number": number,
                "page_sha256": "c" * 64,
                "extraction_method": "ocr",
                "disposition": "review-required",
                "ocr_revision": "tesseract 5.3.0",
                "text": "must never appear in the report",
            }
        ),
        encoding="utf-8",
    )


def test_inventory_is_content_free_and_content_addressed(tmp_path: Path) -> None:
    _write_page(tmp_path)

    report = inventory_legacy_derived(tmp_path)

    assert report["raw_content_included"] is False
    assert report["delete_performed"] is False
    assert report["page_count"] == 1
    assert report["tesseract_page_count"] == 1
    assert "text" not in json.dumps(report)
    assert len(report["tree_sha256"]) == 64


def test_inventory_rejects_parent_digest_mismatch(tmp_path: Path) -> None:
    _write_page(tmp_path, payload_source="d" * 64)

    with pytest.raises(RegistryInvariantError, match="source binding"):
        inventory_legacy_derived(tmp_path)


def test_inventory_rejects_symlinked_page(tmp_path: Path) -> None:
    _write_page(tmp_path)
    page = tmp_path / SOURCE / PIPELINE / "pages" / "000001.json"
    replacement = tmp_path / "replacement.json"
    replacement.write_text(page.read_text(encoding="utf-8"), encoding="utf-8")
    page.unlink()
    page.symlink_to(replacement)

    with pytest.raises(RegistryInvariantError, match="page file"):
        inventory_legacy_derived(tmp_path)
