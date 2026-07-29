"""Persist semantic-classifier binding authority for Assistant Release v3.

Revision ID: 20260729_0019
Revises: 20260729_0018
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260729_0019"
down_revision: str | None = "20260729_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SHA256 = r"^[0-9a-f]{64}$"
_ENVIRONMENTS = "'development','test','staging','production'"
_STATES = "'active','revoked','superseded'"
_EVIDENCE_KINDS = (
    "'approval','automated_gate','static_safe_approval','promotion',"
    "'live_control','classifier_evaluation','classifier_approval'"
)
_LEGACY_EVIDENCE_KINDS = (
    "'approval','automated_gate','static_safe_approval','promotion','live_control'"
)


def upgrade() -> None:
    _extend_evidence_kinds()
    _create_binding_table()
    _create_binding_lifecycle_tables()
    _create_validation_guard()
    _create_lifecycle_guard()
    _create_lifecycle_audit()
    _create_delete_guard()
    _create_transition_function()


def _extend_evidence_kinds() -> None:
    op.drop_constraint(
        "ck_ai_trusted_release_evidence_kind",
        "ai_trusted_release_evidence",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ai_trusted_release_evidence_kind",
        "ai_trusted_release_evidence",
        f"evidence_kind IN ({_EVIDENCE_KINDS})",
    )


def _create_binding_table() -> None:
    op.create_table(
        "ai_semantic_classifier_binding",
        sa.Column("binding_id", sa.String(160), primary_key=True),
        sa.Column(
            "activation_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("activation_envelope_sha256", sa.String(64), nullable=False),
        sa.Column("assistant_profile", sa.String(160), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("classification_stack_sha256", sa.String(64), nullable=False),
        sa.Column("binding_core_sha256", sa.String(64), nullable=False),
        sa.Column("binding_envelope_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_document", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["activation_record_id"],
            ["ai_assistant_release_activation.id"],
            name="fk_ai_semantic_classifier_binding_activation",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "binding_envelope_sha256",
            name="uq_ai_semantic_classifier_binding_envelope",
        ),
        sa.CheckConstraint(
            "length(btrim(binding_id)) BETWEEN 1 AND 160",
            name="ck_ai_semantic_classifier_binding_identity",
        ),
        sa.CheckConstraint(
            f"environment IN ({_ENVIRONMENTS})",
            name="ck_ai_semantic_classifier_binding_environment",
        ),
        sa.CheckConstraint(
            f"state IN ({_STATES})",
            name="ck_ai_semantic_classifier_binding_state",
        ),
        sa.CheckConstraint(
            "expires_at > effective_at",
            name="ck_ai_semantic_classifier_binding_window",
        ),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_ai_semantic_classifier_binding_revision",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(canonical_document) = 'object'",
            name="ck_ai_semantic_classifier_binding_document",
        ),
        *(
            sa.CheckConstraint(
                f"{column} ~ '{_SHA256}'",
                name=f"ck_ai_semantic_classifier_binding_{suffix}",
            )
            for column, suffix in (
                ("activation_envelope_sha256", "activation_envelope_digest"),
                ("classification_stack_sha256", "stack_digest"),
                ("binding_core_sha256", "core_digest"),
                ("binding_envelope_sha256", "envelope_digest"),
            )
        ),
    )
    op.create_index(
        "uq_ai_semantic_classifier_binding_active_activation",
        "ai_semantic_classifier_binding",
        ["activation_record_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )


def _create_binding_lifecycle_tables() -> None:
    op.create_table(
        "ai_semantic_classifier_binding_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("event_ref", sa.String(255), nullable=False),
        sa.Column("binding_id", sa.String(160), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("from_revision", sa.BigInteger(), nullable=False),
        sa.Column("to_revision", sa.BigInteger(), nullable=False),
        sa.Column("actor_subject", sa.String(160), nullable=False),
        sa.Column("reason_code", sa.String(160), nullable=False),
        sa.Column("decision_evidence_ref", sa.String(255), nullable=False),
        sa.Column("decision_evidence_sha256", sa.String(64), nullable=False),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_document", postgresql.JSONB(), nullable=False),
        sa.Column("created_transaction_id", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["ai_semantic_classifier_binding.binding_id"],
            name="fk_ai_semantic_classifier_binding_history_binding",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "event_ref",
            name="uq_ai_semantic_classifier_binding_history_event",
        ),
        sa.UniqueConstraint(
            "binding_id",
            "to_revision",
            name="uq_ai_semantic_classifier_binding_history_revision",
        ),
        sa.CheckConstraint(
            "event_type IN ('revoked','superseded')",
            name="ck_ai_semantic_classifier_binding_history_type",
        ),
        sa.CheckConstraint(
            "from_revision > 0 AND to_revision = from_revision + 1",
            name="ck_ai_semantic_classifier_binding_history_revision",
        ),
        sa.CheckConstraint(
            "length(btrim(event_ref)) BETWEEN 5 AND 255 "
            "AND length(btrim(actor_subject)) BETWEEN 1 AND 160 "
            "AND length(btrim(reason_code)) BETWEEN 1 AND 160 "
            "AND length(btrim(decision_evidence_ref)) BETWEEN 5 AND 255",
            name="ck_ai_semantic_classifier_binding_history_identity",
        ),
        sa.CheckConstraint(
            f"event_sha256 ~ '{_SHA256}' AND decision_evidence_sha256 ~ '{_SHA256}'",
            name="ck_ai_semantic_classifier_binding_history_digest",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(canonical_document) = 'object'",
            name="ck_ai_semantic_classifier_binding_history_document",
        ),
    )
    op.create_table(
        "ai_semantic_classifier_binding_outbox_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "history_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("event_ref", sa.String(255), nullable=False),
        sa.Column("topic", sa.String(160), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["history_record_id"],
            ["ai_semantic_classifier_binding_history.id"],
            name="fk_ai_semantic_classifier_binding_outbox_history",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "history_record_id",
            name="uq_ai_semantic_classifier_binding_outbox_history",
        ),
        sa.UniqueConstraint(
            "event_ref",
            name="uq_ai_semantic_classifier_binding_outbox_event",
        ),
        sa.CheckConstraint(
            "topic = 'ai.semantic-classifier-binding.lifecycle.v1'",
            name="ck_ai_semantic_classifier_binding_outbox_topic",
        ),
        sa.CheckConstraint(
            f"payload_sha256 ~ '{_SHA256}'",
            name="ck_ai_semantic_classifier_binding_outbox_digest",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="ck_ai_semantic_classifier_binding_outbox_payload",
        ),
    )


def _create_validation_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION semantic_classifier_binding_validate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          activation ai_assistant_release_activation%ROWTYPE;
          expected_stack_sha256 text;
          expected_core_sha256 text;
          expected_envelope_sha256 text;
          evidence_found boolean;
          artifact_item jsonb;
          artifact_found boolean;
        BEGIN
          IF TG_OP = 'INSERT'
             AND (NEW.state <> 'active' OR NEW.revision <> 1) THEN
            RAISE EXCEPTION
              'semantic classifier binding must begin active at revision one'
              USING ERRCODE = '23514';
          END IF;

          IF NEW.canonical_document->>'schema_version' <> '1'
             OR NEW.canonical_document - ARRAY[
                  'schema_version',
                  'binding_id',
                  'target_activation',
                  'classifier_artifact',
                  'output_schema',
                  'routing_policy',
                  'classification_stack_sha256',
                  'evaluation_evidence',
                  'effective_at',
                  'expires_at',
                  'binding_core_sha256',
                  'approval_evidence',
                  'binding_envelope_sha256'
                ]::text[] <> '{}'::jsonb
             OR jsonb_typeof(
                  NEW.canonical_document->'target_activation'
                ) IS DISTINCT FROM 'object'
             OR jsonb_typeof(
                  NEW.canonical_document->'classifier_artifact'
                ) IS DISTINCT FROM 'object'
             OR jsonb_typeof(
                  NEW.canonical_document->'output_schema'
                ) IS DISTINCT FROM 'object'
             OR jsonb_typeof(
                  NEW.canonical_document->'routing_policy'
                ) IS DISTINCT FROM 'object'
             OR jsonb_typeof(
                  NEW.canonical_document->'evaluation_evidence'
                ) IS DISTINCT FROM 'object'
             OR jsonb_typeof(
                  NEW.canonical_document->'approval_evidence'
                ) IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION
              'semantic classifier binding canonical contract mismatch'
              USING ERRCODE = '23514';
          END IF;

          SELECT *
          INTO activation
          FROM ai_assistant_release_activation
          WHERE id = NEW.activation_record_id
          FOR SHARE;
          IF NOT FOUND
             OR NEW.canonical_document->'target_activation'->>'activation_id'
                  IS DISTINCT FROM activation.activation_id
             OR NEW.canonical_document->'target_activation'
                    ->>'activation_envelope_sha256'
                  IS DISTINCT FROM activation.activation_envelope_sha256
             OR NEW.canonical_document->'target_activation'->>'assistant_profile'
                  IS DISTINCT FROM activation.assistant_profile
             OR NEW.canonical_document->'target_activation'->>'environment'
                  IS DISTINCT FROM activation.environment
             OR NEW.activation_envelope_sha256
                  IS DISTINCT FROM activation.activation_envelope_sha256
             OR NEW.assistant_profile IS DISTINCT FROM activation.assistant_profile
             OR NEW.environment IS DISTINCT FROM activation.environment
             OR NEW.effective_at < activation.effective_at
             OR NEW.expires_at > activation.expires_at THEN
            RAISE EXCEPTION
              'semantic classifier binding target activation mismatch'
              USING ERRCODE = '23514';
          END IF;

          IF NEW.canonical_document->>'binding_id'
                IS DISTINCT FROM NEW.binding_id
             OR (NEW.canonical_document->>'effective_at')::timestamptz
                IS DISTINCT FROM NEW.effective_at
             OR (NEW.canonical_document->>'expires_at')::timestamptz
                IS DISTINCT FROM NEW.expires_at
             OR NEW.canonical_document->>'classification_stack_sha256'
                IS DISTINCT FROM NEW.classification_stack_sha256
             OR NEW.canonical_document->>'binding_core_sha256'
                IS DISTINCT FROM NEW.binding_core_sha256
             OR NEW.canonical_document->>'binding_envelope_sha256'
                IS DISTINCT FROM NEW.binding_envelope_sha256 THEN
            RAISE EXCEPTION
              'semantic classifier binding document projection mismatch'
              USING ERRCODE = '23514';
          END IF;

          expected_stack_sha256 := encode(
            digest(
              convert_to(
                assistant_release_canonical_jsonb(
                  jsonb_build_object(
                    'classifier_artifact',
                    NEW.canonical_document->'classifier_artifact',
                    'output_schema',
                    NEW.canonical_document->'output_schema',
                    'routing_policy',
                    NEW.canonical_document->'routing_policy'
                  )
                ),
                'UTF8'
              ),
              'sha256'
            ),
            'hex'
          );
          IF NEW.classification_stack_sha256
                IS DISTINCT FROM expected_stack_sha256
             OR NEW.canonical_document->'evaluation_evidence'
                    ->>'target_classification_stack_sha256'
                IS DISTINCT FROM expected_stack_sha256 THEN
            RAISE EXCEPTION
              'semantic classifier classification stack digest mismatch'
              USING ERRCODE = '23514';
          END IF;

          expected_core_sha256 := encode(
            digest(
              convert_to(
                assistant_release_canonical_jsonb(
                  jsonb_build_object(
                    'schema_version',
                    NEW.canonical_document->'schema_version',
                    'binding_id',
                    NEW.canonical_document->'binding_id',
                    'target_activation',
                    NEW.canonical_document->'target_activation',
                    'classification_stack_sha256',
                    NEW.canonical_document->'classification_stack_sha256',
                    'evaluation_evidence',
                    NEW.canonical_document->'evaluation_evidence',
                    'effective_at',
                    NEW.canonical_document->'effective_at',
                    'expires_at',
                    NEW.canonical_document->'expires_at'
                  )
                ),
                'UTF8'
              ),
              'sha256'
            ),
            'hex'
          );
          IF NEW.binding_core_sha256 IS DISTINCT FROM expected_core_sha256
             OR NEW.canonical_document->'approval_evidence'
                    ->>'target_binding_core_sha256'
                IS DISTINCT FROM expected_core_sha256 THEN
            RAISE EXCEPTION
              'semantic classifier binding core digest mismatch'
              USING ERRCODE = '23514';
          END IF;

          expected_envelope_sha256 := encode(
            digest(
              convert_to(
                assistant_release_canonical_jsonb(
                  jsonb_build_object(
                    'approval_evidence',
                    NEW.canonical_document->'approval_evidence',
                    'binding_core_sha256',
                    NEW.canonical_document->'binding_core_sha256'
                  )
                ),
                'UTF8'
              ),
              'sha256'
            ),
            'hex'
          );
          IF NEW.binding_envelope_sha256
                IS DISTINCT FROM expected_envelope_sha256 THEN
            RAISE EXCEPTION
              'semantic classifier binding envelope digest mismatch'
              USING ERRCODE = '23514';
          END IF;

          IF (NEW.canonical_document->'evaluation_evidence'->>'valid_until')
                ::timestamptz < NEW.expires_at THEN
            RAISE EXCEPTION
              'semantic classifier evaluation expires before binding'
              USING ERRCODE = '23514';
          END IF;

          -- Revocation and supersession remain possible after a dependency is
          -- revoked or expires. Runtime freshness is checked independently;
          -- immutable trust admission is required only when binding is born.
          IF TG_OP = 'UPDATE' THEN
            RETURN NEW;
          END IF;

          SELECT true
          INTO evidence_found
          FROM ai_trusted_release_evidence
          WHERE evidence_ref =
                  NEW.canonical_document->'evaluation_evidence'->>'ref'
            AND evidence_kind = 'classifier_evaluation'
            AND evidence_sha256 =
                  NEW.canonical_document->'evaluation_evidence'->>'sha256'
            AND target_sha256 = NEW.classification_stack_sha256
            AND assistant_profile = NEW.assistant_profile
            AND environment = NEW.environment
            AND state = 'active'
            AND effective_at <= NEW.effective_at
            AND (expires_at IS NULL OR expires_at >= NEW.expires_at)
          FOR SHARE;
          IF evidence_found IS NOT TRUE THEN
            RAISE EXCEPTION
              'semantic classifier evaluation evidence is not trusted'
              USING ERRCODE = '23514';
          END IF;

          evidence_found := NULL;
          SELECT true
          INTO evidence_found
          FROM ai_trusted_release_evidence
          WHERE evidence_ref =
                  NEW.canonical_document->'approval_evidence'->>'ref'
            AND evidence_kind = 'classifier_approval'
            AND evidence_sha256 =
                  NEW.canonical_document->'approval_evidence'->>'sha256'
            AND target_sha256 = NEW.binding_core_sha256
            AND assistant_profile = NEW.assistant_profile
            AND environment = NEW.environment
            AND state = 'active'
            AND effective_at <= NEW.effective_at
            AND (expires_at IS NULL OR expires_at >= NEW.expires_at)
          FOR SHARE;
          IF evidence_found IS NOT TRUE THEN
            RAISE EXCEPTION
              'semantic classifier approval evidence is not trusted'
              USING ERRCODE = '23514';
          END IF;

          FOR artifact_item IN
            SELECT value
            FROM jsonb_array_elements(
              jsonb_build_array(
                NEW.canonical_document->'classifier_artifact',
                NEW.canonical_document->'output_schema',
                NEW.canonical_document->'routing_policy'
              )
            )
          LOOP
            artifact_found := NULL;
            SELECT true
            INTO artifact_found
            FROM ai_trusted_release_artifact
            WHERE artifact_ref = artifact_item->>'ref'
              AND artifact_sha256 = artifact_item->>'sha256'
              AND state = 'active'
              AND effective_at <= NEW.effective_at
              AND (expires_at IS NULL OR expires_at >= NEW.expires_at)
            FOR SHARE;
            IF artifact_found IS NOT TRUE THEN
              RAISE EXCEPTION
                'semantic classifier artifact is not trusted'
                USING ERRCODE = '23514';
            END IF;
          END LOOP;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_semantic_classifier_binding_validate
        BEFORE INSERT OR UPDATE
        ON ai_semantic_classifier_binding
        FOR EACH ROW
        EXECUTE FUNCTION semantic_classifier_binding_validate();
        """
    )


