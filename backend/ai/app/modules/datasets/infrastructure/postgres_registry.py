from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.datasets.domain import (
    AllowedUse,
    DatasetArtifact,
    DatasetFetch,
    DatasetScanEvidence,
    DatasetSource,
    DlpDecision,
    FetchState,
    RegistryInvariantError,
    SourceStatus,
)
from app.modules.datasets.infrastructure.models import (
    DatasetArtifactRecord,
    DatasetFetchRecord,
    DatasetSourceRecord,
)


class PostgresDatasetRegistry:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add_source(self, source: DatasetSource) -> None:
        async with self._sessions() as session, session.begin():
            result = cast(
                CursorResult[object],
                await session.execute(
                    insert(DatasetSourceRecord)
                    .values(_source_values(source))
                    .on_conflict_do_nothing(index_elements=["source_key", "source_revision"])
                ),
            )
            if result.rowcount == 1:
                return
            existing = await session.scalar(
                select(DatasetSourceRecord).where(
                    DatasetSourceRecord.source_key == source.source_key,
                    DatasetSourceRecord.source_revision == source.source_revision,
                )
            )
            if existing is None or _source(existing) != source:
                raise RegistryInvariantError("source revision conflicts with registry")

    async def get_source(self, source_id: UUID) -> DatasetSource | None:
        async with self._sessions() as session:
            record = await session.get(DatasetSourceRecord, source_id)
            return None if record is None else _source(record)

    async def save_source(self, source: DatasetSource, *, expected_version: int) -> None:
        if source.row_version != expected_version + 1:
            raise RegistryInvariantError("source transition version is inconsistent")
        async with self._sessions() as session, session.begin():
            result = cast(
                CursorResult[object],
                await session.execute(
                    update(DatasetSourceRecord)
                    .where(
                        DatasetSourceRecord.id == source.source_id,
                        DatasetSourceRecord.row_version == expected_version,
                    )
                    .values(
                        status=source.status.value,
                        approved_uses=[item.value for item in source.approved_uses],
                        rights_evidence_ref=source.rights_evidence_ref,
                        rights_evidence_sha256=source.rights_evidence_sha256,
                        terms_sha256=source.terms_sha256,
                        row_version=source.row_version,
                    )
                ),
            )
            if result.rowcount != 1:
                raise RegistryInvariantError("source update lost optimistic concurrency")

    async def add_fetch(self, fetch: DatasetFetch) -> None:
        async with self._sessions() as session, session.begin():
            result = cast(
                CursorResult[object],
                await session.execute(
                    insert(DatasetFetchRecord)
                    .values(_fetch_values(fetch))
                    .on_conflict_do_nothing(index_elements=["id"])
                ),
            )
            if result.rowcount == 1:
                return
            existing = await session.get(DatasetFetchRecord, fetch.fetch_id)
            if existing is None or _fetch(existing) != fetch:
                raise RegistryInvariantError("fetch id conflicts with registry")

    async def get_fetch(self, fetch_id: UUID) -> DatasetFetch | None:
        async with self._sessions() as session:
            record = await session.get(DatasetFetchRecord, fetch_id)
            return None if record is None else _fetch(record)

    async def save_fetch(self, fetch: DatasetFetch, *, expected_version: int) -> None:
        if fetch.row_version != expected_version + 1:
            raise RegistryInvariantError("fetch transition version is inconsistent")
        async with self._sessions() as session, session.begin():
            result = cast(
                CursorResult[object],
                await session.execute(
                    update(DatasetFetchRecord)
                    .where(
                        DatasetFetchRecord.id == fetch.fetch_id,
                        DatasetFetchRecord.row_version == expected_version,
                    )
                    .values(
                        state=fetch.state.value,
                        observed_sha256=fetch.observed_sha256,
                        observed_tree_sha256=fetch.observed_tree_sha256,
                        byte_size=fetch.byte_size,
                        quarantine_uri=fetch.quarantine_uri,
                        scan_evidence=_scan_evidence_values(fetch.scan_evidence),
                        row_version=fetch.row_version,
                    )
                ),
            )
            if result.rowcount != 1:
                raise RegistryInvariantError("fetch update lost optimistic concurrency")

    async def add_artifact(
        self, artifact: DatasetArtifact, *, provenance: dict[str, object]
    ) -> None:
        async with self._sessions() as session, session.begin():
            values = _artifact_values(artifact, provenance)
            result = cast(
                CursorResult[object],
                await session.execute(
                    insert(DatasetArtifactRecord)
                    .values(values)
                    .on_conflict_do_nothing(index_elements=["content_sha256"])
                ),
            )
            if result.rowcount == 1:
                return
            existing = await session.scalar(
                select(DatasetArtifactRecord).where(
                    DatasetArtifactRecord.content_sha256 == artifact.content_sha256
                )
            )
            if existing is None or not _same_artifact(existing, values):
                raise RegistryInvariantError("artifact digest conflicts with registry")


