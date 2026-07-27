"""Persist idempotent ingestion control command results.

Revision ID: 20260725_0006
Revises: 20260725_0005
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260725_0006"
down_revision: str | None = "20260725_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_knowledge_ingestion_control_command",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("actor_ref", sa.String(160), nullable=False),
        sa.Column("result_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation IN ('request-deletion','replay-dead-letter')",
            name="ck_ai_knowledge_ingestion_control_operation",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["ai_knowledge_ingestion_job.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "operation",
            "idempotency_key_hash",
            name="uq_ai_knowledge_ingestion_control_command",
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_knowledge_ingestion_control_command")
