from __future__ import annotations

from dataclasses import replace

import pytest

from app.modules.datasets.domain import (
    AssetKind,
    CanonicalDatasetRecord,
    DatasetClassification,
    DatasetUse,
    HeldOutSplitLock,
    Modality,
    RecordLineage,
    RegistryInvariantError,
    SplitRole,
    TaskFamily,
)


def _record(
    record_id: str,
    *,
    allowed_use: DatasetUse,
    split_role: SplitRole,
    split_family_id: str,
) -> CanonicalDatasetRecord:
    return CanonicalDatasetRecord(
        record_id=record_id,
        classification=DatasetClassification(
            asset_kind=(
                AssetKind.EVALUATION_CASE
                if allowed_use is DatasetUse.EVALUATION
                else AssetKind.DATASET_RECORD
            ),
            allowed_use=allowed_use,
            task_families=(TaskFamily.FACTUAL_CITATION,),
            modalities=(Modality.TEXT,),
            split_role=split_role,
            split_family_id=split_family_id,
        ),
        payload={"text": f"payload for {record_id}"},
        lineage=RecordLineage(
            source_id="source",
            source_revision="revision",
            source_record_id=record_id,
            source_content_sha256=(record_id[0] * 64),
            transformation_ids=("normalize-v1",),
            contamination_fingerprint=f"minhash-v1:{record_id}",
        ),
        locale="vi-VN",
        quality_scores={"schema": 1.0},
    )


def test_split_lock_rejects_training_descendant_by_each_durable_key() -> None:
    held_out = _record(
        "golden-record",
        allowed_use=DatasetUse.EVALUATION,
        split_role=SplitRole.GOLDEN,
        split_family_id="golden-family",
    )
    split_lock = HeldOutSplitLock.from_records((held_out,))
    training = _record(
        "training-record",
        allowed_use=DatasetUse.SFT,
        split_role=SplitRole.TRAIN,
        split_family_id="training-family",
    )

    collisions = (
        replace(
            training,
            lineage=replace(training.lineage, source_record_id=held_out.lineage.source_record_id),
        ),
        replace(
            training,
            lineage=replace(
                training.lineage,
                source_content_sha256=held_out.lineage.source_content_sha256,
            ),
        ),
        replace(
            training,
            classification=replace(
                training.classification,
                split_family_id=held_out.classification.split_family_id,
            ),
        ),
        replace(
            training,
            lineage=replace(
                training.lineage,
                contamination_fingerprint=held_out.lineage.contamination_fingerprint,
            ),
        ),
    )
    for collision in collisions:
        with pytest.raises(RegistryInvariantError, match="held-out lock"):
            split_lock.reject_training_lineage(collision)


def test_split_lock_does_not_reclassify_non_training_artifacts() -> None:
    held_out = _record(
        "golden-record",
        allowed_use=DatasetUse.EVALUATION,
        split_role=SplitRole.GOLDEN,
        split_family_id="golden-family",
    )
    HeldOutSplitLock.from_records((held_out,)).reject_training_lineage(held_out)
