"""Provider-format dataset export adapters."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass
from io import StringIO
from typing import cast

from app.modules.datasets.domain import (
    DatasetUse,
    RegistryInvariantError,
    require_release_eligible,
)
from app.modules.datasets.domain.records import CanonicalDatasetRecord


@dataclass(frozen=True, slots=True)
class ExportedFile:
    relative_path: str
    media_type: str
    content: bytes
    record_count: int


def export_gemini_sft(records: Iterable[CanonicalDatasetRecord]) -> ExportedFile:
    selected = _require_use(records, DatasetUse.SFT)
    rows: list[str] = []
    for record in selected:
        raw_messages = record.payload.get("messages")
        if not isinstance(raw_messages, list) or not raw_messages:
            raise RegistryInvariantError("Gemini SFT records require non-empty messages")
        messages = cast(list[object], raw_messages)
        system_instruction: dict[str, object] | None = None
        contents: list[dict[str, object]] = []
        for raw_message in messages:
            if not isinstance(raw_message, dict):
                raise RegistryInvariantError("Gemini SFT messages must be objects")
            message = cast(dict[str, object], raw_message)
            role = message.get("role")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise RegistryInvariantError("Gemini SFT message content is required")
            if role == "system":
                if system_instruction is not None or contents:
                    raise RegistryInvariantError(
                        "Gemini SFT supports one leading system instruction"
                    )
                system_instruction = {"role": "system", "parts": [{"text": content}]}
            elif role in {"user", "model", "assistant"}:
                contents.append(
                    {
                        "role": "model" if role == "assistant" else role,
                        "parts": [{"text": content}],
                    }
                )
            else:
                raise RegistryInvariantError(f"unsupported Gemini SFT role: {role}")
        if not contents:
            raise RegistryInvariantError("Gemini SFT requires conversation contents")
        row: dict[str, object] = {"contents": contents}
        if system_instruction is not None:
            row["systemInstruction"] = system_instruction
        rows.append(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
    return _jsonl(f"gemini/sft/{_single_split(selected)}.jsonl", rows)


def export_gemini_preference(records: Iterable[CanonicalDatasetRecord]) -> ExportedFile:
    selected = _require_use(records, DatasetUse.PREFERENCE)
    rows: list[str] = []
    for record in selected:
        prompt = record.payload.get("prompt")
        chosen = record.payload.get("chosen")
        rejected = record.payload.get("rejected")
        if not all(isinstance(item, str) and item.strip() for item in (prompt, chosen, rejected)):
            raise RegistryInvariantError(
                "preference records require prompt, chosen and rejected strings"
            )
        rows.append(
            json.dumps(
                {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "completions": [
                        {
                            "score": 1,
                            "completion": {
                                "role": "model",
                                "parts": [{"text": chosen}],
                            },
                        },
                        {
                            "score": 0,
                            "completion": {
                                "role": "model",
                                "parts": [{"text": rejected}],
                            },
                        },
                    ],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    return _jsonl(f"gemini/preference/{_single_split(selected)}.jsonl", rows)


def export_vertex_embedding(
    records: Iterable[CanonicalDatasetRecord],
) -> tuple[ExportedFile, ...]:
    selected = _require_use(records, DatasetUse.EMBEDDING)
    corpus: dict[str, str] = {}
    queries: list[str] = []
    labels: dict[str, list[tuple[str, str, str]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    for record in selected:
        query_id = _required_string(record.payload, "query_id")
        query = _required_string(record.payload, "query")
        corpus_id = _required_string(record.payload, "corpus_id")
        passage = _required_string(record.payload, "passage")
        split = record.classification.split_role.value
        if split not in labels:
            raise RegistryInvariantError("embedding exports only support train/validation/test")
        existing = corpus.setdefault(corpus_id, passage)
        if existing != passage:
            raise RegistryInvariantError("corpus ID maps to conflicting passages")
        queries.append(json.dumps({"_id": query_id, "text": query}, ensure_ascii=False))
        labels[split].append((query_id, corpus_id, "1"))

    corpus_rows = [
        json.dumps({"_id": key, "text": value}, ensure_ascii=False)
        for key, value in sorted(corpus.items())
    ]
    files = [
        _jsonl("vertex-embedding/corpus.jsonl", corpus_rows),
        _jsonl("vertex-embedding/queries.jsonl", queries),
    ]
    for split, rows in labels.items():
        if not rows:
            continue
        output = StringIO()
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(("query-id", "corpus-id", "score"))
        writer.writerows(rows)
        files.append(
            ExportedFile(
                relative_path=f"vertex-embedding/{split}.tsv",
                media_type="text/tab-separated-values",
                content=output.getvalue().encode(),
                record_count=len(rows),
            )
        )
    return tuple(files)


def export_vfbiz_evaluation(records: Iterable[CanonicalDatasetRecord]) -> ExportedFile:
    selected = _require_use(records, DatasetUse.EVALUATION)
    rows = [
        json.dumps(
            {
                "record_id": record.record_id,
                "task_families": [item.value for item in record.classification.task_families],
                "payload": record.payload,
                "lineage": {
                    "source_id": record.lineage.source_id,
                    "source_revision": record.lineage.source_revision,
                    "source_record_id": record.lineage.source_record_id,
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for record in selected
    ]
    return _jsonl("evaluation/cases.jsonl", rows)


def _require_use(
    records: Iterable[CanonicalDatasetRecord], allowed_use: DatasetUse
) -> tuple[CanonicalDatasetRecord, ...]:
    selected = tuple(records)
    if not selected:
        raise RegistryInvariantError("cannot export an empty dataset")
    if any(record.classification.allowed_use is not allowed_use for record in selected):
        raise RegistryInvariantError("an export cannot mix allowed uses")
    return require_release_eligible(selected)


def _single_split(records: tuple[CanonicalDatasetRecord, ...]) -> str:
    splits = {record.classification.split_role.value for record in records}
    if not splits <= {"train", "validation"}:
        raise RegistryInvariantError("tuning exports only support train or validation splits")
    if len(splits) != 1:
        raise RegistryInvariantError("each tuning export artifact must contain one split")
    return next(iter(splits))


def _required_string(payload: dict[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise RegistryInvariantError(f"{name} must be a non-empty string")
    return value


def _jsonl(path: str, rows: list[str]) -> ExportedFile:
    return ExportedFile(
        relative_path=path,
        media_type="application/x-ndjson",
        content=(("\n".join(rows) + "\n") if rows else "").encode(),
        record_count=len(rows),
    )
