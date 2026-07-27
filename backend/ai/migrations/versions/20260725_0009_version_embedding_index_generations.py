"""Version embedding index generations without changing the active release pointer.

Revision ID: 20260725_0009
Revises: 20260725_0008
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260725_0009"
down_revision: str | None = "20260725_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_embedding_index_generation",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("generation_key", sa.String(255), nullable=False),
        sa.Column("embedding_revision", sa.String(160), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("distance_metric", sa.String(16), nullable=False),
        sa.Column("normalization", sa.String(16), nullable=False),
        sa.Column("instruction_digest", sa.String(64), nullable=False),
        sa.Column("tokenizer_digest", sa.String(64), nullable=False),
        sa.Column("lifecycle", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "generation_key",
            name="uq_ai_embedding_index_generation_key",
        ),
        sa.UniqueConstraint(
            "id",
            "embedding_revision",
            "embedding_dimension",
            name="uq_ai_embedding_generation_compatibility",
        ),
        sa.CheckConstraint(
            "embedding_dimension > 0 AND embedding_dimension <= 16000",
            name="ck_ai_embedding_generation_dimension",
        ),
        sa.CheckConstraint(
            "distance_metric IN ('cosine','inner_product','l2')",
            name="ck_ai_embedding_generation_metric",
        ),
        sa.CheckConstraint(
            "normalization IN ('l2','none')",
            name="ck_ai_embedding_generation_normalization",
        ),
        sa.CheckConstraint(
            "instruction_digest ~ '^[a-f0-9]{64}$' "
            "AND tokenizer_digest ~ '^[a-f0-9]{64}$'",
            name="ck_ai_embedding_generation_digests",
        ),
        sa.CheckConstraint(
            "lifecycle IN ('building','ready','retired','tombstoned')",
            name="ck_ai_embedding_generation_lifecycle",
        ),
    )
    op.add_column(
        "ai_knowledge_release",
        sa.Column(
            "index_generation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "ai_knowledge_chunk",
        sa.Column(
            "index_generation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "ai_knowledge_chunk",
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
    )

    _backfill_legacy_generations()
    _remove_global_vector_typmod()
    _validate_generation_membership()

    op.create_foreign_key(
        "fk_ai_knowledge_release_embedding_generation",
        "ai_knowledge_release",
        "ai_embedding_index_generation",
        ["index_generation_id", "embedding_revision", "embedding_dimension"],
        ["id", "embedding_revision", "embedding_dimension"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_ai_knowledge_chunk_embedding_generation",
        "ai_knowledge_chunk",
        "ai_embedding_index_generation",
        ["index_generation_id", "embedding_revision", "embedding_dimension"],
        ["id", "embedding_revision", "embedding_dimension"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_ai_knowledge_chunk_vector_dimension",
        "ai_knowledge_chunk",
        "embedding_dimension IS NULL OR embedding_dimension = vector_dims(embedding)",
    )
    op.create_index(
        "ix_ai_knowledge_chunk_generation_release_acl",
        "ai_knowledge_chunk",
        ["index_generation_id", "release_id", "acl_namespace"],
    )
    _create_generation_immutability_trigger()


def downgrade() -> None:
    _assert_legacy_dimension_only()
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_embedding_generation_immutable "
        "ON ai_embedding_index_generation"
    )
    op.execute("DROP FUNCTION IF EXISTS vfbiz_guard_embedding_generation()")
    op.drop_index(
        "ix_ai_knowledge_chunk_generation_release_acl",
        table_name="ai_knowledge_chunk",
    )
    op.drop_constraint(
        "ck_ai_knowledge_chunk_vector_dimension",
        "ai_knowledge_chunk",
        type_="check",
    )
    op.drop_constraint(
        "fk_ai_knowledge_chunk_embedding_generation",
        "ai_knowledge_chunk",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_knowledge_release_embedding_generation",
        "ai_knowledge_release",
        type_="foreignkey",
    )
    op.execute(
        "ALTER TABLE ai_knowledge_chunk "
        "ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536)"
    )
    op.drop_column("ai_knowledge_chunk", "embedding_dimension")
    op.drop_column("ai_knowledge_chunk", "index_generation_id")
    op.drop_column("ai_knowledge_release", "index_generation_id")
    op.drop_table("ai_embedding_index_generation")


def _backfill_legacy_generations() -> None:
    op.execute(
        """
        INSERT INTO ai_embedding_index_generation (
          generation_key,
          embedding_revision,
          embedding_dimension,
          distance_metric,
          normalization,
          instruction_digest,
          tokenizer_digest,
          lifecycle
        )
        SELECT
          'legacy-pgvector-' || embedding_dimension::text || '-v1:' ||
            embedding_revision || ':' || embedding_dimension::text,
          embedding_revision,
          embedding_dimension,
          'cosine',
          'l2',
          encode(
            digest(
              'legacy-instruction:' || embedding_revision || ':' ||
                embedding_dimension::text,
              'sha256'
            ),
            'hex'
          ),
          encode(
            digest(
              'legacy-tokenizer:' || embedding_revision || ':' ||
                embedding_dimension::text,
              'sha256'
            ),
            'hex'
          ),
          CASE
            WHEN bool_or(status IN ('active','superseded')) THEN 'ready'
            ELSE 'building'
          END
        FROM ai_knowledge_release
        GROUP BY embedding_revision, embedding_dimension
        """
    )
    op.execute(
        """
        UPDATE ai_knowledge_release release
        SET index_generation_id = generation.id
        FROM ai_embedding_index_generation generation
        WHERE generation.embedding_revision = release.embedding_revision
          AND generation.embedding_dimension = release.embedding_dimension
        """
    )
    op.execute(
        "ALTER TABLE ai_knowledge_chunk "
        "DISABLE TRIGGER trg_ai_knowledge_chunk_immutable"
    )
    op.execute(
        """
        UPDATE ai_knowledge_chunk chunk
        SET index_generation_id = release.index_generation_id,
            embedding_dimension = vector_dims(chunk.embedding)
        FROM ai_knowledge_release release
        WHERE release.id = chunk.release_id
        """
    )
    op.execute(
        "ALTER TABLE ai_knowledge_chunk "
        "ENABLE TRIGGER trg_ai_knowledge_chunk_immutable"
    )


def _remove_global_vector_typmod() -> None:
    op.execute(
        "ALTER TABLE ai_knowledge_chunk "
        "ALTER COLUMN embedding TYPE vector USING embedding::vector"
    )


def _validate_generation_membership() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM ai_knowledge_release release
            LEFT JOIN ai_embedding_index_generation generation
              ON generation.id = release.index_generation_id
             AND generation.embedding_revision = release.embedding_revision
             AND generation.embedding_dimension = release.embedding_dimension
            WHERE generation.id IS NULL
          ) THEN
            RAISE EXCEPTION 'knowledge release embedding generation mismatch';
          END IF;
          IF EXISTS (
            SELECT 1
            FROM ai_knowledge_chunk chunk
            LEFT JOIN ai_embedding_index_generation generation
              ON generation.id = chunk.index_generation_id
             AND generation.embedding_revision = chunk.embedding_revision
             AND generation.embedding_dimension = chunk.embedding_dimension
            WHERE generation.id IS NULL
               OR chunk.embedding_dimension <> vector_dims(chunk.embedding)
          ) THEN
            RAISE EXCEPTION 'knowledge chunk embedding generation mismatch';
          END IF;
        END $$;
        """
    )


