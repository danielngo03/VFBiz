"""Create durable conversation execution fence for cancellation and staleness.

Revision ID: 20260727_0012
Revises: 20260726_0011
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260727_0012"
down_revision: str | None = "20260726_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_conversation_execution_fence",
        sa.Column("turn_hash", sa.String(length=64), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
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
            name="ck_ai_conversation_execution_fence_fencing_positive",
        ),
        sa.CheckConstraint(
            "turn_hash ~ '^[a-f0-9]{64}$'",
            name="ck_ai_conversation_execution_fence_turn_hash",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "turn_hash", name="uq_ai_conversation_execution_fence_turn_hash"
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_conversation_execution_fence")
