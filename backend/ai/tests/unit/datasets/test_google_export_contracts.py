from __future__ import annotations

import csv
import json
from dataclasses import replace
from io import StringIO

import pytest

from app.modules.datasets.domain import (
    AssetKind,
    CanonicalDatasetRecord,
    DatasetClassification,
    DatasetUse,
    Modality,
    RecordLineage,
    RegistryInvariantError,
    SplitRole,
    TaskFamily,
)
from app.modules.datasets.infrastructure.formats.exporters import (
    export_gemini_preference,
    export_gemini_sft,
    export_vertex_embedding,
)


def _record(
    *,
    allowed_use: DatasetUse,
    payload: dict[str, object],
    record_id: str = "record-1",
    split: SplitRole = SplitRole.TRAIN,
) -> CanonicalDatasetRecord:
    return CanonicalDatasetRecord(
        record_id=record_id,
        classification=DatasetClassification(
            asset_kind=AssetKind.DATASET_RECORD,
            allowed_use=allowed_use,
            task_families=(TaskFamily.CONVERSATION_QUALITY,),
            modalities=(Modality.TEXT,),
            split_role=split,
            split_family_id=f"family-{record_id}",
        ),
        payload=payload,
        lineage=RecordLineage(
            source_id="approved-source",
            source_revision="revision-1",
            source_record_id=record_id,
            source_content_sha256="a" * 64,
            transformation_ids=("normalize-v1",),
            contamination_fingerprint=f"minhash-v1:{record_id}",
        ),
        locale="vi-VN",
        quality_scores={
            "schema": 1.0,
            "dlp": 1.0,
            "dedup": 1.0,
            "contamination": 1.0,
            "independent_review": 1.0,
        },
    )


def test_gemini_sft_uses_contents_parts_and_separate_split() -> None:
    exported = export_gemini_sft(
        (
            _record(
                allowed_use=DatasetUse.SFT,
                payload={
                    "messages": [
                        {"role": "system", "content": "Bạn là ViVi."},
                        {"role": "user", "content": "Xin chào"},
                        {"role": "assistant", "content": "Xin chào bạn"},
                    ]
                },
            ),
        )
    )
    row = json.loads(exported.content)
    assert exported.relative_path == "gemini/sft/train.jsonl"
    assert row["systemInstruction"]["parts"] == [{"text": "Bạn là ViVi."}]
    assert row["contents"] == [
        {"role": "user", "parts": [{"text": "Xin chào"}]},
        {"role": "model", "parts": [{"text": "Xin chào bạn"}]},
    ]
    assert "messages" not in row


def test_gemini_preference_uses_scored_completions() -> None:
    exported = export_gemini_preference(
        (
            _record(
                allowed_use=DatasetUse.PREFERENCE,
                payload={
                    "prompt": "Hãy trả lời ngắn gọn.",
                    "chosen": "Được ạ.",
                    "rejected": "Một câu trả lời quá dài.",
                },
            ),
        )
    )
    row = json.loads(exported.content)
    assert exported.relative_path == "gemini/preference/train.jsonl"
    assert row["contents"][0]["parts"][0]["text"] == "Hãy trả lời ngắn gọn."
    assert [item["score"] for item in row["completions"]] == [1, 0]
    assert row["completions"][0]["completion"]["role"] == "model"


def test_vertex_embedding_uses_google_ids_and_tsv_header() -> None:
    files = export_vertex_embedding(
        (
            _record(
                allowed_use=DatasetUse.EMBEDDING,
                payload={
                    "query_id": "query-1",
                    "query": "Bảo hành pin",
                    "corpus_id": "corpus-1",
                    "passage": "Nội dung chính sách đã duyệt.",
                },
            ),
        )
    )
    by_path = {item.relative_path: item for item in files}
    assert json.loads(by_path["vertex-embedding/queries.jsonl"].content) == {
        "_id": "query-1",
        "text": "Bảo hành pin",
    }
    assert json.loads(by_path["vertex-embedding/corpus.jsonl"].content) == {
        "_id": "corpus-1",
        "text": "Nội dung chính sách đã duyệt.",
    }
    rows = list(
        csv.reader(
            StringIO(by_path["vertex-embedding/train.tsv"].content.decode()),
            delimiter="\t",
        )
    )
    assert rows == [
        ["query-id", "corpus-id", "score"],
        ["query-1", "corpus-1", "1"],
    ]
    assert "vertex-embedding/validation.tsv" not in by_path
    assert "vertex-embedding/test.tsv" not in by_path


def test_tuning_export_rejects_mixed_or_held_out_splits() -> None:
    training = _record(
        allowed_use=DatasetUse.SFT,
        payload={"messages": [{"role": "user", "content": "Một câu hỏi"}]},
    )
    validation = replace(
        training,
        record_id="record-2",
        classification=replace(training.classification, split_role=SplitRole.VALIDATION),
    )
    with pytest.raises(RegistryInvariantError, match="one split"):
        export_gemini_sft((training, validation))
