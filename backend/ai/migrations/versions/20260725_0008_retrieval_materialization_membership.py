"""Enforce release-scoped retrieval materialization membership.

Revision ID: 20260725_0008
Revises: 20260725_0007
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260725_0008"
down_revision: str | None = "20260725_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    for column in (
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("embedding_revision", sa.String(160), nullable=True),
        sa.Column("acl_namespace", sa.String(160), nullable=True),
        sa.Column("citation_uri", sa.String(2_048), nullable=True),
        sa.Column("citation_title", sa.String(255), nullable=True),
    ):
        op.add_column("ai_knowledge_chunk", column)
    op.add_column(
        "ai_knowledge_release",
        sa.Column("materialization_checksum", sa.String(64), nullable=True),
    )
    op.add_column(
        "ai_knowledge_release",
        sa.Column("materialized_chunk_count", sa.Integer(), nullable=True),
    )

    _validate_legacy_metadata()
    op.execute(
        """
        UPDATE ai_knowledge_chunk
        SET release_id = (attributes->>'releaseId')::uuid,
            embedding_revision = attributes->>'embeddingRevision',
            acl_namespace = acl->'namespaces'->>0,
            citation_uri = attributes->>'citationUri',
            citation_title = attributes->>'citationTitle'
        """
    )
    _validate_release_membership()
    _backfill_materialization_manifests()

    for column in (
        "release_id",
        "embedding_revision",
        "acl_namespace",
        "citation_uri",
        "citation_title",
    ):
        op.alter_column("ai_knowledge_chunk", column, nullable=False)
    op.create_foreign_key(
        "fk_ai_knowledge_chunk_release",
        "ai_knowledge_chunk",
        "ai_knowledge_release",
        ["release_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_ai_knowledge_chunk_release_source",
        "ai_knowledge_chunk",
        "ai_knowledge_release_source",
        ["release_id", "source_id"],
        ["release_id", "source_id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_ai_knowledge_chunk_release_source_revision",
        "ai_knowledge_chunk",
        ["release_id", "source_id", "chunk_revision"],
    )
    op.create_index(
        "ix_ai_knowledge_chunk_release_acl",
        "ai_knowledge_chunk",
        ["release_id", "acl_namespace"],
    )
    op.create_check_constraint(
        "ck_ai_knowledge_release_materialization",
        "ai_knowledge_release",
        "(materialization_checksum IS NULL AND materialized_chunk_count IS NULL) OR "
        "(materialization_checksum ~ '^[a-f0-9]{64}$' AND materialized_chunk_count > 0)",
    )
    _create_immutability_trigger()


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ai_knowledge_chunk_immutable ON ai_knowledge_chunk")
    op.execute("DROP FUNCTION IF EXISTS vfbiz_guard_knowledge_chunk()")
    op.drop_constraint(
        "ck_ai_knowledge_release_materialization",
        "ai_knowledge_release",
        type_="check",
    )
    op.drop_index(
        "ix_ai_knowledge_chunk_release_acl",
        table_name="ai_knowledge_chunk",
    )
    op.drop_constraint(
        "uq_ai_knowledge_chunk_release_source_revision",
        "ai_knowledge_chunk",
        type_="unique",
    )
    op.drop_constraint(
        "fk_ai_knowledge_chunk_release_source",
        "ai_knowledge_chunk",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_knowledge_chunk_release",
        "ai_knowledge_chunk",
        type_="foreignkey",
    )
    for column in (
        "citation_title",
        "citation_uri",
        "acl_namespace",
        "embedding_revision",
        "release_id",
    ):
        op.drop_column("ai_knowledge_chunk", column)
    op.drop_column("ai_knowledge_release", "materialized_chunk_count")
    op.drop_column("ai_knowledge_release", "materialization_checksum")


def _validate_legacy_metadata() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM ai_knowledge_chunk
            WHERE COALESCE(attributes->>'releaseId', '') !~
                    '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-'
                    '[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$'
               OR COALESCE(attributes->>'embeddingRevision', '') = ''
               OR jsonb_typeof(acl->'namespaces') <> 'array'
               OR jsonb_array_length(acl->'namespaces') <> 1
               OR COALESCE(acl->'namespaces'->>0, '') = ''
               OR COALESCE(attributes->>'citationUri', '') = ''
               OR attributes->>'citationUri' !~ '^(https://|urn:)'
               OR attributes->>'citationUri' ~ '^https://[^/]*@'
               OR attributes->>'citationUri' ~ '[?#]'
               OR COALESCE(attributes->>'citationTitle', '') = ''
          ) THEN
            RAISE EXCEPTION
              'unsafe legacy knowledge chunks require governed re-materialization';
          END IF;
        END $$;
        """
    )


def _validate_release_membership() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM ai_knowledge_chunk chunk
            LEFT JOIN ai_knowledge_release release ON release.id = chunk.release_id
            LEFT JOIN ai_knowledge_release_source link
              ON link.release_id = chunk.release_id AND link.source_id = chunk.source_id
            LEFT JOIN ai_knowledge_source source ON source.id = chunk.source_id
            WHERE release.id IS NULL
               OR link.id IS NULL
               OR source.id IS NULL
               OR source.source_revision <> link.source_revision
               OR chunk.embedding_revision <> release.embedding_revision
               OR chunk.acl_namespace <> release.acl_namespace
          ) THEN
            RAISE EXCEPTION
              'legacy knowledge chunk release/source/ACL membership is inconsistent';
          END IF;
          IF EXISTS (
            SELECT 1
            FROM ai_knowledge_chunk
            GROUP BY release_id, source_id, chunk_revision
            HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION 'duplicate release-scoped knowledge chunk identity';
          END IF;
        END $$;
        """
    )


def _backfill_materialization_manifests() -> None:
    op.execute(
        """
        WITH manifests AS (
          SELECT release_id,
                 count(*)::integer AS chunk_count,
                 encode(
                   digest(
                     string_agg(
                       replace(id::text, '-', '') || ':' || content_checksum,
                       E'\\n' ORDER BY id
                     ),
                     'sha256'
                   ),
                   'hex'
                 ) AS checksum
          FROM ai_knowledge_chunk
          GROUP BY release_id
        )
        UPDATE ai_knowledge_release release
        SET materialization_checksum = manifests.checksum,
            materialized_chunk_count = manifests.chunk_count
        FROM manifests
        WHERE release.id = manifests.release_id
        """
    )


def _create_immutability_trigger() -> None:
    op.execute(
        """
        CREATE FUNCTION vfbiz_guard_knowledge_chunk() RETURNS trigger AS $$
        DECLARE release_status text;
        BEGIN
          IF TG_OP = 'UPDATE' THEN
            RAISE EXCEPTION 'knowledge chunks are immutable; delete and re-materialize';
          END IF;
          SELECT status INTO release_status
          FROM ai_knowledge_release WHERE id = NEW.release_id;
          IF release_status <> 'candidate' THEN
            RAISE EXCEPTION 'knowledge chunks may only be inserted for a candidate release';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_knowledge_chunk_immutable
        BEFORE INSERT OR UPDATE ON ai_knowledge_chunk
        FOR EACH ROW EXECUTE FUNCTION vfbiz_guard_knowledge_chunk()
        """
    )
