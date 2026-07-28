#!/usr/bin/env python3
"""Validate Dataset Example JSONL against the canonical contract and safety scans."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SECRET = re.compile(r"(?i)(?:api[_-]?key|secret|password|bearer)\s*[:=]\s*[A-Za-z0-9._-]{8,}")
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+?84|0)\d{9,10}(?!\d)")
LEGACY_FIELDS = frozenset({"dataset_class", "allowed_uses", "purpose"})
TRAINING_USES = frozenset({"classifier-training", "sft", "preference", "embedding", "reranker"})


def validator() -> Draft202012Validator:
    root = Path(__file__).resolve().parents[6]
    schema = json.loads(
        (root / "contracts/ai/dataset-example.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema, format_checker=FormatChecker())


def text_content(record: dict[str, Any]) -> str:
    return "\n".join(
        turn.get("content", "") for turn in record.get("turns", []) if isinstance(turn, dict)
    )


def validate(path: Path) -> tuple[int, list[str]]:
    contract = validator()
    errors: list[str] = []
    seen: set[str] = set()
    count = 0
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        count += 1
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as error:
            errors.append(f"line {line_number}: invalid JSON: {error.msg}")
            continue
        for error in sorted(contract.iter_errors(record), key=lambda item: list(item.path)):
            errors.append(f"line {line_number}: contract: {error.message}")
        example_id = record.get("example_id") if isinstance(record, dict) else None
        if example_id in seen:
            errors.append(f"line {line_number}: duplicate example_id {example_id}")
        elif isinstance(example_id, str):
            seen.add(example_id)
        if isinstance(record, dict):
            legacy = sorted(LEGACY_FIELDS & record.keys())
            if legacy:
                errors.append(
                    f"line {line_number}: deprecated classification fields: {', '.join(legacy)}"
                )
            missing_dimensions = sorted(
                {
                    "asset_kind",
                    "allowed_use",
                    "task_families",
                    "modalities",
                    "split_role",
                }
                - record.keys()
            )
            if missing_dimensions:
                errors.append(
                    f"line {line_number}: missing V10.1 dimensions: "
                    + ", ".join(missing_dimensions)
                )
            if (
                record.get("split_role") in {"golden", "test"}
                and record.get("allowed_use") in TRAINING_USES
            ):
                errors.append(f"line {line_number}: held-out records cannot be training candidates")
            text = text_content(record)
            if SECRET.search(text):
                errors.append(f"line {line_number}: possible secret")
            if EMAIL.search(text) or PHONE.search(text):
                errors.append(f"line {line_number}: possible PII")
    if count == 0:
        errors.append("candidate shard is empty")
    return count, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        count, errors = validate(args.input)
    except OSError as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "valid", "records": count}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
