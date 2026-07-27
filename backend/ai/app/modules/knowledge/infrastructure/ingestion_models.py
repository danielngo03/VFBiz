from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, UUIDTimestampMixin


class KnowledgeIngestionJobRecord(Base):
    __tablename__ = "ai_knowledge_ingestion_job"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(240), nullable=False)
    command_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deletion_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    aggregate: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "actor_ref",
            "idempotency_key_hash",
            name="uq_ai_knowledge_ingestion_command",
        ),
        CheckConstraint("version > 0", name="ck_ai_knowledge_ingestion_version"),
        CheckConstraint("fencing_token >= 0", name="ck_ai_knowledge_ingestion_fence"),
        CheckConstraint(
            "deletion_generation >= 0",
            name="ck_ai_knowledge_ingestion_deletion_generation",
        ),
        CheckConstraint(
            "status IN ('queued','running','retry_wait','candidate_ready',"
            "'failed_safely','dead_lettered','deletion_pending','deleting','tombstoned')",
            name="ck_ai_knowledge_ingestion_status",
        ),
        CheckConstraint(
            "current_stage IN ('quarantine','pre_scan','parse','content_scan',"
            "'chunk','embed','verify','delete')",
            name="ck_ai_knowledge_ingestion_stage",
        ),
        Index(
            "ix_ai_knowledge_ingestion_claim",
            "status",
            "next_attempt_at",
            "lease_expires_at",
            "created_at",
        ),
    )


class KnowledgeIngestionStageAttempt(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_ingestion_stage_attempt"

    job_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_knowledge_ingestion_job.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "stage",
            "attempt_number",
            "fencing_token",
            name="uq_ai_knowledge_ingestion_attempt",
        ),
        CheckConstraint(
            "outcome IN ('completed','checkpointed','retry_scheduled','dead_lettered',"
            "'failed_safely','deletion_scheduled','tombstoned')",
            name="ck_ai_knowledge_ingestion_attempt_outcome",
        ),
    )


class KnowledgeIngestionArtifact(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_ingestion_artifact"

    job_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_knowledge_ingestion_job.id", ondelete="CASCADE"),
        nullable=False,
    )
    deletion_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    unit_key: Mapped[str] = mapped_column(String(256), nullable=False)
    artifact_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    record_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parent_checksum: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "deletion_generation",
            "stage",
            "kind",
            "unit_key",
            name="uq_ai_knowledge_ingestion_artifact",
        ),
        CheckConstraint(
            "byte_count >= 0 AND record_count >= 0",
            name="ck_ai_knowledge_ingestion_artifact_counts",
        ),
    )


class KnowledgeIngestionOutbox(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_ingestion_outbox"

    job_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_knowledge_ingestion_job.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "aggregate_version",
            "event_type",
            name="uq_ai_knowledge_ingestion_outbox_event",
        ),
        Index(
            "ix_ai_knowledge_ingestion_outbox_pending",
            "published_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )


class KnowledgeIngestionControlCommand(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_ingestion_control_command"

    job_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_knowledge_ingestion_job.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "operation IN ('request-deletion','replay-dead-letter')",
            name="ck_ai_knowledge_ingestion_control_operation",
        ),
        UniqueConstraint(
            "job_id",
            "operation",
            "idempotency_key_hash",
            name="uq_ai_knowledge_ingestion_control_command",
        ),
    )