def _source_values(source: DatasetSource) -> dict[str, object]:
    return {
        "id": source.source_id,
        "source_key": source.source_key,
        "source_revision": source.source_revision,
        "origin_uri": source.origin_uri,
        "status": source.status.value,
        "owner_ref": source.owner_ref,
        "classification": source.classification,
        "proposed_uses": [item.value for item in source.proposed_uses],
        "approved_uses": [item.value for item in source.approved_uses],
        "rights_evidence_ref": source.rights_evidence_ref,
        "rights_evidence_sha256": source.rights_evidence_sha256,
        "terms_sha256": source.terms_sha256,
        "row_version": source.row_version,
    }


def _source(record: DatasetSourceRecord) -> DatasetSource:
    return DatasetSource(
        source_id=record.id,
        source_key=record.source_key,
        source_revision=record.source_revision,
        origin_uri=record.origin_uri,
        status=SourceStatus(record.status),
        owner_ref=record.owner_ref,
        classification=record.classification,
        proposed_uses=tuple(AllowedUse(item) for item in record.proposed_uses),
        approved_uses=tuple(AllowedUse(item) for item in record.approved_uses),
        rights_evidence_ref=record.rights_evidence_ref,
        rights_evidence_sha256=record.rights_evidence_sha256,
        terms_sha256=record.terms_sha256,
        row_version=record.row_version,
    )


def _fetch_values(fetch: DatasetFetch) -> dict[str, object]:
    return {
        "id": fetch.fetch_id,
        "source_id": fetch.source_id,
        "state": fetch.state.value,
        "requested_by": fetch.requested_by,
        "approval_evidence_ref": fetch.approval_evidence_ref,
        "approval_evidence_sha256": fetch.approval_evidence_sha256,
        "observed_sha256": fetch.observed_sha256,
        "observed_tree_sha256": fetch.observed_tree_sha256,
        "byte_size": fetch.byte_size,
        "quarantine_uri": fetch.quarantine_uri,
        "scan_evidence": _scan_evidence_values(fetch.scan_evidence),
        "row_version": fetch.row_version,
    }


def _scan_evidence_values(evidence: DatasetScanEvidence | None) -> dict[str, object]:
    if evidence is None:
        return {}
    return {
        "evidence_ref": evidence.evidence_ref,
        "evidence_sha256": evidence.evidence_sha256,
        "artifact_sha256": evidence.artifact_sha256,
        "scanner_revision": evidence.scanner_revision,
        "signature_revision": evidence.signature_revision,
        "structural_valid": evidence.structural_valid,
        "malware_passed": evidence.malware_passed,
        "dlp_decision": evidence.dlp_decision.value,
    }


def _fetch(record: DatasetFetchRecord) -> DatasetFetch:
    raw = record.scan_evidence
    evidence = None
    if raw:
        evidence = DatasetScanEvidence(
            evidence_ref=str(raw["evidence_ref"]),
            evidence_sha256=str(raw["evidence_sha256"]),
            artifact_sha256=str(raw["artifact_sha256"]),
            scanner_revision=str(raw["scanner_revision"]),
            signature_revision=str(raw["signature_revision"]),
            structural_valid=bool(raw["structural_valid"]),
            malware_passed=bool(raw["malware_passed"]),
            dlp_decision=DlpDecision(str(raw["dlp_decision"])),
        )
    return DatasetFetch(
        fetch_id=record.id,
        source_id=record.source_id,
        state=FetchState(record.state),
        requested_by=record.requested_by,
        approval_evidence_ref=record.approval_evidence_ref,
        approval_evidence_sha256=record.approval_evidence_sha256,
        observed_sha256=record.observed_sha256,
        observed_tree_sha256=record.observed_tree_sha256,
        byte_size=record.byte_size,
        quarantine_uri=record.quarantine_uri,
        scan_evidence=evidence,
        row_version=record.row_version,
    )


def _artifact_values(artifact: DatasetArtifact, provenance: dict[str, object]) -> dict[str, object]:
    return {
        "id": artifact.artifact_id,
        "content_sha256": artifact.content_sha256,
        "trust_zone": artifact.trust_zone.value,
        "processing_stage": artifact.processing_stage.value,
        "allowed_uses": [item.value for item in artifact.allowed_uses],
        "storage_uri": artifact.storage_uri,
        "media_type": artifact.media_type,
        "byte_size": artifact.byte_size,
        "classification": artifact.classification,
        "provenance": provenance,
        "status": artifact.status.value,
        "row_version": 1,
    }


def _same_artifact(record: DatasetArtifactRecord, values: dict[str, object]) -> bool:
    return all(getattr(record, field) == value for field, value in values.items() if field != "id")
