"""Extend evaluation runs with resumable, plan-bound state.

Revision ID: 20260728_0017
Revises: 20260728_0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260728_0017"
down_revision: str | None = "20260728_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUN_STATES = (
    "requested",
    "queued",
    "running",
    "grading",
    "comparing",
    "decision_ready",
    "failed",
    "cancelled",
    "invalid",
)


def upgrade() -> None:
    op.alter_column("ai_evaluation_run", "release_id", nullable=True)
    op.alter_column("ai_evaluation_run", "security_passed", nullable=True)
    op.add_column(
        "ai_evaluation_run",
        sa.Column("run_key", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "ai_evaluation_run",
        sa.Column("plan_digest", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "ai_evaluation_run",
        sa.Column(
            "plan_document",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "ai_evaluation_run",
        sa.Column("authority_class", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "ai_evaluation_run",
        sa.Column("candidate_release_ref", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "ai_evaluation_run",
        sa.Column("candidate_manifest_digest", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "ai_evaluation_run",
        sa.Column("baseline_release_ref", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "ai_evaluation_run",
        sa.Column("baseline_manifest_digest", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "ai_evaluation_run",
        sa.Column(
            "benchmark_definition_digest",
            sa.String(length=71),
            nullable=True,
        ),
    )
    for name in ("completed_case_count", "attempt_count", "row_version"):
        op.add_column(
            "ai_evaluation_run",
            sa.Column(
                name,
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    op.add_column(
        "ai_evaluation_run",
        sa.Column("evidence_bundle_digest", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "ai_evaluation_run",
        sa.Column("failure_code", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "ai_evaluation_run",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "uq_ai_evaluation_run_run_key",
        "ai_evaluation_run",
        ["run_key"],
        unique=True,
    )
    op.create_check_constraint(
        "ck_ai_evaluation_run_governed_state",
        "ai_evaluation_run",
        f"run_key IS NULL OR status IN { _RUN_STATES }",
    )
    op.create_check_constraint(
        "ck_ai_evaluation_run_plan_binding",
        "ai_evaluation_run",
        """
        run_key IS NULL OR (
          plan_digest IS NOT NULL
          AND plan_digest ~ '^sha256:[a-f0-9]{64}$'
          AND plan_document IS NOT NULL
          AND jsonb_typeof(plan_document) = 'object'
          AND authority_class IN ('vinfast-acceptance', 'public-diagnostic')
          AND candidate_release_ref IS NOT NULL
          AND candidate_manifest_digest IS NOT NULL
          AND candidate_manifest_digest ~ '^sha256:[a-f0-9]{64}$'
          AND benchmark_definition_digest IS NOT NULL
          AND benchmark_definition_digest ~ '^sha256:[a-f0-9]{64}$'
          AND (
            (
              baseline_release_ref IS NULL
              AND baseline_manifest_digest IS NULL
            )
            OR (
              baseline_release_ref IS NOT NULL
              AND baseline_manifest_digest IS NOT NULL
              AND baseline_manifest_digest ~ '^sha256:[a-f0-9]{64}$'
            )
          )
        )
        """,
    )
    op.create_check_constraint(
        "ck_ai_evaluation_run_progress",
        "ai_evaluation_run",
        "completed_case_count >= 0 AND attempt_count >= 0 AND row_version >= 0",
    )
    op.create_check_constraint(
        "ck_ai_evaluation_run_terminal_evidence",
        "ai_evaluation_run",
        """
        run_key IS NULL
        OR status <> 'decision_ready'
        OR (
          evidence_bundle_digest IS NOT NULL
          AND evidence_bundle_digest ~ '^sha256:[a-f0-9]{64}$'
        )
        """,
    )
    op.create_check_constraint(
        "ck_ai_evaluation_run_terminal_failure",
        "ai_evaluation_run",
        """
        run_key IS NULL
        OR status NOT IN ('failed', 'invalid')
        OR (failure_code IS NOT NULL AND btrim(failure_code) <> '')
        """,
    )


def downgrade() -> None:
    connection = op.get_bind()
    governed_rows = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM ai_evaluation_run WHERE run_key IS NOT NULL)"
        )
    ).scalar_one()
    if governed_rows:
        raise RuntimeError(
            "cannot downgrade 20260728_0017 while governed evaluation runs exist; "
            "export or delete them under approved retention policy first"
        )
    op.execute(
        "ALTER TABLE ai_evaluation_run "
        "DROP CONSTRAINT IF EXISTS ck_ai_evaluation_run_terminal_failure"
    )
    op.execute(
        "ALTER TABLE ai_evaluation_run "
        "DROP CONSTRAINT IF EXISTS ck_ai_evaluation_run_terminal_evidence"
    )
    op.drop_constraint(
        "ck_ai_evaluation_run_progress",
        "ai_evaluation_run",
        type_="check",
    )
    op.drop_constraint(
        "ck_ai_evaluation_run_plan_binding",
        "ai_evaluation_run",
        type_="check",
    )
    op.drop_constraint(
        "ck_ai_evaluation_run_governed_state",
        "ai_evaluation_run",
        type_="check",
    )
    op.drop_index("uq_ai_evaluation_run_run_key", table_name="ai_evaluation_run")
    for name in (
        "updated_at",
        "failure_code",
        "evidence_bundle_digest",
        "row_version",
        "attempt_count",
        "completed_case_count",
        "benchmark_definition_digest",
        "baseline_manifest_digest",
        "baseline_release_ref",
        "candidate_manifest_digest",
        "candidate_release_ref",
        "authority_class",
        "plan_document",
        "plan_digest",
        "run_key",
    ):
        op.drop_column("ai_evaluation_run", name)
    op.alter_column("ai_evaluation_run", "security_passed", nullable=False)
    op.alter_column("ai_evaluation_run", "release_id", nullable=False)
