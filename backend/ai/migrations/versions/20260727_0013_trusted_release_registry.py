"""Add trusted artifact and evidence registries for Assistant Release authority.

Revision ID: 20260727_0013
Revises: 20260727_0012
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0013"
down_revision: str | None = "20260727_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SHA256 = r"^[0-9a-f]{64}$"
_ENVIRONMENTS = "'development','test','staging','production'"
_STATES = "'active','revoked'"
_EVIDENCE_KINDS = "'approval','automated_gate','static_safe_approval','promotion','live_control'"


def upgrade() -> None:
    op.create_table(
        "ai_trusted_release_artifact",
        sa.Column("artifact_ref", sa.String(255), primary_key=True),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(artifact_ref)) BETWEEN 1 AND 255",
            name="ck_ai_trusted_release_artifact_ref",
        ),
        sa.CheckConstraint(
            f"artifact_sha256 ~ '{_SHA256}'",
            name="ck_ai_trusted_release_artifact_sha",
        ),
        sa.CheckConstraint(
            f"state IN ({_STATES})",
            name="ck_ai_trusted_release_artifact_state",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_ai_trusted_release_artifact_window",
        ),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_ai_trusted_release_artifact_revision",
        ),
    )
    op.create_table(
        "ai_trusted_release_evidence",
        sa.Column("evidence_ref", sa.String(255), primary_key=True),
        sa.Column("evidence_kind", sa.String(32), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("target_sha256", sa.String(64), nullable=False),
        sa.Column("assistant_profile", sa.String(160), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("authority_role", sa.String(160)),
        sa.Column("approver_subject", sa.String(160)),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(evidence_ref)) BETWEEN 1 AND 255",
            name="ck_ai_trusted_release_evidence_ref",
        ),
        sa.CheckConstraint(
            f"evidence_kind IN ({_EVIDENCE_KINDS})",
            name="ck_ai_trusted_release_evidence_kind",
        ),
        sa.CheckConstraint(
            f"evidence_sha256 ~ '{_SHA256}' AND target_sha256 ~ '{_SHA256}'",
            name="ck_ai_trusted_release_evidence_sha",
        ),
        sa.CheckConstraint(
            f"environment IN ({_ENVIRONMENTS})",
            name="ck_ai_trusted_release_evidence_environment",
        ),
        sa.CheckConstraint(
            f"state IN ({_STATES})",
            name="ck_ai_trusted_release_evidence_state",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_ai_trusted_release_evidence_window",
        ),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_ai_trusted_release_evidence_revision",
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_trusted_release_evidence")
    op.drop_table("ai_trusted_release_artifact")
