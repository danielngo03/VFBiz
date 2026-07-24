#!/usr/bin/env python3
"""Validate a synthetic Dataset Example JSONL shard without external dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DATASET_CLASSES = {
    "knowledge",
    "retrieval-evaluation",
    "intent-ood",
    "conversation-quality",
    "tool-evaluation",
    "refusal-safety",
    "red-team",
    "state-resilience",
    "multimodal",
}
PROFILES = {"public_customer", "authenticated_customer"}
LOCALES = {"vi-VN", "en-US", "vi-Latn-no-diacritics", "mixed"}
OUTCOMES = {"answer", "clarification", "refusal", "handoff", "tool-proposal"}
ALLOWED_USES = {"knowledge", "evaluation", "red-team", "training-candidate"}
HIGH_RISK = {"pricing", "safety", "legal", "pii", "tool-authorization"}
SECRET = re.compile(r"(?i)(?:api[_-]?key|secret|password|bearer)\s*[:=]\s*[A-Za-z0-9._-]{8,}")
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+?84|0)\d{9,10}(?!\d)")


def strings(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return value


def validate_record(record: Any, line_number: int, seen: set[str]) -> list[str]:
    prefix = f"line {line_number}"
    if not isinstance(record, dict):
        return [f"{prefix}: record must be an object"]
    errors: list[str] = []
    required = {
        "example_id",
        "dataset_class",
        "assistant_profile",
        "locale",
        "turns",
        "expected",
        "risk_labels",
        "source_refs",
        "synthetic_fact_namespace",
        "allowed_uses",
        "requires_human_review",
    }
    missing = sorted(required - record.keys())
    if missing:
        errors.append(f"{prefix}: missing {', '.join(missing)}")
        return errors
    example_id = record["example_id"]
    if not isinstance(example_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", example_id):
        errors.append(f"{prefix}: invalid example_id")
    elif example_id in seen:
        errors.append(f"{prefix}: duplicate example_id {example_id}")
    else:
        seen.add(example_id)
    if record["dataset_class"] not in DATASET_CLASSES:
        errors.append(f"{prefix}: invalid dataset_class")
    if record["assistant_profile"] not in PROFILES:
        errors.append(f"{prefix}: invalid assistant_profile")
    if record["locale"] not in LOCALES:
        errors.append(f"{prefix}: invalid locale")
    turns = record["turns"]
    if not isinstance(turns, list) or not 1 <= len(turns) <= 30:
        errors.append(f"{prefix}: turns must contain 1..30 items")
        turns = []
    text_parts: list[str] = []
    for index, turn in enumerate(turns):
        if (
            not isinstance(turn, dict)
            or turn.get("role") not in {"user", "assistant", "tool"}
            or not isinstance(turn.get("content"), str)
            or not turn["content"].strip()
        ):
            errors.append(f"{prefix}: invalid turn {index}")
        else:
            text_parts.append(turn["content"])
    expected = record["expected"]
    if not isinstance(expected, dict) or expected.get("outcome") not in OUTCOMES:
        errors.append(f"{prefix}: invalid expected outcome")
    uses = strings(record["allowed_uses"])
    if len(uses) != 1 or uses[0] not in ALLOWED_USES:
        errors.append(f"{prefix}: exactly one allowed use is required")
    dataset_class = record["dataset_class"]
    if dataset_class == "knowledge" and uses != ["knowledge"]:
        errors.append(f"{prefix}: knowledge record must have knowledge use")
    if dataset_class == "red-team" and uses != ["red-team"]:
        errors.append(f"{prefix}: red-team record must have red-team use")
    if dataset_class not in {"knowledge", "red-team", "conversation-quality"} and uses != [
        "evaluation"
    ]:
        errors.append(f"{prefix}: evaluation class cannot enter knowledge/training")
    source_refs = record["source_refs"]
    namespace = record["synthetic_fact_namespace"]
    if not isinstance(source_refs, list):
        errors.append(f"{prefix}: source_refs must be an array")
        source_refs = []
    if not source_refs and not (isinstance(namespace, str) and namespace.startswith("synthetic.")):
        errors.append(f"{prefix}: source grounding or synthetic namespace is required")
    risk_labels = set(strings(record["risk_labels"]))
    if risk_labels & HIGH_RISK and record["requires_human_review"] is not True:
        errors.append(f"{prefix}: high-risk record requires human review")
    joined = "\n".join(text_parts)
    if SECRET.search(joined):
        errors.append(f"{prefix}: possible secret")
    if EMAIL.search(joined) or PHONE.search(joined):
        errors.append(f"{prefix}: possible PII")
    return errors


def validate(path: Path) -> tuple[int, list[str]]:
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
        errors.extend(validate_record(record, line_number, seen))
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
