"""Enforce embedding generation membership after runtime cutover.

Revision ID: 20260725_0010
Revises: 20260725_0009
Create Date: 2026-07-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260725_0010"
down_revision: str | None = "20260725_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _assert_generation_backfill_complete()
    op.alter_column("ai_knowledge_release", "index_generation_id", nullable=False)
    op.alter_column("ai_knowledge_chunk", "index_generation_id", nullable=False)
    op.alter_column("ai_knowledge_chunk", "embedding_dimension", nullable=False)


def downgrade() -> None:
    op.alter_column("ai_knowledge_chunk", "embedding_dimension", nullable=True)
    op.alter_column("ai_knowledge_chunk", "index_generation_id", nullable=True)
    op.alter_column("ai_knowledge_release", "index_generation_id", nullable=True)


def _assert_generation_backfill_complete() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM ai_knowledge_release
            WHERE index_generation_id IS NULL
          ) OR EXISTS (
            SELECT 1
            FROM ai_knowledge_chunk
            WHERE index_generation_id IS NULL
               OR embedding_dimension IS NULL
               OR embedding_dimension <> vector_dims(embedding)
          ) THEN
            RAISE EXCEPTION
              'embedding generation contract preflight failed: legacy NULL or dimension mismatch';
          END IF;
        END $$;
        """
    )
