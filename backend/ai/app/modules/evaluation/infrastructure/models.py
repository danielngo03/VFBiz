from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
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
    candidate_manifest_digest: Mapped[str | None] = mapped_column(
        String(71), nullable=True
    )
    baseline_release_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    baseline_manifest_digest: Mapped[str | None] = mapped_column(
        String(71), nullable=True
    )
    benchmark_definition_digest: Mapped[str | None] = mapped_column(
        String(71), nullable=True
    )
    completed_case_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    row_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    evidence_bundle_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
