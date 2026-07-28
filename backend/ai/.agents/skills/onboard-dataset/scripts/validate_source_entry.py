#!/usr/bin/env python3
"""Validate Source Register structure and explicit fetch/purpose gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def repository_root() -> Path:
    return Path(__file__).resolve().parents[6]


def load_entry(path: Path, source_id: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload if isinstance(payload, list) else [payload]
    matches: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("source_id") != source_id:
            continue
        snapshot = entry.get("source_register_snapshot")
        matches.append(snapshot if isinstance(snapshot, dict) else entry)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one Source Register entry for {source_id}")
    return matches[0]


def contract_errors(entry: dict[str, Any], schema_name: str) -> list[str]:
    schema_path = repository_root() / "contracts/ai" / schema_name
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        error.message
        for error in sorted(validator.iter_errors(entry), key=lambda item: list(item.path))
    ]


def gate_errors(
    entry: dict[str, Any],
    gate: str,
    purpose: str | None,
    fetch_manifest: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    status = entry.get("status")
    rights = entry.get("rights", {})
    if gate == "fetch":
        if status not in {"fetch-approved", "purpose-approved"}:
            errors.append("source does not have fetch approval")
        if rights.get("commercial_use") != "permitted" or rights.get("legal_review") != "approved":
            errors.append("commercial rights and Legal fetch review are not approved")
        if not entry.get("fetch_approval_evidence"):
            errors.append("fetch approval evidence is missing")
        elif not any(
            item.get("role") == "legal-owner"
            for item in entry["fetch_approval_evidence"]
            if isinstance(item, dict)
        ):
            errors.append("Legal Owner fetch approval is missing")
        if not entry.get("allowed_origin"):
            errors.append("allowlisted origin is missing")
    else:
        if status != "purpose-approved":
            errors.append("source does not have purpose approval")
        approved = set(entry.get("approved_purposes") or [])
        proposed = set(entry.get("proposed_purposes") or [])
        if not purpose or purpose not in approved:
            errors.append(f"requested purpose is not approved: {purpose or 'missing'}")
        if not approved.issubset(proposed):
            errors.append("approved purposes are outside proposed purposes")
        if not entry.get("purpose_approval_evidence"):
            errors.append("purpose approval evidence is missing")
        elif not any(
            item.get("role") == "data-owner"
            for item in entry["purpose_approval_evidence"]
            if isinstance(item, dict)
        ):
            errors.append("Data Owner purpose approval is missing")
        fetch_actors = {
            item.get("actor_ref")
            for item in entry.get("fetch_approval_evidence", [])
            if isinstance(item, dict)
        }
        purpose_actors = {
            item.get("actor_ref")
            for item in entry.get("purpose_approval_evidence", [])
            if isinstance(item, dict)
        }
        if fetch_actors & purpose_actors:
            errors.append("fetch and purpose decisions must use different human actors")
        fetch_ids = set(entry.get("verified_fetch_ids") or [])
        if fetch_manifest is None:
            errors.append("verified scan-passed fetch manifest is missing")
        elif (
            fetch_manifest.get("fetch_id") not in fetch_ids
            or fetch_manifest.get("source_id") != entry.get("source_id")
            or fetch_manifest.get("source_version") != entry.get("version")
            or fetch_manifest.get("source_revision") != entry.get("source_revision")
            or fetch_manifest.get("requested_uri") != entry.get("locator")
            or fetch_manifest.get("resolved_uri") != entry.get("locator")
            or fetch_manifest.get("status") != "scan-passed"
        ):
            errors.append("fetch manifest is not scan-passed and bound to this source revision")
        upstream_checksum = entry.get("upstream_checksum_sha256")
        if upstream_checksum and fetch_manifest is not None:
            if fetch_manifest.get("observed_sha256") != upstream_checksum:
                errors.append("observed checksum does not match the pinned upstream checksum")
        if not entry.get("acl_namespaces") or not entry.get("custodian_role"):
            errors.append("purpose ACL or custodian is missing")
        if rights.get("derivatives") != "permitted":
            errors.append("derivative use is not approved")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--gate", required=True, choices=("fetch", "purpose"))
    parser.add_argument("--purpose")
    parser.add_argument("--fetch-manifest", type=Path)
    args = parser.parse_args()
    if args.gate == "purpose" and not args.purpose:
        parser.error("--purpose is required for the purpose gate")
    try:
        entry = load_entry(args.register, args.source_id)
        fetch_manifest = (
            json.loads(args.fetch_manifest.read_text(encoding="utf-8"))
            if args.fetch_manifest is not None
            else None
        )
        errors = contract_errors(entry, "source-register.schema.json")
        if fetch_manifest is not None:
            errors += contract_errors(fetch_manifest, "source-fetch-manifest.schema.json")
        errors += gate_errors(entry, args.gate, args.purpose, fetch_manifest)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"DENIED: {error}", file=sys.stderr)
        return 2
    if errors:
        print("DENIED: " + "; ".join(errors), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "decision": f"{args.gate}-authorized",
                "source_id": entry["source_id"],
                "version": entry["version"],
                "source_revision": entry["source_revision"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
