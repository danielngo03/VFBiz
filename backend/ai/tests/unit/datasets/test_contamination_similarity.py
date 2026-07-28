from __future__ import annotations

from dataclasses import replace

import pytest

from app.modules.datasets.application.curation.quality import ContaminationIndex
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


def _record(record_id: str, text: str, family: str) -> CanonicalDatasetRecord:
    return CanonicalDatasetRecord(
        record_id=record_id,
        classification=DatasetClassification(
            asset_kind=AssetKind.DATASET_RECORD,
            allowed_use=DatasetUse.SFT,
            task_families=(TaskFamily.CONVERSATION_QUALITY,),
            modalities=(Modality.TEXT,),
            split_role=SplitRole.TRAIN,
            split_family_id=family,
        ),
        payload={"text": text},
        lineage=RecordLineage(
            source_id="source",
            source_revision="revision",
            source_record_id=record_id,
            source_content_sha256="a" * 64,
            transformation_ids=("normalize-v1",),
            contamination_fingerprint=f"fingerprint:{record_id}",
        ),
        locale="vi-VN",
        quality_scores={"schema": 1.0},
    )


def test_minhash_rejects_near_duplicate_with_same_meaning() -> None:
    held_out = _record(
        "golden-1",
        "Chính sách bảo hành pin có hiệu lực từ ngày 01 tháng 08 năm 2026.",
        "golden-family",
    )
    index = ContaminationIndex.from_held_out(
        (held_out,),
        permutations=128,
        similarity_threshold=0.60,
    )
    candidate = _record(
        "train-1",
        "Chính sách bảo hành pin có hiệu lực từ ngày 02 tháng 08 năm 2026.",
        "training-family",
    )
    with pytest.raises(RegistryInvariantError, match="near-duplicates"):
        index.reject_if_contaminated(candidate)


def test_contamination_index_uses_configured_signature_size() -> None:
    held_out = _record("golden-1", "Một nội dung kiểm thử dài và ổn định.", "golden")
    index = ContaminationIndex.from_held_out((held_out,), permutations=64)
    candidate = replace(
        held_out,
        record_id="train-1",
        classification=replace(held_out.classification, split_family_id="train"),
        lineage=replace(held_out.lineage, source_record_id="train-1"),
    )
    with pytest.raises(RegistryInvariantError, match="exactly matches"):
        index.reject_if_contaminated(candidate)
