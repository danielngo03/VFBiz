"""Persist immutable Assistant Release authority and active-pointer history.

Revision ID: 20260726_0011
Revises: 20260725_0010
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260726_0011"
down_revision: str | None = "20260725_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SHA256 = r"^[0-9a-f]{64}$"
_ENVIRONMENTS = "'development','test','staging','production'"
_TABLES = (
    "ai_assistant_release_candidate",
    "ai_assistant_static_safe_release",
    "ai_assistant_release_activation",
    "ai_assistant_release_history",
    "ai_assistant_release_pointer",
    "ai_assistant_release_outbox_event",
    "ai_assistant_release_outbox_delivery",
)


def upgrade() -> None:
    _create_candidate()
    _create_static_safe_release()
    _create_activation()
    _create_history()
    _create_pointer()
    _create_outbox()
    _create_immutability_guards()
    _create_canonical_json_function()
    _create_target_document_function()
    _create_history_guard()
    _create_pointer_guard()
    _create_outbox_guard()
    _create_history_commit_guard()
    _create_outbox_claim_function()


def _identifier_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
    )


def _scope_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column("assistant_profile", sa.String(160), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
    )


def _scope_checks(prefix: str) -> tuple[sa.CheckConstraint, ...]:
    return (
        sa.CheckConstraint(
            "length(btrim(assistant_profile)) BETWEEN 1 AND 160",
            name=f"ck_{prefix}_profile",
        ),
        sa.CheckConstraint(
            f"environment IN ({_ENVIRONMENTS})",
            name=f"ck_{prefix}_environment",
        ),
    )


def _json_object_constraint(column: str, name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"jsonb_typeof({column}) = 'object'",
        name=name,
    )


def _sha_constraint(column: str, name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{column} ~ '{_SHA256}'", name=name)


def _create_candidate() -> None:
    op.create_table(
        "ai_assistant_release_candidate",
        *_identifier_columns(),
        *_scope_columns(),
        sa.Column("candidate_id", sa.String(160), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("requested_by_subject", sa.String(160), nullable=False),
        sa.Column("gate_policy_revision", sa.String(160), nullable=False),
        sa.Column("gate_policy_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_document", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assistant_profile",
            "environment",
            "candidate_id",
            name="uq_ai_assistant_release_candidate_identity",
        ),
        sa.UniqueConstraint(
            "assistant_profile",
            "environment",
            "content_sha256",
            name="uq_ai_assistant_release_candidate_digest",
        ),
        sa.UniqueConstraint(
            "id",
            "assistant_profile",
            "environment",
            name="uq_ai_assistant_release_candidate_scope",
        ),
        sa.UniqueConstraint(
            "id",
            "assistant_profile",
            "environment",
            "content_sha256",
            name="uq_ai_assistant_release_candidate_scope_digest",
        ),
        sa.CheckConstraint(
            "length(btrim(candidate_id)) BETWEEN 1 AND 160 "
            "AND length(btrim(requested_by_subject)) BETWEEN 1 AND 160 "
            "AND length(btrim(gate_policy_revision)) BETWEEN 1 AND 160",
            name="ck_ai_assistant_release_candidate_identifiers",
        ),
        _sha_constraint(
            "content_sha256",
            "ck_ai_assistant_release_candidate_content_digest",
        ),
        _sha_constraint(
            "gate_policy_sha256",
            "ck_ai_assistant_release_candidate_gate_digest",
        ),
        _json_object_constraint(
            "canonical_document",
            "ck_ai_assistant_release_candidate_document",
        ),
        *_scope_checks("ai_assistant_release_candidate"),
    )


def _create_static_safe_release() -> None:
    op.create_table(
        "ai_assistant_static_safe_release",
        *_identifier_columns(),
        *_scope_columns(),
        sa.Column("safe_release_id", sa.String(160), nullable=False),
        sa.Column("safe_release_ref", sa.String(255), nullable=False),
        sa.Column("safe_release_core_sha256", sa.String(64), nullable=False),
        sa.Column("approval_set_sha256", sa.String(64), nullable=False),
        sa.Column("safe_release_envelope_sha256", sa.String(64), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canonical_document", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assistant_profile",
            "environment",
            "safe_release_id",
            name="uq_ai_assistant_static_safe_release_identity",
        ),
        sa.UniqueConstraint(
            "assistant_profile",
            "environment",
            "safe_release_envelope_sha256",
            name="uq_ai_assistant_static_safe_release_envelope",
        ),
        sa.UniqueConstraint(
            "id",
            "assistant_profile",
            "environment",
            name="uq_ai_assistant_static_safe_release_scope",
        ),
        sa.CheckConstraint(
            "length(btrim(safe_release_id)) BETWEEN 1 AND 160 "
            "AND length(btrim(safe_release_ref)) BETWEEN 5 AND 255",
            name="ck_ai_assistant_static_safe_release_identifiers",
        ),
        sa.CheckConstraint(
            "expires_at > effective_at",
            name="ck_ai_assistant_static_safe_release_window",
        ),
        _sha_constraint(
            "safe_release_core_sha256",
            "ck_ai_assistant_static_safe_release_core_digest",
        ),
        _sha_constraint(
            "approval_set_sha256",
            "ck_ai_assistant_static_safe_release_approval_digest",
        ),
        _sha_constraint(
            "safe_release_envelope_sha256",
            "ck_ai_assistant_static_safe_release_envelope_digest",
        ),
        _json_object_constraint(
            "canonical_document",
            "ck_ai_assistant_static_safe_release_document",
        ),
        *_scope_checks("ai_assistant_static_safe_release"),
    )


def _create_activation() -> None:
    op.create_table(
        "ai_assistant_release_activation",
        *_identifier_columns(),
        *_scope_columns(),
        sa.Column("activation_id", sa.String(160), nullable=False),
        sa.Column(
            "candidate_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "static_safe_release_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("candidate_sha256", sa.String(64), nullable=False),
        sa.Column("approval_set_sha256", sa.String(64), nullable=False),
        sa.Column("automated_gate_evidence_sha256", sa.String(64), nullable=False),
        sa.Column("activation_core_sha256", sa.String(64), nullable=False),
        sa.Column("activation_envelope_sha256", sa.String(64), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rollback_target_kind", sa.String(24), nullable=False),
        sa.Column(
            "rollback_activation_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "rollback_static_safe_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("kill_switch_registry_ref", sa.String(255), nullable=False),
        sa.Column("kill_switch_registry_sha256", sa.String(64), nullable=False),
        sa.Column("rollback_drill_evidence_ref", sa.String(255), nullable=False),
        sa.Column("rollback_drill_evidence_sha256", sa.String(64), nullable=False),
        sa.Column("promotion_evidence_ref", sa.String(255), nullable=False),
        sa.Column("promotion_evidence_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_document", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            [
                "candidate_record_id",
                "assistant_profile",
                "environment",
                "candidate_sha256",
            ],
            [
                "ai_assistant_release_candidate.id",
                "ai_assistant_release_candidate.assistant_profile",
                "ai_assistant_release_candidate.environment",
                "ai_assistant_release_candidate.content_sha256",
            ],
            name="fk_ai_assistant_activation_candidate_scope_digest",
        ),
        sa.ForeignKeyConstraint(
            [
                "static_safe_release_record_id",
                "assistant_profile",
                "environment",
            ],
            [
                "ai_assistant_static_safe_release.id",
                "ai_assistant_static_safe_release.assistant_profile",
                "ai_assistant_static_safe_release.environment",
            ],
            name="fk_ai_assistant_activation_static_safe_scope",
        ),
        sa.ForeignKeyConstraint(
            [
                "rollback_activation_record_id",
                "assistant_profile",
                "environment",
            ],
            [
                "ai_assistant_release_activation.id",
                "ai_assistant_release_activation.assistant_profile",
                "ai_assistant_release_activation.environment",
            ],
            name="fk_ai_assistant_activation_rollback_activation_scope",
        ),
        sa.ForeignKeyConstraint(
            [
                "rollback_static_safe_record_id",
                "assistant_profile",
                "environment",
            ],
            [
                "ai_assistant_static_safe_release.id",
                "ai_assistant_static_safe_release.assistant_profile",
                "ai_assistant_static_safe_release.environment",
            ],
            name="fk_ai_assistant_activation_rollback_static_safe_scope",
        ),
        sa.UniqueConstraint(
            "assistant_profile",
            "environment",
            "activation_id",
            name="uq_ai_assistant_release_activation_identity",
        ),
        sa.UniqueConstraint(
            "assistant_profile",
            "environment",
            "activation_envelope_sha256",
            name="uq_ai_assistant_release_activation_envelope",
        ),
        sa.UniqueConstraint(
            "id",
            "assistant_profile",
            "environment",
            name="uq_ai_assistant_release_activation_scope",
        ),
        sa.CheckConstraint(
            "length(btrim(activation_id)) BETWEEN 1 AND 160",
            name="ck_ai_assistant_release_activation_identity",
        ),
        sa.CheckConstraint(
            "expires_at > effective_at",
            name="ck_ai_assistant_release_activation_window",
        ),
        sa.CheckConstraint(
            "(rollback_target_kind = 'prior_activation' "
            "AND rollback_activation_record_id IS NOT NULL "
            "AND rollback_static_safe_record_id IS NULL) "
            "OR (rollback_target_kind = 'static_safe_release' "
            "AND rollback_activation_record_id IS NULL "
            "AND rollback_static_safe_record_id IS NOT NULL)",
            name="ck_ai_assistant_release_activation_rollback_target",
        ),
        *(
            _sha_constraint(column, f"ck_ai_assistant_release_activation_{suffix}")
            for column, suffix in (
                ("candidate_sha256", "candidate_digest"),
                ("approval_set_sha256", "approval_digest"),
                ("automated_gate_evidence_sha256", "gate_digest"),
                ("activation_core_sha256", "core_digest"),
                ("activation_envelope_sha256", "envelope_digest"),
                ("kill_switch_registry_sha256", "kill_switch_digest"),
                ("rollback_drill_evidence_sha256", "rollback_drill_digest"),
                ("promotion_evidence_sha256", "promotion_digest"),
            )
        ),
        _json_object_constraint(
            "canonical_document",
            "ck_ai_assistant_release_activation_document",
        ),
        *_scope_checks("ai_assistant_release_activation"),
    )


def _create_history() -> None:
    op.create_table(
        "ai_assistant_release_history",
        *_identifier_columns(),
        *_scope_columns(),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("pointer_revision", sa.BigInteger(), nullable=False),
        sa.Column("from_target_kind", sa.String(24), nullable=False),
        sa.Column(
            "from_activation_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "from_static_safe_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("to_target_kind", sa.String(24), nullable=False),
        sa.Column(
            "to_activation_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "to_static_safe_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("history_event_ref", sa.String(255), nullable=False),
        sa.Column("previous_event_sha256", sa.String(64), nullable=True),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("activation_envelope_sha256", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(160), nullable=False),
        sa.Column("idempotency_key_sha256", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_transaction_id",
            sa.BigInteger(),
            server_default=sa.text("txid_current()"),
            nullable=False,
        ),
        sa.Column("transaction_context", postgresql.JSONB(), nullable=False),
        sa.Column("canonical_document", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            [
                "from_activation_record_id",
                "assistant_profile",
                "environment",
            ],
            [
                "ai_assistant_release_activation.id",
                "ai_assistant_release_activation.assistant_profile",
                "ai_assistant_release_activation.environment",
            ],
            name="fk_ai_assistant_history_from_activation_scope",
        ),
        sa.ForeignKeyConstraint(
            [
                "to_activation_record_id",
                "assistant_profile",
                "environment",
            ],
            [
                "ai_assistant_release_activation.id",
                "ai_assistant_release_activation.assistant_profile",
                "ai_assistant_release_activation.environment",
            ],
            name="fk_ai_assistant_history_to_activation_scope",
        ),
        sa.ForeignKeyConstraint(
            [
                "from_static_safe_record_id",
                "assistant_profile",
                "environment",
            ],
            [
                "ai_assistant_static_safe_release.id",
                "ai_assistant_static_safe_release.assistant_profile",
                "ai_assistant_static_safe_release.environment",
            ],
            name="fk_ai_assistant_history_from_static_safe_scope",
        ),
        sa.ForeignKeyConstraint(
            [
                "to_static_safe_record_id",
                "assistant_profile",
                "environment",
            ],
            [
                "ai_assistant_static_safe_release.id",
                "ai_assistant_static_safe_release.assistant_profile",
                "ai_assistant_static_safe_release.environment",
            ],
            name="fk_ai_assistant_history_to_static_safe_scope",
        ),
        sa.UniqueConstraint(
            "assistant_profile",
            "environment",
            "sequence",
            name="uq_ai_assistant_release_history_sequence",
        ),
        sa.UniqueConstraint(
            "assistant_profile",
            "environment",
            "event_sha256",
            name="uq_ai_assistant_release_history_digest",
        ),
        sa.UniqueConstraint(
            "assistant_profile",
            "environment",
            "idempotency_key_sha256",
            name="uq_ai_assistant_release_history_idempotency",
        ),
        sa.UniqueConstraint(
            "id",
            "assistant_profile",
            "environment",
            name="uq_ai_assistant_release_history_scope",
        ),
        sa.CheckConstraint(
            "sequence > 0 AND pointer_revision > 0",
            name="ck_ai_assistant_release_history_revisions",
        ),
        sa.CheckConstraint(
            "length(btrim(correlation_id)) BETWEEN 1 AND 160 "
            "AND length(btrim(history_event_ref)) BETWEEN 5 AND 255",
            name="ck_ai_assistant_release_history_identifiers",
        ),
        sa.CheckConstraint(
            "((from_target_kind = 'activation' "
            "AND from_activation_record_id IS NOT NULL "
            "AND from_static_safe_record_id IS NULL) "
            "OR (from_target_kind = 'static_safe_release' "
            "AND from_activation_record_id IS NULL "
            "AND from_static_safe_record_id IS NOT NULL)) "
            "AND ((to_target_kind = 'activation' "
            "AND to_activation_record_id IS NOT NULL "
            "AND to_static_safe_record_id IS NULL) "
            "OR (to_target_kind = 'static_safe_release' "
            "AND to_activation_record_id IS NULL "
            "AND to_static_safe_record_id IS NOT NULL))",
            name="ck_ai_assistant_release_history_target_shape",
        ),
        sa.CheckConstraint(
            "(event_type = 'activated' "
            "AND from_target_kind = 'static_safe_release' "
            "AND to_target_kind = 'activation') "
            "OR (event_type = 'superseded' "
            "AND from_target_kind = 'activation' "
            "AND to_target_kind = 'activation') "
            "OR (event_type = 'revoked' "
            "AND from_target_kind = 'activation' "
            "AND to_target_kind = 'static_safe_release') "
            "OR (event_type = 'rolled_back' "
            "AND from_target_kind = 'activation' "
            "AND to_target_kind = 'activation')",
            name="ck_ai_assistant_release_history_event_matrix",
        ),
        sa.CheckConstraint(
            "(from_activation_record_id IS DISTINCT FROM to_activation_record_id) "
            "OR (from_static_safe_record_id IS DISTINCT FROM to_static_safe_record_id)",
            name="ck_ai_assistant_release_history_distinct_targets",
        ),
        sa.CheckConstraint(
            "(sequence = 1 AND previous_event_sha256 IS NULL) "
            "OR (sequence > 1 AND previous_event_sha256 IS NOT NULL)",
            name="ck_ai_assistant_release_history_chain_shape",
        ),
        _sha_constraint(
            "event_sha256",
            "ck_ai_assistant_release_history_event_digest",
        ),
        _sha_constraint(
            "activation_envelope_sha256",
            "ck_ai_assistant_release_history_activation_digest",
        ),
        _sha_constraint(
            "idempotency_key_sha256",
            "ck_ai_assistant_release_history_idempotency_digest",
        ),
        sa.CheckConstraint(
            f"previous_event_sha256 IS NULL OR previous_event_sha256 ~ '{_SHA256}'",
            name="ck_ai_assistant_release_history_previous_digest",
        ),
        _json_object_constraint(
            "transaction_context",
            "ck_ai_assistant_release_history_transaction_context",
        ),
        _json_object_constraint(
            "canonical_document",
            "ck_ai_assistant_release_history_document",
        ),
        *_scope_checks("ai_assistant_release_history"),
    )


def _create_pointer() -> None:
    op.create_table(
        "ai_assistant_release_pointer",
        *_identifier_columns(),
        *_scope_columns(),
        sa.Column("target_kind", sa.String(24), nullable=False),
        sa.Column(
            "activation_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "static_safe_release_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("last_history_event_sha256", sa.String(64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            [
                "activation_record_id",
                "assistant_profile",
                "environment",
            ],
            [
                "ai_assistant_release_activation.id",
                "ai_assistant_release_activation.assistant_profile",
                "ai_assistant_release_activation.environment",
            ],
            name="fk_ai_assistant_pointer_activation_scope",
        ),
        sa.ForeignKeyConstraint(
            [
                "static_safe_release_record_id",
                "assistant_profile",
                "environment",
            ],
            [
                "ai_assistant_static_safe_release.id",
                "ai_assistant_static_safe_release.assistant_profile",
                "ai_assistant_static_safe_release.environment",
            ],
            name="fk_ai_assistant_pointer_static_safe_scope",
        ),
        sa.UniqueConstraint(
            "assistant_profile",
            "environment",
            name="uq_ai_assistant_release_pointer_scope",
        ),
        sa.CheckConstraint(
            "revision >= 0",
            name="ck_ai_assistant_release_pointer_revision",
        ),
        sa.CheckConstraint(
            "(target_kind = 'activation' "
            "AND activation_record_id IS NOT NULL "
            "AND static_safe_release_record_id IS NULL) "
            "OR (target_kind = 'static_safe_release' "
            "AND activation_record_id IS NULL "
            "AND static_safe_release_record_id IS NOT NULL)",
            name="ck_ai_assistant_release_pointer_target",
        ),
        sa.CheckConstraint(
            f"last_history_event_sha256 IS NULL OR last_history_event_sha256 ~ '{_SHA256}'",
            name="ck_ai_assistant_release_pointer_history_digest",
        ),
        *_scope_checks("ai_assistant_release_pointer"),
    )


def _create_outbox() -> None:
    op.create_table(
        "ai_assistant_release_outbox_event",
        *_identifier_columns(),
        *_scope_columns(),
        sa.Column(
            "history_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("event_ref", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("idempotency_key_sha256", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            [
                "history_record_id",
                "assistant_profile",
                "environment",
            ],
            [
                "ai_assistant_release_history.id",
                "ai_assistant_release_history.assistant_profile",
                "ai_assistant_release_history.environment",
            ],
            name="fk_ai_assistant_release_outbox_history_scope",
        ),
        sa.UniqueConstraint(
            "assistant_profile",
            "environment",
            "event_ref",
            name="uq_ai_assistant_release_outbox_event_ref",
        ),
        sa.UniqueConstraint(
            "assistant_profile",
            "environment",
            "idempotency_key_sha256",
            name="uq_ai_assistant_release_outbox_idempotency",
        ),
        sa.UniqueConstraint(
            "history_record_id",
            name="uq_ai_assistant_release_outbox_history",
        ),
        sa.CheckConstraint(
            "length(btrim(event_ref)) BETWEEN 5 AND 255 "
            "AND length(btrim(event_type)) BETWEEN 1 AND 80",
            name="ck_ai_assistant_release_outbox_identifiers",
        ),
        _sha_constraint(
            "event_sha256",
            "ck_ai_assistant_release_outbox_event_digest",
        ),
        _sha_constraint(
            "payload_sha256",
            "ck_ai_assistant_release_outbox_payload_digest",
        ),
        _sha_constraint(
            "idempotency_key_sha256",
            "ck_ai_assistant_release_outbox_idempotency_digest",
        ),
        _json_object_constraint(
            "payload",
            "ck_ai_assistant_release_outbox_payload",
        ),
        *_scope_checks("ai_assistant_release_outbox_event"),
    )
    op.create_table(
        "ai_assistant_release_outbox_delivery",
        *_identifier_columns(),
        sa.Column(
            "event_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("destination", sa.String(160), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default=sa.text("12"),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(160), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(160), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["event_record_id"],
            ["ai_assistant_release_outbox_event.id"],
            name="fk_ai_assistant_release_delivery_event",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "event_record_id",
            "destination",
            name="uq_ai_assistant_release_outbox_delivery",
        ),
        sa.CheckConstraint(
            "length(btrim(destination)) BETWEEN 1 AND 160",
            name="ck_ai_assistant_release_delivery_destination",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts",
            name="ck_ai_assistant_release_delivery_attempts",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND lease_owner IS NULL "
            "AND lease_expires_at IS NULL AND delivered_at IS NULL) "
            "OR (status = 'leased' AND lease_owner IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND delivered_at IS NULL) "
            "OR (status = 'delivered' AND lease_owner IS NULL "
            "AND lease_expires_at IS NULL AND delivered_at IS NOT NULL) "
            "OR (status = 'dead_letter' AND lease_owner IS NULL "
            "AND lease_expires_at IS NULL AND delivered_at IS NULL)",
            name="ck_ai_assistant_release_delivery_state",
        ),
    )
    op.create_index(
        "ix_ai_assistant_release_outbox_delivery_claim",
        "ai_assistant_release_outbox_delivery",
        ["status", "available_at", "lease_expires_at"],
        postgresql_where=sa.text("status IN ('pending','leased')"),
    )


def _create_immutability_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION assistant_release_reject_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION '% is immutable', TG_TABLE_NAME
            USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    for table in (
        "ai_assistant_release_candidate",
        "ai_assistant_static_safe_release",
        "ai_assistant_release_activation",
        "ai_assistant_release_history",
        "ai_assistant_release_outbox_event",
    ):
        op.execute(
            f"""
            CREATE TRIGGER tr_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION assistant_release_reject_mutation();
            """
        )


def _create_canonical_json_function() -> None:
    op.execute(
        """
        CREATE FUNCTION assistant_release_canonical_jsonb(value jsonb)
        RETURNS text
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        AS $$
        DECLARE
          rendered text;
        BEGIN
          CASE jsonb_typeof(value)
            WHEN 'object' THEN
              SELECT '{' || COALESCE(
                string_agg(
                  to_jsonb(entry.key)::text || ':' ||
                    assistant_release_canonical_jsonb(entry.value),
                  ',' ORDER BY entry.key COLLATE "C"
                ),
                ''
              ) || '}'
              INTO rendered
              FROM jsonb_each(value) AS entry;
            WHEN 'array' THEN
              SELECT '[' || COALESCE(
                string_agg(
                  assistant_release_canonical_jsonb(entry.value),
                  ',' ORDER BY entry.ordinality
                ),
                ''
              ) || ']'
              INTO rendered
              FROM jsonb_array_elements(value)
                WITH ORDINALITY AS entry(value, ordinality);
            ELSE
              rendered := value::text;
          END CASE;
          RETURN rendered;
        END;
        $$;
        """
    )


def _create_target_document_function() -> None:
    op.execute(
        """
        CREATE FUNCTION assistant_release_target_document(
          requested_kind varchar,
          requested_activation_id uuid,
          requested_static_safe_id uuid,
          requested_profile varchar,
          requested_environment varchar
        )
        RETURNS jsonb
        LANGUAGE plpgsql
        STABLE
        AS $$
        DECLARE
          target jsonb;
        BEGIN
          IF requested_kind = 'activation' THEN
            SELECT jsonb_build_object(
              'kind', 'activation',
              'activation_id', activation.activation_id,
              'activation_envelope_sha256',
                activation.activation_envelope_sha256,
              'candidate_id', candidate.candidate_id,
              'candidate_sha256', activation.candidate_sha256,
              'assistant_profile', activation.assistant_profile,
              'environment', activation.environment
            )
            INTO target
            FROM ai_assistant_release_activation activation
            JOIN ai_assistant_release_candidate candidate
              ON candidate.id = activation.candidate_record_id
            WHERE activation.id = requested_activation_id
              AND activation.assistant_profile = requested_profile
              AND activation.environment = requested_environment;
          ELSIF requested_kind = 'static_safe_release' THEN
            SELECT jsonb_build_object(
              'kind', 'static_safe_release',
              'safe_release_id', safe.safe_release_id,
              'safe_release_ref', safe.safe_release_ref,
              'safe_release_core_sha256', safe.safe_release_core_sha256,
              'approval_set_sha256', safe.approval_set_sha256,
              'safe_release_envelope_sha256',
                safe.safe_release_envelope_sha256,
              'assistant_profile', safe.assistant_profile,
              'environment', safe.environment
            )
            INTO target
            FROM ai_assistant_static_safe_release safe
            WHERE safe.id = requested_static_safe_id
              AND safe.assistant_profile = requested_profile
              AND safe.environment = requested_environment;
          ELSE
            RAISE EXCEPTION 'unsupported assistant release target kind'
              USING ERRCODE = '23514';
          END IF;

          IF target IS NULL THEN
            RAISE EXCEPTION 'assistant release target does not exist in scope'
              USING ERRCODE = '23503';
          END IF;
          RETURN target;
        END;
        $$;
        """
    )


def _create_history_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION assistant_release_validate_history()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          prior_sequence bigint;
          prior_digest varchar(64);
          expected_from_target jsonb;
          expected_to_target jsonb;
          expected_activation_envelope varchar(64);
          expected_event_digest varchar(64);
          expected_event_keys text[] := ARRAY[
            'activation_envelope_sha256',
            'event_ref',
            'event_sha256',
            'event_type',
            'from_target',
            'occurred_at',
            'pointer_revision',
            'previous_event_sha256',
            'sequence',
            'to_target',
            'transaction_context'
          ];
        BEGIN
          PERFORM pg_advisory_xact_lock(
            hashtextextended(NEW.assistant_profile || ':' || NEW.environment, 0)
          );

          SELECT sequence, event_sha256
          INTO prior_sequence, prior_digest
          FROM ai_assistant_release_history
          WHERE assistant_profile = NEW.assistant_profile
            AND environment = NEW.environment
          ORDER BY sequence DESC
          LIMIT 1;

          IF prior_sequence IS NULL THEN
            IF NEW.sequence <> 1 OR NEW.previous_event_sha256 IS NOT NULL THEN
              RAISE EXCEPTION 'assistant release history must start at sequence one'
                USING ERRCODE = '23514';
            END IF;
          ELSIF NEW.sequence <> prior_sequence + 1
             OR NEW.previous_event_sha256 IS DISTINCT FROM prior_digest THEN
            RAISE EXCEPTION 'assistant release history hash chain is not contiguous'
              USING ERRCODE = '23514';
          END IF;

          IF NEW.pointer_revision <> NEW.sequence THEN
            RAISE EXCEPTION 'assistant release pointer/history revisions diverged'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.created_transaction_id <> txid_current() THEN
            RAISE EXCEPTION
              'assistant release history transaction identity is invalid'
              USING ERRCODE = '23514';
          END IF;

          expected_event_digest := encode(
            digest(
              convert_to(
                assistant_release_canonical_jsonb(
                  NEW.canonical_document - 'event_sha256'
                ),
                'UTF8'
              ),
              'sha256'
            ),
            'hex'
          );
          IF NEW.event_sha256 IS DISTINCT FROM expected_event_digest THEN
            RAISE EXCEPTION 'assistant release canonical event digest mismatch'
              USING ERRCODE = '23514';
          END IF;

          expected_from_target := assistant_release_target_document(
            NEW.from_target_kind,
            NEW.from_activation_record_id,
            NEW.from_static_safe_record_id,
            NEW.assistant_profile,
            NEW.environment
          );
          expected_to_target := assistant_release_target_document(
            NEW.to_target_kind,
            NEW.to_activation_record_id,
            NEW.to_static_safe_record_id,
            NEW.assistant_profile,
            NEW.environment
          );
          IF NEW.event_type = 'revoked' THEN
            expected_activation_envelope :=
              expected_from_target->>'activation_envelope_sha256';
          ELSE
            expected_activation_envelope :=
              expected_to_target->>'activation_envelope_sha256';
          END IF;

          IF jsonb_typeof(NEW.canonical_document) <> 'object'
             OR ARRAY(
               SELECT key
               FROM jsonb_object_keys(NEW.canonical_document) AS key
               ORDER BY key COLLATE "C"
             ) IS DISTINCT FROM expected_event_keys
             OR NEW.canonical_document->>'event_ref'
                IS DISTINCT FROM NEW.history_event_ref
             OR (NEW.canonical_document->>'sequence')::bigint
                IS DISTINCT FROM NEW.sequence
             OR NEW.canonical_document->>'previous_event_sha256'
                IS DISTINCT FROM NEW.previous_event_sha256
             OR NEW.canonical_document->>'event_sha256'
                IS DISTINCT FROM NEW.event_sha256
             OR NEW.canonical_document->>'event_type'
                IS DISTINCT FROM NEW.event_type
             OR NEW.canonical_document->'from_target'
                IS DISTINCT FROM expected_from_target
             OR NEW.canonical_document->'to_target'
                IS DISTINCT FROM expected_to_target
             OR NEW.canonical_document->>'activation_envelope_sha256'
                IS DISTINCT FROM NEW.activation_envelope_sha256
             OR NEW.activation_envelope_sha256
                IS DISTINCT FROM expected_activation_envelope
             OR (NEW.canonical_document->>'pointer_revision')::bigint
                IS DISTINCT FROM NEW.pointer_revision
             OR NEW.canonical_document->'transaction_context'
                IS DISTINCT FROM NEW.transaction_context
             OR (NEW.canonical_document->>'occurred_at')::timestamptz
                IS DISTINCT FROM NEW.occurred_at THEN
            RAISE EXCEPTION 'assistant release canonical event payload mismatch'
              USING ERRCODE = '23514';
          END IF;

          IF NEW.event_type = 'activated' AND NOT EXISTS (
            SELECT 1
            FROM ai_assistant_release_activation target_activation
            WHERE target_activation.id = NEW.to_activation_record_id
              AND target_activation.assistant_profile = NEW.assistant_profile
              AND target_activation.environment = NEW.environment
              AND target_activation.rollback_target_kind =
                'static_safe_release'
              AND target_activation.rollback_static_safe_record_id =
                NEW.from_static_safe_record_id
          ) THEN
            RAISE EXCEPTION
              'activation source does not match activation-pinned authority'
              USING ERRCODE = '23514';
          END IF;

          IF NEW.event_type = 'rolled_back' AND NOT EXISTS (
            SELECT 1
            FROM ai_assistant_release_activation current_activation
            WHERE current_activation.id = NEW.from_activation_record_id
              AND current_activation.assistant_profile = NEW.assistant_profile
              AND current_activation.environment = NEW.environment
              AND current_activation.rollback_target_kind = 'prior_activation'
              AND current_activation.rollback_activation_record_id =
                NEW.to_activation_record_id
          ) THEN
            RAISE EXCEPTION
              'rollback target does not match activation-pinned authority'
              USING ERRCODE = '23514';
          END IF;

          IF NEW.event_type = 'revoked' AND NOT EXISTS (
            SELECT 1
            FROM ai_assistant_release_activation current_activation
            WHERE current_activation.id = NEW.from_activation_record_id
              AND current_activation.assistant_profile = NEW.assistant_profile
              AND current_activation.environment = NEW.environment
              AND current_activation.rollback_target_kind =
                'static_safe_release'
              AND current_activation.rollback_static_safe_record_id =
                NEW.to_static_safe_record_id
          ) THEN
            RAISE EXCEPTION
              'revoke target does not match activation-pinned authority'
              USING ERRCODE = '23514';
          END IF;

          IF NEW.event_type = 'rolled_back' AND NOT EXISTS (
            SELECT 1
            FROM ai_assistant_release_history prior
            WHERE prior.assistant_profile = NEW.assistant_profile
              AND prior.environment = NEW.environment
              AND prior.sequence < NEW.sequence
              AND prior.to_activation_record_id = NEW.to_activation_record_id
              AND prior.event_type IN ('activated', 'superseded', 'rolled_back')
          ) THEN
            RAISE EXCEPTION
              'eligible rollback activation has never been authoritative'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tr_ai_assistant_release_history_chain
        BEFORE INSERT ON ai_assistant_release_history
        FOR EACH ROW EXECUTE FUNCTION assistant_release_validate_history();
        """
    )


