from __future__ import annotations

from dataclasses import replace

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
from app.modules.datasets.infrastructure.formats.exporters import export_gemini_sft


def _record() -> CanonicalDatasetRecord:
    return CanonicalDatasetRecord(
        record_id="sft-1",
        classification=DatasetClassification(
            asset_kind=AssetKind.DATASET_RECORD,
            allowed_use=DatasetUse.SFT,
            task_families=(TaskFamily.CONVERSATION_QUALITY,),
            modalities=(Modality.TEXT,),
            split_role=SplitRole.TRAIN,
            split_family_id="family-1",
        ),
        payload={
            "messages": [
                {"role": "user", "content": "Xin chào"},
                {"role": "model", "content": "Xin chào bạn"},
            ]
        },
        lineage=RecordLineage(
            source_id="approved-source",
            source_revision="revision-1",
            source_record_id="record-1",
            source_content_sha256="a" * 64,
            transformation_ids=("normalize-v1",),
            contamination_fingerprint="minhash-v1:abc",
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


def test_export_requires_all_release_quality_gates() -> None:
    assert export_gemini_sft((_record(),)).record_count == 1

    missing_gate = replace(_record(), quality_scores={"schema": 1.0})
    with pytest.raises(RegistryInvariantError, match="missing release quality gates"):
        export_gemini_sft((missing_gate,))

    rejected = replace(_record(), rejection_reasons=("unsafe-source",))
    with pytest.raises(RegistryInvariantError, match="rejected records"):
        export_gemini_sft((rejected,))


def test_export_rejects_failed_release_gate() -> None:
    failed = replace(
        _record(),
        quality_scores={**_record().quality_scores, "contamination": 0.0},
    )
    with pytest.raises(RegistryInvariantError, match="must pass"):
        export_gemini_sft((failed,))
