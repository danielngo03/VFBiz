"""Add a fail-closed Document AI submission ledger.

Revision ID: 20260730_0021
Revises: 20260730_0020
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260730_0021"
down_revision: str | None = "20260730_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_document_submission",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("receipt_payload", postgresql.JSONB(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("budget_date", sa.Date(), nullable=False),
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "idempotency_key ~ '^[a-f0-9]{64}$' AND request_digest ~ '^[a-f0-9]{64}$'",
            name="ck_ai_document_submission_digests",
        ),
        sa.CheckConstraint(
            "state IN ('reserved','submitted')",
            name="ck_ai_document_submission_state",
        ),
        sa.CheckConstraint(
            "page_count BETWEEN 1 AND 500",
            name="ck_ai_document_submission_page_count",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(request_payload) = 'object' "
            "AND (receipt_payload IS NULL OR jsonb_typeof(receipt_payload) = 'object')",
            name="ck_ai_document_submission_payloads",
        ),
        sa.CheckConstraint(
            "(state = 'reserved' AND receipt_payload IS NULL) "
            "OR (state = 'submitted' AND receipt_payload IS NOT NULL)",
            name="ck_ai_document_submission_receipt_state",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_ai_document_submission_idempotency_key",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION document_ai_submission_guard_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF OLD.state <> 'reserved'
             OR NEW.state <> 'submitted'
             OR NEW.id IS DISTINCT FROM OLD.id
             OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
             OR NEW.request_digest IS DISTINCT FROM OLD.request_digest
             OR NEW.request_payload IS DISTINCT FROM OLD.request_payload
             OR NEW.page_count IS DISTINCT FROM OLD.page_count
             OR NEW.budget_date IS DISTINCT FROM OLD.budget_date
             OR NEW.reservation_expires_at IS DISTINCT FROM OLD.reservation_expires_at
             OR NEW.created_at IS DISTINCT FROM OLD.created_at
             OR NEW.receipt_payload IS NULL THEN
            RAISE EXCEPTION 'Document AI submission ledger mutation refused'
              USING ERRCODE = '55000';
          END IF;
          NEW.updated_at := clock_timestamp();
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_ai_submission_guard_update
        BEFORE UPDATE ON ai_document_submission
        FOR EACH ROW
        EXECUTE FUNCTION document_ai_submission_guard_update();
        """
    )
    op.execute(
        """
        CREATE FUNCTION document_ai_submission_reject_delete()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'Document AI submission ledger deletion refused'
            USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_ai_submission_reject_delete
        BEFORE DELETE ON ai_document_submission
        FOR EACH ROW
        EXECUTE FUNCTION document_ai_submission_reject_delete();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_ai_submission_reject_truncate
        BEFORE TRUNCATE ON ai_document_submission
        FOR EACH STATEMENT
        EXECUTE FUNCTION document_ai_submission_reject_delete();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM ai_document_submission) THEN
            RAISE EXCEPTION
              'Document AI submission ledger downgrade refused: persisted rows exist'
              USING ERRCODE = '55000';
          END IF;
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER trg_document_ai_submission_reject_truncate ON ai_document_submission")
    op.execute("DROP TRIGGER trg_document_ai_submission_reject_delete ON ai_document_submission")
    op.execute("DROP FUNCTION document_ai_submission_reject_delete()")
    op.execute("DROP TRIGGER trg_document_ai_submission_guard_update ON ai_document_submission")
    op.execute("DROP FUNCTION document_ai_submission_guard_update()")
    op.drop_table("ai_document_submission")
