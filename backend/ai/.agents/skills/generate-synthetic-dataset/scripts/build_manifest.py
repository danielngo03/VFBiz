#!/usr/bin/env python3
"""Build an atomic candidate Dataset Manifest from validated JSONL shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def artifact(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    records = sum(1 for line in content.splitlines() if line.strip())
    return {
        "uri": str(path),
        "sha256": hashlib.sha256(content).hexdigest(),
        "records": records,
        "bytes": len(content),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--purpose", required=True)
    parser.add_argument(
        "--profile", required=True, choices=["public_customer", "authenticated_customer"]
    )
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--shard", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    artifacts = [artifact(path.resolve()) for path in args.shard]
    total = sum(item["records"] for item in artifacts)
    combined = hashlib.sha256("".join(item["sha256"] for item in artifacts).encode()).hexdigest()
    manifest = {
        "dataset_id": args.dataset_id,
        "version": args.version,
        "status": "candidate",
        "purpose": args.purpose,
        "assistant_profiles": [args.profile],
        "source_ids": sorted(set(args.source_id)),
        "generator": None,
        "artifacts": artifacts,
        "record_counts": {"candidate": total, "accepted": 0, "rejected": 0},
        "split_strategy": "Candidate only; held-out split assigned by independent review.",
        "quality_metrics": {"schema_validated": True},
        "known_limitations": ["Independent quality and rights review pending."],
        "approval_evidence": [],
        "retention_policy_id": "candidate-dataset-v1",
        "deletion_method": "Delete candidate objects and tombstone lineage.",
        "rollback_target": None,
        "content_hash": combined,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{args.output.name}.", dir=args.output.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, args.output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(json.dumps({"manifest": str(args.output), "content_hash": combined, "records": total}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
