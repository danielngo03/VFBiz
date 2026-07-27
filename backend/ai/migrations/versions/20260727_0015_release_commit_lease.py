"""Fence Assistant Release changes while final conversation commits are leased.

Revision ID: 20260727_0015
Revises: 20260727_0014
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260727_0015"
down_revision: str | None = "20260727_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_assistant_release_commit_lease",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("assistant_profile", sa.String(80), nullable=False),
        sa.Column("environment", sa.String(24), nullable=False),
        sa.Column(
            "activation_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("candidate_sha256", sa.CHAR(64), nullable=False),
        sa.Column("activation_envelope_sha256", sa.CHAR(64), nullable=False),
        sa.Column("pointer_revision", sa.BigInteger(), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_version", sa.BigInteger(), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "candidate_sha256 ~ '^[a-f0-9]{64}$' "
            "AND activation_envelope_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_ai_assistant_release_commit_lease_digests",
        ),
        sa.CheckConstraint(
            "pointer_revision > 0 AND conversation_version >= 0 "
            "AND fencing_token > 0",
            name="ck_ai_assistant_release_commit_lease_versions",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at "
            "AND expires_at <= issued_at + interval '15 seconds'",
            name="ck_ai_assistant_release_commit_lease_window",
        ),
        sa.ForeignKeyConstraint(
            ["activation_record_id", "assistant_profile", "environment"],
            [
                "ai_assistant_release_activation.id",
                "ai_assistant_release_activation.assistant_profile",
                "ai_assistant_release_activation.environment",
            ],
            name="fk_ai_assistant_release_commit_lease_activation",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "session_id",
            "turn_id",
            "fencing_token",
            name="uq_ai_assistant_release_commit_lease_turn_fence",
        ),
    )
    op.create_index(
        "ix_ai_assistant_release_commit_lease_active",
        "ai_assistant_release_commit_lease",
        ["assistant_profile", "environment", "activation_record_id", "expires_at"],
    )
    op.create_index(
        "ix_ai_assistant_release_commit_lease_expiry",
        "ai_assistant_release_commit_lease",
        ["expires_at"],
    )
    op.execute(
        """
        CREATE FUNCTION assistant_release_guard_active_commit_lease()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF TG_OP = 'UPDATE'
             AND OLD.target_kind = 'activation'
             AND (
               NEW.target_kind IS DISTINCT FROM OLD.target_kind
               OR NEW.activation_record_id IS DISTINCT FROM OLD.activation_record_id
             )
             AND EXISTS (
               SELECT 1
               FROM ai_assistant_release_commit_lease lease
               WHERE lease.assistant_profile = OLD.assistant_profile
                 AND lease.environment = OLD.environment
                 AND lease.activation_record_id = OLD.activation_record_id
                 AND lease.expires_at > clock_timestamp()
             ) THEN
            RAISE EXCEPTION
              'assistant release has active final-commit leases'
              USING ERRCODE = '55006';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tr_ai_assistant_release_commit_lease_guard
        BEFORE UPDATE ON ai_assistant_release_pointer
        FOR EACH ROW EXECUTE FUNCTION
          assistant_release_guard_active_commit_lease();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS tr_ai_assistant_release_commit_lease_guard "
        "ON ai_assistant_release_pointer"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS assistant_release_guard_active_commit_lease()"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_ai_assistant_release_commit_lease_expiry"
    )
    op.drop_index(
        "ix_ai_assistant_release_commit_lease_active",
        table_name="ai_assistant_release_commit_lease",
    )
    op.drop_table("ai_assistant_release_commit_lease")
