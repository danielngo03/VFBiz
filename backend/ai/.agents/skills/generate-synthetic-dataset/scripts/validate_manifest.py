#!/usr/bin/env python3
"""Validate canonical Dataset Manifest contract and cross-field invariants."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def repository_root() -> Path:
    return Path(__file__).resolve().parents[6]


def semantic_errors(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    counts = manifest.get("record_counts", {})
    candidate = counts.get("candidate")
    accepted = counts.get("accepted")
    rejected = counts.get("rejected")
    if all(isinstance(value, int) for value in (candidate, accepted, rejected)):
        decided = accepted + rejected
        if manifest.get("status") == "released" and candidate != decided:
            errors.append("released candidate count must equal accepted plus rejected")
        elif manifest.get("status") != "released" and decided > candidate:
            errors.append("accepted plus rejected cannot exceed candidate count")

    artifact_records = sum(
        item.get("records", 0)
        for item in manifest.get("artifacts", [])
        if isinstance(item, dict) and isinstance(item.get("records"), int)
    )
    partition_records = sum(
        value
        for value in manifest.get("split", {}).get("partitions", {}).values()
        if isinstance(value, int)
    )
    expected_records = accepted if manifest.get("status") == "released" else candidate
    if isinstance(expected_records, int):
        if artifact_records != expected_records:
            errors.append("artifact record total does not match manifest state")
        if partition_records != expected_records:
            errors.append("partition total does not match manifest state")

    approvals = manifest.get("approval_evidence", [])
    actors = [
        item.get("actor_ref")
        for item in approvals
        if isinstance(item, dict) and isinstance(item.get("actor_ref"), str)
    ]
    if len(actors) != len(set(actors)):
        errors.append("approval decisions must use distinct human actors")
    return errors


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    schema = json.loads(
        (repository_root() / "contracts/ai/dataset-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        error.message
        for error in sorted(validator.iter_errors(manifest), key=lambda item: list(item.path))
    ]
    return [*errors, *semantic_errors(manifest)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        errors = validate_manifest(manifest)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "valid", "release_id": manifest["release_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