def _create_lifecycle_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION semantic_classifier_binding_guard_lifecycle()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          decision_evidence_found boolean;
        BEGIN
          IF btrim(COALESCE(
               current_setting('vfbiz.semantic_classifier_actor', true),
               ''
             )) = ''
             OR btrim(COALESCE(
               current_setting('vfbiz.semantic_classifier_reason', true),
               ''
             )) = ''
             OR btrim(COALESCE(
               current_setting('vfbiz.semantic_classifier_event_ref', true),
               ''
             )) = ''
             OR btrim(COALESCE(
               current_setting(
                 'vfbiz.semantic_classifier_decision_evidence_ref',
                 true
               ),
               ''
             )) = ''
             OR COALESCE(
               current_setting(
                 'vfbiz.semantic_classifier_decision_evidence_sha256',
                 true
               ),
               ''
             ) !~ '^[0-9a-f]{64}$' THEN
            RAISE EXCEPTION
              'semantic classifier binding transition metadata is required'
              USING ERRCODE = '23514';
          END IF;
          SELECT true
          INTO decision_evidence_found
          FROM ai_trusted_release_evidence
          WHERE evidence_ref = current_setting(
                  'vfbiz.semantic_classifier_decision_evidence_ref',
                  true
                )
            AND evidence_kind = 'live_control'
            AND evidence_sha256 = current_setting(
                  'vfbiz.semantic_classifier_decision_evidence_sha256',
                  true
                )
            AND target_sha256 = OLD.binding_envelope_sha256
            AND assistant_profile = OLD.assistant_profile
            AND environment = OLD.environment
            AND state = 'active'
            AND effective_at <= clock_timestamp()
            AND (expires_at IS NULL OR expires_at > clock_timestamp())
          FOR SHARE;
          IF decision_evidence_found IS NOT TRUE THEN
            RAISE EXCEPTION
              'semantic classifier binding decision evidence is not trusted'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.binding_id <> OLD.binding_id
             OR NEW.activation_record_id <> OLD.activation_record_id
             OR NEW.activation_envelope_sha256
                  <> OLD.activation_envelope_sha256
             OR NEW.assistant_profile <> OLD.assistant_profile
             OR NEW.environment <> OLD.environment
             OR NEW.classification_stack_sha256
                  <> OLD.classification_stack_sha256
             OR NEW.binding_core_sha256 <> OLD.binding_core_sha256
             OR NEW.binding_envelope_sha256 <> OLD.binding_envelope_sha256
             OR NEW.canonical_document <> OLD.canonical_document
             OR NEW.effective_at <> OLD.effective_at
             OR NEW.expires_at <> OLD.expires_at
             OR NEW.created_at <> OLD.created_at THEN
            RAISE EXCEPTION
              'semantic classifier binding identity is immutable'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.revision <> OLD.revision + 1 THEN
            RAISE EXCEPTION
              'semantic classifier binding revision must advance exactly once'
              USING ERRCODE = '23514';
          END IF;
          IF OLD.state <> 'active'
             OR NEW.state NOT IN ('revoked', 'superseded') THEN
            RAISE EXCEPTION
              'semantic classifier binding transition is invalid'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.state = 'superseded'
             AND current_setting(
                   'vfbiz.semantic_classifier_allow_supersede',
                   true
                 ) IS DISTINCT FROM 'true' THEN
            RAISE EXCEPTION
              'semantic classifier supersede requires atomic replacement'
              USING ERRCODE = '23514';
          END IF;
          NEW.updated_at := clock_timestamp();
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_semantic_classifier_binding_lifecycle
        BEFORE UPDATE
        ON ai_semantic_classifier_binding
        FOR EACH ROW
        EXECUTE FUNCTION semantic_classifier_binding_guard_lifecycle();
        """
    )


def _create_lifecycle_audit() -> None:
    op.execute(
        """
        CREATE FUNCTION semantic_classifier_binding_write_lifecycle()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          history_id uuid := gen_random_uuid();
          occurred timestamptz := clock_timestamp();
          history_document jsonb;
          history_sha256 text;
          outbox_payload jsonb;
          outbox_sha256 text;
          event_ref text :=
            current_setting('vfbiz.semantic_classifier_event_ref', true);
          actor text :=
            current_setting('vfbiz.semantic_classifier_actor', true);
          reason text :=
            current_setting('vfbiz.semantic_classifier_reason', true);
          decision_ref text :=
            current_setting(
              'vfbiz.semantic_classifier_decision_evidence_ref',
              true
            );
          decision_sha256 text :=
            current_setting(
              'vfbiz.semantic_classifier_decision_evidence_sha256',
              true
            );
        BEGIN
          history_document := jsonb_build_object(
            'event_ref', event_ref,
            'binding_id', NEW.binding_id,
            'event_type', NEW.state,
            'from_revision', OLD.revision,
            'to_revision', NEW.revision,
            'actor_subject', actor,
            'reason_code', reason,
            'decision_evidence_ref', decision_ref,
            'decision_evidence_sha256', decision_sha256,
            'binding_envelope_sha256', NEW.binding_envelope_sha256,
            'occurred_at', to_jsonb(occurred)
          );
          history_sha256 := encode(
            digest(
              convert_to(
                assistant_release_canonical_jsonb(history_document),
                'UTF8'
              ),
              'sha256'
            ),
            'hex'
          );
          INSERT INTO ai_semantic_classifier_binding_history (
            id, event_ref, binding_id, event_type, from_revision, to_revision,
            actor_subject, reason_code, decision_evidence_ref,
            decision_evidence_sha256, event_sha256, canonical_document,
            created_transaction_id, occurred_at
          ) VALUES (
            history_id, event_ref, NEW.binding_id, NEW.state,
            OLD.revision, NEW.revision, actor, reason, decision_ref,
            decision_sha256, history_sha256, history_document,
            txid_current(), occurred
          );

          outbox_payload := jsonb_build_object(
            'schema_version', 1,
            'event_ref', event_ref,
            'history_record_id', history_id,
            'binding_id', NEW.binding_id,
            'event_type', NEW.state,
            'binding_revision', NEW.revision,
            'binding_envelope_sha256', NEW.binding_envelope_sha256,
            'history_sha256', history_sha256,
            'occurred_at', to_jsonb(occurred)
          );
          outbox_sha256 := encode(
            digest(
              convert_to(
                assistant_release_canonical_jsonb(outbox_payload),
                'UTF8'
              ),
              'sha256'
            ),
            'hex'
          );
          INSERT INTO ai_semantic_classifier_binding_outbox_event (
            history_record_id, event_ref, topic, payload_sha256, payload
          ) VALUES (
            history_id,
            event_ref,
            'ai.semantic-classifier-binding.lifecycle.v1',
            outbox_sha256,
            outbox_payload
          );
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_semantic_classifier_binding_lifecycle_audit
        AFTER UPDATE
        ON ai_semantic_classifier_binding
        FOR EACH ROW
        EXECUTE FUNCTION semantic_classifier_binding_write_lifecycle();
        """
    )
    op.execute(
        """
        CREATE FUNCTION semantic_classifier_binding_reject_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION
            'semantic classifier binding audit mutation is forbidden'
            USING ERRCODE = '23514';
        END;
        $$;
        """
    )
    for table in (
        "ai_semantic_classifier_binding_history",
        "ai_semantic_classifier_binding_outbox_event",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE
            ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION semantic_classifier_binding_reject_audit_mutation();
            """
        )
    op.execute(
        """
        CREATE FUNCTION semantic_classifier_binding_validate_supersede_commit()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          replacement_found boolean;
        BEGIN
          IF NEW.event_type <> 'superseded' THEN
            RETURN NEW;
          END IF;
          SELECT true
          INTO replacement_found
          FROM ai_semantic_classifier_binding AS replacement
          JOIN ai_semantic_classifier_binding AS superseded
            ON superseded.binding_id = NEW.binding_id
          WHERE replacement.activation_record_id =
                  superseded.activation_record_id
            AND replacement.binding_id <> superseded.binding_id
            AND replacement.state = 'active'
            AND replacement.effective_at <= clock_timestamp()
            AND replacement.expires_at > clock_timestamp()
          LIMIT 1;
          IF replacement_found IS NOT TRUE THEN
            RAISE EXCEPTION
              'semantic classifier supersede requires active replacement'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
          trg_ai_semantic_classifier_binding_supersede_commit
        AFTER INSERT
        ON ai_semantic_classifier_binding_history
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION
          semantic_classifier_binding_validate_supersede_commit();
        """
    )


