from __future__ import annotations

from dataclasses import dataclass

from app.modules.datasets.domain.records import CanonicalDatasetRecord
from app.modules.datasets.domain.registry import RegistryInvariantError


@dataclass(frozen=True, slots=True)
class HeldOutSplitLock:
    """Immutable identifiers that must never enter a training lineage."""

    source_record_ids: frozenset[str]
    source_content_hashes: frozenset[str]
    split_family_ids: frozenset[str]
    contamination_fingerprints: frozenset[str]

    @classmethod
    def from_records(cls, records: tuple[CanonicalDatasetRecord, ...]) -> HeldOutSplitLock:
        if not records:
            raise RegistryInvariantError("held-out split lock cannot be empty")
        return cls(
            source_record_ids=frozenset(record.lineage.source_record_id for record in records),
            source_content_hashes=frozenset(
                record.lineage.source_content_sha256 for record in records
            ),
            split_family_ids=frozenset(record.classification.split_family_id for record in records),
            contamination_fingerprints=frozenset(
                record.lineage.contamination_fingerprint for record in records
            ),
        )

    def reject_training_lineage(self, record: CanonicalDatasetRecord) -> None:
        if not record.classification.is_training_artifact:
            return
        collisions: list[str] = []
        if record.lineage.source_record_id in self.source_record_ids:
            collisions.append("source record")
        if record.lineage.source_content_sha256 in self.source_content_hashes:
            collisions.append("source content hash")
        if record.classification.split_family_id in self.split_family_ids:
            collisions.append("split family")
        if record.lineage.contamination_fingerprint in self.contamination_fingerprints:
            collisions.append("contamination fingerprint")
        if collisions:
            raise RegistryInvariantError(
                "training lineage overlaps held-out lock: " + ", ".join(collisions)
            )