def _create_generation_immutability_trigger() -> None:
    op.execute(
        """
        CREATE FUNCTION vfbiz_guard_embedding_generation() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'embedding generations are tombstoned, not deleted';
          END IF;
          IF NEW.generation_key <> OLD.generation_key
             OR NEW.embedding_revision <> OLD.embedding_revision
             OR NEW.embedding_dimension <> OLD.embedding_dimension
             OR NEW.distance_metric <> OLD.distance_metric
             OR NEW.normalization <> OLD.normalization
             OR NEW.instruction_digest <> OLD.instruction_digest
             OR NEW.tokenizer_digest <> OLD.tokenizer_digest THEN
            RAISE EXCEPTION 'embedding generation identity is immutable';
          END IF;
          IF NEW.created_at <> OLD.created_at THEN
            RAISE EXCEPTION 'embedding generation creation time is immutable';
          END IF;
          IF NEW.lifecycle <> OLD.lifecycle
             AND NOT (
               (OLD.lifecycle = 'building' AND NEW.lifecycle IN ('ready','tombstoned'))
               OR (OLD.lifecycle = 'ready' AND NEW.lifecycle IN ('retired','tombstoned'))
               OR (OLD.lifecycle = 'retired' AND NEW.lifecycle = 'tombstoned')
             ) THEN
            RAISE EXCEPTION 'invalid embedding generation lifecycle transition';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_embedding_generation_immutable
        BEFORE UPDATE OR DELETE ON ai_embedding_index_generation
        FOR EACH ROW EXECUTE FUNCTION vfbiz_guard_embedding_generation()
        """
    )


def _assert_legacy_dimension_only() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM ai_knowledge_chunk
            WHERE embedding_dimension <> 1536 OR vector_dims(embedding) <> 1536
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade: non-legacy embedding generations exist';
          END IF;
        END $$;
        """
    )
