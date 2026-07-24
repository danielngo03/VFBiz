"""Create governed AI persistence foundation.

Revision ID: 20260722_0001
Revises:
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260722_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def uuid_timestamp_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "ai_knowledge_source",
        *uuid_timestamp_columns(),
        sa.Column("uri", sa.String(length=1024), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("classification", sa.String(length=40), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("source_revision", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ai_knowledge_source_status_revision",
        "ai_knowledge_source",
        ["status", "source_revision"],
    )
    op.create_table(
        "ai_knowledge_chunk",
        *uuid_timestamp_columns(),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_revision", sa.String(length=160), nullable=False),
        sa.Column("content_checksum", sa.String(length=64), nullable=False),
        sa.Column("redacted_text", sa.Text(), nullable=False),
        sa.Column("acl", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=1536), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["ai_knowledge_source.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_ai_knowledge_chunk_source_revision",
        "ai_knowledge_chunk",
        ["source_id", "chunk_revision"],
    )
    op.create_table(
        "ai_dataset_release",
        *uuid_timestamp_columns(),
        sa.Column("manifest_ref", sa.String(length=255), nullable=False),
        sa.Column("owner_ref", sa.String(length=160), nullable=False),
        sa.Column("purpose", sa.String(length=255), nullable=False),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("classification", sa.String(length=40), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("manifest_ref"),
    )
    op.create_table(
        "ai_release",
        *uuid_timestamp_columns(),
        sa.Column("manifest_ref", sa.String(length=255), nullable=False),
        sa.Column("assistant_profile", sa.String(length=40), nullable=False),
        sa.Column("model_revision", sa.String(length=160), nullable=False),
        sa.Column("prompt_revision", sa.String(length=160), nullable=False),
        sa.Column("embedding_revision", sa.String(length=160), nullable=False),
        sa.Column("retriever_revision", sa.String(length=160), nullable=False),
        sa.Column("dataset_revisions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tool_registry_revision", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("kill_switch_enabled", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("manifest_ref"),
    )
    op.create_table(
        "ai_evaluation_run",
        *uuid_timestamp_columns(),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suite_revision", sa.String(length=160), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("security_passed", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["release_id"], ["ai_release.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "ai_audit_event",
        *uuid_timestamp_columns(),
        sa.Column("actor_ref", sa.String(length=160), nullable=True),
        sa.Column("action", sa.String(length=160), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_ref", sa.String(length=160), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_audit_event")
    op.drop_table("ai_evaluation_run")
    op.drop_table("ai_release")
    op.drop_table("ai_dataset_release")
    op.drop_index("ix_ai_knowledge_chunk_source_revision", table_name="ai_knowledge_chunk")
    op.drop_table("ai_knowledge_chunk")
    op.drop_index("ix_ai_knowledge_source_status_revision", table_name="ai_knowledge_source")
    op.drop_table("ai_knowledge_source")
