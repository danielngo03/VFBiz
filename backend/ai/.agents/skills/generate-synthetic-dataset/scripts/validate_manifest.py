#!/usr/bin/env python3
"""Validate canonical Dataset Manifest contract and cross-field invariants."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

AI_ROOT = Path(__file__).resolve().parents[4]
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))

from app.modules.datasets.application.curation.release_manifest import (  # noqa: E402
    DatasetManifestV4SemanticValidator,
    LegacyDatasetManifestV3SemanticValidator,
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[6]


def semantic_errors(manifest: dict[str, Any]) -> list[str]:
    if "split_lock" in manifest:
        return DatasetManifestV4SemanticValidator().errors(manifest)
    return LegacyDatasetManifestV3SemanticValidator().errors(manifest)


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
