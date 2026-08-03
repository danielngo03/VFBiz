"""Make sealed evaluation evidence the decision-ready authority.

Revision ID: 20260730_0020
Revises: 20260729_0019
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260730_0020"
down_revision: str | None = "20260729_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SHA256 = r"^sha256:[0-9a-f]{64}$"


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM ai_evaluation_run
            WHERE run_key IS NOT NULL
              AND (
                status = 'decision_ready'
                OR evidence_bundle_digest IS NOT NULL
              )
          ) THEN
            RAISE EXCEPTION
              'legacy governed evaluation evidence must be invalidated and rerun'
              USING ERRCODE = '55000';
          END IF;
        END;
        $$;
        """
    )

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        ALTER TABLE ai_evaluation_run
          DROP CONSTRAINT ck_ai_evaluation_run_terminal_evidence
        """
    )
    op.execute(
        """
        ALTER TABLE ai_evaluation_run
          ADD CONSTRAINT ck_ai_evaluation_run_terminal_evidence
          CHECK (
            run_key IS NULL
            OR (
              (status = 'decision_ready')
              = (evidence_bundle_digest IS NOT NULL)
              AND (
                evidence_bundle_digest IS NULL
                OR evidence_bundle_digest ~ '^sha256:[a-f0-9]{64}$'
              )
            )
          );
        """
    )
    _create_case_result_table()
    _create_case_task_table()
    _create_evidence_bundle_table()
    _create_case_result_guard()
    _create_case_task_cancellation()
    _create_evidence_bundle_guard()
    _create_decision_ready_guard()
    _create_atomic_seal_guard()


def _create_case_result_table() -> None:
    op.create_table(
        "ai_evaluation_case_result",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("run_key", sa.String(160), nullable=False),
        sa.Column("case_key", sa.String(200), nullable=False),
        sa.Column("case_digest", sa.String(71), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("output_digest", sa.String(71), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("usage", postgresql.JSONB(), nullable=False),
        sa.Column("sanitized_trace_ref", sa.String(500), nullable=True),
        sa.Column("grader_outputs", postgresql.JSONB(), nullable=False),
        sa.Column("validity_flags", postgresql.JSONB(), nullable=False),
        sa.Column("result_digest", sa.String(71), nullable=False),
        sa.Column("canonical_payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_key"],
            ["ai_evaluation_run.run_key"],
            name="fk_ai_evaluation_case_result_run",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "run_key",
            "case_key",
            "attempt",
            name="uq_ai_evaluation_case_result_attempt",
        ),
        sa.CheckConstraint(
            f"case_digest ~ '{_SHA256}' AND result_digest ~ '{_SHA256}' "
            f"AND (output_digest IS NULL OR output_digest ~ '{_SHA256}')",
            name="ck_ai_evaluation_case_result_digests",
        ),
        sa.CheckConstraint(
            "attempt BETWEEN 1 AND 3 AND latency_ms >= 0",
            name="ck_ai_evaluation_case_result_bounds",
        ),
        sa.CheckConstraint(
            "status IN ('valid','invalid','failed','cancelled')",
            name="ck_ai_evaluation_case_result_status",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(usage) = 'object' "
            "AND jsonb_typeof(grader_outputs) = 'array' "
            "AND jsonb_typeof(validity_flags) = 'array'",
            name="ck_ai_evaluation_case_result_documents",
        ),
    )
    op.create_index(
        "ix_ai_evaluation_case_result_latest",
        "ai_evaluation_case_result",
        ["run_key", "case_key", "attempt"],
    )


def _create_evidence_bundle_table() -> None:
    op.create_table(
        "ai_evaluation_evidence_bundle",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("run_key", sa.String(160), nullable=False),
        sa.Column("plan_digest", sa.String(71), nullable=False),
        sa.Column("bundle_digest", sa.String(71), nullable=False),
        sa.Column("case_results_digest", sa.String(71), nullable=False),
        sa.Column("run_result_digest", sa.String(71), nullable=False),
        sa.Column("authority_class", sa.String(40), nullable=False),
        sa.Column("recommendation", sa.String(40), nullable=False),
        sa.Column("sealed_from_row_version", sa.Integer(), nullable=False),
        sa.Column("suite_snapshot_payload", sa.Text(), nullable=False),
        sa.Column("baseline_policy_payload", sa.Text(), nullable=False),
        sa.Column("canonical_document", postgresql.JSONB(), nullable=False),
        sa.Column("canonical_payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_key"],
            ["ai_evaluation_run.run_key"],
            name="fk_ai_evaluation_evidence_bundle_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "run_key",
            name="uq_ai_evaluation_evidence_bundle_run",
        ),
        sa.UniqueConstraint(
            "bundle_digest",
            name="uq_ai_evaluation_evidence_bundle_digest",
        ),
        sa.UniqueConstraint(
            "run_key",
            "bundle_digest",
            "plan_digest",
            name="uq_ai_evaluation_evidence_bundle_binding",
        ),
        sa.CheckConstraint(
            f"plan_digest ~ '{_SHA256}' "
            f"AND bundle_digest ~ '{_SHA256}' "
            f"AND case_results_digest ~ '{_SHA256}' "
            f"AND run_result_digest ~ '{_SHA256}'",
            name="ck_ai_evaluation_evidence_bundle_digests",
        ),
        sa.CheckConstraint(
            "authority_class IN ('vinfast-acceptance','public-diagnostic')",
            name="ck_ai_evaluation_evidence_bundle_authority",
        ),
        sa.CheckConstraint(
            "recommendation IN ('recommend','reject','needs-human-decision')",
            name="ck_ai_evaluation_evidence_bundle_recommendation",
        ),
        sa.CheckConstraint(
            "sealed_from_row_version >= 0",
            name="ck_ai_evaluation_evidence_bundle_version",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(canonical_document) = 'object'",
            name="ck_ai_evaluation_evidence_bundle_document",
        ),
    )
    op.create_foreign_key(
        "fk_ai_evaluation_run_evidence_binding",
        "ai_evaluation_run",
        "ai_evaluation_evidence_bundle",
        ["run_key", "evidence_bundle_digest", "plan_digest"],
        ["run_key", "bundle_digest", "plan_digest"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )


def _create_case_task_table() -> None:
    op.create_table(
        "ai_evaluation_case_task",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("run_key", sa.String(160), nullable=False),
        sa.Column("case_key", sa.String(200), nullable=False),
        sa.Column("case_digest", sa.String(71), nullable=False),
        sa.Column("suite_digest", sa.String(71), nullable=False),
        sa.Column("shard_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(160), nullable=True),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_key"],
            ["ai_evaluation_run.run_key"],
            name="fk_ai_evaluation_case_task_run",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "run_key",
            "case_key",
            name="uq_ai_evaluation_case_task_case",
        ),
        sa.CheckConstraint(
            f"case_digest ~ '{_SHA256}' AND suite_digest ~ '{_SHA256}'",
            name="ck_ai_evaluation_case_task_digests",
        ),
        sa.CheckConstraint(
            "shard_index >= 0 AND attempt_count BETWEEN 0 AND 3 "
            "AND max_attempts BETWEEN 1 AND 3 "
            "AND attempt_count <= max_attempts",
            name="ck_ai_evaluation_case_task_bounds",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_ai_evaluation_case_task_status",
        ),
        sa.CheckConstraint(
            """
            (
              status = 'running'
              AND lease_owner IS NOT NULL
              AND lease_token IS NOT NULL
              AND lease_expires_at IS NOT NULL
              AND completed_at IS NULL
            )
            OR (
              status <> 'running'
              AND lease_owner IS NULL
              AND lease_token IS NULL
              AND lease_expires_at IS NULL
              AND (status = 'completed') = (completed_at IS NOT NULL)
            )
            """,
            name="ck_ai_evaluation_case_task_lease",
        ),
    )
    op.create_index(
        "ix_ai_evaluation_case_task_claim",
        "ai_evaluation_case_task",
        ["run_key", "status", "shard_index", "lease_expires_at"],
    )


def _create_case_result_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION evaluation_case_result_validate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          run_status text;
          expected_document jsonb;
          matching_task boolean;
          total_input_tokens bigint;
          total_output_tokens bigint;
          total_duration_seconds numeric;
          total_cost_usd numeric;
        BEGIN
          SELECT status
          INTO run_status
          FROM ai_evaluation_run
          WHERE run_key = NEW.run_key
          FOR UPDATE;
          IF run_status IS NULL THEN
            RAISE EXCEPTION 'evaluation case result requires governed run'
              USING ERRCODE = '23503';
          END IF;
          IF run_status NOT IN ('running','grading') THEN
            RAISE EXCEPTION
              'evaluation case results are closed outside running/grading'
              USING ERRCODE = '23514';
          END IF;
          SELECT true
          INTO matching_task
          FROM ai_evaluation_case_task
          WHERE run_key = NEW.run_key
            AND case_key = NEW.case_key
            AND case_digest = NEW.case_digest
            AND status = 'running'
            AND attempt_count = NEW.attempt
            AND lease_expires_at > clock_timestamp()
          LIMIT 1;
          IF matching_task IS NOT TRUE THEN
            RAISE EXCEPTION
              'evaluation case result requires active matching lease'
              USING ERRCODE = '23514';
          END IF;

          WITH latest AS (
            SELECT DISTINCT ON (case_key)
              case_key, usage, latency_ms
            FROM ai_evaluation_case_result
            WHERE run_key = NEW.run_key
              AND case_key <> NEW.case_key
            ORDER BY case_key, attempt DESC
          )
          SELECT
            coalesce(sum((usage ->> 'input_tokens')::bigint), 0)
              + (NEW.usage ->> 'input_tokens')::bigint,
            coalesce(sum((usage ->> 'output_tokens')::bigint), 0)
              + (NEW.usage ->> 'output_tokens')::bigint,
            coalesce(sum(latency_ms)::numeric / 1000, 0)
              + NEW.latency_ms::numeric / 1000,
            coalesce(sum((usage ->> 'cost_usd')::numeric), 0)
              + (NEW.usage ->> 'cost_usd')::numeric
          INTO
            total_input_tokens,
            total_output_tokens,
            total_duration_seconds,
            total_cost_usd
          FROM latest;
          IF total_input_tokens
                > (
                  SELECT (plan_document #>>
                    '{budgets,maxInputTokens}')::bigint
                  FROM ai_evaluation_run WHERE run_key = NEW.run_key
                )
             OR total_output_tokens
                > (
                  SELECT (plan_document #>>
                    '{budgets,maxOutputTokens}')::bigint
                  FROM ai_evaluation_run WHERE run_key = NEW.run_key
                )
             OR total_duration_seconds
                > (
                  SELECT (plan_document #>>
                    '{budgets,maxDurationSeconds}')::numeric
                  FROM ai_evaluation_run WHERE run_key = NEW.run_key
                )
             OR total_cost_usd
                > (
                  SELECT (plan_document #>>
                    '{budgets,maxCostUsd}')::numeric
                  FROM ai_evaluation_run WHERE run_key = NEW.run_key
                ) THEN
            RAISE EXCEPTION 'evaluation case budget would be exceeded'
              USING ERRCODE = '23514';
          END IF;

          expected_document := jsonb_build_object(
            'attempt', NEW.attempt,
            'case_digest', NEW.case_digest,
            'case_id', NEW.case_key,
            'grader_outputs', NEW.grader_outputs,
            'latency_ms', NEW.latency_ms,
            'output_digest', NEW.output_digest,
            'run_id', NEW.run_key,
            'sanitized_trace_ref', NEW.sanitized_trace_ref,
            'status', NEW.status,
            'usage', NEW.usage,
            'validity_flags', NEW.validity_flags
          );
          IF NEW.canonical_payload::jsonb <> expected_document THEN
            RAISE EXCEPTION 'evaluation case canonical payload mismatch'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.result_digest <> (
            'sha256:' || encode(
              digest(convert_to(NEW.canonical_payload, 'UTF8'), 'sha256'),
              'hex'
            )
          ) THEN
            RAISE EXCEPTION 'evaluation case result digest mismatch'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE FUNCTION evaluation_case_result_reject_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'evaluation case results are immutable'
            USING ERRCODE = '23514';
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_case_result_validate
        BEFORE INSERT ON ai_evaluation_case_result
        FOR EACH ROW EXECUTE FUNCTION evaluation_case_result_validate();
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_case_result_immutable
        BEFORE UPDATE OR DELETE ON ai_evaluation_case_result
        FOR EACH ROW EXECUTE FUNCTION evaluation_case_result_reject_mutation();
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_case_result_reject_truncate
        BEFORE TRUNCATE ON ai_evaluation_case_result
        FOR EACH STATEMENT
        EXECUTE FUNCTION evaluation_case_result_reject_mutation();
        """
    )


