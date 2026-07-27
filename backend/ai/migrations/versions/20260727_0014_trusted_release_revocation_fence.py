"""Fence and audit trusted release registry revocation.

Revision ID: 20260727_0014
Revises: 20260727_0013
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260727_0014"
down_revision: str | None = "20260727_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_trusted_release_registry_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("registry_kind", sa.String(16), nullable=False),
        sa.Column("registry_ref", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("from_revision", sa.BigInteger(), nullable=False),
        sa.Column("to_revision", sa.BigInteger(), nullable=False),
        sa.Column("actor_subject", sa.String(160), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "registry_kind",
            "registry_ref",
            "idempotency_key",
            name="uq_ai_trusted_release_registry_history_idempotency",
        ),
        sa.CheckConstraint(
            "registry_kind IN ('artifact','evidence')",
            name="ck_ai_trusted_release_registry_history_kind",
        ),
        sa.CheckConstraint(
            "event_type = 'revoked' AND to_revision = from_revision + 1",
            name="ck_ai_trusted_release_registry_history_transition",
        ),
    )
    op.create_table(
        "ai_trusted_release_registry_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "history_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_trusted_release_registry_history.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        """
        CREATE FUNCTION vfbiz_guard_trusted_release_registry_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          actor text := current_setting('vfbiz.release_actor', true);
          reason text := current_setting('vfbiz.release_reason', true);
          operation_key text := current_setting('vfbiz.release_idempotency_key', true);
          registry_kind text := TG_ARGV[0];
          registry_ref text;
          history_id uuid;
        BEGIN
          IF OLD.state <> 'active' OR NEW.state <> 'revoked'
             OR NEW.revision <> OLD.revision + 1 THEN
            RAISE EXCEPTION 'trusted release registry transition must be active to revoked';
          END IF;
          IF actor IS NULL OR btrim(actor) = ''
             OR reason IS NULL OR btrim(reason) = ''
             OR operation_key IS NULL OR btrim(operation_key) = '' THEN
            RAISE EXCEPTION 'trusted release revocation requires actor, reason and idempotency key';
          END IF;
          IF registry_kind = 'artifact' THEN
            IF ROW(NEW.artifact_ref, NEW.artifact_sha256, NEW.effective_at, NEW.expires_at)
               IS DISTINCT FROM
               ROW(OLD.artifact_ref, OLD.artifact_sha256, OLD.effective_at, OLD.expires_at) THEN
              RAISE EXCEPTION 'trusted artifact identity is immutable';
            END IF;
            registry_ref := NEW.artifact_ref;
          ELSE
            IF ROW(
              NEW.evidence_ref, NEW.evidence_kind, NEW.evidence_sha256,
              NEW.target_sha256, NEW.assistant_profile, NEW.environment,
              NEW.authority_role, NEW.approver_subject, NEW.effective_at, NEW.expires_at
            ) IS DISTINCT FROM ROW(
              OLD.evidence_ref, OLD.evidence_kind, OLD.evidence_sha256,
              OLD.target_sha256, OLD.assistant_profile, OLD.environment,
              OLD.authority_role, OLD.approver_subject, OLD.effective_at, OLD.expires_at
            ) THEN
              RAISE EXCEPTION 'trusted evidence identity is immutable';
            END IF;
            registry_ref := NEW.evidence_ref;
          END IF;
          INSERT INTO ai_trusted_release_registry_history (
            registry_kind, registry_ref, event_type, from_revision, to_revision,
            actor_subject, reason, idempotency_key
          ) VALUES (
            registry_kind, registry_ref, 'revoked', OLD.revision, NEW.revision,
            actor, reason, operation_key
          ) RETURNING id INTO history_id;
          INSERT INTO ai_trusted_release_registry_outbox (
            history_id, event_type, payload
          ) VALUES (
            history_id, 'ai.release.trust.revoked',
            jsonb_build_object(
              'registryKind', registry_kind,
              'registryRef', registry_ref,
              'revision', NEW.revision
            )
          );
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_trusted_release_artifact_guard
        BEFORE UPDATE ON ai_trusted_release_artifact
        FOR EACH ROW EXECUTE FUNCTION
          vfbiz_guard_trusted_release_registry_update('artifact');
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_trusted_release_evidence_guard
        BEFORE UPDATE ON ai_trusted_release_evidence
        FOR EACH ROW EXECUTE FUNCTION
          vfbiz_guard_trusted_release_registry_update('evidence');
        """
    )
    op.execute(
        """
        CREATE FUNCTION vfbiz_reject_trusted_release_registry_delete()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'trusted release registry rows cannot be deleted';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_trusted_release_artifact_no_delete
        BEFORE DELETE ON ai_trusted_release_artifact
        FOR EACH ROW EXECUTE FUNCTION
          vfbiz_reject_trusted_release_registry_delete();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_trusted_release_evidence_no_delete
        BEFORE DELETE ON ai_trusted_release_evidence
        FOR EACH ROW EXECUTE FUNCTION
          vfbiz_reject_trusted_release_registry_delete();
        """
    )
    op.execute(
        """
        CREATE FUNCTION vfbiz_reject_trusted_release_history_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'trusted release registry history is append-only';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_trusted_release_history_immutable
        BEFORE UPDATE OR DELETE ON ai_trusted_release_registry_history
        FOR EACH ROW EXECUTE FUNCTION
          vfbiz_reject_trusted_release_history_mutation();
        """
    )
    op.execute(
        """
        CREATE FUNCTION vfbiz_guard_trusted_release_outbox_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'trusted release outbox rows cannot be deleted';
          END IF;
          IF ROW(NEW.id, NEW.history_id, NEW.event_type, NEW.payload, NEW.created_at)
             IS DISTINCT FROM
             ROW(OLD.id, OLD.history_id, OLD.event_type, OLD.payload, OLD.created_at)
             OR OLD.published_at IS NOT NULL
             OR NEW.published_at IS NULL THEN
            RAISE EXCEPTION 'trusted release outbox identity is immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_trusted_release_outbox_guard
        BEFORE UPDATE OR DELETE ON ai_trusted_release_registry_outbox
        FOR EACH ROW EXECUTE FUNCTION
          vfbiz_guard_trusted_release_outbox_update();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_trusted_release_outbox_guard "
        "ON ai_trusted_release_registry_outbox"
    )
    op.execute("DROP FUNCTION IF EXISTS vfbiz_guard_trusted_release_outbox_update()")
    op.execute(
        "DROP TRIGGER trg_ai_trusted_release_history_immutable "
        "ON ai_trusted_release_registry_history"
    )
    op.execute("DROP FUNCTION vfbiz_reject_trusted_release_history_mutation()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_trusted_release_evidence_no_delete "
        "ON ai_trusted_release_evidence"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_trusted_release_artifact_no_delete "
        "ON ai_trusted_release_artifact"
    )
    op.execute("DROP FUNCTION IF EXISTS vfbiz_reject_trusted_release_registry_delete()")
    op.execute("DROP TRIGGER trg_ai_trusted_release_evidence_guard ON ai_trusted_release_evidence")
    op.execute("DROP TRIGGER trg_ai_trusted_release_artifact_guard ON ai_trusted_release_artifact")
    op.execute("DROP FUNCTION vfbiz_guard_trusted_release_registry_update()")
    op.drop_table("ai_trusted_release_registry_outbox")
    op.drop_table("ai_trusted_release_registry_history")
