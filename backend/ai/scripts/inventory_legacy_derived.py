#!/usr/bin/env python3
"""Inventory legacy derived pages without copying OCR text into evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import cast

from app.modules.datasets.domain import RegistryInvariantError

_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_MAX_PAGE_BYTES = 4 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = inventory_legacy_derived(args.root)
        if args.output is None:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            _write_report(args.output, report)
            print(json.dumps(_summary(report), ensure_ascii=False, sort_keys=True))
    except (OSError, ValueError, RegistryInvariantError) as error:
        print(f"FAILED-SAFELY: {error}", file=sys.stderr)
        return 2
    return 0


def inventory_legacy_derived(root: Path) -> dict[str, object]:
    trusted_root = _trusted_directory(root)
    records: list[dict[str, object]] = []
    for source_dir in sorted(trusted_root.iterdir(), key=lambda item: item.name):
        if source_dir.name.startswith("."):
            continue
        source_sha256 = _digest_directory(source_dir, "source")
        for pipeline_dir in sorted(source_dir.iterdir(), key=lambda item: item.name):
            pipeline_digest = _digest_directory(pipeline_dir, "pipeline")
            pages_dir = pipeline_dir / "pages"
            if pages_dir.is_symlink() or not pages_dir.is_dir():
                raise RegistryInvariantError("legacy derived pages directory is invalid")
            records.append(
                _inventory_pipeline(
                    pages_dir,
                    source_sha256=source_sha256,
                    pipeline_digest=pipeline_digest,
                )
            )

    page_count = sum(cast(int, record["page_count"]) for record in records)
    byte_size = sum(cast(int, record["byte_size"]) for record in records)
    method_counts = Counter(
        {
            method: sum(
                cast(dict[str, int], record["extraction_methods"]).get(method, 0)
                for record in records
            )
            for method in sorted(
                {
                    method
                    for record in records
                    for method in cast(dict[str, int], record["extraction_methods"])
                }
            )
        }
    )
    disposition_counts = Counter(
        {
            disposition: sum(
                cast(dict[str, int], record["dispositions"]).get(disposition, 0)
                for record in records
            )
            for disposition in sorted(
                {
                    disposition
                    for record in records
                    for disposition in cast(dict[str, int], record["dispositions"])
                }
            )
        }
    )
    tesseract_pages = sum(cast(int, record["tesseract_page_count"]) for record in records)
    report: dict[str, object] = {
        "schema_version": "vfbiz-legacy-derived-inventory/v1",
        "state": "inventory-only",
        "source_count": len({record["source_sha256"] for record in records}),
        "pipeline_count": len(records),
        "page_count": page_count,
        "byte_size": byte_size,
        "tesseract_page_count": tesseract_pages,
        "extraction_methods": dict(sorted(method_counts.items())),
        "dispositions": dict(sorted(disposition_counts.items())),
        "records": records,
        "tree_sha256": _digest_json(records),
        "raw_content_included": False,
        "delete_performed": False,
        "active_retriever_visible": False,
        "next_action": "reviewed-tombstone-or-trash-operation",
    }
    return report


def _inventory_pipeline(
    pages_dir: Path, *, source_sha256: str, pipeline_digest: str
) -> dict[str, object]:
    page_numbers: list[int] = []
    methods: Counter[str] = Counter()
    dispositions: Counter[str] = Counter()
    ocr_revisions: Counter[str] = Counter()
    byte_size = 0
    tesseract_page_count = 0
    for page_path in sorted(pages_dir.iterdir(), key=lambda item: item.name):
        if page_path.is_symlink() or not page_path.is_file() or page_path.suffix != ".json":
            raise RegistryInvariantError("legacy derived page file is invalid")
        size = page_path.stat().st_size
        if size > _MAX_PAGE_BYTES:
            raise RegistryInvariantError("legacy derived page exceeds bounded size")
        payload = _load_page(page_path)
        _validate_parent_binding(
            payload, source_sha256=source_sha256, pipeline_digest=pipeline_digest
        )
        page_number = _positive_int(payload.get("page_number"), "page number")
        method = _text(payload.get("extraction_method"), "extraction method")
        disposition = _text(payload.get("disposition"), "disposition")
        page_numbers.append(page_number)
        methods[method] += 1
        dispositions[disposition] += 1
        ocr_revision = payload.get("ocr_revision")
        if isinstance(ocr_revision, str) and ocr_revision:
            ocr_revisions[ocr_revision] += 1
            if ocr_revision.lower().startswith("tesseract"):
                tesseract_page_count += 1
        byte_size += size
    expected = list(range(1, len(page_numbers) + 1))
    ordered = sorted(page_numbers)
    return {
        "source_sha256": source_sha256,
        "pipeline_digest": pipeline_digest,
        "page_count": len(page_numbers),
        "byte_size": byte_size,
        "page_numbers_contiguous": ordered == expected,
        "page_numbers": ordered,
        "extraction_methods": dict(sorted(methods.items())),
        "dispositions": dict(sorted(dispositions.items())),
        "ocr_revisions": dict(sorted(ocr_revisions.items())),
        "tesseract_page_count": tesseract_page_count,
        "raw_content_included": False,
    }


def _load_page(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RegistryInvariantError("legacy derived page must be a JSON object")
    return cast(dict[str, object], value)


def _validate_parent_binding(
    payload: dict[str, object], *, source_sha256: str, pipeline_digest: str
) -> None:
    if payload.get("source_sha256") != source_sha256:
        raise RegistryInvariantError("legacy derived source binding is invalid")
    if payload.get("pipeline_digest") != pipeline_digest:
        raise RegistryInvariantError("legacy derived pipeline binding is invalid")


def _digest_directory(path: Path, label: str) -> str:
    if path.is_symlink() or not path.is_dir() or not _DIGEST.fullmatch(path.name):
        raise RegistryInvariantError(f"legacy derived {label} directory is invalid")
    return path.name


def _trusted_directory(path: Path) -> Path:
    if path.is_symlink():
        raise RegistryInvariantError("inventory root must not be a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise RegistryInvariantError("inventory root must be a directory")
    return resolved


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RegistryInvariantError(f"{label} is invalid")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RegistryInvariantError(f"{label} is invalid")
    return value


def _digest_json(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _summary(report: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": report["schema_version"],
        "state": report["state"],
        "source_count": report["source_count"],
        "pipeline_count": report["pipeline_count"],
        "page_count": report["page_count"],
        "byte_size": report["byte_size"],
        "tesseract_page_count": report["tesseract_page_count"],
        "tree_sha256": report["tree_sha256"],
        "raw_content_included": report["raw_content_included"],
        "delete_performed": report["delete_performed"],
    }


def _write_report(path: Path, report: dict[str, object]) -> None:
    if path.exists() and path.is_symlink():
        raise RegistryInvariantError("inventory output must not be a symlink")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.pending")
    with temporary.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
