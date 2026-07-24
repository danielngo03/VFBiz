#!/usr/bin/env python3
"""Fail-closed Source Register download gate using only the standard library."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA256 = re.compile(r"^[a-f0-9]{64}$")
ACL_NAMESPACE = re.compile(
    r"^(public_customer|authenticated_customer|restricted_evaluation|"
    r"red_team|training_candidate):[a-z0-9]+(?:-[a-z0-9]+)*:"
    r"(?:vi|en)(?:-[A-Z]{2})?$"
)


def load_entry(path: Path, source_id: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload if isinstance(payload, list) else [payload]
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("source_id") == source_id
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one Source Register entry for {source_id}")
    return matches[0]


def validate_download_gate(entry: dict[str, Any], purpose: str) -> list[str]:
    errors: list[str] = []
    rights = entry.get("rights") if isinstance(entry.get("rights"), dict) else {}
    if entry.get("status") != "approved":
        errors.append("source status is not approved")
    if rights.get("commercial_use") != "permitted":
        errors.append("commercial use is not permitted")
    if rights.get("derivatives") != "permitted":
        errors.append("derivative use is not permitted")
    if rights.get("legal_review") != "approved":
        errors.append("Legal review is not approved")
    if not rights.get("evidence_urls"):
        errors.append("license evidence URL is missing")
    proposed_purposes = set(entry.get("proposed_purposes") or [])
    approved_purposes = set(entry.get("approved_purposes") or [])
    if not approved_purposes:
        errors.append("approved purpose is missing")
    elif not approved_purposes.issubset(proposed_purposes):
        errors.append("approved purpose is outside proposed purposes")
    if purpose not in approved_purposes:
        errors.append(f"requested purpose is not approved: {purpose}")
    acl_namespaces = entry.get("acl_namespaces") or []
    if not acl_namespaces:
        errors.append("ACL namespace is missing")
    elif any(
        not isinstance(namespace, str) or ACL_NAMESPACE.fullmatch(namespace) is None
        for namespace in acl_namespaces
    ):
        errors.append("ACL namespace is invalid")
    if (
        purpose == "knowledge"
        and not any(
            namespace.startswith(("public_customer:", "authenticated_customer:"))
            for namespace in acl_namespaces
        )
    ):
        errors.append("knowledge purpose requires a customer assistant namespace")
    if (
        any(namespace.startswith("public_customer:") for namespace in acl_namespaces)
        and entry.get("classification") != "public"
    ):
        errors.append("public customer namespace requires public classification")
    if entry.get("source_type") == "customer-derived":
        if entry.get("classification") != "restricted":
            errors.append("customer-derived source must be restricted")
        if any(namespace.startswith("public_customer:") for namespace in acl_namespaces):
            errors.append("customer-derived source cannot use public customer namespace")
    if not entry.get("custodian_role"):
        errors.append("custodian is missing")
    checksum = entry.get("checksum_sha256")
    if not isinstance(checksum, str) or not SHA256.fullmatch(checksum):
        errors.append("pinned SHA-256 checksum is missing")
    if not entry.get("approval_evidence"):
        errors.append("human approval evidence is missing")
    if not entry.get("deletion_method"):
        errors.append("deletion method is missing")
    if not entry.get("retention"):
        errors.append("retention policy is missing")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--purpose", required=True)
    args = parser.parse_args()
    try:
        entry = load_entry(args.register, args.source_id)
        errors = validate_download_gate(entry, args.purpose)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"DENIED: {error}", file=sys.stderr)
        return 2
    if errors:
        print("DENIED: " + "; ".join(errors), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "decision": "download-authorized-by-evidence",
                "source_id": entry["source_id"],
                "version": entry["version"],
                "checksum_sha256": entry["checksum_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