def _create_pointer_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION assistant_release_guard_pointer()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          transition ai_assistant_release_history%ROWTYPE;
        BEGIN
          IF TG_OP = 'INSERT' THEN
            IF NEW.revision <> 0
               OR NEW.target_kind <> 'static_safe_release'
               OR NEW.activation_record_id IS NOT NULL
               OR NEW.static_safe_release_record_id IS NULL
               OR NEW.last_history_event_sha256 IS NOT NULL THEN
              RAISE EXCEPTION
                'assistant release pointer must initialize on static safe revision zero'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'assistant release pointer cannot be deleted'
              USING ERRCODE = '55000';
          END IF;
          IF NEW.id <> OLD.id
             OR NEW.assistant_profile <> OLD.assistant_profile
             OR NEW.environment <> OLD.environment
             OR NEW.created_at <> OLD.created_at THEN
            RAISE EXCEPTION 'assistant release pointer scope is immutable'
              USING ERRCODE = '55000';
          END IF;
          IF NEW.revision <> OLD.revision + 1 THEN
            RAISE EXCEPTION 'assistant release pointer revision must increment once'
              USING ERRCODE = '40001';
          END IF;
          IF NEW.updated_at <= OLD.updated_at THEN
            RAISE EXCEPTION 'assistant release pointer update timestamp must advance'
              USING ERRCODE = '23514';
          END IF;

          IF NEW.last_history_event_sha256 IS NULL THEN
            RAISE EXCEPTION
              'assistant release pointer requires matching history transition'
              USING ERRCODE = '23514';
          END IF;
          SELECT history.*
          INTO transition
          FROM ai_assistant_release_history history
          WHERE history.assistant_profile = NEW.assistant_profile
            AND history.environment = NEW.environment
            AND history.pointer_revision = NEW.revision
            AND history.event_sha256 = NEW.last_history_event_sha256
            AND history.created_transaction_id = txid_current();

          IF NOT FOUND THEN
            RAISE EXCEPTION
              'assistant release pointer requires matching history transition'
              USING ERRCODE = '23514';
          END IF;
          IF transition.from_target_kind IS DISTINCT FROM OLD.target_kind
             OR transition.from_activation_record_id
                IS DISTINCT FROM OLD.activation_record_id
             OR transition.from_static_safe_record_id
                IS DISTINCT FROM OLD.static_safe_release_record_id
             OR transition.to_target_kind IS DISTINCT FROM NEW.target_kind
             OR transition.to_activation_record_id
                IS DISTINCT FROM NEW.activation_record_id
             OR transition.to_static_safe_record_id
                IS DISTINCT FROM NEW.static_safe_release_record_id THEN
            RAISE EXCEPTION
              'assistant release history transition does not match pointer targets'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tr_ai_assistant_release_pointer_guard
        BEFORE INSERT OR UPDATE OR DELETE ON ai_assistant_release_pointer
        FOR EACH ROW EXECUTE FUNCTION assistant_release_guard_pointer();
        """
    )


def _create_outbox_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION assistant_release_validate_outbox_event()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          history ai_assistant_release_history%ROWTYPE;
          expected_payload_sha256 varchar(64);
        BEGIN
          SELECT release_history.*
          INTO history
          FROM ai_assistant_release_history release_history
          WHERE release_history.id = NEW.history_record_id
            AND release_history.assistant_profile = NEW.assistant_profile
            AND release_history.environment = NEW.environment;

          IF NOT FOUND
             OR NEW.event_type IS DISTINCT FROM
                'assistant.release.' || history.event_type
             OR NEW.event_sha256 IS DISTINCT FROM history.event_sha256 THEN
            RAISE EXCEPTION
              'outbox event is not bound to release history'
              USING ERRCODE = '23514';
          END IF;

          expected_payload_sha256 := encode(
            digest(
              convert_to(
                assistant_release_canonical_jsonb(NEW.payload),
                'UTF8'
              ),
              'sha256'
            ),
            'hex'
          );
          IF NEW.payload IS DISTINCT FROM history.canonical_document
             OR NEW.payload_sha256 IS DISTINCT FROM expected_payload_sha256 THEN
            RAISE EXCEPTION
              'outbox payload is not bound to release history'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tr_ai_assistant_release_outbox_binding
        BEFORE INSERT ON ai_assistant_release_outbox_event
        FOR EACH ROW EXECUTE FUNCTION assistant_release_validate_outbox_event();
        """
    )


