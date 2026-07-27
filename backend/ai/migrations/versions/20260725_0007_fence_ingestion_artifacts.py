"""Fence ingestion artifacts and constrain persisted state.

Revision ID: 20260725_0007
Revises: 20260725_0006
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_0007"
down_revision: str | None = "20260725_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_knowledge_ingestion_artifact",
        sa.Column("fencing_token", sa.BigInteger(), nullable=True),
    )
    op.execute(
        "UPDATE ai_knowledge_ingestion_artifact AS artifact "
        "SET fencing_token = job.fencing_token "
        "FROM ai_knowledge_ingestion_job AS job WHERE artifact.job_id = job.id"
    )
    op.alter_column(
        "ai_knowledge_ingestion_artifact", "fencing_token", nullable=False
    )
    op.create_check_constraint(
        "ck_ai_knowledge_ingestion_deletion_generation",
        "ai_knowledge_ingestion_job",
        "deletion_generation >= 0",
    )
    op.create_check_constraint(
        "ck_ai_knowledge_ingestion_status",
        "ai_knowledge_ingestion_job",
        "status IN ('queued','running','retry_wait','candidate_ready','failed_safely',"
        "'dead_lettered','deletion_pending','deleting','tombstoned')",
    )
    op.create_check_constraint(
        "ck_ai_knowledge_ingestion_stage",
        "ai_knowledge_ingestion_job",
        "current_stage IN ('quarantine','pre_scan','parse','content_scan','chunk',"
        "'embed','verify','delete')",
    )
    op.create_check_constraint(
        "ck_ai_knowledge_ingestion_attempt_outcome",
        "ai_knowledge_ingestion_stage_attempt",
        "outcome IN ('completed','checkpointed','retry_scheduled','dead_lettered',"
        "'failed_safely','deletion_scheduled','tombstoned')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ai_knowledge_ingestion_attempt_outcome",
        "ai_knowledge_ingestion_stage_attempt",
        type_="check",
    )
    op.drop_constraint(
        "ck_ai_knowledge_ingestion_stage",
        "ai_knowledge_ingestion_job",
        type_="check",
    )
    op.drop_constraint(
        "ck_ai_knowledge_ingestion_status",
        "ai_knowledge_ingestion_job",
        type_="check",
    )
    op.drop_constraint(
        "ck_ai_knowledge_ingestion_deletion_generation",
        "ai_knowledge_ingestion_job",
        type_="check",
    )
    op.drop_column("ai_knowledge_ingestion_artifact", "fencing_token")