def _create_case_task_cancellation() -> None:
    op.execute(
        """
        CREATE FUNCTION evaluation_run_cancel_case_tasks()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF NEW.status = 'cancelled'
             AND OLD.status IS DISTINCT FROM 'cancelled' THEN
            UPDATE ai_evaluation_case_task
            SET
              status = 'cancelled',
              lease_owner = NULL,
              lease_token = NULL,
              lease_expires_at = NULL
            WHERE run_key = NEW.run_key
              AND status IN ('pending','running');
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_run_cancel_case_tasks
        AFTER UPDATE ON ai_evaluation_run
        FOR EACH ROW EXECUTE FUNCTION evaluation_run_cancel_case_tasks();
        """
    )


def _create_evidence_bundle_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION evaluation_evidence_bundle_validate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          parent ai_evaluation_run%ROWTYPE;
          observed_count integer;
          invalid_count integer;
          binding_mismatch_count integer;
          grader_mismatch_count integer;
          observed_case_results_digest text;
          input_tokens bigint;
          output_tokens bigint;
          duration_seconds numeric;
          cost_usd numeric;
          suite_document jsonb;
          baseline_policy_document jsonb;
        BEGIN
          SELECT *
          INTO parent
          FROM ai_evaluation_run
          WHERE run_key = NEW.run_key
          FOR UPDATE;
          IF parent.run_key IS NULL OR parent.status <> 'comparing' THEN
            RAISE EXCEPTION
              'evaluation evidence requires a comparing governed run'
              USING ERRCODE = '23514';
          END IF;
          IF parent.plan_digest <> NEW.plan_digest
             OR parent.authority_class <> NEW.authority_class
             OR parent.row_version <> NEW.sealed_from_row_version THEN
            RAISE EXCEPTION 'evaluation evidence run binding mismatch'
              USING ERRCODE = '23514';
          END IF;
          suite_document := NEW.suite_snapshot_payload::jsonb;
          baseline_policy_document := NEW.baseline_policy_payload::jsonb;
          IF (
               'sha256:' || encode(
                 digest(
                   convert_to(NEW.suite_snapshot_payload, 'UTF8'),
                   'sha256'
                 ),
                 'hex'
               )
             ) <> parent.plan_document #>> '{suite,digest}'
             OR suite_document ->> 'suite_id'
                <> parent.plan_document #>> '{suite,id}'
             OR (
               'sha256:' || encode(
                 digest(
                   convert_to(NEW.baseline_policy_payload, 'UTF8'),
                   'sha256'
                 ),
                 'hex'
               )
             ) <> parent.plan_document ->> 'baselinePolicyDigest'
             OR NEW.canonical_document ->> 'baseline_policy_digest'
                <> parent.plan_document ->> 'baselinePolicyDigest'
             OR NOT (
               baseline_policy_document -> 'hard_gates' @>
               jsonb_build_array(
                 jsonb_build_object(
                   'gate_revision', 'acl-leakage-v1',
                   'required_value', 0
                 ),
                 jsonb_build_object(
                   'gate_revision', 'citation-validity-v1',
                   'required_value', 0
                 ),
                 jsonb_build_object(
                   'gate_revision', 'pii-leakage-v1',
                   'required_value', 0
                 ),
                 jsonb_build_object(
                   'gate_revision', 'tool-authorization-v1',
                   'required_value', 0
                 )
               )
             ) THEN
            RAISE EXCEPTION 'evaluation evidence policy/suite binding mismatch'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.canonical_payload::jsonb
             <> (NEW.canonical_document - 'bundle_digest') THEN
            RAISE EXCEPTION 'evaluation evidence canonical payload mismatch'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.bundle_digest <> (
            'sha256:' || encode(
              digest(convert_to(NEW.canonical_payload, 'UTF8'), 'sha256'),
              'hex'
            )
          ) OR NEW.canonical_document ->> 'bundle_digest'
             <> NEW.bundle_digest THEN
            RAISE EXCEPTION 'evaluation evidence bundle digest mismatch'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.canonical_document ->> 'run_request_digest'
                <> NEW.plan_digest
             OR NEW.canonical_document ->> 'case_results_digest'
                <> NEW.case_results_digest
             OR NEW.canonical_document ->> 'run_result_digest'
                <> NEW.run_result_digest
             OR NEW.canonical_document ->> 'authority_class'
                <> NEW.authority_class
             OR NEW.canonical_document ->> 'recommendation'
                <> NEW.recommendation
             OR NEW.canonical_document -> 'case_set_complete' <> 'true'::jsonb
             OR NEW.canonical_document -> 'human_approval_included'
                <> 'false'::jsonb
             OR (
               NEW.authority_class = 'public-diagnostic'
               AND NEW.recommendation = 'recommend'
             ) THEN
            RAISE EXCEPTION 'evaluation evidence semantic binding mismatch'
              USING ERRCODE = '23514';
          END IF;

          WITH latest AS (
            SELECT DISTINCT ON (case_key)
              case_key, result_digest, status
            FROM ai_evaluation_case_result
            WHERE run_key = NEW.run_key
            ORDER BY case_key, attempt DESC
          )
          SELECT
            count(*)::integer,
            count(*) FILTER (WHERE status <> 'valid')::integer,
            'sha256:' || encode(
              digest(
                convert_to(
                  '{"case_results":[' ||
                  string_agg(
                    to_json(result_digest)::text,
                    ',' ORDER BY case_key
                  ) ||
                  ']}',
                  'UTF8'
                ),
                'sha256'
              ),
              'hex'
            )
          INTO observed_count, invalid_count, observed_case_results_digest
          FROM latest;

          WITH expected AS (
            SELECT
              binding ->> 'case_id' AS case_key,
              binding ->> 'case_digest' AS case_digest
            FROM jsonb_array_elements(
              suite_document -> 'case_bindings'
            ) AS binding
          ),
          latest AS (
            SELECT DISTINCT ON (case_key)
              case_key, case_digest, grader_outputs
            FROM ai_evaluation_case_result
            WHERE run_key = NEW.run_key
            ORDER BY case_key, attempt DESC
          ),
          required_graders AS (
            SELECT jsonb_array_elements_text(
              parent.plan_document -> 'graderRevisions'
            ) AS revision
          )
          SELECT
            (
              SELECT count(*)::integer
              FROM (
                SELECT case_key, case_digest FROM expected
                EXCEPT
                SELECT case_key, case_digest FROM latest
                UNION ALL
                SELECT case_key, case_digest FROM latest
                EXCEPT
                SELECT case_key, case_digest FROM expected
              ) AS differences
            ),
            (
              SELECT count(*)::integer
              FROM latest
              WHERE (
                SELECT array_agg(value ORDER BY value)
                FROM jsonb_array_elements_text(
                  jsonb_path_query_array(
                    latest.grader_outputs,
                    '$[*].grader_revision'
                  )
                ) AS value
              ) IS DISTINCT FROM (
                SELECT array_agg(revision ORDER BY revision)
                FROM required_graders
              )
            )
          INTO binding_mismatch_count, grader_mismatch_count;

          WITH latest AS (
            SELECT DISTINCT ON (case_key)
              usage, latency_ms
            FROM ai_evaluation_case_result
            WHERE run_key = NEW.run_key
            ORDER BY case_key, attempt DESC
          )
          SELECT
            coalesce(sum((usage ->> 'input_tokens')::bigint), 0),
            coalesce(sum((usage ->> 'output_tokens')::bigint), 0),
            coalesce(sum(latency_ms)::numeric / 1000, 0),
            coalesce(sum((usage ->> 'cost_usd')::numeric), 0)
          INTO input_tokens, output_tokens, duration_seconds, cost_usd
          FROM latest;

          IF observed_count = 0
             OR observed_count <> parent.completed_case_count
             OR invalid_count <> 0
             OR binding_mismatch_count <> 0
             OR grader_mismatch_count <> 0
             OR observed_case_results_digest <> NEW.case_results_digest THEN
            RAISE EXCEPTION 'evaluation evidence case set mismatch'
              USING ERRCODE = '23514';
          END IF;
          IF EXISTS (
            SELECT 1
            FROM ai_evaluation_case_task
            WHERE run_key = NEW.run_key
              AND status <> 'completed'
          ) OR (
            SELECT count(*)
            FROM ai_evaluation_case_task
            WHERE run_key = NEW.run_key
          ) <> observed_count THEN
            RAISE EXCEPTION 'evaluation execution tasks are incomplete'
              USING ERRCODE = '23514';
          END IF;
          IF input_tokens
                > (parent.plan_document #>> '{budgets,maxInputTokens}')::bigint
             OR output_tokens
                > (parent.plan_document #>> '{budgets,maxOutputTokens}')::bigint
             OR duration_seconds
                > (parent.plan_document #>> '{budgets,maxDurationSeconds}')::numeric
             OR cost_usd
                > (parent.plan_document #>> '{budgets,maxCostUsd}')::numeric THEN
            RAISE EXCEPTION 'evaluation evidence budget exceeded'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE FUNCTION evaluation_evidence_bundle_reject_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'evaluation evidence bundles are immutable'
            USING ERRCODE = '23514';
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_evidence_bundle_validate
        BEFORE INSERT ON ai_evaluation_evidence_bundle
        FOR EACH ROW EXECUTE FUNCTION evaluation_evidence_bundle_validate();
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_evidence_bundle_immutable
        BEFORE UPDATE OR DELETE ON ai_evaluation_evidence_bundle
        FOR EACH ROW
        EXECUTE FUNCTION evaluation_evidence_bundle_reject_mutation();
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_evidence_bundle_reject_truncate
        BEFORE TRUNCATE ON ai_evaluation_evidence_bundle
        FOR EACH STATEMENT
        EXECUTE FUNCTION evaluation_evidence_bundle_reject_mutation();
        """
    )


def _create_decision_ready_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION evaluation_run_validate_decision_ready()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          matching_evidence boolean;
        BEGIN
          IF OLD.status = 'decision_ready' AND (
            NEW.status <> OLD.status
            OR NEW.evidence_bundle_digest IS DISTINCT FROM
               OLD.evidence_bundle_digest
            OR NEW.plan_digest IS DISTINCT FROM OLD.plan_digest
          ) THEN
            RAISE EXCEPTION 'decision-ready evaluation run is terminal'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.status = 'decision_ready'
             AND OLD.status IS DISTINCT FROM 'decision_ready' THEN
            IF OLD.status <> 'comparing'
               OR NEW.evidence_bundle_digest IS NULL THEN
              RAISE EXCEPTION
                'decision-ready requires comparing evidence transition'
                USING ERRCODE = '23514';
            END IF;
            SELECT true
            INTO matching_evidence
            FROM ai_evaluation_evidence_bundle
            WHERE run_key = NEW.run_key
              AND plan_digest = NEW.plan_digest
              AND bundle_digest = NEW.evidence_bundle_digest
              AND authority_class = NEW.authority_class
            LIMIT 1;
            IF matching_evidence IS NOT TRUE THEN
              RAISE EXCEPTION
                'decision-ready requires matching sealed evidence row'
                USING ERRCODE = '23514';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_run_decision_ready
        BEFORE UPDATE ON ai_evaluation_run
        FOR EACH ROW EXECUTE FUNCTION evaluation_run_validate_decision_ready();
        """
    )


def _create_atomic_seal_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION evaluation_evidence_validate_seal_commit()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          sealed boolean;
        BEGIN
          SELECT true
          INTO sealed
          FROM ai_evaluation_run
          WHERE run_key = NEW.run_key
            AND plan_digest = NEW.plan_digest
            AND status = 'decision_ready'
            AND evidence_bundle_digest = NEW.bundle_digest
            AND row_version = NEW.sealed_from_row_version + 1
          LIMIT 1;
          IF sealed IS NOT TRUE THEN
            RAISE EXCEPTION
              'evaluation evidence insert requires atomic decision-ready seal'
              USING ERRCODE = '23514';
          END IF;
          RETURN NULL;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
          trg_ai_evaluation_evidence_bundle_seal_commit
        AFTER INSERT ON ai_evaluation_evidence_bundle
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION evaluation_evidence_validate_seal_commit();
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE ai_evaluation_run, ai_evaluation_case_task, "
            "ai_evaluation_case_result, "
            "ai_evaluation_evidence_bundle IN ACCESS EXCLUSIVE MODE"
        )
    )
    retained = connection.execute(
        sa.text(
            """
            SELECT
              EXISTS (SELECT 1 FROM ai_evaluation_case_result)
              OR EXISTS (SELECT 1 FROM ai_evaluation_case_task)
              OR EXISTS (SELECT 1 FROM ai_evaluation_evidence_bundle)
            """
        )
    ).scalar_one()
    if retained:
        raise RuntimeError(
            "cannot downgrade 20260730_0020 while immutable evaluation evidence "
            "exists; retain the authority schema or follow approved retention"
        )

    op.drop_constraint(
        "fk_ai_evaluation_run_evidence_binding",
        "ai_evaluation_run",
        type_="foreignkey",
    )
    for statement in (
        "DROP TRIGGER IF EXISTS "
        "trg_ai_evaluation_evidence_bundle_seal_commit "
        "ON ai_evaluation_evidence_bundle",
        "DROP TRIGGER IF EXISTS "
        "trg_ai_evaluation_evidence_bundle_reject_truncate "
        "ON ai_evaluation_evidence_bundle",
        "DROP TRIGGER IF EXISTS trg_ai_evaluation_run_decision_ready "
        "ON ai_evaluation_run",
        "DROP TRIGGER IF EXISTS trg_ai_evaluation_run_cancel_case_tasks "
        "ON ai_evaluation_run",
        "DROP TRIGGER IF EXISTS trg_ai_evaluation_evidence_bundle_immutable "
        "ON ai_evaluation_evidence_bundle",
        "DROP TRIGGER IF EXISTS trg_ai_evaluation_evidence_bundle_validate "
        "ON ai_evaluation_evidence_bundle",
        "DROP TRIGGER IF EXISTS trg_ai_evaluation_case_result_immutable "
        "ON ai_evaluation_case_result",
        "DROP TRIGGER IF EXISTS trg_ai_evaluation_case_result_reject_truncate "
        "ON ai_evaluation_case_result",
        "DROP TRIGGER IF EXISTS trg_ai_evaluation_case_result_validate "
        "ON ai_evaluation_case_result",
        "DROP FUNCTION IF EXISTS evaluation_evidence_validate_seal_commit()",
        "DROP FUNCTION IF EXISTS evaluation_run_validate_decision_ready()",
        "DROP FUNCTION IF EXISTS evaluation_run_cancel_case_tasks()",
        "DROP FUNCTION IF EXISTS evaluation_evidence_bundle_reject_mutation()",
        "DROP FUNCTION IF EXISTS evaluation_evidence_bundle_validate()",
        "DROP FUNCTION IF EXISTS evaluation_case_result_reject_mutation()",
        "DROP FUNCTION IF EXISTS evaluation_case_result_validate()",
    ):
        op.execute(statement)
    op.drop_table("ai_evaluation_evidence_bundle")
    op.drop_index(
        "ix_ai_evaluation_case_task_claim",
        table_name="ai_evaluation_case_task",
    )
    op.drop_table("ai_evaluation_case_task")
    op.drop_index(
        "ix_ai_evaluation_case_result_latest",
        table_name="ai_evaluation_case_result",
    )
    op.drop_table("ai_evaluation_case_result")
    op.execute(
        """
        ALTER TABLE ai_evaluation_run
          DROP CONSTRAINT ck_ai_evaluation_run_terminal_evidence
        """
    )
    op.execute(
        """
        ALTER TABLE ai_evaluation_run
          ADD CONSTRAINT ck_ai_evaluation_run_terminal_evidence
          CHECK (
            run_key IS NULL
            OR status <> 'decision_ready'
            OR (
              evidence_bundle_digest IS NOT NULL
              AND evidence_bundle_digest ~ '^sha256:[a-f0-9]{64}$'
            )
          );
        """
    )
