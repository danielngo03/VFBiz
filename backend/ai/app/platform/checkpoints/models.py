from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, UUIDTimestampMixin


class ConversationResumeGate(UUIDTimestampMixin, Base):
    """Durable single-consumer gate for one assistant turn.

    Identifiers and bearer-like values are represented by SHA-256 digests. The
    native checkpoint identifier is an opaque database locator, never a message
    or customer identity.
    """

    __tablename__ = "ai_conversation_resume_gate"

    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reservation_token_hash: Mapped[str | None] = mapped_column(String(64))
    native_checkpoint_id: Mapped[str | None] = mapped_column(String(255))
    envelope_digest: Mapped[str | None] = mapped_column(String(64))
    interrupt_nonce_hash: Mapped[str | None] = mapped_column(String(64))
    claim_token_hash: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('reserved', 'waiting', 'claimed', 'completed', "
            "'failed_closed', 'expired')",
            name="ck_ai_conversation_resume_gate_state",
        ),
        CheckConstraint(
            "state <> 'reserved' OR reservation_token_hash IS NOT NULL",
            name="ck_ai_conversation_resume_gate_reserved_shape",
        ),
        CheckConstraint(
            "state NOT IN ('waiting', 'claimed') OR "
            "(native_checkpoint_id IS NOT NULL AND envelope_digest IS NOT NULL "
            "AND interrupt_nonce_hash IS NOT NULL)",
            name="ck_ai_conversation_resume_gate_checkpoint_shape",
        ),
        CheckConstraint(
            "state <> 'claimed' OR claim_token_hash IS NOT NULL",
            name="ck_ai_conversation_resume_gate_claimed_shape",
        ),
        CheckConstraint(
            "fencing_token > 0",
            name="ck_ai_conversation_resume_gate_fencing_positive",
        ),
        CheckConstraint(
            "key_hash ~ '^[a-f0-9]{64}$'",
            name="ck_ai_conversation_resume_gate_key_hash",
        ),
        CheckConstraint(
            "reservation_token_hash IS NULL OR "
            "reservation_token_hash ~ '^[a-f0-9]{64}$'",
            name="ck_ai_conversation_resume_gate_reservation_hash",
        ),
        CheckConstraint(
            "envelope_digest IS NULL OR envelope_digest ~ '^[a-f0-9]{64}$'",
            name="ck_ai_conversation_resume_gate_envelope_digest",
        ),
        CheckConstraint(
            "interrupt_nonce_hash IS NULL OR "
            "interrupt_nonce_hash ~ '^[a-f0-9]{64}$'",
            name="ck_ai_conversation_resume_gate_nonce_hash",
        ),
        CheckConstraint(
            "claim_token_hash IS NULL OR claim_token_hash ~ '^[a-f0-9]{64}$'",
            name="ck_ai_conversation_resume_gate_claim_hash",
        ),
        UniqueConstraint(
            "key_hash",
            name="uq_ai_conversation_resume_gate_key_hash",
        ),
        Index(
            "ix_ai_conversation_resume_gate_state_deadline",
            "state",
            "deadline_at",
        ),
    )


class ConversationExecutionFence(UUIDTimestampMixin, Base):
    """Durable per-turn fencing pointer for cancellation and staleness checks.

    `turn_hash` is a SHA-256 digest of the opaque (session_id, turn_id) pair,
    never the raw identifiers. `fencing_token` only ever advances; a lower
    incoming token is stale and must not change stored state.
    """

    __tablename__ = "ai_conversation_execution_fence"

    turn_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "fencing_token > 0",
            name="ck_ai_conversation_execution_fence_fencing_positive",
        ),
        CheckConstraint(
            "turn_hash ~ '^[a-f0-9]{64}$'",
            name="ck_ai_conversation_execution_fence_turn_hash",
        ),
        UniqueConstraint(
            "turn_hash", name="uq_ai_conversation_execution_fence_turn_hash"
        ),
    )
