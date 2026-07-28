from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, UUIDTimestampMixin


class DatasetSourceRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_dataset_source"

    source_key: Mapped[str] = mapped_column(String(160), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(255), nullable=False)
    origin_uri: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    proposed_uses: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    approved_uses: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    rights_evidence_ref: Mapped[str | None] = mapped_column(String(255))
    rights_evidence_sha256: Mapped[str | None] = mapped_column(String(64))
    terms_sha256: Mapped[str | None] = mapped_column(String(64))
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class DatasetFetchRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_dataset_fetch"

    source_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("ai_dataset_source.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False)
    approval_evidence_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    approval_evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_sha256: Mapped[str | None] = mapped_column(String(64))
    observed_tree_sha256: Mapped[str | None] = mapped_column(String(64))
    media_type: Mapped[str | None] = mapped_column(String(160))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    quarantine_uri: Mapped[str | None] = mapped_column(Text)
    scan_evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class DatasetArtifactRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_dataset_artifact"

    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tree_sha256: Mapped[str | None] = mapped_column(String(64))
    trust_zone: Mapped[str] = mapped_column(String(40), nullable=False)
    processing_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed_uses: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class DatasetFetchArtifactRecord(Base):
    __tablename__ = "ai_dataset_fetch_artifact"

    fetch_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_dataset_fetch.id"),
        primary_key=True,
    )
    artifact_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_dataset_artifact.id"),
        primary_key=True,
    )


class DatasetLineageEdgeRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_dataset_lineage_edge"

    parent_artifact_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("ai_dataset_artifact.id"), nullable=False
    )
    child_artifact_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("ai_dataset_artifact.id"), nullable=False
    )
    transformation_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    transformation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    generator_revision: Mapped[str | None] = mapped_column(String(255))


class DatasetQualityRunRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_dataset_quality_run"

    artifact_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("ai_dataset_artifact.id"), nullable=False
    )
    suite_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    report_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class DatasetReleasePointerRecord(Base):
    __tablename__ = "ai_dataset_release_pointer"

    environment: Mapped[str] = mapped_column(String(24), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(40), primary_key=True)
    release_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("ai_dataset_release.id"), nullable=False
    )
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    pointer_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_by: Mapped[str] = mapped_column(String(160), nullable=False)


class DatasetTombstoneRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_dataset_tombstone"

    artifact_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("ai_dataset_artifact.id"), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(160), nullable=False)
    deletion_method: Mapped[str] = mapped_column(String(80), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
