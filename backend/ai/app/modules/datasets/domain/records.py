from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.datasets.domain.classification import DatasetClassification
from app.modules.datasets.domain.registry import RegistryInvariantError


@dataclass(frozen=True, slots=True)
class RecordLineage:
    source_id: str
    source_revision: str
    source_record_id: str
    source_content_sha256: str
    transformation_ids: tuple[str, ...]
    contamination_fingerprint: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.source_id,
                self.source_revision,
                self.source_record_id,
                self.contamination_fingerprint,
            )
        ):
            raise RegistryInvariantError("record lineage fields are required")
        if len(self.source_content_sha256) != 64:
            raise RegistryInvariantError("source record digest must be SHA-256")


@dataclass(frozen=True, slots=True)
class CanonicalDatasetRecord:
    record_id: str
    classification: DatasetClassification
    payload: dict[str, Any]
    lineage: RecordLineage
    locale: str
    quality_scores: dict[str, float]
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.record_id.strip() or not self.locale.strip():
            raise RegistryInvariantError("record ID and locale are required")
        if not self.payload:
            raise RegistryInvariantError("canonical payload cannot be empty")
        for name, value in self.quality_scores.items():
            if not name.strip() or not 0 <= value <= 1:
                raise RegistryInvariantError("quality scores must be named values in [0, 1]")
