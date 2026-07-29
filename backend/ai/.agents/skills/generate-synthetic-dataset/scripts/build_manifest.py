#!/usr/bin/env python3
"""Build an atomic candidate Dataset Manifest from validated JSONL shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from validate_candidate import validate
from validate_manifest import validate_manifest

LEGACY_PURPOSES = (
    "retrieval-evaluation",
    "intent-ood",
    "conversation-quality",
    "tool-evaluation",
    "refusal-safety",
    "red-team",
    "state-resilience",
)
ALLOWED_USES = (
    "classifier-training",
    "sft",
    "preference",
    "embedding",
    "reranker",
    "evaluation",
    "red-team",
)
TASK_FAMILIES = (
    "factual-citation",
    "retrieval",
    "intent-ood",
    "conversation-quality",
    "tool-use",
    "refusal-safety",
    "state-resilience",
)
MODALITIES = ("text", "document", "image", "audio")
_LEGACY_MAPPING = {
    "retrieval-evaluation": ("evaluation", ("retrieval",), ("text",)),
    "intent-ood": ("evaluation", ("intent-ood",), ("text",)),
    "conversation-quality": ("evaluation", ("conversation-quality",), ("text",)),
    "tool-evaluation": ("evaluation", ("tool-use",), ("text",)),
    "refusal-safety": ("evaluation", ("refusal-safety",), ("text",)),
    "red-team": ("red-team", ("refusal-safety",), ("text",)),
    "state-resilience": ("evaluation", ("state-resilience",), ("text",)),
}


def artifact(path: Path) -> dict[str, Any]:
    records, errors = validate(path)
    if errors:
        raise ValueError(f"invalid candidate shard {path}: " + "; ".join(errors))
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    return {
        "zone": "candidate",
        "content_address": f"sha256/{digest[:2]}/{digest}",
        "sha256": digest,
        "tree_hash": digest,
        "records": records,
        "bytes": len(content),
        "media_type": "application/x-ndjson",
    }


def sha256_ref(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--purpose",
        choices=LEGACY_PURPOSES,
        help="Deprecated compatibility alias; prefer orthogonal V10.1 dimensions.",
    )
    parser.add_argument("--allowed-use", choices=ALLOWED_USES)
    parser.add_argument("--task-family", action="append", choices=TASK_FAMILIES)
    parser.add_argument("--modality", action="append", choices=MODALITIES)
    parser.add_argument(
        "--asset-kind",
        default="synthetic-candidate",
        choices=("dataset-record", "evaluation-case", "synthetic-candidate"),
    )
    parser.add_argument(
        "--profile", required=True, choices=["public_customer", "authenticated_customer"]
    )
    parser.add_argument("--source-id", action="append", required=True)
    parser.add_argument("--shard", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.purpose and any((args.allowed_use, args.task_family, args.modality)):
        parser.error("--purpose cannot be combined with V10.1 classification flags")
    if args.purpose:
        allowed_use, task_families, modalities = _LEGACY_MAPPING[args.purpose]
    else:
        if not args.allowed_use or not args.task_family:
            parser.error("--allowed-use and at least one --task-family are required")
        allowed_use = args.allowed_use
        task_families = tuple(dict.fromkeys(args.task_family))
        modalities = tuple(dict.fromkeys(args.modality or ("text",)))
    artifacts = [artifact(path.resolve()) for path in args.shard]
    seen_example_ids: set[str] = set()
    for shard in args.shard:
        for raw in shard.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            example_id = json.loads(raw)["example_id"]
            if example_id in seen_example_ids:
                raise ValueError(f"duplicate example_id across shards: {example_id}")
            seen_example_ids.add(example_id)
    total = sum(item["records"] for item in artifacts)
    combined = hashlib.sha256("".join(item["sha256"] for item in artifacts).encode()).hexdigest()
    created_at = datetime.now(UTC).isoformat()
    source_ids = sorted(set(args.source_id))
    payload_contract_id = "https://vfbiz.example/contracts/ai/dataset-example/v2"
    payload_revision = "v2"
    payload_digest = sha256_ref(f"{payload_contract_id}@{payload_revision}".encode())
    recipe_revision = "synthetic-candidate-normalization-v1"
    recipe_digest = sha256_ref(
        json.dumps(
            {
                "allowed_use": allowed_use,
                "asset_kind": args.asset_kind,
                "modalities": modalities,
                "revision": recipe_revision,
                "task_families": task_families,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    lineage_digest = sha256_ref(
        json.dumps(
            {
                "artifact_digests": [item["sha256"] for item in artifacts],
                "dataset_id": args.dataset_id,
                "recipe_digest": recipe_digest,
                "source_ids": source_ids,
                "version": args.version,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    manifest = {
        "release_id": f"{args.dataset_id}-{args.version}",
        "dataset_id": args.dataset_id,
        "version": args.version,
        "status": "candidate",
        "asset_kind": args.asset_kind,
        "allowed_use": allowed_use,
        "task_families": list(task_families),
        "modalities": list(modalities),
        "trust_zone": "candidate",
        "processing_stage": "normalized",
        "payload_schema": {
            "contract_id": payload_contract_id,
            "revision": payload_revision,
            "digest": payload_digest,
        },
        "classification": "internal",
        "assistant_profiles": [args.profile],
        "source_ids": source_ids,
        "provenance": {
            "sources": [
                {
                    "source_id": source_id,
                    "source_revision": "candidate-input-unresolved",
                    "artifact_digest": f"sha256:{combined}",
                }
                for source_id in source_ids
            ],
            "transformation_recipe_revision": recipe_revision,
            "transformation_recipe_digest": recipe_digest,
            "lineage_digest": lineage_digest,
        },
        "artifacts": artifacts,
        "record_counts": {"candidate": total, "accepted": 0, "rejected": 0},
        "split_lock": {
            "state": "unlocked",
            "strategy_revision": "candidate-unassigned-v1",
            "family_hash": combined,
            "partitions": {"candidate": total},
        },
        "quality_evidence": [
            {
                "run_id": f"candidate-schema-validation:{index}",
                "validator_revision": "dataset-example-v10.1",
                "artifact_digest": f"sha256:{item['sha256']}",
                "evidence_digest": sha256_ref(
                    f"candidate-schema-validation:{item['sha256']}".encode()
                ),
                "authority_ref": "dataset-candidate-validator",
                "state": "pending",
                "observed_at": created_at,
            }
            for index, item in enumerate(artifacts, start=1)
        ],
        "known_limitations": [
            "Independent quality and rights review pending.",
            "Source revisions require resolution before decision-ready.",
        ],
        "approval_evidence": [],
        "retention_policy_id": "candidate-dataset-v1",
        "deletion_method": "Delete candidate objects and tombstone lineage.",
        "rollback_target": None,
        "content_hash": combined,
        "created_at": created_at,
    }
    contract_errors = validate_manifest(manifest)
    if contract_errors:
        raise ValueError(
            "candidate manifest violates canonical contract: " + "; ".join(contract_errors)
        )
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
