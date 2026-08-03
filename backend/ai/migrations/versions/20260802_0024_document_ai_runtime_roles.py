"""Separate Document AI submitter and reconciler database capabilities.

Revision ID: 20260802_0024
Revises: 20260801_0023
Create Date: 2026-08-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260802_0024"
down_revision: str | None = "20260801_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A collision is treated as privilege drift. PostgreSQL transactional DDL
    # rolls back the first CREATE if the second role already exists.
    op.execute("CREATE ROLE vfbiz_ai_document_submitter NOLOGIN")
    op.execute("CREATE ROLE vfbiz_ai_document_reconciler NOLOGIN")
    op.execute(
        "ALTER ROLE vfbiz_ai_document_submitter "
        "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
    )
    op.execute(
        "ALTER ROLE vfbiz_ai_document_reconciler "
        "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
    )
    op.execute(
        """
        REVOKE ALL ON
          public.ai_document_submission,
          public.ai_document_reconciliation_claim,
          public.ai_document_operation_observation,
          public.ai_document_extraction_evidence,
          public.ai_document_reconciliation_failure
        FROM vfbiz_ai_document_submitter, vfbiz_ai_document_reconciler
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON public.ai_document_submission "
        "TO vfbiz_ai_document_submitter"
    )
    op.execute(
        "GRANT SELECT ON public.ai_document_submission "
        "TO vfbiz_ai_document_reconciler"
    )
    # SELECT ... FOR UPDATE/SHARE requires UPDATE privilege. Restrict it to the
    # immutable primary-key column so the reconciler cannot alter ledger data.
    op.execute(
        "GRANT UPDATE (id) ON public.ai_document_submission "
        "TO vfbiz_ai_document_reconciler"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON "
        "public.ai_document_reconciliation_claim "
        "TO vfbiz_ai_document_reconciler"
    )
    op.execute(
        "GRANT SELECT, INSERT ON "
        "public.ai_document_operation_observation, "
        "public.ai_document_extraction_evidence, "
        "public.ai_document_reconciliation_failure "
        "TO vfbiz_ai_document_reconciler"
    )


def downgrade() -> None:
    op.execute(
        """
        REVOKE ALL ON
          public.ai_document_submission,
          public.ai_document_reconciliation_claim,
          public.ai_document_operation_observation,
          public.ai_document_extraction_evidence,
          public.ai_document_reconciliation_failure
        FROM vfbiz_ai_document_submitter, vfbiz_ai_document_reconciler
        """
    )
    op.execute("DROP ROLE IF EXISTS vfbiz_ai_document_submitter")
    op.execute("DROP ROLE IF EXISTS vfbiz_ai_document_reconciler")
