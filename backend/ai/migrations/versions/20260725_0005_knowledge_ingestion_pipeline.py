"""Add bounded and fenced knowledge ingestion jobs.

Revision ID: 20260725_0005
Revises: 20260725_0004
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260725_0005"
down_revision: str | None = "20260725_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_knowledge_ingestion_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.String(160), nullable=False),
        sa.Column("source_revision", sa.String(160), nullable=False),
        sa.Column("scope_key", sa.String(240), nullable=False),
        sa.Column("command_fingerprint", sa.String(64), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("actor_ref", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_stage", sa.String(32), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("deletion_generation", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("aggregate", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_ai_knowledge_ingestion_version"),
        sa.CheckConstraint("fencing_token >= 0", name="ck_ai_knowledge_ingestion_fence"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "actor_ref", "idempotency_key_hash", name="uq_ai_knowledge_ingestion_command"
        ),
    )
    op.create_index(
        "ix_ai_knowledge_ingestion_claim",
        "ai_knowledge_ingestion_job",
        ["status", "next_attempt_at", "lease_expires_at", "created_at"],
    )
    op.create_table(
        "ai_knowledge_ingestion_stage_attempt",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("checkpoint", postgresql.JSONB()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["ai_knowledge_ingestion_job.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id", "stage", "attempt_number", "fencing_token",
            name="uq_ai_knowledge_ingestion_attempt",
        ),
    )
    op.create_table(
        "ai_knowledge_ingestion_artifact",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deletion_generation", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("unit_key", sa.String(256), nullable=False),
        sa.Column("artifact_ref", sa.String(512), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("record_count", sa.BigInteger(), nullable=False),
        sa.Column("parent_checksum", sa.String(64)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "byte_count >= 0 AND record_count >= 0",
            name="ck_ai_knowledge_ingestion_artifact_counts",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["ai_knowledge_ingestion_job.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id", "deletion_generation", "stage", "kind", "unit_key",
            name="uq_ai_knowledge_ingestion_artifact",
        ),
    )
    op.create_table(
        "ai_knowledge_ingestion_outbox",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_version", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["ai_knowledge_ingestion_job.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id", "aggregate_version", "event_type",
            name="uq_ai_knowledge_ingestion_outbox_event",
        ),
    )
    op.create_index(
        "ix_ai_knowledge_ingestion_outbox_pending",
        "ai_knowledge_ingestion_outbox",
        ["published_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_knowledge_ingestion_outbox_pending",
        table_name="ai_knowledge_ingestion_outbox",
    )
    op.drop_table("ai_knowledge_ingestion_outbox")
    op.drop_table("ai_knowledge_ingestion_artifact")
    op.drop_table("ai_knowledge_ingestion_stage_attempt")
    op.drop_index("ix_ai_knowledge_ingestion_claim", table_name="ai_knowledge_ingestion_job")
    op.drop_table("ai_knowledge_ingestion_job")
