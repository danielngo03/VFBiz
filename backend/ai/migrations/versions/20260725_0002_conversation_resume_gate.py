"""Create durable assistant conversation resume gate.

Revision ID: 20260725_0002
Revises: 20260722_0001
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260725_0002"
down_revision: str | None = "20260722_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_conversation_resume_gate",
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reservation_token_hash", sa.String(length=64), nullable=True),
        sa.Column("native_checkpoint_id", sa.String(length=255), nullable=True),
        sa.Column("envelope_digest", sa.String(length=64), nullable=True),
        sa.Column("interrupt_nonce_hash", sa.String(length=64), nullable=True),
        sa.Column("claim_token_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "fencing_token > 0",
            name="ck_ai_conversation_resume_gate_fencing_positive",
        ),
        sa.CheckConstraint(
            "key_hash ~ '^[a-f0-9]{64}$'",
            name="ck_ai_conversation_resume_gate_key_hash",
        ),
        sa.CheckConstraint(
            "reservation_token_hash IS NULL OR reservation_token_hash ~ '^[a-f0-9]{64}$'",
            name="ck_ai_conversation_resume_gate_reservation_hash",
        ),
        sa.CheckConstraint(
            "envelope_digest IS NULL OR envelope_digest ~ '^[a-f0-9]{64}$'",
            name="ck_ai_conversation_resume_gate_envelope_digest",
        ),
        sa.CheckConstraint(
            "interrupt_nonce_hash IS NULL OR interrupt_nonce_hash ~ '^[a-f0-9]{64}$'",
            name="ck_ai_conversation_resume_gate_nonce_hash",
        ),
        sa.CheckConstraint(
            "claim_token_hash IS NULL OR claim_token_hash ~ '^[a-f0-9]{64}$'",
            name="ck_ai_conversation_resume_gate_claim_hash",
        ),
        sa.CheckConstraint(
            "state IN ('reserved', 'waiting', 'claimed', 'completed', 'failed_closed', 'expired')",
            name="ck_ai_conversation_resume_gate_state",
        ),
        sa.CheckConstraint(
            "state <> 'reserved' OR reservation_token_hash IS NOT NULL",
            name="ck_ai_conversation_resume_gate_reserved_shape",
        ),
        sa.CheckConstraint(
            "state NOT IN ('waiting', 'claimed') OR "
            "(native_checkpoint_id IS NOT NULL AND envelope_digest IS NOT NULL "
            "AND interrupt_nonce_hash IS NOT NULL)",
            name="ck_ai_conversation_resume_gate_checkpoint_shape",
        ),
        sa.CheckConstraint(
            "state <> 'claimed' OR claim_token_hash IS NOT NULL",
            name="ck_ai_conversation_resume_gate_claimed_shape",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_ai_conversation_resume_gate_key_hash"),
    )
    op.create_index(
        "ix_ai_conversation_resume_gate_state_deadline",
        "ai_conversation_resume_gate",
        ["state", "deadline_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_conversation_resume_gate_state_deadline",
        table_name="ai_conversation_resume_gate",
    )
    op.drop_table("ai_conversation_resume_gate")
