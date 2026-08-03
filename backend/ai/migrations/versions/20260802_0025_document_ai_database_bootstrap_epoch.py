"""Fence the one-shot Document AI database identity bootstrap.

Revision ID: 20260802_0025
Revises: 20260802_0024
Create Date: 2026-08-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260802_0025"
down_revision: str | None = "20260802_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.ai_document_database_bootstrap (
          singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
          bootstrap_epoch text NOT NULL UNIQUE
            CHECK (bootstrap_epoch ~ '^[a-z0-9][a-z0-9-]{2,127}$'),
          claim_id uuid NOT NULL UNIQUE,
          authority_digest character(64) NOT NULL
            CHECK (authority_digest ~ '^[0-9a-f]{64}$'),
          fencing_token bigint NOT NULL DEFAULT 1 CHECK (fencing_token = 1),
          state text NOT NULL CHECK (state IN ('reserved', 'completed', 'failed')),
          started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
          completed_at timestamptz,
          submitter_secret_version bigint,
          reconciler_secret_version bigint,
          failure_code text,
          CONSTRAINT ai_document_database_bootstrap_state_shape CHECK (
            (
              state = 'reserved'
              AND completed_at IS NULL
              AND submitter_secret_version IS NULL
              AND reconciler_secret_version IS NULL
              AND failure_code IS NULL
            )
            OR
            (
              state = 'completed'
              AND completed_at IS NOT NULL
              AND submitter_secret_version > 0
              AND reconciler_secret_version > 0
              AND failure_code IS NULL
            )
            OR
            (
              state = 'failed'
              AND completed_at IS NOT NULL
              AND submitter_secret_version IS NULL
              AND reconciler_secret_version IS NULL
              AND failure_code IN (
                'IDENTITY_PROVISIONING_FAILED',
                'IDENTITY_PROVISIONING_FAILED_CLEANUP_INCOMPLETE'
              )
            )
          )
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.guard_ai_document_database_bootstrap()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF TG_OP = 'DELETE' OR TG_OP = 'TRUNCATE' THEN
            RAISE EXCEPTION 'Document AI database bootstrap evidence is immutable';
          END IF;
          IF TG_OP = 'INSERT' THEN
            IF NEW.state <> 'reserved' THEN
              RAISE EXCEPTION 'Document AI database bootstrap must start reserved';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.state <> 'reserved' OR NEW.state NOT IN ('completed', 'failed') THEN
            RAISE EXCEPTION 'Document AI database bootstrap transition is terminal';
          END IF;
          IF (
            NEW.singleton,
            NEW.bootstrap_epoch,
            NEW.claim_id,
            NEW.authority_digest,
            NEW.fencing_token,
            NEW.started_at
          ) IS DISTINCT FROM (
            OLD.singleton,
            OLD.bootstrap_epoch,
            OLD.claim_id,
            OLD.authority_digest,
            OLD.fencing_token,
            OLD.started_at
          ) THEN
            RAISE EXCEPTION 'Document AI database bootstrap authority is immutable';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER ai_document_database_bootstrap_guard
        BEFORE INSERT OR UPDATE OR DELETE
        ON public.ai_document_database_bootstrap
        FOR EACH ROW EXECUTE FUNCTION public.guard_ai_document_database_bootstrap()
        """
    )
    op.execute(
        """
        CREATE TRIGGER ai_document_database_bootstrap_truncate_guard
        BEFORE TRUNCATE ON public.ai_document_database_bootstrap
        FOR EACH STATEMENT EXECUTE FUNCTION public.guard_ai_document_database_bootstrap()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM public.ai_document_database_bootstrap
          ) THEN
            RAISE EXCEPTION
              'Document AI database bootstrap downgrade refused: evidence exists';
          END IF;
        END;
        $$
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS ai_document_database_bootstrap_truncate_guard "
        "ON public.ai_document_database_bootstrap"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS ai_document_database_bootstrap_guard "
        "ON public.ai_document_database_bootstrap"
    )
    op.execute("DROP FUNCTION IF EXISTS public.guard_ai_document_database_bootstrap()")
    op.execute("DROP TABLE IF EXISTS public.ai_document_database_bootstrap")
