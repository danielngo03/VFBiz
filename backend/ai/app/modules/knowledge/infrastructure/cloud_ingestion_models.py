from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, UUIDTimestampMixin


class DocumentAiSubmissionRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_document_submission"

    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    receipt_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_date: Mapped[date] = mapped_column(Date, nullable=False)
    reservation_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_ai_document_submission_idempotency_key",
        ),
        CheckConstraint(
            "idempotency_key ~ '^[a-f0-9]{64}$' AND request_digest ~ '^[a-f0-9]{64}$'",
            name="ck_ai_document_submission_digests",
        ),
        CheckConstraint(
            "state IN ('reserved','submitted')",
            name="ck_ai_document_submission_state",
        ),
        CheckConstraint(
            "page_count BETWEEN 1 AND 500",
            name="ck_ai_document_submission_page_count",
        ),
        CheckConstraint(
            "jsonb_typeof(request_payload) = 'object' "
            "AND (receipt_payload IS NULL OR jsonb_typeof(receipt_payload) = 'object')",
            name="ck_ai_document_submission_payloads",
        ),
        CheckConstraint(
            "(state = 'reserved' AND receipt_payload IS NULL) "
            "OR (state = 'submitted' AND receipt_payload IS NOT NULL)",
            name="ck_ai_document_submission_receipt_state",
        ),
    )


class DocumentAiOperationObservationRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_document_operation_observation"

    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ai_document_submission.idempotency_key",
            name="fk_ai_document_operation_submission",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    operation_name: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    observation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_payload: Mapped[str] = mapped_column(Text, nullable=False)
    reconciled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            "observation_digest",
            name="uq_ai_document_operation_observation_digest",
        ),
        Index(
            "uq_ai_document_operation_terminal",
            "idempotency_key",
            unique=True,
            postgresql_where=text("state IN ('succeeded','failed','cancelled')"),
        ),
        CheckConstraint(
            "idempotency_key ~ '^[a-f0-9]{64}$' "
            "AND observation_digest ~ '^[a-f0-9]{64}$'",
            name="ck_ai_document_operation_digests",
        ),
        CheckConstraint(
            "state IN ('running','succeeded','failed','cancelled')",
            name="ck_ai_document_operation_state",
        ),
    )


class DocumentAiReconciliationClaimRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_document_reconciliation_claim"

    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ai_document_submission.idempotency_key",
            name="fk_ai_document_reconciliation_claim_submission",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    owner_token: Mapped[str] = mapped_column(String(64), nullable=False)
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_ai_document_reconciliation_claim_idempotency_key",
        ),
        CheckConstraint(
            "idempotency_key ~ '^[a-f0-9]{64}$' "
            "AND owner_token ~ '^[a-f0-9]{64}$' "
            "AND fencing_token >= 1 AND lease_until > claimed_at "
            "AND (released_at IS NULL OR released_at >= claimed_at)",
            name="ck_ai_document_reconciliation_claim_values",
        ),
    )


class DocumentAiExtractionEvidenceRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_document_extraction_evidence"

    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ai_document_submission.idempotency_key",
            name="fk_ai_document_extraction_submission",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_payload: Mapped[str] = mapped_column(Text, nullable=False)
    expected_page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    review_required_count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_ai_document_extraction_idempotency_key",
        ),
        UniqueConstraint(
            "evidence_digest",
            name="uq_ai_document_extraction_evidence_digest",
        ),
        CheckConstraint(
            "idempotency_key ~ '^[a-f0-9]{64}$' "
            "AND evidence_digest ~ '^[a-f0-9]{64}$'",
            name="ck_ai_document_extraction_digests",
        ),
        CheckConstraint(
            "expected_page_count BETWEEN 1 AND 500 "
            "AND review_required_count BETWEEN 0 AND expected_page_count",
            name="ck_ai_document_extraction_counts",
        ),
    )


class DocumentAiReconciliationFailureRecord(UUIDTimestampMixin, Base):
    __tablename__ = "ai_document_reconciliation_failure"

    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ai_document_submission.idempotency_key",
            name="fk_ai_document_reconciliation_failure_submission",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_code: Mapped[str] = mapped_column(String(80), nullable=False)
    retryable: Mapped[bool] = mapped_column(nullable=False)
    disposition: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_payload: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            "attempt",
            name="uq_ai_document_reconciliation_failure_attempt",
        ),
        UniqueConstraint(
            "evidence_digest",
            name="uq_ai_document_reconciliation_failure_digest",
        ),
        Index(
            "uq_ai_document_reconciliation_failure_quarantine",
            "idempotency_key",
            unique=True,
            postgresql_where=text("disposition = 'quarantined'"),
        ),
        CheckConstraint(
            "idempotency_key ~ '^[a-f0-9]{64}$' "
            "AND evidence_digest ~ '^[a-f0-9]{64}$'",
            name="ck_ai_document_reconciliation_failure_digests",
        ),
        CheckConstraint(
            "attempt BETWEEN 1 AND 3 "
            "AND failure_code ~ '^[A-Z][A-Z0-9_]{2,79}$' "
            "AND disposition IN ('retry-scheduled','quarantined')",
            name="ck_ai_document_reconciliation_failure_values",
        ),
        CheckConstraint(
            "(disposition = 'retry-scheduled' AND retryable AND next_retry_at IS NOT NULL) "
            "OR (disposition = 'quarantined' AND next_retry_at IS NULL)",
            name="ck_ai_document_reconciliation_failure_schedule",
        ),
    )
