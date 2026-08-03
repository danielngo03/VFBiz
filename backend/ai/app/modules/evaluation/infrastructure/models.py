from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, UUIDTimestampMixin


class EvaluationRunRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_evaluation_run"

    release_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_release.id", ondelete="RESTRICT"),
        nullable=True,
    )
    suite_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    security_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    run_key: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    plan_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    plan_document: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    authority_class: Mapped[str | None] = mapped_column(String(40), nullable=True)
    candidate_release_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    candidate_manifest_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    baseline_release_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    baseline_manifest_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    benchmark_definition_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    completed_case_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    evidence_bundle_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class EvaluationCaseResultRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_evaluation_case_result"

    run_key: Mapped[str] = mapped_column(
        String(160),
        ForeignKey("ai_evaluation_run.run_key", ondelete="CASCADE"),
        nullable=False,
    )
    case_key: Mapped[str] = mapped_column(String(200), nullable=False)
    case_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(160), nullable=False)
    lease_token: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    output_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sanitized_trace_ref: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    grader_outputs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
    )
    metric_outputs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
    )
    validity_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    result_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    canonical_payload: Mapped[str] = mapped_column(Text, nullable=False)


class EvaluationCaseTaskRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_evaluation_case_task"

    run_key: Mapped[str] = mapped_column(
        String(160),
        ForeignKey("ai_evaluation_run.run_key", ondelete="CASCADE"),
        nullable=False,
    )
    case_key: Mapped[str] = mapped_column(String(200), nullable=False)
    case_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    suite_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    shard_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lease_token: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class EvaluationEvidenceBundleRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_evaluation_evidence_bundle"

    run_key: Mapped[str] = mapped_column(
        String(160),
        ForeignKey("ai_evaluation_run.run_key", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    plan_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    bundle_digest: Mapped[str] = mapped_column(
        String(71),
        nullable=False,
        unique=True,
    )
    case_results_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    run_result_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    authority_class: Mapped[str] = mapped_column(String(40), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(40), nullable=False)
    sealed_from_row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    suite_snapshot_payload: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_policy_payload: Mapped[str] = mapped_column(Text, nullable=False)
    run_result_payload: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_document: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    canonical_payload: Mapped[str] = mapped_column(Text, nullable=False)


class EvaluationDefinitionReleaseRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_evaluation_definition_release"

    definition_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    definition_key: Mapped[str] = mapped_column(String(200), nullable=False)
    revision: Mapped[str] = mapped_column(String(200), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    canonical_payload: Mapped[str] = mapped_column(Text, nullable=False)
    release_evidence_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    released_by_subject: Mapped[str] = mapped_column(String(200), nullable=False)
    released_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