def _create_history_commit_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION assistant_release_validate_history_commit()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM ai_assistant_release_pointer pointer
            WHERE pointer.assistant_profile = NEW.assistant_profile
              AND pointer.environment = NEW.environment
              AND pointer.revision = NEW.pointer_revision
              AND pointer.last_history_event_sha256 = NEW.event_sha256
              AND pointer.target_kind = NEW.to_target_kind
              AND pointer.activation_record_id
                    IS NOT DISTINCT FROM NEW.to_activation_record_id
              AND pointer.static_safe_release_record_id
                    IS NOT DISTINCT FROM NEW.to_static_safe_record_id
          ) OR NOT EXISTS (
            SELECT 1
            FROM ai_assistant_release_outbox_event outbox
            WHERE outbox.history_record_id = NEW.id
              AND outbox.assistant_profile = NEW.assistant_profile
              AND outbox.environment = NEW.environment
              AND outbox.event_type = 'assistant.release.' || NEW.event_type
              AND outbox.event_sha256 = NEW.event_sha256
              AND outbox.payload = NEW.canonical_document
              AND outbox.payload_sha256 = encode(
                digest(
                  convert_to(
                    assistant_release_canonical_jsonb(outbox.payload),
                    'UTF8'
                  ),
                  'sha256'
                ),
                'hex'
              )
          ) THEN
            RAISE EXCEPTION
              'assistant release history commit requires matching pointer and outbox'
              USING ERRCODE = '23514';
          END IF;
          RETURN NULL;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER tr_ai_assistant_release_history_commit
        AFTER INSERT ON ai_assistant_release_history
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION assistant_release_validate_history_commit();
        """
    )


def _create_outbox_claim_function() -> None:
    op.execute(
        """
        CREATE FUNCTION assistant_release_claim_outbox_delivery(
          requested_destination varchar,
          requested_owner varchar,
          requested_lease_seconds integer,
          requested_limit integer
        )
        RETURNS SETOF ai_assistant_release_outbox_delivery
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF length(btrim(requested_destination)) NOT BETWEEN 1 AND 160
             OR length(btrim(requested_owner)) NOT BETWEEN 1 AND 160
             OR requested_lease_seconds NOT BETWEEN 1 AND 3600
             OR requested_limit NOT BETWEEN 1 AND 1000 THEN
            RAISE EXCEPTION 'invalid assistant release outbox lease request'
              USING ERRCODE = '22023';
          END IF;

          UPDATE ai_assistant_release_outbox_delivery delivery
          SET status = 'dead_letter',
              lease_owner = NULL,
              lease_expires_at = NULL,
              last_error_code = COALESCE(
                delivery.last_error_code,
                'LEASE_EXPIRED_AFTER_FINAL_ATTEMPT'
              ),
              updated_at = clock_timestamp()
          WHERE delivery.destination = requested_destination
            AND delivery.status = 'leased'
            AND delivery.lease_expires_at <= clock_timestamp()
            AND delivery.attempt_count >= delivery.max_attempts;

          RETURN QUERY
          WITH claimable AS (
            SELECT delivery.id
            FROM ai_assistant_release_outbox_delivery delivery
            WHERE delivery.destination = requested_destination
              AND delivery.attempt_count < delivery.max_attempts
              AND delivery.available_at <= clock_timestamp()
              AND (
                delivery.status = 'pending'
                OR (
                  delivery.status = 'leased'
                  AND delivery.lease_expires_at <= clock_timestamp()
                )
              )
            ORDER BY delivery.available_at, delivery.created_at, delivery.id
            FOR UPDATE SKIP LOCKED
            LIMIT requested_limit
          )
          UPDATE ai_assistant_release_outbox_delivery delivery
          SET status = 'leased',
              attempt_count = delivery.attempt_count + 1,
              lease_owner = requested_owner,
              lease_expires_at =
                clock_timestamp() + make_interval(secs => requested_lease_seconds),
              updated_at = clock_timestamp()
          FROM claimable
          WHERE delivery.id = claimable.id
          RETURNING delivery.*;
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM ai_assistant_release_candidate
            UNION ALL SELECT 1 FROM ai_assistant_static_safe_release
            UNION ALL SELECT 1 FROM ai_assistant_release_activation
            UNION ALL SELECT 1 FROM ai_assistant_release_history
            UNION ALL SELECT 1 FROM ai_assistant_release_pointer
            UNION ALL SELECT 1 FROM ai_assistant_release_outbox_event
            UNION ALL SELECT 1 FROM ai_assistant_release_outbox_delivery
          ) THEN
            RAISE EXCEPTION
              'assistant release authority downgrade refused: persisted rows exist'
              USING ERRCODE = '55000';
          END IF;
        END;
        $$;
        """
    )
    op.execute(
        "DROP FUNCTION assistant_release_claim_outbox_delivery(varchar,varchar,integer,integer)"
    )
    for table in reversed(_TABLES):
        if table == "ai_assistant_release_outbox_delivery":
            op.drop_index(
                "ix_ai_assistant_release_outbox_delivery_claim",
                table_name=table,
            )
        op.drop_table(table)
    op.execute("DROP FUNCTION assistant_release_guard_pointer()")
    op.execute("DROP FUNCTION assistant_release_validate_history()")
    op.execute("DROP FUNCTION assistant_release_validate_history_commit()")
    op.execute("DROP FUNCTION assistant_release_validate_outbox_event()")
    op.execute("DROP FUNCTION assistant_release_target_document(varchar,uuid,uuid,varchar,varchar)")
    op.execute("DROP FUNCTION assistant_release_canonical_jsonb(jsonb)")
    op.execute("DROP FUNCTION assistant_release_reject_mutation()")
