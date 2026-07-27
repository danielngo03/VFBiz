from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, UUIDTimestampMixin


class EmbeddingIndexGenerationRecord(Base):
    __tablename__ = "ai_embedding_index_generation"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    generation_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    embedding_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_metric: Mapped[str] = mapped_column(String(16), nullable=False)
    normalization: Mapped[str] = mapped_column(String(16), nullable=False)
    instruction_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    tokenizer_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class KnowledgeSource(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_source"

    uri: Mapped[str] = mapped_column(String(1_024), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canonical_source_id: Mapped[str | None] = mapped_column(String(160), unique=True)
    version: Mapped[str | None] = mapped_column(String(160))
    source_type: Mapped[str | None] = mapped_column(String(40))
    locator_ref: Mapped[str | None] = mapped_column(String(255))
    approved_purposes: Mapped[list[str] | None] = mapped_column(JSONB)
    acl_namespaces: Mapped[list[str] | None] = mapped_column(JSONB)
    rights: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    retention: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    deletion_method: Mapped[str | None] = mapped_column(String(160))
    owner_role: Mapped[str | None] = mapped_column(String(160))
    custodian_role: Mapped[str | None] = mapped_column(String(160))
    approval_evidence: Mapped[list[str] | None] = mapped_column(JSONB)
    review_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registry_document_hash: Mapped[str | None] = mapped_column(String(64))
    deletion_fenced: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (Index("ix_ai_knowledge_source_status_revision", "status", "source_revision"),)


class KnowledgeChunk(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_chunk"

    source_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_knowledge_source.id", ondelete="CASCADE"),
        nullable=False,
    )
    release_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_knowledge_release.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    index_generation_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    embedding_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acl_namespace: Mapped[str] = mapped_column(String(160), nullable=False)
    citation_uri: Mapped[str] = mapped_column(String(2_048), nullable=False)
    citation_title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    redacted_text: Mapped[str] = mapped_column(Text, nullable=False)
    acl: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["release_id", "source_id"],
            [
                "ai_knowledge_release_source.release_id",
                "ai_knowledge_release_source.source_id",
            ],
            ondelete="CASCADE",
            name="fk_ai_knowledge_chunk_release_source",
        ),
        UniqueConstraint(
            "release_id",
            "source_id",
            "chunk_revision",
            name="uq_ai_knowledge_chunk_release_source_revision",
        ),
        Index("ix_ai_knowledge_chunk_source_revision", "source_id", "chunk_revision"),
        Index(
            "ix_ai_knowledge_chunk_release_acl",
            "release_id",
            "acl_namespace",
        ),
    )


class KnowledgeReleaseRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_release"

    domain: Mapped[str] = mapped_column(String(80), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    assistant_profile: Mapped[str] = mapped_column(String(40), nullable=False)
    acl_namespace: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    criticality: Mapped[str] = mapped_column(String(24), nullable=False)
    source_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    transform_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    chunking_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    index_generation_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    embedding_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    retriever_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    policy_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    index_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    materialization_checksum: Mapped[str | None] = mapped_column(String(64))
    materialized_chunk_count: Mapped[int | None] = mapped_column(Integer)
    evaluation_run_ref: Mapped[str | None] = mapped_column(String(160))
    evaluation_suite_revision: Mapped[str | None] = mapped_column(String(160))
    evaluation_evidence_hashes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    proposer_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    approver_ref: Mapped[str | None] = mapped_column(String(160))
    approval_source_set_hash: Mapped[str | None] = mapped_column(String(64))
    approval_evidence_hash: Mapped[str | None] = mapped_column(String(64))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    freshness_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_release_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("ai_knowledge_release.id")
    )
    rollback_of_release_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("ai_knowledge_release.id")
    )
    barrier_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate','evaluated','ready','active','superseded',"
            "'rejected','tombstoned')",
            name="ck_ai_knowledge_release_status",
        ),
        CheckConstraint(
            "criticality IN ('critical','non_critical')",
            name="ck_ai_knowledge_release_criticality",
        ),
        CheckConstraint("version > 0", name="ck_ai_knowledge_release_version"),
        CheckConstraint(
            "embedding_dimension > 0",
            name="ck_ai_knowledge_release_embedding_dimension",
        ),
        Index(
            "uq_ai_knowledge_release_active_scope",
            "domain",
            "locale",
            "assistant_profile",
            "acl_namespace",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )


class KnowledgeReleaseSource(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_release_source"

    release_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_knowledge_release.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_knowledge_source.id"),
        nullable=False,
    )
    source_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    registry_document_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "release_id",
            "source_id",
            name="uq_ai_knowledge_release_source",
        ),
    )


class KnowledgeReleaseDecision(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_release_decision"

    release_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_knowledge_release.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    entitlement_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "decision IN ('approved','rejected')",
            name="ck_ai_knowledge_release_decision",
        ),
    )


class KnowledgeRevisionPointer(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_revision_pointer"

    domain: Mapped[str] = mapped_column(String(80), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    assistant_profile: Mapped[str] = mapped_column(String(40), nullable=False)
    acl_namespace: Mapped[str] = mapped_column(String(160), nullable=False)
    active_release_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("ai_knowledge_release.id")
    )
    previous_release_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("ai_knowledge_release.id")
    )
    candidate_release_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("ai_knowledge_release.id")
    )
    barrier_state: Mapped[str] = mapped_column(String(16), nullable=False)
    barrier_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    barrier_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "domain",
            "locale",
            "assistant_profile",
            "acl_namespace",
            name="uq_ai_knowledge_revision_pointer_scope",
        ),
        CheckConstraint(
            "barrier_state IN ('clear','syncing','blocked')",
            name="ck_ai_knowledge_revision_pointer_barrier",
        ),
        CheckConstraint(
            "version >= 0 AND barrier_generation >= 0",
            name="ck_ai_knowledge_revision_pointer_versions",
        ),
    )


class KnowledgeReleaseTransition(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_release_transition"

    release_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_knowledge_release.id", ondelete="CASCADE"),
        nullable=False,
    )
    previous_state: Mapped[str | None] = mapped_column(String(24))
    next_state: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(String(160), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_hash: Mapped[str | None] = mapped_column(String(64))
    barrier_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    result_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key_hash",
            name="uq_ai_knowledge_release_transition_idempotency",
        ),
    )


class KnowledgeReleaseOutbox(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_release_outbox"

    aggregate_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key_hash",
            "event_type",
            name="uq_ai_knowledge_release_outbox_event",
        ),
        Index("ix_ai_knowledge_release_outbox_pending", "published_at"),
    )
