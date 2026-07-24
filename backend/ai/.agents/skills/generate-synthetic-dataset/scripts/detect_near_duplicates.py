#!/usr/bin/env python3
"""Detect exact and near-duplicate conversation examples using bounded LSH."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

TOKEN = re.compile(r"\w+", re.UNICODE)
SEEDS = tuple(range(8))


def normalized_text(record: dict[str, Any]) -> str:
    parts = [
        str(turn.get("content", "")) for turn in record.get("turns", []) if isinstance(turn, dict)
    ]
    return " ".join(TOKEN.findall(" ".join(parts).lower()))


def shingles(text: str) -> set[str]:
    tokens = text.split()
    if len(tokens) < 3:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[index : index + 3]) for index in range(len(tokens) - 2)}


def minhash(values: set[str]) -> tuple[int, ...]:
    if not values:
        return tuple(0 for _ in SEEDS)
    result = []
    for seed in SEEDS:
        result.append(
            min(
                int.from_bytes(hashlib.sha256(f"{seed}:{value}".encode()).digest()[:8], "big")
                for value in values
            )
        )
    return tuple(result)


def load(paths: list[Path]) -> list[tuple[str, str, set[str]]]:
    records: list[tuple[str, str, set[str]]] = []
    for path in paths:
        for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            value = json.loads(raw)
            text = normalized_text(value)
            identifier = str(value.get("example_id", f"{path.name}:{line_number}"))
            records.append((identifier, text, shingles(text)))
    return records


def detect(records: list[tuple[str, str, set[str]]], threshold: float) -> list[dict[str, Any]]:
    buckets: dict[tuple[int, tuple[int, int]], list[int]] = defaultdict(list)
    exact: dict[str, int] = {}
    candidate_pairs: set[tuple[int, int]] = set()
    signatures: list[tuple[int, ...]] = []
    duplicates: list[dict[str, Any]] = []
    for index, (identifier, text, values) in enumerate(records):
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest in exact:
            other = exact[digest]
            duplicates.append(
                {
                    "left": records[other][0],
                    "right": identifier,
                    "similarity": 1.0,
                    "kind": "exact",
                }
            )
        else:
            exact[digest] = index
        signature = minhash(values)
        signatures.append(signature)
        for band in range(4):
            key = (band, (signature[band * 2], signature[band * 2 + 1]))
            for other in buckets[key]:
                candidate_pairs.add((other, index))
            buckets[key].append(index)
    exact_pairs = {(item["left"], item["right"]) for item in duplicates}
    for left, right in sorted(candidate_pairs):
        left_values = records[left][2]
        right_values = records[right][2]
        union = left_values | right_values
        score = len(left_values & right_values) / len(union) if union else 1.0
        pair = (records[left][0], records[right][0])
        if score >= threshold and pair not in exact_pairs:
            duplicates.append(
                {
                    "left": pair[0],
                    "right": pair[1],
                    "similarity": round(score, 6),
                    "kind": "near",
                }
            )
    return duplicates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--threshold", type=float, default=0.9)
    args = parser.parse_args()
    if not 0 < args.threshold <= 1:
        parser.error("--threshold must be in (0, 1]")
    try:
        records = load(args.inputs)
        duplicates = detect(records, args.threshold)
    except (OSError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "records": len(records),
                "duplicates": duplicates,
                "threshold": args.threshold,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if duplicates else 0


if __name__ == "__main__":
    raise SystemExit(main())
