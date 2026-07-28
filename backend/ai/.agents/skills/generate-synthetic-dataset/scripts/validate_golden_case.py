#!/usr/bin/env python3
"""Validate Golden Case v2 contract and citation-snapshot membership."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def semantic_errors(case: dict[str, Any]) -> list[str]:
    snapshot = case.get("knowledge_snapshot")
    evidence_ids = set(snapshot.get("evidence_ids", [])) if isinstance(snapshot, dict) else set()
    errors: list[str] = []
    expected = case.get("expected", {})
    for claim in expected.get("required_claims", []) if isinstance(expected, dict) else []:
        if not isinstance(claim, dict):
            continue
        unknown = set(claim.get("citation_evidence_ids", [])) - evidence_ids
        if unknown:
            errors.append(
                f"claim {claim.get('claim_id', 'unknown')} cites evidence outside snapshot: "
                + ", ".join(sorted(unknown))
            )
    return errors


def validate_case(case: dict[str, Any]) -> list[str]:
    root = Path(__file__).resolve().parents[6]
    schema = json.loads(
        (root / "contracts/ai/evaluation-case.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    contract_errors = [
        error.message
        for error in sorted(validator.iter_errors(case), key=lambda item: list(item.path))
    ]
    return [*contract_errors, *semantic_errors(case)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path)
    args = parser.parse_args()
    try:
        case = json.loads(args.case.read_text(encoding="utf-8"))
        if not isinstance(case, dict):
            raise ValueError("golden case must be an object")
        errors = validate_case(case)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "valid", "case_id": case["case_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
