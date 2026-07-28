#!/usr/bin/env python3
"""Fail when candidate records overlap held-out IDs, families, or source lineage."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

TOKEN = re.compile(r"[\w]+", re.UNICODE)


def records(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: record must be an object")
        result.append(value)
    return result


def keys(record: dict[str, Any]) -> set[str]:
    record_id = record.get("example_id") or record.get("case_id")
    result = {f"id:{record_id}"} if record_id else set()
    if family := record.get("split_family_id"):
        result.add(f"family:{family}")
    source_refs = record.get("source_refs", [])
    lineage = record.get("lineage")
    if isinstance(lineage, dict):
        source_refs = [*source_refs, *lineage.get("source_refs", [])]
        for name in (
            "source_record_id",
            "source_content_sha256",
            "contamination_fingerprint",
            "parent_artifact_sha256",
        ):
            if value := lineage.get(name):
                result.add(f"{name}:{value}")
    for name in (
        "source_record_id",
        "source_content_sha256",
        "contamination_fingerprint",
    ):
        if value := record.get(name):
            result.add(f"{name}:{value}")
    for source in source_refs:
        if isinstance(source, dict):
            result.add(f"source:{source.get('source_id')}@{source.get('revision')}")
        elif isinstance(source, str):
            result.add(f"source:{source}")
    return result


def content(record: dict[str, Any]) -> str:
    turns = record.get("turns", [])
    parts = [
        str(turn.get("content", ""))
        for turn in turns
        if isinstance(turn, dict)
    ]
    if not parts and isinstance(record.get("payload"), dict):
        parts.append(
            json.dumps(
                record["payload"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return " ".join(parts)


def minhash(value: str, *, permutations: int = 64) -> tuple[int, ...]:
    normalized = " ".join(unicodedata.normalize("NFC", value).casefold().split())
    tokens = TOKEN.findall(normalized)
    shingles = {
        " ".join(tokens[index : index + 3])
        for index in range(max(1, len(tokens) - 2))
    } or {""}
    return tuple(
        min(
            int.from_bytes(
                hashlib.sha256(f"{seed}:{shingle}".encode()).digest()[:8],
                "big",
            )
            for shingle in shingles
        )
        for seed in range(permutations)
    )


def similarity(first: tuple[int, ...], second: tuple[int, ...]) -> float:
    return sum(left == right for left, right in zip(first, second, strict=True)) / len(first)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--held-out", required=True, type=Path)
    parser.add_argument("--near-duplicate-threshold", type=float, default=0.80)
    args = parser.parse_args()
    try:
        if not 0 < args.near_duplicate_threshold <= 1:
            raise ValueError("near-duplicate threshold must be in (0, 1]")
        held_out_records = records(args.held_out)
        candidate_records = records(args.candidate)
        protected = set().union(*(keys(item) for item in held_out_records))
        overlaps = sorted(
            set().union(*(keys(item) for item in candidate_records)) & protected
        )
        held_out_signatures = tuple(
            minhash(text) for item in held_out_records if (text := content(item))
        )
        for candidate in candidate_records:
            text = content(candidate)
            if not text:
                continue
            signature = minhash(text)
            if any(
                similarity(signature, held_out) >= args.near_duplicate_threshold
                for held_out in held_out_signatures
            ):
                overlaps.append(f"near-duplicate:{candidate.get('example_id', 'unknown')}")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    if overlaps:
        print(
            json.dumps(
                {"status": "contaminated", "overlaps": sorted(set(overlaps))},
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps({"status": "clean", "overlaps": []}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
