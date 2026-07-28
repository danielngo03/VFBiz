"""Provision durable Dataset Registry metadata and lineage.

Revision ID: 20260728_0016
Revises: 20260727_0015
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260728_0016"
down_revision: str | None = "20260727_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identity_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "ai_dataset_source",
        *_identity_columns(),
        sa.Column("source_key", sa.String(160), nullable=False),
        sa.Column("source_revision", sa.String(255), nullable=False),
        sa.Column("origin_uri", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("owner_ref", sa.String(160), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("proposed_uses", postgresql.JSONB(), nullable=False),
        sa.Column("approved_uses", postgresql.JSONB(), nullable=False),
        sa.Column("rights_evidence_ref", sa.String(255), nullable=True),
        sa.Column("rights_evidence_sha256", sa.CHAR(64), nullable=True),
        sa.Column("terms_sha256", sa.CHAR(64), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.BigInteger(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('candidate','legal-hold','fetch-approved',"
            "'purpose-approved','rejected','tombstoned')",
            name="ck_ai_dataset_source_status",
        ),
        sa.CheckConstraint("row_version > 0", name="ck_ai_dataset_source_version"),
        sa.CheckConstraint(
            "rights_evidence_sha256 IS NULL OR rights_evidence_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_ai_dataset_source_rights_digest",
        ),
        sa.CheckConstraint(
            "terms_sha256 IS NULL OR terms_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_ai_dataset_source_terms_digest",
        ),
        sa.UniqueConstraint("source_key", "source_revision", name="uq_ai_dataset_source_revision"),
    )
    op.create_index("ix_ai_dataset_source_status", "ai_dataset_source", ["status"])

    op.create_table(
        "ai_dataset_fetch",
        *_identity_columns(),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("requested_by", sa.String(160), nullable=False),
        sa.Column("approval_evidence_ref", sa.String(255), nullable=False),
        sa.Column("approval_evidence_sha256", sa.CHAR(64), nullable=False),
        sa.Column("observed_sha256", sa.CHAR(64), nullable=True),
        sa.Column("observed_tree_sha256", sa.CHAR(64), nullable=True),
        sa.Column("media_type", sa.String(160), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("quarantine_uri", sa.Text(), nullable=True),
        sa.Column("scan_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("failure_code", sa.String(80), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.BigInteger(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["ai_dataset_source.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "state IN ('requested','downloading','quarantined','verified',"
            "'scan-passed','rejected','deleted')",
            name="ck_ai_dataset_fetch_state",
        ),
        sa.CheckConstraint("byte_size IS NULL OR byte_size >= 0", name="ck_ai_dataset_fetch_size"),
        sa.CheckConstraint("row_version > 0", name="ck_ai_dataset_fetch_version"),
        sa.CheckConstraint(
            "approval_evidence_sha256 ~ '^[a-f0-9]{64}$' AND "
            "(observed_sha256 IS NULL OR observed_sha256 ~ '^[a-f0-9]{64}$') AND "
            "(observed_tree_sha256 IS NULL OR observed_tree_sha256 ~ '^[a-f0-9]{64}$')",
            name="ck_ai_dataset_fetch_digests",
        ),
    )
    op.create_index("ix_ai_dataset_fetch_source_state", "ai_dataset_fetch", ["source_id", "state"])

    op.create_table(
        "ai_dataset_artifact",
        *_identity_columns(),
        sa.Column("content_sha256", sa.CHAR(64), nullable=False),
        sa.Column("tree_sha256", sa.CHAR(64), nullable=True),
        sa.Column("trust_zone", sa.String(40), nullable=False),
        sa.Column("processing_stage", sa.String(32), nullable=False),
        sa.Column("allowed_uses", postgresql.JSONB(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(160), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("row_version", sa.BigInteger(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "trust_zone IN ('quarantine','candidate','released','restricted-evaluation',"
            "'red-team','review-evidence','tombstones')",
            name="ck_ai_dataset_artifact_zone",
        ),
        sa.CheckConstraint(
            "processing_stage IN ('raw','normalized','filtered','enriched','adjudicated')",
            name="ck_ai_dataset_artifact_stage",
        ),
        sa.CheckConstraint(
            "status IN ('active','rejected','tombstoned','deleted')",
            name="ck_ai_dataset_artifact_status",
        ),
        sa.CheckConstraint(
            "byte_size >= 0 AND row_version > 0", name="ck_ai_dataset_artifact_values"
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[a-f0-9]{64}$' AND "
            "(tree_sha256 IS NULL OR tree_sha256 ~ '^[a-f0-9]{64}$')",
            name="ck_ai_dataset_artifact_digests",
        ),
        sa.UniqueConstraint("content_sha256", name="uq_ai_dataset_artifact_content"),
    )
    op.create_index(
        "ix_ai_dataset_artifact_zone_stage",
        "ai_dataset_artifact",
        ["trust_zone", "processing_stage", "status"],
    )

    op.create_table(
        "ai_dataset_fetch_artifact",
        sa.Column("fetch_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.ForeignKeyConstraint(["fetch_id"], ["ai_dataset_fetch.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["artifact_id"], ["ai_dataset_artifact.id"], ondelete="RESTRICT"),
    )

    op.create_table(
        "ai_dataset_lineage_edge",
        *_identity_columns(),
        sa.Column("parent_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("child_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transformation_kind", sa.String(80), nullable=False),
        sa.Column("transformation_sha256", sa.CHAR(64), nullable=False),
        sa.Column("execution_ref", sa.String(255), nullable=False),
        sa.Column("generator_revision", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_artifact_id"], ["ai_dataset_artifact.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["child_artifact_id"], ["ai_dataset_artifact.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "parent_artifact_id <> child_artifact_id", name="ck_ai_dataset_lineage_no_self"
        ),
        sa.CheckConstraint(
            "transformation_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_ai_dataset_lineage_digest",
        ),
        sa.UniqueConstraint(
            "parent_artifact_id",
            "child_artifact_id",
            "transformation_sha256",
            name="uq_ai_dataset_lineage_edge",
        ),
    )

    op.create_table(
        "ai_dataset_quality_run",
        *_identity_columns(),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suite_revision", sa.String(160), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("report_sha256", sa.CHAR(64), nullable=False),
        sa.Column("execution_provenance", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["ai_dataset_artifact.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status IN ('running','passed','failed','cancelled')",
            name="ck_ai_dataset_quality_status",
        ),
        sa.CheckConstraint("report_sha256 ~ '^[a-f0-9]{64}$'", name="ck_ai_dataset_quality_digest"),
        sa.UniqueConstraint("artifact_id", "suite_revision", name="uq_ai_dataset_quality_suite"),
    )

    op.add_column("ai_dataset_release", sa.Column("manifest_sha256", sa.CHAR(64), nullable=True))
    op.add_column(
        "ai_dataset_release",
        sa.Column("status", sa.String(24), server_default="draft", nullable=False),
    )
    op.add_column(
        "ai_dataset_release",
        sa.Column("allowed_uses", postgresql.JSONB(), server_default="[]", nullable=False),
    )
    op.add_column(
        "ai_dataset_release",
        sa.Column("artifact_ids", postgresql.JSONB(), server_default="[]", nullable=False),
    )
    op.add_column(
        "ai_dataset_release", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "ai_dataset_release", sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "ai_dataset_release",
        sa.Column("row_version", sa.BigInteger(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        "ck_ai_dataset_release_status",
        "ai_dataset_release",
        "status IN ('draft','candidate','approved','released','rolled-back','tombstoned')",
    )
    op.create_check_constraint(
        "ck_ai_dataset_release_digest",
        "ai_dataset_release",
        "manifest_sha256 IS NULL OR manifest_sha256 ~ '^[a-f0-9]{64}$'",
    )
    op.create_check_constraint(
        "ck_ai_dataset_release_version", "ai_dataset_release", "row_version > 0"
    )
    op.create_unique_constraint(
        "uq_ai_dataset_release_digest", "ai_dataset_release", ["manifest_sha256"]
    )

    op.create_table(
        "ai_dataset_release_pointer",
        sa.Column("environment", sa.String(24), primary_key=True),
        sa.Column("purpose", sa.String(40), primary_key=True),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_sha256", sa.CHAR(64), nullable=False),
        sa.Column("pointer_revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("activated_by", sa.String(160), nullable=False),
        sa.ForeignKeyConstraint(["release_id"], ["ai_dataset_release.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "manifest_sha256 ~ '^[a-f0-9]{64}$'", name="ck_ai_dataset_pointer_digest"
        ),
        sa.CheckConstraint("pointer_revision > 0", name="ck_ai_dataset_pointer_revision"),
    )

    op.create_table(
        "ai_dataset_tombstone",
        *_identity_columns(),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("evidence_ref", sa.String(255), nullable=False),
        sa.Column("evidence_sha256", sa.CHAR(64), nullable=False),
        sa.Column("requested_by", sa.String(160), nullable=False),
        sa.Column("approved_by", sa.String(160), nullable=False),
        sa.Column("deletion_method", sa.String(80), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["artifact_id"], ["ai_dataset_artifact.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("requested_by <> approved_by", name="ck_ai_dataset_tombstone_sod"),
        sa.CheckConstraint(
            "evidence_sha256 ~ '^[a-f0-9]{64}$'", name="ck_ai_dataset_tombstone_digest"
        ),
        sa.UniqueConstraint("artifact_id", name="uq_ai_dataset_tombstone_artifact"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    governed_rows = connection.execute(
        sa.text(
            """
            SELECT
                EXISTS (SELECT 1 FROM ai_dataset_source)
                OR EXISTS (SELECT 1 FROM ai_dataset_fetch)
                OR EXISTS (SELECT 1 FROM ai_dataset_artifact)
                OR EXISTS (SELECT 1 FROM ai_dataset_fetch_artifact)
                OR EXISTS (SELECT 1 FROM ai_dataset_lineage_edge)
                OR EXISTS (SELECT 1 FROM ai_dataset_quality_run)
                OR EXISTS (SELECT 1 FROM ai_dataset_release_pointer)
                OR EXISTS (SELECT 1 FROM ai_dataset_tombstone)
                OR EXISTS (
                    SELECT 1
                    FROM ai_dataset_release
                    WHERE manifest_sha256 IS NOT NULL
                       OR status <> 'draft'
                       OR allowed_uses <> '[]'::jsonb
                       OR artifact_ids <> '[]'::jsonb
                       OR released_at IS NOT NULL
                       OR tombstoned_at IS NOT NULL
                       OR row_version <> 1
                )
            """
        )
    ).scalar_one()
    if governed_rows:
        raise RuntimeError(
            "cannot downgrade 20260728_0016 while governed dataset records exist; "
            "export or delete them under approved retention policy first"
        )
    op.drop_table("ai_dataset_tombstone")
    op.drop_table("ai_dataset_release_pointer")
    op.drop_constraint("uq_ai_dataset_release_digest", "ai_dataset_release", type_="unique")
    op.drop_constraint("ck_ai_dataset_release_version", "ai_dataset_release", type_="check")
    op.drop_constraint("ck_ai_dataset_release_digest", "ai_dataset_release", type_="check")
    op.drop_constraint("ck_ai_dataset_release_status", "ai_dataset_release", type_="check")
    for column in (
        "row_version",
        "tombstoned_at",
        "released_at",
        "artifact_ids",
        "allowed_uses",
        "status",
        "manifest_sha256",
    ):
        op.drop_column("ai_dataset_release", column)
    op.drop_table("ai_dataset_quality_run")
    op.drop_table("ai_dataset_lineage_edge")
    op.drop_table("ai_dataset_fetch_artifact")
    op.drop_index("ix_ai_dataset_artifact_zone_stage", table_name="ai_dataset_artifact")
    op.drop_table("ai_dataset_artifact")
    op.drop_index("ix_ai_dataset_fetch_source_state", table_name="ai_dataset_fetch")
    op.drop_table("ai_dataset_fetch")
    op.drop_index("ix_ai_dataset_source_status", table_name="ai_dataset_source")
    op.drop_table("ai_dataset_source")
