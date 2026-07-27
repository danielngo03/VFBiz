"""Create governed Knowledge Release control plane.

Revision ID: 20260725_0003
Revises: 20260725_0002
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260725_0003"
down_revision: str | None = "20260725_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        sa.Column("canonical_source_id", sa.String(160), nullable=True),
        sa.Column("version", sa.String(160), nullable=True),
        sa.Column("source_type", sa.String(40), nullable=True),
        sa.Column("locator_ref", sa.String(255), nullable=True),
        sa.Column("approved_purposes", postgresql.JSONB(), nullable=True),
        sa.Column("acl_namespaces", postgresql.JSONB(), nullable=True),
        sa.Column("rights", postgresql.JSONB(), nullable=True),
        sa.Column("retention", postgresql.JSONB(), nullable=True),
        sa.Column("deletion_method", sa.String(160), nullable=True),
        sa.Column("owner_role", sa.String(160), nullable=True),
        sa.Column("custodian_role", sa.String(160), nullable=True),
        sa.Column("approval_evidence", postgresql.JSONB(), nullable=True),
        sa.Column("review_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registry_document_hash", sa.String(64), nullable=True),
        sa.Column(
            "deletion_fenced",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ):
        op.add_column("ai_knowledge_source", column)
    op.create_unique_constraint(
        "uq_ai_knowledge_source_canonical_source_id",
        "ai_knowledge_source",
        ["canonical_source_id"],
    )

    op.create_table(
        "ai_knowledge_release",
        sa.Column("domain", sa.String(80), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column("assistant_profile", sa.String(40), nullable=False),
        sa.Column("acl_namespace", sa.String(160), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("criticality", sa.String(24), nullable=False),
        sa.Column("source_set_hash", sa.String(64), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("transform_revision", sa.String(160), nullable=False),
        sa.Column("chunking_revision", sa.String(160), nullable=False),
        sa.Column("embedding_revision", sa.String(160), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("retriever_revision", sa.String(160), nullable=False),
        sa.Column("policy_revision", sa.String(160), nullable=False),
        sa.Column("index_checksum", sa.String(64), nullable=False),
        sa.Column("evaluation_run_ref", sa.String(160), nullable=True),
        sa.Column("evaluation_suite_revision", sa.String(160), nullable=True),
        sa.Column(
            "evaluation_evidence_hashes",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("proposer_ref", sa.String(160), nullable=False),
        sa.Column("approver_ref", sa.String(160), nullable=True),
        sa.Column("approval_source_set_hash", sa.String(64), nullable=True),
        sa.Column("approval_evidence_hash", sa.String(64), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("freshness_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_release_id", postgresql.UUID(as_uuid=True)),
        sa.Column("rollback_of_release_id", postgresql.UUID(as_uuid=True)),
        sa.Column("barrier_generation", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
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
            "status IN ('candidate','evaluated','ready','active','superseded',"
            "'rejected','tombstoned')",
            name="ck_ai_knowledge_release_status",
        ),
        sa.CheckConstraint(
            "criticality IN ('critical','non_critical')",
            name="ck_ai_knowledge_release_criticality",
        ),
        sa.CheckConstraint("version > 0", name="ck_ai_knowledge_release_version"),
        sa.CheckConstraint(
            "embedding_dimension > 0",
            name="ck_ai_knowledge_release_embedding_dimension",
        ),
        sa.ForeignKeyConstraint(
            ["rollback_of_release_id"], ["ai_knowledge_release.id"]
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_release_id"], ["ai_knowledge_release.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_ai_knowledge_release_active_scope",
        "ai_knowledge_release",
        ["domain", "locale", "assistant_profile", "acl_namespace"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    _create_release_source()
    _create_decision()
    _create_pointer()
    _create_transition()
    _create_outbox()


def _create_release_source() -> None:
    op.create_table(
        "ai_knowledge_release_source",
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_revision", sa.String(160), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("registry_document_hash", sa.String(64), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["release_id"], ["ai_knowledge_release.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["ai_knowledge_source.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "release_id", "source_id", name="uq_ai_knowledge_release_source"
        ),
    )


def _create_decision() -> None:
    op.create_table(
        "ai_knowledge_release_decision",
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("actor_ref", sa.String(160), nullable=False),
        sa.Column("entitlement_revision", sa.String(160), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('approved','rejected')",
            name="ck_ai_knowledge_release_decision",
        ),
        sa.ForeignKeyConstraint(
            ["release_id"], ["ai_knowledge_release.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_pointer() -> None:
    op.create_table(
        "ai_knowledge_revision_pointer",
        sa.Column("domain", sa.String(80), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column("assistant_profile", sa.String(40), nullable=False),
        sa.Column("acl_namespace", sa.String(160), nullable=False),
        sa.Column("active_release_id", postgresql.UUID(as_uuid=True)),
        sa.Column("previous_release_id", postgresql.UUID(as_uuid=True)),
        sa.Column("candidate_release_id", postgresql.UUID(as_uuid=True)),
        sa.Column("barrier_state", sa.String(16), nullable=False),
        sa.Column("barrier_generation", sa.BigInteger(), nullable=False),
        sa.Column("barrier_deadline_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.BigInteger(), nullable=False),
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
            "barrier_state IN ('clear','syncing','blocked')",
            name="ck_ai_knowledge_revision_pointer_barrier",
        ),
        sa.CheckConstraint(
            "version >= 0 AND barrier_generation >= 0",
            name="ck_ai_knowledge_revision_pointer_versions",
        ),
        sa.ForeignKeyConstraint(["active_release_id"], ["ai_knowledge_release.id"]),
        sa.ForeignKeyConstraint(
            ["candidate_release_id"], ["ai_knowledge_release.id"]
        ),
        sa.ForeignKeyConstraint(
            ["previous_release_id"], ["ai_knowledge_release.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "domain",
            "locale",
            "assistant_profile",
            "acl_namespace",
            name="uq_ai_knowledge_revision_pointer_scope",
        ),
    )


def _create_transition() -> None:
    op.create_table(
        "ai_knowledge_release_transition",
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_state", sa.String(24)),
        sa.Column("next_state", sa.String(24), nullable=False),
        sa.Column("actor_ref", sa.String(160), nullable=False),
        sa.Column("reason", sa.String(160), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("evidence_hash", sa.String(64)),
        sa.Column("barrier_generation", sa.BigInteger(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["release_id"], ["ai_knowledge_release.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key_hash",
            name="uq_ai_knowledge_release_transition_idempotency",
        ),
    )


def _create_outbox() -> None:
    op.create_table(
        "ai_knowledge_release_outbox",
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key_hash",
            "event_type",
            name="uq_ai_knowledge_release_outbox_event",
        ),
    )
    op.create_index(
        "ix_ai_knowledge_release_outbox_pending",
        "ai_knowledge_release_outbox",
        ["published_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_knowledge_release_outbox_pending",
        table_name="ai_knowledge_release_outbox",
    )
    for table in (
        "ai_knowledge_release_outbox",
        "ai_knowledge_release_transition",
        "ai_knowledge_revision_pointer",
        "ai_knowledge_release_decision",
        "ai_knowledge_release_source",
    ):
        op.drop_table(table)
    op.drop_index(
        "uq_ai_knowledge_release_active_scope",
        table_name="ai_knowledge_release",
    )
    op.drop_table("ai_knowledge_release")
    op.drop_constraint(
        "uq_ai_knowledge_source_canonical_source_id",
        "ai_knowledge_source",
        type_="unique",
    )
    for column in (
        "updated_at",
        "deletion_fenced",
        "registry_document_hash",
        "review_date",
        "approval_evidence",
        "custodian_role",
        "owner_role",
        "deletion_method",
        "retention",
        "rights",
        "acl_namespaces",
        "approved_purposes",
        "locator_ref",
        "source_type",
        "version",
        "canonical_source_id",
    ):
        op.drop_column("ai_knowledge_source", column)