def _create_delete_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION semantic_classifier_binding_reject_delete()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION
            'semantic classifier binding delete is forbidden'
            USING ERRCODE = '23514';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_semantic_classifier_binding_reject_delete
        BEFORE DELETE
        ON ai_semantic_classifier_binding
        FOR EACH ROW
        EXECUTE FUNCTION semantic_classifier_binding_reject_delete();
        """
    )


def _create_transition_function() -> None:
    op.execute(
        """
        CREATE FUNCTION semantic_classifier_binding_transition(
          requested_binding_id varchar,
          expected_revision bigint,
          target_state varchar,
          actor_subject varchar,
          reason_code varchar,
          requested_event_ref varchar,
          requested_decision_evidence_ref varchar,
          requested_decision_evidence_sha256 varchar
        )
        RETURNS ai_semantic_classifier_binding
        LANGUAGE plpgsql
        AS $$
        DECLARE
          binding ai_semantic_classifier_binding%ROWTYPE;
          existing_history ai_semantic_classifier_binding_history%ROWTYPE;
          evidence_found boolean;
          transitioned ai_semantic_classifier_binding%ROWTYPE;
        BEGIN
          SELECT *
          INTO binding
          FROM ai_semantic_classifier_binding
          WHERE binding_id = requested_binding_id
          FOR UPDATE;
          IF NOT FOUND THEN
            RAISE EXCEPTION
              'semantic classifier binding does not exist'
              USING ERRCODE = 'P0002';
          END IF;

          SELECT *
          INTO existing_history
          FROM ai_semantic_classifier_binding_history
          WHERE ai_semantic_classifier_binding_history.event_ref =
                requested_event_ref;
          IF FOUND THEN
            IF existing_history.binding_id = requested_binding_id
               AND existing_history.event_type = target_state
               AND existing_history.from_revision = expected_revision
               AND existing_history.actor_subject = actor_subject
               AND existing_history.reason_code = reason_code
               AND existing_history.decision_evidence_ref =
                    requested_decision_evidence_ref
               AND existing_history.decision_evidence_sha256 =
                    requested_decision_evidence_sha256 THEN
              RETURN binding;
            END IF;
            RAISE EXCEPTION
              'semantic classifier binding event replay conflicts'
              USING ERRCODE = '23505';
          END IF;

          IF target_state NOT IN ('revoked', 'superseded')
             OR binding.state <> 'active'
             OR binding.revision <> expected_revision THEN
            RAISE EXCEPTION
              'semantic classifier binding transition fence mismatch'
              USING ERRCODE = '40001';
          END IF;

          SELECT true
          INTO evidence_found
          FROM ai_trusted_release_evidence
          WHERE evidence_ref =
                  requested_decision_evidence_ref
            AND evidence_kind = 'live_control'
            AND evidence_sha256 =
                  requested_decision_evidence_sha256
            AND target_sha256 = binding.binding_envelope_sha256
            AND assistant_profile = binding.assistant_profile
            AND environment = binding.environment
            AND state = 'active'
            AND effective_at <= clock_timestamp()
            AND (expires_at IS NULL OR expires_at > clock_timestamp())
          FOR SHARE;
          IF evidence_found IS NOT TRUE THEN
            RAISE EXCEPTION
              'semantic classifier binding decision evidence is not trusted'
              USING ERRCODE = '23514';
          END IF;

          PERFORM set_config(
            'vfbiz.semantic_classifier_actor',
            actor_subject,
            true
          );
          PERFORM set_config(
            'vfbiz.semantic_classifier_reason',
            reason_code,
            true
          );
          PERFORM set_config(
            'vfbiz.semantic_classifier_event_ref',
            requested_event_ref,
            true
          );
          PERFORM set_config(
            'vfbiz.semantic_classifier_decision_evidence_ref',
            requested_decision_evidence_ref,
            true
          );
          PERFORM set_config(
            'vfbiz.semantic_classifier_decision_evidence_sha256',
            requested_decision_evidence_sha256,
            true
          );

          UPDATE ai_semantic_classifier_binding
          SET state = target_state,
              revision = revision + 1
          WHERE binding_id = requested_binding_id
            AND state = 'active'
            AND revision = expected_revision
          RETURNING *
          INTO transitioned;
          IF NOT FOUND THEN
            RAISE EXCEPTION
              'semantic classifier binding transition lost its fence'
              USING ERRCODE = '40001';
          END IF;
          RETURN transitioned;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION semantic_classifier_binding_supersede(
          requested_binding_id varchar,
          expected_revision bigint,
          replacement_activation_record_id uuid,
          replacement_document jsonb,
          actor_subject varchar,
          reason_code varchar,
          event_ref varchar,
          decision_evidence_ref varchar,
          decision_evidence_sha256 varchar
        )
        RETURNS ai_semantic_classifier_binding
        LANGUAGE plpgsql
        AS $$
        DECLARE
          current_binding ai_semantic_classifier_binding%ROWTYPE;
          replacement ai_semantic_classifier_binding%ROWTYPE;
        BEGIN
          SELECT *
          INTO current_binding
          FROM ai_semantic_classifier_binding
          WHERE binding_id = requested_binding_id
          FOR UPDATE;
          IF NOT FOUND
             OR replacement_activation_record_id
                  <> current_binding.activation_record_id THEN
            RAISE EXCEPTION
              'semantic classifier replacement activation mismatch'
              USING ERRCODE = '23514';
          END IF;

          PERFORM set_config(
            'vfbiz.semantic_classifier_allow_supersede',
            'true',
            true
          );
          PERFORM semantic_classifier_binding_transition(
            requested_binding_id,
            expected_revision,
            'superseded',
            actor_subject,
            reason_code,
            event_ref,
            decision_evidence_ref,
            decision_evidence_sha256
          );
          PERFORM set_config(
            'vfbiz.semantic_classifier_allow_supersede',
            'false',
            true
          );

          SELECT *
          INTO replacement
          FROM ai_semantic_classifier_binding
          WHERE binding_id = replacement_document->>'binding_id';
          IF FOUND THEN
            IF replacement.activation_record_id =
                  replacement_activation_record_id
               AND replacement.canonical_document = replacement_document THEN
              RETURN replacement;
            END IF;
            RAISE EXCEPTION
              'semantic classifier replacement replay conflicts'
              USING ERRCODE = '23505';
          END IF;

          INSERT INTO ai_semantic_classifier_binding (
            binding_id, activation_record_id, activation_envelope_sha256,
            assistant_profile, environment, classification_stack_sha256,
            binding_core_sha256, binding_envelope_sha256, canonical_document,
            state, effective_at, expires_at, revision
          ) VALUES (
            replacement_document->>'binding_id',
            replacement_activation_record_id,
            replacement_document->'target_activation'
              ->>'activation_envelope_sha256',
            replacement_document->'target_activation'->>'assistant_profile',
            replacement_document->'target_activation'->>'environment',
            replacement_document->>'classification_stack_sha256',
            replacement_document->>'binding_core_sha256',
            replacement_document->>'binding_envelope_sha256',
            replacement_document,
            'active',
            (replacement_document->>'effective_at')::timestamptz,
            (replacement_document->>'expires_at')::timestamptz,
            1
          )
          RETURNING *
          INTO replacement;
          RETURN replacement;
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
            SELECT 1 FROM ai_semantic_classifier_binding
          ) OR EXISTS (
            SELECT 1 FROM ai_semantic_classifier_binding_history
          ) OR EXISTS (
            SELECT 1 FROM ai_semantic_classifier_binding_outbox_event
          ) OR EXISTS (
            SELECT 1
            FROM ai_trusted_release_evidence
            WHERE evidence_kind IN (
              'classifier_evaluation',
              'classifier_approval'
            )
          ) THEN
            RAISE EXCEPTION
              'semantic classifier binding downgrade refused: persisted rows exist'
              USING ERRCODE = '55000';
          END IF;
        END;
        $$;
        """
    )
    op.execute(
        "DROP FUNCTION semantic_classifier_binding_supersede("
        "varchar,bigint,uuid,jsonb,varchar,varchar,varchar,varchar,varchar)"
    )
    op.execute(
        "DROP FUNCTION semantic_classifier_binding_transition("
        "varchar,bigint,varchar,varchar,varchar,varchar,varchar,varchar)"
    )
    op.execute(
        "DROP TRIGGER trg_ai_semantic_classifier_binding_reject_delete "
        "ON ai_semantic_classifier_binding"
    )
    op.execute(
        "DROP TRIGGER trg_ai_semantic_classifier_binding_lifecycle_audit "
        "ON ai_semantic_classifier_binding"
    )
    op.execute(
        "DROP TRIGGER trg_ai_semantic_classifier_binding_lifecycle "
        "ON ai_semantic_classifier_binding"
    )
    op.execute(
        "DROP TRIGGER trg_ai_semantic_classifier_binding_validate ON ai_semantic_classifier_binding"
    )
    op.execute("DROP FUNCTION semantic_classifier_binding_reject_delete()")
    op.execute("DROP FUNCTION semantic_classifier_binding_write_lifecycle()")
    op.execute("DROP FUNCTION semantic_classifier_binding_guard_lifecycle()")
    op.execute("DROP FUNCTION semantic_classifier_binding_validate()")
    op.drop_table("ai_semantic_classifier_binding_outbox_event")
    op.drop_table("ai_semantic_classifier_binding_history")
    op.execute("DROP FUNCTION semantic_classifier_binding_validate_supersede_commit()")
    op.execute("DROP FUNCTION semantic_classifier_binding_reject_audit_mutation()")
    op.drop_index(
        "uq_ai_semantic_classifier_binding_active_activation",
        table_name="ai_semantic_classifier_binding",
    )
    op.drop_table("ai_semantic_classifier_binding")
    op.drop_constraint(
        "ck_ai_trusted_release_evidence_kind",
        "ai_trusted_release_evidence",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ai_trusted_release_evidence_kind",
        "ai_trusted_release_evidence",
        f"evidence_kind IN ({_LEGACY_EVIDENCE_KINDS})",
    )
