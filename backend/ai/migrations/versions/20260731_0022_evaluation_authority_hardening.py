"""Harden evaluation evidence against lease and semantic forgery.

Revision ID: 20260731_0022
Revises: 20260730_0021
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260731_0022"
down_revision: str | None = "20260730_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        LOCK TABLE ai_evaluation_run, ai_evaluation_case_task,
          ai_evaluation_case_result, ai_evaluation_evidence_bundle
        IN ACCESS EXCLUSIVE MODE
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
               SELECT 1 FROM ai_evaluation_run WHERE run_key IS NOT NULL
             )
             OR EXISTS (SELECT 1 FROM ai_evaluation_case_task)
             OR EXISTS (SELECT 1 FROM ai_evaluation_case_result)
             OR EXISTS (SELECT 1 FROM ai_evaluation_evidence_bundle) THEN
            RAISE EXCEPTION
              '20260731_0022 requires governed evaluation runs to be rerun; '
              'lease and semantic authority cannot be backfilled'
              USING ERRCODE = '55000';
          END IF;
        END;
        $$;
        """
    )

    op.add_column(
        "ai_evaluation_case_result",
        sa.Column("lease_owner", sa.String(160), nullable=False),
    )
    op.add_column(
        "ai_evaluation_case_result",
        sa.Column(
            "lease_token",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
    )
    op.add_column(
        "ai_evaluation_case_result",
        sa.Column(
            "metric_outputs",
            postgresql.JSONB(),
            nullable=False,
        ),
    )
    op.add_column(
        "ai_evaluation_evidence_bundle",
        sa.Column("run_result_payload", sa.Text(), nullable=False),
    )
    op.create_check_constraint(
        "ck_ai_evaluation_case_result_metric_outputs",
        "ai_evaluation_case_result",
        "jsonb_typeof(metric_outputs) = 'array'",
    )
    op.create_table(
        "ai_evaluation_definition_release",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("definition_kind", sa.String(40), nullable=False),
        sa.Column("definition_key", sa.String(200), nullable=False),
        sa.Column("revision", sa.String(200), nullable=False),
        sa.Column("content_digest", sa.String(71), nullable=False),
        sa.Column("canonical_payload", sa.Text(), nullable=False),
        sa.Column("release_evidence_uri", sa.String(500), nullable=False),
        sa.Column("released_by_subject", sa.String(200), nullable=False),
        sa.Column(
            "released_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "definition_kind",
            "definition_key",
            "revision",
            name="uq_ai_evaluation_definition_release_identity",
        ),
        sa.CheckConstraint(
            "definition_kind IN "
            "('benchmark','metric','grader','calibration','suite',"
            "'suite-authority','baseline-policy')",
            name="ck_ai_evaluation_definition_release_kind",
        ),
        sa.CheckConstraint(
            "content_digest ~ '^sha256:[a-f0-9]{64}$'",
            name="ck_ai_evaluation_definition_release_digest",
        ),
        sa.CheckConstraint(
            "release_evidence_uri LIKE 'evidence://%'",
            name="ck_ai_evaluation_definition_release_evidence",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= released_at",
            name="ck_ai_evaluation_definition_release_window",
        ),
    )

    _create_canonical_json_authority()
    _create_definition_release_guard()
    _replace_case_result_guard()
    _create_case_task_guard()
    _create_run_authority_guard()
    _replace_evidence_guard()
    _create_runtime_role_boundary()
    op.execute(
        """
        REVOKE INSERT, UPDATE, DELETE, TRUNCATE
        ON ai_evaluation_case_result, ai_evaluation_case_task,
           ai_evaluation_evidence_bundle, ai_evaluation_definition_release
        FROM PUBLIC
        """
    )


def _create_runtime_role_boundary() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles
            WHERE rolname = 'vfbiz_ai_evaluation_runner'
          ) THEN
            CREATE ROLE vfbiz_ai_evaluation_runner NOLOGIN;
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles
            WHERE rolname = 'vfbiz_ai_evaluation_sealer'
          ) THEN
            CREATE ROLE vfbiz_ai_evaluation_sealer NOLOGIN;
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles
            WHERE rolname = 'vfbiz_ai_evaluation_reader'
          ) THEN
            CREATE ROLE vfbiz_ai_evaluation_reader NOLOGIN;
          END IF;
        END;
        $$;
        """
    )
    for schema_name in (
        "vfbiz_eval_runner",
        "vfbiz_eval_sealer",
        "vfbiz_eval_reader",
    ):
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
    view_statements = (
        "CREATE VIEW vfbiz_eval_runner.ai_evaluation_run AS SELECT * FROM public.ai_evaluation_run",
        "CREATE VIEW vfbiz_eval_runner.ai_evaluation_case_task "
        "AS SELECT * FROM public.ai_evaluation_case_task",
        "CREATE VIEW vfbiz_eval_runner.ai_evaluation_case_result "
        "AS SELECT * FROM public.ai_evaluation_case_result",
        "CREATE VIEW vfbiz_eval_runner.ai_evaluation_evidence_bundle "
        "AS SELECT * FROM public.ai_evaluation_evidence_bundle",
        "CREATE VIEW vfbiz_eval_runner.ai_evaluation_definition_release "
        "AS SELECT * FROM public.ai_evaluation_definition_release",
        "CREATE VIEW vfbiz_eval_sealer.ai_evaluation_run AS SELECT * FROM public.ai_evaluation_run",
        "CREATE VIEW vfbiz_eval_sealer.ai_evaluation_case_task "
        "AS SELECT * FROM public.ai_evaluation_case_task",
        "CREATE VIEW vfbiz_eval_sealer.ai_evaluation_case_result "
        "AS SELECT * FROM public.ai_evaluation_case_result",
        "CREATE VIEW vfbiz_eval_sealer.ai_evaluation_evidence_bundle "
        "AS SELECT * FROM public.ai_evaluation_evidence_bundle",
        "CREATE VIEW vfbiz_eval_sealer.ai_evaluation_definition_release "
        "AS SELECT * FROM public.ai_evaluation_definition_release",
        "CREATE VIEW vfbiz_eval_reader.ai_evaluation_run AS SELECT * FROM public.ai_evaluation_run",
        "CREATE VIEW vfbiz_eval_reader.ai_evaluation_case_task "
        "AS SELECT * FROM public.ai_evaluation_case_task",
        "CREATE VIEW vfbiz_eval_reader.ai_evaluation_case_result "
        "AS SELECT * FROM public.ai_evaluation_case_result",
        "CREATE VIEW vfbiz_eval_reader.ai_evaluation_evidence_bundle "
        "AS SELECT * FROM public.ai_evaluation_evidence_bundle",
        "CREATE VIEW vfbiz_eval_reader.ai_evaluation_definition_release "
        "AS SELECT * FROM public.ai_evaluation_definition_release",
    )
    for statement in view_statements:
        op.execute(statement)
    privilege_statements = (
        "REVOKE ALL ON ai_evaluation_run, ai_evaluation_case_task, "
        "ai_evaluation_case_result, ai_evaluation_evidence_bundle, "
        "ai_evaluation_definition_release FROM "
        "vfbiz_ai_evaluation_runner, vfbiz_ai_evaluation_sealer, "
        "vfbiz_ai_evaluation_reader",
        "GRANT USAGE ON SCHEMA vfbiz_eval_runner TO vfbiz_ai_evaluation_runner",
        "GRANT SELECT, INSERT, UPDATE ON "
        "vfbiz_eval_runner.ai_evaluation_run, "
        "vfbiz_eval_runner.ai_evaluation_case_task "
        "TO vfbiz_ai_evaluation_runner",
        "GRANT SELECT, INSERT ON "
        "vfbiz_eval_runner.ai_evaluation_case_result "
        "TO vfbiz_ai_evaluation_runner",
        "GRANT SELECT ON "
        "vfbiz_eval_runner.ai_evaluation_evidence_bundle, "
        "vfbiz_eval_runner.ai_evaluation_definition_release "
        "TO vfbiz_ai_evaluation_runner",
        "GRANT USAGE ON SCHEMA vfbiz_eval_sealer TO vfbiz_ai_evaluation_sealer",
        "GRANT SELECT, UPDATE ON vfbiz_eval_sealer.ai_evaluation_run TO vfbiz_ai_evaluation_sealer",
        "GRANT SELECT ON vfbiz_eval_sealer.ai_evaluation_case_task, "
        "vfbiz_eval_sealer.ai_evaluation_case_result, "
        "vfbiz_eval_sealer.ai_evaluation_definition_release "
        "TO vfbiz_ai_evaluation_sealer",
        "GRANT SELECT, INSERT ON "
        "vfbiz_eval_sealer.ai_evaluation_evidence_bundle "
        "TO vfbiz_ai_evaluation_sealer",
        "GRANT USAGE ON SCHEMA vfbiz_eval_reader TO vfbiz_ai_evaluation_reader",
        "GRANT SELECT ON vfbiz_eval_reader.ai_evaluation_run, "
        "vfbiz_eval_reader.ai_evaluation_case_task, "
        "vfbiz_eval_reader.ai_evaluation_case_result, "
        "vfbiz_eval_reader.ai_evaluation_evidence_bundle, "
        "vfbiz_eval_reader.ai_evaluation_definition_release "
        "TO vfbiz_ai_evaluation_reader",
    )
    for statement in privilege_statements:
        op.execute(statement)
    op.execute(
        """
        DO $$
        BEGIN
          EXECUTE format(
            'ALTER ROLE vfbiz_ai_evaluation_runner IN DATABASE %I '
            'SET search_path = vfbiz_eval_runner, public',
            current_database()
          );
          EXECUTE format(
            'ALTER ROLE vfbiz_ai_evaluation_sealer IN DATABASE %I '
            'SET search_path = vfbiz_eval_sealer, public',
            current_database()
          );
          EXECUTE format(
            'ALTER ROLE vfbiz_ai_evaluation_reader IN DATABASE %I '
            'SET search_path = vfbiz_eval_reader, public',
            current_database()
          );
        END;
        $$;
        """
    )


def _create_canonical_json_authority() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION evaluation_canonical_json(value jsonb)
        RETURNS text
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        AS $$
        DECLARE
          kind text := jsonb_typeof(value);
          result text;
          numeric_value numeric;
          scientific text;
          mantissa text;
          exponent_value integer;
        BEGIN
          IF kind = 'null' THEN
            RETURN 'null';
          ELSIF kind = 'boolean' THEN
            RETURN value::text;
          ELSIF kind = 'number' THEN
            numeric_value := (value #>> '{}')::numeric;
            IF numeric_value = 0 THEN
              RETURN '0';
            END IF;
            IF abs(numeric_value) >= 0.000001
               AND abs(numeric_value) < 1000000000000000000000 THEN
              RETURN trim_scale(numeric_value)::text;
            END IF;
            scientific := btrim(
              to_char(numeric_value, '9.9999999999999999EEEE')
            );
            mantissa := rtrim(
              rtrim(split_part(scientific, 'e', 1), '0'),
              '.'
            );
            exponent_value := split_part(scientific, 'e', 2)::integer;
            RETURN mantissa || 'e'
              || CASE WHEN exponent_value >= 0 THEN '+' ELSE '' END
              || exponent_value::text;
          ELSIF kind = 'string' THEN
            RETURN to_json(value #>> '{}')::text;
          ELSIF kind = 'array' THEN
            SELECT '[' || coalesce(
              string_agg(evaluation_canonical_json(item), ',' ORDER BY ordinal),
              ''
            ) || ']'
            INTO result
            FROM jsonb_array_elements(value)
              WITH ORDINALITY AS items(item, ordinal);
            RETURN result;
          ELSIF kind = 'object' THEN
            SELECT '{' || coalesce(
              string_agg(
                to_json(key)::text || ':' || evaluation_canonical_json(item),
                ',' ORDER BY key COLLATE "C"
              ),
              ''
            ) || '}'
            INTO result
            FROM jsonb_each(value) AS entries(key, item);
            RETURN result;
          END IF;
          RAISE EXCEPTION 'unsupported canonical JSON value';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION evaluation_calibration_metrics_valid(document jsonb)
        RETURNS boolean
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        AS $$
        DECLARE
          matrix jsonb;
          slice_item jsonb;
          slice_matrix jsonb;
          tp numeric;
          tn numeric;
          fp numeric;
          fn numeric;
          sample numeric;
          expected_balanced numeric;
          expected_f1 numeric;
          seen_all boolean := false;
          seen_high_risk boolean := false;
        BEGIN
          IF jsonb_typeof(document -> 'confusion_matrix') <> 'object'
             OR jsonb_typeof(document -> 'slice_metrics') <> 'array'
             OR jsonb_typeof(document -> 'balanced_accuracy') <> 'number'
             OR jsonb_typeof(document -> 'f1') <> 'number'
             OR (document ->> 'sample_size') !~ '^[0-9]+$'
             OR (document ->> 'sample_size')::numeric < 30
             OR (document ->> 'sample_size')::numeric
                > 9007199254740991
             OR document ->> 'calibrated_at'
                !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
             OR document ->> 'expires_at'
                !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
             OR (document ->> 'expires_at')::timestamptz
                <= (document ->> 'calibrated_at')::timestamptz THEN
            RETURN false;
          END IF;
          matrix := document -> 'confusion_matrix';
          IF (
               SELECT count(*)
               FROM jsonb_array_elements(document -> 'slice_metrics')
             ) <> (
               SELECT count(DISTINCT value ->> 'slice')
               FROM jsonb_array_elements(document -> 'slice_metrics')
             ) THEN
            RETURN false;
          END IF;
          tp := (matrix ->> 'true_positive')::numeric;
          tn := (matrix ->> 'true_negative')::numeric;
          fp := (matrix ->> 'false_positive')::numeric;
          fn := (matrix ->> 'false_negative')::numeric;
          sample := (document ->> 'sample_size')::numeric;
          IF least(tp, tn, fp, fn) < 0
             OR greatest(tp, tn, fp, fn) > 9007199254740991
             OR tp + tn + fp + fn <> sample
             OR tp + fn <= 0
             OR tn + fp <= 0
             OR 2 * tp + fp + fn <= 0 THEN
            RETURN false;
          END IF;
          expected_balanced :=
            ((tp / (tp + fn)) + (tn / (tn + fp))) / 2;
          expected_f1 := (2 * tp) / (2 * tp + fp + fn);
          IF abs(
               (document ->> 'balanced_accuracy')::numeric
               - expected_balanced
             ) > 0.000000000001
             OR abs(
               (document ->> 'f1')::numeric - expected_f1
             ) > 0.000000000001 THEN
            RETURN false;
          END IF;
          FOR slice_item IN
            SELECT value
            FROM jsonb_array_elements(document -> 'slice_metrics')
          LOOP
            IF jsonb_typeof(slice_item) <> 'object'
               OR btrim(coalesce(slice_item ->> 'slice', '')) = ''
               OR jsonb_typeof(slice_item -> 'confusion_matrix') <> 'object'
               OR jsonb_typeof(slice_item -> 'balanced_accuracy') <> 'number'
               OR jsonb_typeof(slice_item -> 'f1') <> 'number'
               OR (slice_item ->> 'sample_size') !~ '^[0-9]+$'
               OR (slice_item ->> 'sample_size')::numeric
                  > 9007199254740991 THEN
              RETURN false;
            END IF;
            slice_matrix := slice_item -> 'confusion_matrix';
            tp := (slice_matrix ->> 'true_positive')::numeric;
            tn := (slice_matrix ->> 'true_negative')::numeric;
            fp := (slice_matrix ->> 'false_positive')::numeric;
            fn := (slice_matrix ->> 'false_negative')::numeric;
            sample := (slice_item ->> 'sample_size')::numeric;
            IF least(tp, tn, fp, fn) < 0
               OR greatest(tp, tn, fp, fn) > 9007199254740991
               OR tp + tn + fp + fn <> sample
               OR sample > (document ->> 'sample_size')::numeric
               OR tp + fn <= 0
               OR tn + fp <= 0
               OR 2 * tp + fp + fn <= 0 THEN
              RETURN false;
            END IF;
            expected_balanced :=
              ((tp / (tp + fn)) + (tn / (tn + fp))) / 2;
            expected_f1 := (2 * tp) / (2 * tp + fp + fn);
            IF abs(
                 (slice_item ->> 'balanced_accuracy')::numeric
                 - expected_balanced
               ) > 0.000000000001
               OR abs(
                 (slice_item ->> 'f1')::numeric - expected_f1
               ) > 0.000000000001 THEN
              RETURN false;
            END IF;
            IF slice_item ->> 'slice' = 'all' THEN
              seen_all := true;
              IF (slice_item ->> 'sample_size')::numeric <>
                   (document ->> 'sample_size')::numeric
                 OR slice_matrix <> document -> 'confusion_matrix'
                 OR (slice_item ->> 'balanced_accuracy')::numeric <>
                    (document ->> 'balanced_accuracy')::numeric
                 OR (slice_item ->> 'f1')::numeric <>
                    (document ->> 'f1')::numeric THEN
                RETURN false;
              END IF;
            ELSIF slice_item ->> 'slice' = 'high-risk' THEN
              seen_high_risk := true;
            END IF;
          END LOOP;
          RETURN seen_all AND seen_high_risk;
        EXCEPTION WHEN OTHERS THEN
          RETURN false;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION evaluation_baseline_policy_valid(document jsonb)
        RETURNS boolean
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        AS $$
        DECLARE
          semantic_digest text;
        BEGIN
          IF document ->> 'binary_interval' <> 'wilson-95'
             OR document -> 'composite_score_authoritative' <> 'false'::jsonb
             OR jsonb_typeof(document -> 'hard_gates') <> 'array'
             OR jsonb_typeof(document -> 'protected_metrics') <> 'array'
             OR jsonb_array_length(document -> 'protected_metrics') = 0
             OR jsonb_typeof(document -> 'operational_budgets') <> 'object'
             OR jsonb_typeof(document -> 'paired_comparison') <> 'object'
             OR jsonb_typeof(document -> 'waiver_policy') <> 'object' THEN
            RETURN false;
          END IF;
          semantic_digest := 'sha256:' || encode(
            digest(
              convert_to(
                evaluation_canonical_json(document - 'policy_digest'),
                'UTF8'
              ),
              'sha256'
            ),
            'hex'
          );
          IF document ->> 'policy_digest' IS DISTINCT FROM semantic_digest
             OR (
               SELECT count(*)
               FROM jsonb_array_elements(document -> 'hard_gates')
             ) <> (
               SELECT count(DISTINCT value ->> 'gate_revision')
               FROM jsonb_array_elements(document -> 'hard_gates')
             )
             OR EXISTS (
               SELECT 1
               FROM unnest(ARRAY[
                 'acl-leakage-v1',
                 'citation-validity-v1',
                 'pii-leakage-v1',
                 'tool-authorization-v1'
               ]) AS required(revision)
               WHERE NOT EXISTS (
                 SELECT 1
                 FROM jsonb_array_elements(
                   document -> 'hard_gates'
                 ) AS gate
                 WHERE gate ->> 'gate_revision' = required.revision
                   AND gate -> 'required_value' = '0'::jsonb
               )
             )
             OR EXISTS (
               SELECT 1
               FROM jsonb_array_elements(
                 document -> 'protected_metrics'
               ) AS metric
               WHERE btrim(coalesce(metric ->> 'metric_revision', '')) = ''
                  OR metric ->> 'direction'
                     NOT IN ('higher-is-better', 'lower-is-better')
                  OR jsonb_typeof(
                       metric -> 'non_inferiority_margin'
                     ) <> 'number'
                  OR (metric ->> 'non_inferiority_margin')::numeric < 0
                  OR metric -> 'require_protected_95_bound'
                     <> 'true'::jsonb
                  OR jsonb_typeof(metric -> 'required_slices') <> 'array'
                  OR NOT (
                    metric -> 'required_slices' @> '["all"]'::jsonb
                  )
             )
             OR document #>> '{paired_comparison,method}'
                <> 'paired-bootstrap'
             OR (document #>> '{paired_comparison,samples}')::integer
                <> 10000
             OR (document #>> '{paired_comparison,confidence}')::numeric
                <> 0.95
             OR (document #>> '{operational_budgets,latency_p95_ms}')::numeric
                <= 0
             OR (document #>> '{operational_budgets,normalized_cost_usd}')::numeric
                < 0
             OR (document #>> '{operational_budgets,provider_failure_rate}')::numeric
                < 0
             OR (document #>> '{operational_budgets,provider_failure_rate}')::numeric
                > 1
             OR document #> '{waiver_policy,requires_expiry}'
                <> 'true'::jsonb
             OR document #> '{waiver_policy,requires_mitigation}'
                <> 'true'::jsonb
             OR document #> '{waiver_policy,requires_owner}'
                <> 'true'::jsonb
             OR document #>> '{waiver_policy,authority_contract_id}'
                NOT LIKE 'https://%' THEN
            RETURN false;
          END IF;
          RETURN true;
        EXCEPTION WHEN OTHERS THEN
          RETURN false;
        END;
        $$;
        """
    )


def _create_definition_release_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION evaluation_definition_release_validate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          document jsonb;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'released evaluation definitions cannot be deleted'
              USING ERRCODE = '23514';
          END IF;
          IF TG_OP = 'UPDATE' THEN
            IF NEW.definition_kind <> OLD.definition_kind
               OR NEW.definition_key <> OLD.definition_key
               OR NEW.revision <> OLD.revision
               OR NEW.content_digest <> OLD.content_digest
               OR NEW.canonical_payload <> OLD.canonical_payload
               OR NEW.release_evidence_uri <> OLD.release_evidence_uri
               OR NEW.released_by_subject <> OLD.released_by_subject
               OR NEW.released_at <> OLD.released_at
               OR OLD.revoked_at IS NOT NULL
               OR NEW.revoked_at IS NULL THEN
              RAISE EXCEPTION 'released evaluation definition is immutable'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;
          document := NEW.canonical_payload::jsonb;
          IF NEW.canonical_payload <> evaluation_canonical_json(document)
             OR NEW.content_digest <> (
               'sha256:' || encode(
                 digest(convert_to(NEW.canonical_payload, 'UTF8'), 'sha256'),
                 'hex'
               )
             )
             OR btrim(NEW.definition_key) = ''
             OR btrim(NEW.revision) = ''
             OR btrim(NEW.released_by_subject) = '' THEN
            RAISE EXCEPTION 'invalid evaluation definition release'
              USING ERRCODE = '23514';
          END IF;
          IF (
               NEW.definition_kind = 'benchmark'
               AND (
                 NEW.definition_key IS DISTINCT FROM document ->> 'benchmark_id'
                 OR NEW.revision IS DISTINCT FROM document ->> 'revision'
               )
             )
             OR (
               NEW.definition_kind IN ('metric', 'grader')
               AND (
                 NEW.definition_key IS DISTINCT FROM document ->> 'revision'
                 OR NEW.revision IS DISTINCT FROM document ->> 'revision'
               )
             )
             OR (
               NEW.definition_kind = 'calibration'
               AND (
                 NEW.definition_key IS DISTINCT FROM document ->> 'grader_revision'
                 OR NEW.revision IS DISTINCT FROM document ->> 'evidence_digest'
                 OR document ->> 'evidence_digest' IS DISTINCT FROM (
                   'sha256:' || encode(
                     digest(
                       convert_to(
                         evaluation_canonical_json(
                           document - 'evidence_digest'
                         ),
                         'UTF8'
                       ),
                       'sha256'
                     ),
                     'hex'
                   )
                 )
               )
             )
             OR (
               NEW.definition_kind = 'suite-authority'
               AND (
                 NEW.definition_key IS DISTINCT FROM document ->> 'suite_id'
                 OR NEW.revision IS DISTINCT FROM
                    document ->> 'authority_digest'
               )
             )
             OR (
               NEW.definition_kind = 'suite'
               AND (
                 NEW.definition_key IS DISTINCT FROM document ->> 'suite_id'
                 OR NEW.revision IS DISTINCT FROM document ->> 'suite_digest'
               )
             )
             OR (
               NEW.definition_kind = 'baseline-policy'
               AND (
                 NEW.definition_key IS DISTINCT FROM document ->> 'policy_digest'
                 OR NEW.revision IS DISTINCT FROM document ->> 'policy_digest'
               )
             ) THEN
            RAISE EXCEPTION 'evaluation definition release identity mismatch'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.definition_kind = 'suite-authority' AND (
               document ->> 'authority_digest' <> (
                 'sha256:' || encode(
                   digest(
                     convert_to(
                       evaluation_canonical_json(
                         document - 'authority_digest'
                       ),
                       'UTF8'
                     ),
                     'sha256'
                   ),
                   'hex'
                 )
               )
               OR document ->> 'authority_class'
                  NOT IN ('vinfast-acceptance', 'public-diagnostic')
               OR document ->> 'authority_class' = 'vinfast-acceptance'
               OR btrim(coalesce(document ->> 'qualification_profile', '')) = ''
               OR document ->> 'qualification_policy_digest'
                  !~ '^sha256:[a-f0-9]{64}$'
               OR document ->> 'case_bindings_digest'
                  !~ '^sha256:[a-f0-9]{64}$'
               OR document ->> 'case_composition_digest'
                  !~ '^sha256:[a-f0-9]{64}$'
               OR document ->> 'risk_taxonomy_digest'
                  !~ '^sha256:[a-f0-9]{64}$'
               OR document ->> 'provenance_digest'
                  !~ '^sha256:[a-f0-9]{64}$'
               OR document ->> 'provenance_status' <> 'verified'
               OR document ->> 'provenance_evidence_uri'
                  NOT LIKE 'evidence://%'
               OR document ->> 'contamination_scan_digest'
                  !~ '^sha256:[a-f0-9]{64}$'
               OR document ->> 'contamination_status' <> 'passed'
               OR document ->> 'contamination_evidence_uri'
                  NOT LIKE 'evidence://%'
               OR jsonb_typeof(document -> 'held_out') <> 'boolean'
               OR document #>> '{subject_roles,author}' <> 'dataset-author'
               OR document #>> '{subject_roles,evaluator}'
                  <> 'independent-evaluator'
               OR document #>> '{subject_roles,release_owner}'
                  <> 'release-owner'
               OR btrim(coalesce(document ->> 'author_subject', '')) = ''
               OR btrim(coalesce(document ->> 'evaluator_subject', '')) = ''
               OR btrim(coalesce(document ->> 'release_owner_subject', '')) = ''
               OR document ->> 'release_owner_subject'
                  IS DISTINCT FROM NEW.released_by_subject
               OR document ->> 'author_subject'
                  = document ->> 'evaluator_subject'
               OR document ->> 'author_subject'
                  = document ->> 'release_owner_subject'
               OR document ->> 'evaluator_subject'
                  = document ->> 'release_owner_subject'
             ) THEN
            RAISE EXCEPTION 'invalid evaluation suite authority record'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.definition_kind = 'benchmark' AND (
               (document #>> '{budgets,max_input_tokens}') !~ '^[0-9]+$'
               OR (document #>> '{budgets,max_output_tokens}') !~ '^[0-9]+$'
               OR (document #>> '{budgets,max_duration_seconds}') !~ '^[0-9]+$'
               OR (document #>> '{budgets,max_input_tokens}')::numeric
                  NOT BETWEEN 1 AND 9007199254740991
               OR (document #>> '{budgets,max_output_tokens}')::numeric
                  NOT BETWEEN 1 AND 9007199254740991
               OR (document #>> '{budgets,max_duration_seconds}')::numeric
                  NOT BETWEEN 1 AND 2147483
               OR jsonb_typeof(document #> '{budgets,max_cost_usd}')
                  <> 'number'
               OR (document #>> '{budgets,max_cost_usd}')::numeric < 0
               OR (document #>> '{budgets,max_cost_usd}')::numeric > 1000000
               OR (document #>> '{budgets,max_cost_usd}')::numeric <>
                  trunc(
                    (document #>> '{budgets,max_cost_usd}')::numeric,
                    6
                  )
             ) THEN
            RAISE EXCEPTION 'invalid released evaluation benchmark budget'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.definition_kind = 'suite' AND (
               jsonb_typeof(document -> 'case_bindings') <> 'array'
               OR jsonb_array_length(document -> 'case_bindings') = 0
               OR (
                 SELECT count(*)
                 FROM jsonb_array_elements(
                   document -> 'case_bindings'
                 )
               ) <> (
                 SELECT count(DISTINCT binding ->> 'case_id')
                 FROM jsonb_array_elements(
                   document -> 'case_bindings'
                 ) AS binding
               )
               OR (
                 SELECT count(*)
                 FROM jsonb_array_elements(
                   document -> 'case_bindings'
                 )
               ) <> (
                 SELECT count(DISTINCT binding ->> 'case_digest')
                 FROM jsonb_array_elements(
                   document -> 'case_bindings'
                 ) AS binding
               )
               OR document ->> 'authority_class'
                  NOT IN ('vinfast-acceptance', 'public-diagnostic')
               OR btrim(coalesce(document ->> 'qualification_profile', '')) = ''
               OR document ->> 'authority_record_digest'
                  !~ '^sha256:[a-f0-9]{64}$'
               OR document ->> 'qualification_policy_digest'
                  !~ '^sha256:[a-f0-9]{64}$'
               OR document ->> 'case_composition_digest'
                  !~ '^sha256:[a-f0-9]{64}$'
               OR document ->> 'risk_taxonomy_digest'
                  !~ '^sha256:[a-f0-9]{64}$'
               OR document ->> 'provenance_digest'
                  !~ '^sha256:[a-f0-9]{64}$'
               OR document ->> 'provenance_status' <> 'verified'
               OR document ->> 'provenance_evidence_uri'
                  NOT LIKE 'evidence://%'
               OR document ->> 'contamination_scan_digest'
                  !~ '^sha256:[a-f0-9]{64}$'
               OR document ->> 'contamination_status' <> 'passed'
               OR document ->> 'contamination_evidence_uri'
                  NOT LIKE 'evidence://%'
               OR jsonb_typeof(document -> 'held_out') <> 'boolean'
               OR btrim(coalesce(document ->> 'author_subject', '')) = ''
               OR btrim(coalesce(document ->> 'evaluator_subject', '')) = ''
               OR btrim(coalesce(document ->> 'release_owner_subject', '')) = ''
               OR document ->> 'release_owner_subject'
                  IS DISTINCT FROM NEW.released_by_subject
               OR document ->> 'author_subject'
                  = document ->> 'evaluator_subject'
               OR document ->> 'author_subject'
                  = document ->> 'release_owner_subject'
               OR document ->> 'evaluator_subject'
                  = document ->> 'release_owner_subject'
               OR (
                 document ->> 'authority_class' = 'vinfast-acceptance'
                 AND (
                   jsonb_array_length(document -> 'case_bindings') < 500
                   OR document -> 'held_out' <> 'true'::jsonb
                 )
               )
               OR document ->> 'suite_digest' <> (
                 'sha256:' || encode(
                   digest(
                     convert_to(
                       evaluation_canonical_json(document - 'suite_digest'),
                       'UTF8'
                     ),
                     'sha256'
                   ),
                   'hex'
                 )
               )
               OR NOT EXISTS (
                 SELECT 1
                 FROM ai_evaluation_definition_release authority
                 WHERE authority.definition_kind = 'suite-authority'
                   AND authority.definition_key = document ->> 'suite_id'
                   AND authority.revision =
                       document ->> 'authority_record_digest'
                   AND authority.revoked_at IS NULL
                   AND authority.released_by_subject =
                       document ->> 'release_owner_subject'
                   AND authority.canonical_payload::jsonb
                       ->> 'authority_digest' =
                       document ->> 'authority_record_digest'
                   AND authority.canonical_payload::jsonb
                       ->> 'authority_class' =
                       document ->> 'authority_class'
                   AND authority.canonical_payload::jsonb
                       ->> 'qualification_profile' =
                       document ->> 'qualification_profile'
                   AND authority.canonical_payload::jsonb
                       ->> 'qualification_policy_digest' =
                       document ->> 'qualification_policy_digest'
                   AND authority.canonical_payload::jsonb
                       ->> 'case_composition_digest' =
                       document ->> 'case_composition_digest'
                   AND authority.canonical_payload::jsonb
                       ->> 'risk_taxonomy_digest' =
                       document ->> 'risk_taxonomy_digest'
                   AND authority.canonical_payload::jsonb
                       ->> 'provenance_digest' =
                       document ->> 'provenance_digest'
                   AND authority.canonical_payload::jsonb
                       ->> 'provenance_evidence_uri' =
                       document ->> 'provenance_evidence_uri'
                   AND authority.canonical_payload::jsonb
                       ->> 'contamination_scan_digest' =
                       document ->> 'contamination_scan_digest'
                   AND authority.canonical_payload::jsonb
                       ->> 'contamination_evidence_uri' =
                       document ->> 'contamination_evidence_uri'
                   AND authority.canonical_payload::jsonb
                       ->> 'author_subject' =
                       document ->> 'author_subject'
                   AND authority.canonical_payload::jsonb
                       ->> 'evaluator_subject' =
                       document ->> 'evaluator_subject'
                   AND authority.canonical_payload::jsonb
                       ->> 'release_owner_subject' =
                       document ->> 'release_owner_subject'
                   AND authority.canonical_payload::jsonb
                       -> 'held_out' = document -> 'held_out'
                   AND authority.canonical_payload::jsonb
                       ->> 'case_bindings_digest' = (
                     'sha256:' || encode(
                       digest(
                         convert_to(
                           evaluation_canonical_json(
                             jsonb_build_object(
                               'case_bindings',
                               document -> 'case_bindings'
                             )
                           ),
                           'UTF8'
                         ),
                         'sha256'
                       ),
                       'hex'
                     )
                   )
               )
             ) THEN
            RAISE EXCEPTION 'invalid released evaluation suite authority'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.definition_kind = 'calibration'
             AND NOT evaluation_calibration_metrics_valid(document) THEN
            RAISE EXCEPTION 'invalid released grader calibration metrics'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.definition_kind = 'baseline-policy'
             AND NOT evaluation_baseline_policy_valid(document) THEN
            RAISE EXCEPTION 'invalid released evaluation baseline policy'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_definition_release_guard
        BEFORE INSERT OR UPDATE OR DELETE
        ON ai_evaluation_definition_release
        FOR EACH ROW EXECUTE FUNCTION evaluation_definition_release_validate()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_definition_release_no_truncate
        BEFORE TRUNCATE ON ai_evaluation_definition_release
        FOR EACH STATEMENT
        EXECUTE FUNCTION evaluation_case_result_reject_mutation()
        """
    )


def _replace_case_result_guard() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION evaluation_case_result_validate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          parent ai_evaluation_run%ROWTYPE;
          task ai_evaluation_case_task%ROWTYPE;
          expected_document jsonb;
          total_input_tokens bigint;
          total_output_tokens bigint;
          total_duration_ms bigint;
          total_cost_usd numeric;
        BEGIN
          SELECT * INTO parent
          FROM ai_evaluation_run
          WHERE run_key = NEW.run_key
          FOR UPDATE;
          IF parent.run_key IS NULL
             OR parent.status NOT IN ('running', 'grading') THEN
            RAISE EXCEPTION 'evaluation case results are not open'
              USING ERRCODE = '23514';
          END IF;

          SELECT * INTO task
          FROM ai_evaluation_case_task
          WHERE run_key = NEW.run_key AND case_key = NEW.case_key
          FOR UPDATE;
          IF task.run_key IS NULL
             OR task.case_digest <> NEW.case_digest
             OR task.status <> 'running'
             OR task.attempt_count <> NEW.attempt
             OR task.lease_owner <> NEW.lease_owner
             OR task.lease_token <> NEW.lease_token
             OR (
               task.lease_expires_at <= clock_timestamp()
               AND NOT (
                 NEW.status = 'failed'
                 AND NEW.validity_flags =
                   '["runner-unavailable", "usage-unknown"]'::jsonb
               )
             ) THEN
            RAISE EXCEPTION
              'evaluation case result requires exact active lease'
              USING ERRCODE = '23514';
          END IF;

          IF jsonb_typeof(NEW.usage) <> 'object'
             OR NEW.usage <> jsonb_build_object(
               'cost_usd', NEW.usage -> 'cost_usd',
               'input_tokens', NEW.usage -> 'input_tokens',
               'output_tokens', NEW.usage -> 'output_tokens'
             )
             OR jsonb_typeof(NEW.usage -> 'input_tokens') <> 'number'
             OR jsonb_typeof(NEW.usage -> 'output_tokens') <> 'number'
             OR jsonb_typeof(NEW.usage -> 'cost_usd') <> 'number'
             OR (NEW.usage ->> 'input_tokens') !~ '^[0-9]+$'
             OR (NEW.usage ->> 'output_tokens') !~ '^[0-9]+$'
             OR (NEW.usage ->> 'input_tokens')::numeric
                > 9007199254740991
             OR (NEW.usage ->> 'output_tokens')::numeric
                > 9007199254740991
             OR (NEW.usage ->> 'cost_usd')::numeric < 0
             OR (NEW.usage ->> 'cost_usd')::numeric > 1000000
             OR (NEW.usage ->> 'cost_usd')::numeric <>
                trunc((NEW.usage ->> 'cost_usd')::numeric, 6) THEN
            RAISE EXCEPTION 'invalid evaluation usage'
              USING ERRCODE = '23514';
          END IF;
          IF jsonb_typeof(NEW.grader_outputs) <> 'array'
             OR jsonb_typeof(NEW.metric_outputs) <> 'array'
             OR jsonb_typeof(NEW.validity_flags) <> 'array'
             OR EXISTS (
               SELECT 1
               FROM jsonb_array_elements(NEW.grader_outputs) AS item
               WHERE jsonb_typeof(item) <> 'object'
                 OR item <> jsonb_build_object(
                   'evidence_digest', item -> 'evidence_digest',
                   'grader_revision', item -> 'grader_revision',
                   'outcome', item -> 'outcome',
                   'score', item -> 'score'
                 )
                 OR item ->> 'grader_revision' IS NULL
                 OR item ->> 'outcome'
                    NOT IN ('pass', 'fail', 'abstain', 'invalid')
                 OR item ->> 'evidence_digest'
                    !~ '^sha256:[a-f0-9]{64}$'
             )
             OR (
               SELECT count(*) FROM jsonb_array_elements(NEW.grader_outputs)
             ) <> (
               SELECT count(DISTINCT item ->> 'grader_revision')
               FROM jsonb_array_elements(NEW.grader_outputs) AS item
             )
             OR EXISTS (
               SELECT 1
               FROM jsonb_array_elements(NEW.metric_outputs) AS item
               WHERE jsonb_typeof(item) <> 'object'
                 OR item <> jsonb_build_object(
                   'metric_revision', item -> 'metric_revision',
                   'slice', item -> 'slice',
                   'value', item -> 'value'
                 )
                 OR item ->> 'metric_revision' IS NULL
                 OR item ->> 'slice' IS NULL
                 OR jsonb_typeof(item -> 'value') <> 'number'
             )
             OR (
               SELECT count(*) FROM jsonb_array_elements(NEW.metric_outputs)
             ) <> (
               SELECT count(
                 DISTINCT (item ->> 'metric_revision', item ->> 'slice')
               )
               FROM jsonb_array_elements(NEW.metric_outputs) AS item
             )
             OR EXISTS (
               SELECT 1
               FROM jsonb_array_elements(NEW.validity_flags) AS flag
               WHERE jsonb_typeof(flag) <> 'string'
             )
             OR (
               SELECT count(*) FROM jsonb_array_elements(NEW.validity_flags)
             ) <> (
               SELECT count(DISTINCT flag)
               FROM jsonb_array_elements_text(NEW.validity_flags) AS flag
             ) THEN
            RAISE EXCEPTION 'invalid evaluation result documents'
              USING ERRCODE = '23514';
          END IF;
          IF (
               NEW.status = 'valid'
               AND (
                 NEW.output_digest IS NULL
                 OR jsonb_array_length(NEW.grader_outputs) = 0
                 OR jsonb_array_length(NEW.metric_outputs) = 0
                 OR jsonb_array_length(NEW.validity_flags) <> 0
               )
             )
             OR (
               NEW.status IN ('failed', 'cancelled')
               AND (
                 NEW.output_digest IS NOT NULL
                 OR jsonb_array_length(NEW.grader_outputs) <> 0
                 OR jsonb_array_length(NEW.metric_outputs) <> 0
               )
             )
             OR (
               NEW.status = 'invalid'
               AND jsonb_array_length(NEW.validity_flags) = 0
             ) THEN
            RAISE EXCEPTION 'evaluation result status invariant failed'
              USING ERRCODE = '23514';
          END IF;

          SELECT
            coalesce(sum((usage ->> 'input_tokens')::bigint), 0)
              + (NEW.usage ->> 'input_tokens')::bigint,
            coalesce(sum((usage ->> 'output_tokens')::bigint), 0)
              + (NEW.usage ->> 'output_tokens')::bigint,
            coalesce(sum(latency_ms), 0) + NEW.latency_ms,
            coalesce(sum((usage ->> 'cost_usd')::numeric), 0)
              + (NEW.usage ->> 'cost_usd')::numeric
          INTO total_input_tokens, total_output_tokens,
               total_duration_ms, total_cost_usd
          FROM ai_evaluation_case_result
          WHERE run_key = NEW.run_key;
          IF total_input_tokens
                > (parent.plan_document #>> '{budgets,maxInputTokens}')::bigint
             OR total_output_tokens
                > (parent.plan_document #>> '{budgets,maxOutputTokens}')::bigint
             OR total_duration_ms
                > (
                  (parent.plan_document #>>
                    '{budgets,maxDurationSeconds}')::bigint * 1000
                )
             OR total_cost_usd
                > (parent.plan_document #>> '{budgets,maxCostUsd}')::numeric
          THEN
            RAISE EXCEPTION 'evaluation case budget would be exceeded'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.validity_flags =
               '["runner-unavailable", "usage-unknown"]'::jsonb
             AND (
               total_input_tokens <>
                 (parent.plan_document #>>
                   '{budgets,maxInputTokens}')::bigint
               OR total_output_tokens <>
                 (parent.plan_document #>>
                   '{budgets,maxOutputTokens}')::bigint
               OR total_duration_ms <>
                 (
                   (parent.plan_document #>>
                     '{budgets,maxDurationSeconds}')::bigint * 1000
                 )
               OR total_cost_usd <>
                 (parent.plan_document #>>
                   '{budgets,maxCostUsd}')::numeric
             ) THEN
            RAISE EXCEPTION
              'unknown evaluation usage must reserve remaining budget'
              USING ERRCODE = '23514';
          END IF;

          expected_document := jsonb_build_object(
            'attempt', NEW.attempt,
            'case_digest', NEW.case_digest,
            'case_id', NEW.case_key,
            'grader_outputs', NEW.grader_outputs,
            'latency_ms', NEW.latency_ms,
            'metric_outputs', NEW.metric_outputs,
            'output_digest', NEW.output_digest,
            'run_id', NEW.run_key,
            'sanitized_trace_ref', NEW.sanitized_trace_ref,
            'status', NEW.status,
            'usage', NEW.usage,
            'validity_flags', NEW.validity_flags
          );
          IF NEW.canonical_payload::jsonb <> expected_document
             OR NEW.canonical_payload
                <> evaluation_canonical_json(expected_document)
             OR NEW.result_digest <> (
               'sha256:' || encode(
                 digest(
                   convert_to(NEW.canonical_payload, 'UTF8'),
                   'sha256'
                 ),
                 'hex'
               )
             ) THEN
            RAISE EXCEPTION 'evaluation case canonical digest mismatch'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )


def _create_case_task_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION evaluation_case_task_validate_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          parent_status text;
          parent_plan jsonb;
          matching_result boolean;
          consumed_input_tokens bigint;
          consumed_output_tokens bigint;
          consumed_duration_ms bigint;
          consumed_cost_usd numeric;
          active_task_count integer;
        BEGIN
          IF TG_OP = 'INSERT' THEN
            SELECT status, plan_document
            INTO parent_status, parent_plan
            FROM ai_evaluation_run
            WHERE run_key = NEW.run_key
            FOR UPDATE;
            IF parent_status <> 'queued'
               OR NEW.status <> 'pending'
               OR NEW.attempt_count <> 0
               OR NEW.max_attempts <> (
                 parent_plan #>> '{attemptPolicy,maxAttempts}'
               )::integer
               OR NEW.suite_digest <> parent_plan #>> '{suite,digest}'
               OR NEW.lease_owner IS NOT NULL
               OR NEW.lease_token IS NOT NULL
               OR NEW.lease_expires_at IS NOT NULL THEN
              RAISE EXCEPTION
                'evaluation task insert does not match immutable plan'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'evaluation case tasks are immutable'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.run_key <> OLD.run_key
             OR NEW.case_key <> OLD.case_key
             OR NEW.case_digest <> OLD.case_digest
             OR NEW.suite_digest <> OLD.suite_digest
             OR NEW.shard_index <> OLD.shard_index
             OR NEW.max_attempts <> OLD.max_attempts
             OR NEW.created_at <> OLD.created_at THEN
            RAISE EXCEPTION 'evaluation case task identity is immutable'
              USING ERRCODE = '23514';
          END IF;
          IF OLD.status = 'pending' AND NEW.status = 'running' THEN
            SELECT status, plan_document
            INTO parent_status, parent_plan
            FROM ai_evaluation_run
            WHERE run_key = OLD.run_key
            FOR UPDATE;
            SELECT
              coalesce(sum((usage ->> 'input_tokens')::bigint), 0),
              coalesce(sum((usage ->> 'output_tokens')::bigint), 0),
              coalesce(sum(latency_ms), 0),
              coalesce(sum((usage ->> 'cost_usd')::numeric), 0)
            INTO consumed_input_tokens, consumed_output_tokens,
                 consumed_duration_ms, consumed_cost_usd
            FROM ai_evaluation_case_result
            WHERE run_key = OLD.run_key;
            SELECT count(*)::integer INTO active_task_count
            FROM ai_evaluation_case_task
            WHERE run_key = OLD.run_key AND status = 'running';
            IF NEW.attempt_count <> OLD.attempt_count + 1
               OR NEW.lease_owner IS NULL
               OR NEW.lease_token IS NULL
               OR NEW.lease_expires_at <= clock_timestamp()
               OR parent_status <> 'running'
               OR active_task_count <> 0
               OR consumed_input_tokens >= (
                    parent_plan #>> '{budgets,maxInputTokens}'
                  )::bigint
               OR consumed_output_tokens >= (
                    parent_plan #>> '{budgets,maxOutputTokens}'
                  )::bigint
               OR consumed_duration_ms >= (
                    (parent_plan #>> '{budgets,maxDurationSeconds}')::bigint
                    * 1000
                  )
               OR consumed_cost_usd >= (
                    parent_plan #>> '{budgets,maxCostUsd}'
                  )::numeric THEN
              RAISE EXCEPTION 'invalid evaluation task claim'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.status = 'running' AND NEW.status = 'pending' THEN
            SELECT plan_document INTO parent_plan
            FROM ai_evaluation_run WHERE run_key = OLD.run_key;
            SELECT true INTO matching_result
            FROM ai_evaluation_case_result
            WHERE run_key = OLD.run_key
              AND case_key = OLD.case_key
              AND attempt = OLD.attempt_count
              AND lease_owner = OLD.lease_owner
              AND lease_token = OLD.lease_token
              AND status = 'failed'
              AND jsonb_array_length(validity_flags) = 1
              AND validity_flags ->> 0 IN (
                SELECT jsonb_array_elements_text(
                  parent_plan #> '{attemptPolicy,retryableFailureCodes}'
                )
              )
              AND NOT validity_flags ? 'usage-unknown'
            LIMIT 1;
            IF matching_result IS NOT TRUE
               OR NEW.attempt_count <> OLD.attempt_count
               OR NEW.attempt_count >= NEW.max_attempts
               OR NEW.lease_owner IS NOT NULL
               OR NEW.lease_token IS NOT NULL
               OR NEW.lease_expires_at IS NOT NULL
               OR NEW.completed_at IS NOT NULL THEN
              RAISE EXCEPTION 'invalid evaluation task retry'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.status = 'running' AND NEW.status = 'completed' THEN
            SELECT true INTO matching_result
            FROM ai_evaluation_case_result
            WHERE run_key = OLD.run_key
              AND case_key = OLD.case_key
              AND attempt = OLD.attempt_count
              AND lease_owner = OLD.lease_owner
              AND lease_token = OLD.lease_token
            LIMIT 1;
            IF matching_result IS NOT TRUE
               OR NEW.attempt_count <> OLD.attempt_count THEN
              RAISE EXCEPTION
                'task completion requires exact leased result'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.status = 'cancelled'
             AND OLD.status IN ('pending', 'running') THEN
            SELECT status INTO parent_status
            FROM ai_evaluation_run WHERE run_key = OLD.run_key;
            IF parent_status <> 'cancelled' THEN
              RAISE EXCEPTION 'task cancellation requires cancelled run'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.status = 'running' AND NEW.status = 'failed' THEN
            SELECT plan_document INTO parent_plan
            FROM ai_evaluation_run WHERE run_key = OLD.run_key;
            SELECT true INTO matching_result
            FROM ai_evaluation_case_result
            WHERE run_key = OLD.run_key
              AND case_key = OLD.case_key
              AND attempt = OLD.attempt_count
              AND lease_owner = OLD.lease_owner
              AND lease_token = OLD.lease_token
              AND status = 'failed'
              AND validity_flags =
                '["runner-unavailable", "usage-unknown"]'::jsonb
            LIMIT 1;
            IF OLD.lease_expires_at > clock_timestamp()
               OR matching_result IS NOT TRUE THEN
              RAISE EXCEPTION
                'task failure requires expired lease with unknown usage'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'illegal evaluation task transition'
            USING ERRCODE = '23514';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_case_task_guard
        BEFORE INSERT OR UPDATE OR DELETE ON ai_evaluation_case_task
        FOR EACH ROW EXECUTE FUNCTION evaluation_case_task_validate_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_case_task_reject_truncate
        BEFORE TRUNCATE ON ai_evaluation_case_task
        FOR EACH STATEMENT
        EXECUTE FUNCTION evaluation_case_result_reject_mutation()
        """
    )


def _create_run_authority_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION evaluation_run_guard_authority()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          active_count integer;
          released_benchmark_document jsonb;
        BEGIN
          IF TG_OP = 'INSERT' THEN
            IF NEW.plan_document IS NULL
               OR NEW.plan_digest IS DISTINCT FROM (
                 'sha256:' || encode(
                   digest(
                     convert_to(
                       evaluation_canonical_json(NEW.plan_document),
                       'UTF8'
                     ),
                     'sha256'
                   ),
                   'hex'
                 )
               )
               OR NEW.status <> 'requested'
               OR NEW.row_version <> 0
               OR NEW.run_key IS DISTINCT FROM
                  NEW.plan_document ->> 'runId'
               OR NEW.authority_class IS DISTINCT FROM
                  NEW.plan_document ->> 'authorityClass'
               OR NEW.candidate_release_ref IS DISTINCT FROM
                  NEW.plan_document #>> '{candidate,releaseId}'
               OR NEW.candidate_manifest_digest IS DISTINCT FROM
                  NEW.plan_document #>> '{candidate,manifestDigest}'
               OR NEW.baseline_release_ref IS DISTINCT FROM
                  NEW.plan_document #>> '{baseline,releaseId}'
               OR NEW.baseline_manifest_digest IS DISTINCT FROM
                  NEW.plan_document #>> '{baseline,manifestDigest}'
               OR NEW.benchmark_definition_digest IS DISTINCT FROM
                  NEW.plan_document ->> 'benchmarkDefinitionDigest'
               OR NEW.suite_revision IS DISTINCT FROM
                  NEW.plan_document #>> '{suite,id}'
               OR NEW.metrics IS DISTINCT FROM jsonb_build_object(
                  'revisions',
                  NEW.plan_document -> 'metricRevisions'
               ) THEN
              RAISE EXCEPTION
                'evaluation run insert does not match canonical plan'
                USING ERRCODE = '23514';
            END IF;

            SELECT count(*) INTO active_count
            FROM ai_evaluation_definition_release
            WHERE definition_kind = 'benchmark'
              AND revoked_at IS NULL
              AND canonical_payload::jsonb ->> 'definition_digest'
                  = NEW.plan_document ->> 'benchmarkDefinitionDigest';
            IF active_count <> 1 THEN
              RAISE EXCEPTION
                'evaluation run requires exact released benchmark'
                USING ERRCODE = '23514';
            END IF;
            SELECT canonical_payload::jsonb
            INTO released_benchmark_document
            FROM ai_evaluation_definition_release
            WHERE definition_kind = 'benchmark'
              AND revoked_at IS NULL
              AND canonical_payload::jsonb ->> 'definition_digest'
                  = NEW.plan_document ->> 'benchmarkDefinitionDigest'
            LIMIT 1;
            IF released_benchmark_document IS NULL
               OR NEW.plan_document ->> 'authorityClass'
                  IS DISTINCT FROM
                  released_benchmark_document ->> 'authority_class'
               OR NEW.plan_document #>> '{suite,id}'
                  IS DISTINCT FROM
                  released_benchmark_document ->> 'suite_id'
               OR NEW.plan_document #>> '{suite,digest}'
                  IS DISTINCT FROM
                  released_benchmark_document ->> 'suite_digest'
               OR NEW.plan_document ->> 'runnerImageDigest'
                  IS DISTINCT FROM
                  released_benchmark_document ->> 'runner_image_digest'
               OR NEW.plan_document ->> 'harnessRevision'
                  IS DISTINCT FROM
                  released_benchmark_document ->> 'harness_revision'
               OR NEW.plan_document -> 'toolSimulatorRevision'
                  IS DISTINCT FROM
                  released_benchmark_document -> 'tool_simulator_revision'
               OR NEW.plan_document -> 'metricRevisions'
                  IS DISTINCT FROM
                  released_benchmark_document -> 'metric_revisions'
               OR NEW.plan_document -> 'graderRevisions'
                  IS DISTINCT FROM
                  released_benchmark_document -> 'grader_revisions'
               OR NEW.plan_document ->> 'environmentRevision'
                  IS DISTINCT FROM
                  released_benchmark_document ->> 'environment_revision'
               OR NEW.plan_document ->> 'baselinePolicyDigest'
                  IS DISTINCT FROM
                  released_benchmark_document ->> 'baseline_policy_digest'
               OR NEW.plan_document -> 'budgets'
                  IS DISTINCT FROM jsonb_build_object(
                    'maxCostUsd',
                    released_benchmark_document #> '{budgets,max_cost_usd}',
                    'maxDurationSeconds',
                    released_benchmark_document
                      #> '{budgets,max_duration_seconds}',
                    'maxInputTokens',
                    released_benchmark_document #> '{budgets,max_input_tokens}',
                    'maxOutputTokens',
                    released_benchmark_document
                      #> '{budgets,max_output_tokens}'
                  )
               OR NEW.plan_document -> 'attemptPolicy'
                  IS DISTINCT FROM jsonb_build_object(
                    'maxAttempts',
                    released_benchmark_document -> 'max_attempts',
                    'retryableFailureCodes',
                    released_benchmark_document -> 'retryable_failure_codes'
                  ) THEN
              RAISE EXCEPTION
                'evaluation run plan diverges from released benchmark'
                USING ERRCODE = '23514';
            END IF;
            IF jsonb_array_length(
                 NEW.plan_document -> 'graderCalibrations'
               ) <> jsonb_array_length(
                 NEW.plan_document -> 'graderRevisions'
               )
               OR jsonb_array_length(
                 NEW.plan_document -> 'graderKinds'
               ) <> jsonb_array_length(
                 NEW.plan_document -> 'graderRevisions'
               )
               OR (
                 SELECT count(DISTINCT binding ->> 'graderRevision')
                 FROM jsonb_array_elements(
                   NEW.plan_document -> 'graderCalibrations'
                 ) AS binding
               ) <> jsonb_array_length(
                 NEW.plan_document -> 'graderRevisions'
               )
               OR (
                 SELECT count(DISTINCT binding ->> 'revision')
                 FROM jsonb_array_elements(
                   NEW.plan_document -> 'graderKinds'
                 ) AS binding
               ) <> jsonb_array_length(
                 NEW.plan_document -> 'graderRevisions'
               )
               OR EXISTS (
                 SELECT 1
                 FROM jsonb_array_elements_text(
                   NEW.plan_document -> 'graderRevisions'
                 ) AS required(revision)
                 WHERE NOT EXISTS (
                   SELECT 1
                   FROM jsonb_array_elements(
                     NEW.plan_document -> 'graderCalibrations'
                   ) AS binding
                   WHERE binding ->> 'graderRevision'
                         = required.revision
                 )
               )
               OR EXISTS (
                 SELECT 1
                 FROM jsonb_array_elements_text(
                   NEW.plan_document -> 'graderRevisions'
                 ) AS required(revision)
                 WHERE NOT EXISTS (
                   SELECT 1
                   FROM jsonb_array_elements(
                     NEW.plan_document -> 'graderKinds'
                   ) AS binding
                   WHERE binding ->> 'revision' = required.revision
                 )
               )
               OR EXISTS (
                 SELECT 1
                 FROM jsonb_array_elements(
                   NEW.plan_document -> 'graderCalibrations'
                 ) AS binding
                 WHERE NOT EXISTS (
                   SELECT 1
                   FROM ai_evaluation_definition_release calibration
                   JOIN ai_evaluation_definition_release grader
                     ON grader.definition_kind = 'grader'
                    AND grader.definition_key =
                        binding ->> 'graderRevision'
                    AND grader.revision =
                        binding ->> 'graderRevision'
                    AND grader.revoked_at IS NULL
                   WHERE calibration.definition_kind = 'calibration'
                     AND calibration.definition_key =
                         binding ->> 'graderRevision'
                     AND calibration.revision =
                         binding ->> 'calibrationDigest'
                     AND calibration.revoked_at IS NULL
                     AND calibration.canonical_payload::jsonb
                           ->> 'grader_definition_digest'
                         = binding ->> 'definitionDigest'
                     AND calibration.canonical_payload::jsonb
                           ->> 'implementation_digest'
                         = binding ->> 'implementationDigest'
                     AND calibration.canonical_payload::jsonb
                           ->> 'human_labelled_suite_digest'
                         = binding ->> 'humanLabelledSuiteDigest'
                     AND calibration.canonical_payload::jsonb
                           ->> 'calibrated_at'
                         = binding ->> 'calibratedAt'
                     AND calibration.canonical_payload::jsonb
                           ->> 'expires_at'
                         = binding ->> 'expiresAt'
                     AND (binding ->> 'calibratedAt')::timestamptz
                         <= clock_timestamp()
                     AND clock_timestamp()
                         < (binding ->> 'expiresAt')::timestamptz
                     AND grader.canonical_payload::jsonb
                           ->> 'definition_digest'
                         = binding ->> 'definitionDigest'
                     AND grader.canonical_payload::jsonb
                           ->> 'implementation_digest'
                         = binding ->> 'implementationDigest'
                 )
               )
               OR EXISTS (
                 SELECT 1
                 FROM jsonb_array_elements(
                   NEW.plan_document -> 'graderKinds'
                 ) AS binding
                 WHERE NOT EXISTS (
                   SELECT 1
                   FROM ai_evaluation_definition_release grader
                   WHERE grader.definition_kind = 'grader'
                     AND grader.definition_key = binding ->> 'revision'
                     AND grader.revision = binding ->> 'revision'
                     AND grader.revoked_at IS NULL
                     AND grader.canonical_payload::jsonb ->> 'kind'
                         = binding ->> 'kind'
                 )
               ) THEN
              RAISE EXCEPTION
                'evaluation run requires released grader calibration authority'
                USING ERRCODE = '23514';
            END IF;
            IF NOT EXISTS (
              SELECT 1
              FROM jsonb_array_elements(
                NEW.plan_document -> 'graderKinds'
              ) AS binding
              WHERE binding ->> 'kind' <> 'model-judge'
            ) THEN
              RAISE EXCEPTION
                'evaluation run requires non-model-judge authority'
                USING ERRCODE = '23514';
            END IF;

            SELECT count(*) INTO active_count
            FROM ai_evaluation_definition_release suite_release
            WHERE suite_release.definition_kind = 'suite'
              AND suite_release.definition_key =
                  NEW.plan_document #>> '{suite,id}'
              AND suite_release.revision =
                  NEW.plan_document #>> '{suite,digest}'
              AND suite_release.canonical_payload::jsonb
                  ->> 'authority_class'
                  = NEW.plan_document ->> 'authorityClass'
              AND (
                NEW.plan_document ->> 'authorityClass' <> 'vinfast-acceptance'
                OR (
                    jsonb_array_length(
                    suite_release.canonical_payload::jsonb
                      -> 'case_bindings'
                  ) >= 500
                  AND suite_release.canonical_payload::jsonb
                      -> 'held_out' = 'true'::jsonb
                )
              )
              AND EXISTS (
                SELECT 1
                FROM ai_evaluation_definition_release authority
                WHERE authority.definition_kind = 'suite-authority'
                  AND authority.definition_key =
                      suite_release.canonical_payload::jsonb
                        ->> 'suite_id'
                  AND authority.revision =
                      suite_release.canonical_payload::jsonb
                        ->> 'authority_record_digest'
                  AND authority.revoked_at IS NULL
              )
              AND suite_release.revoked_at IS NULL;
            IF active_count <> 1 THEN
              RAISE EXCEPTION
                'evaluation run requires exact released suite'
                USING ERRCODE = '23514';
            END IF;

            SELECT count(*) INTO active_count
            FROM ai_evaluation_definition_release
            WHERE definition_kind = 'baseline-policy'
              AND definition_key =
                  NEW.plan_document ->> 'baselinePolicyDigest'
              AND revision =
                  NEW.plan_document ->> 'baselinePolicyDigest'
              AND revoked_at IS NULL;
            IF active_count <> 1 THEN
              RAISE EXCEPTION
                'evaluation run requires exact released baseline policy'
                USING ERRCODE = '23514';
            END IF;

            IF EXISTS (
              SELECT 1
              FROM jsonb_array_elements_text(
                NEW.plan_document -> 'metricRevisions'
              ) AS required(revision)
              WHERE NOT EXISTS (
                SELECT 1
                FROM ai_evaluation_definition_release released
                WHERE released.definition_kind = 'metric'
                  AND released.definition_key = required.revision
                  AND released.revision = required.revision
                  AND released.revoked_at IS NULL
              )
            ) OR EXISTS (
              SELECT 1
              FROM jsonb_array_elements_text(
                NEW.plan_document -> 'graderRevisions'
              ) AS required(revision)
              WHERE NOT EXISTS (
                SELECT 1
                FROM ai_evaluation_definition_release released
                WHERE released.definition_kind = 'grader'
                  AND released.definition_key = required.revision
                  AND released.revision = required.revision
                  AND released.revoked_at IS NULL
              )
            ) THEN
              RAISE EXCEPTION
                'evaluation run requires all released metrics and graders'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.run_key IS NOT NULL AND (
            NEW.run_key IS DISTINCT FROM OLD.run_key
            OR NEW.plan_digest IS DISTINCT FROM OLD.plan_digest
            OR NEW.plan_document IS DISTINCT FROM OLD.plan_document
            OR NEW.authority_class IS DISTINCT FROM OLD.authority_class
            OR NEW.candidate_release_ref
               IS DISTINCT FROM OLD.candidate_release_ref
            OR NEW.candidate_manifest_digest
               IS DISTINCT FROM OLD.candidate_manifest_digest
            OR NEW.baseline_release_ref
               IS DISTINCT FROM OLD.baseline_release_ref
            OR NEW.baseline_manifest_digest
               IS DISTINCT FROM OLD.baseline_manifest_digest
            OR NEW.benchmark_definition_digest
               IS DISTINCT FROM OLD.benchmark_definition_digest
            OR NEW.suite_revision IS DISTINCT FROM OLD.suite_revision
          ) THEN
            RAISE EXCEPTION 'evaluation run authority is immutable'
              USING ERRCODE = '23514';
          END IF;
          IF OLD.status IN ('decision_ready', 'cancelled', 'failed', 'invalid')
             AND NEW IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'terminal evaluation run is immutable'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_evaluation_run_authority
        BEFORE INSERT OR UPDATE ON ai_evaluation_run
        FOR EACH ROW EXECUTE FUNCTION evaluation_run_guard_authority()
        """
    )


def _replace_evidence_guard() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION evaluation_evidence_bundle_validate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          parent ai_evaluation_run%ROWTYPE;
          suite_document jsonb;
          policy_document jsonb;
          run_result jsonb;
          expected_count integer;
          observed_count integer;
          invalid_count integer;
          binding_mismatch_count integer;
          grader_mismatch_count integer;
          metric_mismatch_count integer;
          protected_metric_mismatch_count integer;
          observed_case_results_digest text;
          input_tokens bigint;
          output_tokens bigint;
          duration_ms bigint;
          cost_usd numeric;
          hard_gate_failures jsonb;
          expected_recommendation text;
          expected_metrics jsonb;
          expected_evidence_digest text;
          expected_run_result jsonb;
          expected_report_digest text;
          expected_calibrations jsonb;
          expected_bundle jsonb;
          released_suite_document jsonb;
          released_policy_document jsonb;
          active_count integer;
        BEGIN
          SELECT * INTO parent
          FROM ai_evaluation_run
          WHERE run_key = NEW.run_key
          FOR UPDATE;
          IF parent.run_key IS NULL OR parent.status <> 'comparing'
             OR parent.plan_digest <> NEW.plan_digest
             OR parent.authority_class <> NEW.authority_class
             OR parent.row_version <> NEW.sealed_from_row_version THEN
            RAISE EXCEPTION 'evaluation evidence run binding mismatch'
              USING ERRCODE = '23514';
          END IF;
          suite_document := NEW.suite_snapshot_payload::jsonb;
          policy_document := NEW.baseline_policy_payload::jsonb;
          run_result := NEW.run_result_payload::jsonb;
          PERFORM 1
          FROM ai_evaluation_definition_release released
          WHERE released.revoked_at IS NULL
            AND (
              (
                released.definition_kind = 'benchmark'
                AND released.canonical_payload::jsonb
                      ->> 'definition_digest'
                    = parent.plan_document
                      ->> 'benchmarkDefinitionDigest'
              )
              OR (
                released.definition_kind = 'suite'
                AND released.definition_key =
                    parent.plan_document #>> '{suite,id}'
                AND released.revision =
                    parent.plan_document #>> '{suite,digest}'
              )
              OR (
                released.definition_kind = 'suite-authority'
                AND released.definition_key =
                    parent.plan_document #>> '{suite,id}'
                AND released.revision = (
                  SELECT suite_release.canonical_payload::jsonb
                           ->> 'authority_record_digest'
                  FROM ai_evaluation_definition_release suite_release
                  WHERE suite_release.definition_kind = 'suite'
                    AND suite_release.definition_key =
                        parent.plan_document #>> '{suite,id}'
                    AND suite_release.revision =
                        parent.plan_document #>> '{suite,digest}'
                    AND suite_release.revoked_at IS NULL
                )
              )
              OR (
                released.definition_kind = 'baseline-policy'
                AND released.definition_key =
                    parent.plan_document ->> 'baselinePolicyDigest'
                AND released.revision =
                    parent.plan_document ->> 'baselinePolicyDigest'
              )
              OR (
                released.definition_kind = 'metric'
                AND released.definition_key IN (
                  SELECT jsonb_array_elements_text(
                    parent.plan_document -> 'metricRevisions'
                  )
                )
              )
              OR (
                released.definition_kind = 'grader'
                AND released.definition_key IN (
                  SELECT jsonb_array_elements_text(
                    parent.plan_document -> 'graderRevisions'
                  )
                )
              )
              OR (
                released.definition_kind = 'calibration'
                AND EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements(
                    parent.plan_document -> 'graderCalibrations'
                  ) AS binding
                  WHERE released.definition_key =
                        binding ->> 'graderRevision'
                    AND released.revision =
                        binding ->> 'calibrationDigest'
                )
              )
            )
          FOR SHARE;
          SELECT count(*) INTO active_count
          FROM ai_evaluation_definition_release
          WHERE definition_kind = 'benchmark'
            AND revoked_at IS NULL
            AND canonical_payload::jsonb ->> 'definition_digest'
                = parent.plan_document ->> 'benchmarkDefinitionDigest';
          IF active_count <> 1
             OR EXISTS (
               SELECT 1
               FROM jsonb_array_elements_text(
                 parent.plan_document -> 'metricRevisions'
               ) AS required(revision)
               WHERE NOT EXISTS (
                 SELECT 1
                 FROM ai_evaluation_definition_release released
                 WHERE released.definition_kind = 'metric'
                   AND released.definition_key = required.revision
                   AND released.revision = required.revision
                   AND released.revoked_at IS NULL
               )
             ) THEN
            RAISE EXCEPTION
              'evaluation evidence released benchmark or metric unavailable'
              USING ERRCODE = '23514';
          END IF;
          SELECT canonical_payload::jsonb
          INTO released_suite_document
          FROM ai_evaluation_definition_release
          WHERE definition_kind = 'suite'
            AND definition_key = parent.plan_document #>> '{suite,id}'
            AND revision = parent.plan_document #>> '{suite,digest}'
            AND revoked_at IS NULL
          FOR SHARE;
          SELECT canonical_payload::jsonb
          INTO released_policy_document
          FROM ai_evaluation_definition_release
          WHERE definition_kind = 'baseline-policy'
            AND definition_key =
                parent.plan_document ->> 'baselinePolicyDigest'
            AND revision =
                parent.plan_document ->> 'baselinePolicyDigest'
            AND revoked_at IS NULL
          FOR SHARE;
          IF released_suite_document IS NULL
             OR released_policy_document IS NULL
             OR NOT EXISTS (
               SELECT 1
               FROM ai_evaluation_definition_release authority
               WHERE authority.definition_kind = 'suite-authority'
                 AND authority.definition_key =
                     parent.plan_document #>> '{suite,id}'
                 AND authority.revision =
                     released_suite_document
                       ->> 'authority_record_digest'
                 AND authority.revoked_at IS NULL
             )
             OR suite_document IS DISTINCT FROM
                (released_suite_document - 'suite_digest')
             OR policy_document IS DISTINCT FROM
                (released_policy_document - 'policy_digest')
             OR (
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
             OR NEW.recommendation NOT IN ('reject', 'needs-human-decision')
          THEN
            RAISE EXCEPTION 'evaluation evidence authority mismatch'
              USING ERRCODE = '23514';
          END IF;
          IF EXISTS (
               SELECT 1
               FROM jsonb_array_elements(
                 parent.plan_document -> 'graderCalibrations'
               ) AS binding
               WHERE NOT EXISTS (
                 SELECT 1
                 FROM ai_evaluation_definition_release calibration
                 JOIN ai_evaluation_definition_release grader
                   ON grader.definition_kind = 'grader'
                  AND grader.definition_key =
                      binding ->> 'graderRevision'
                  AND grader.revision = binding ->> 'graderRevision'
                  AND grader.revoked_at IS NULL
                 WHERE calibration.definition_kind = 'calibration'
                   AND calibration.definition_key =
                       binding ->> 'graderRevision'
                   AND calibration.revision =
                       binding ->> 'calibrationDigest'
                   AND calibration.revoked_at IS NULL
                   AND calibration.canonical_payload::jsonb
                         ->> 'grader_definition_digest'
                       = binding ->> 'definitionDigest'
                   AND calibration.canonical_payload::jsonb
                         ->> 'implementation_digest'
                       = binding ->> 'implementationDigest'
                   AND calibration.canonical_payload::jsonb
                         ->> 'human_labelled_suite_digest'
                       = binding ->> 'humanLabelledSuiteDigest'
                   AND calibration.canonical_payload::jsonb
                         ->> 'calibrated_at'
                       = binding ->> 'calibratedAt'
                   AND calibration.canonical_payload::jsonb
                         ->> 'expires_at'
                       = binding ->> 'expiresAt'
                   AND (binding ->> 'calibratedAt')::timestamptz
                       <= clock_timestamp()
                   AND clock_timestamp()
                       < (binding ->> 'expiresAt')::timestamptz
                   AND grader.canonical_payload::jsonb
                         ->> 'definition_digest'
                       = binding ->> 'definitionDigest'
                   AND grader.canonical_payload::jsonb
                         ->> 'implementation_digest'
                       = binding ->> 'implementationDigest'
               )
             )
             OR EXISTS (
               SELECT 1
               FROM jsonb_array_elements(
                 parent.plan_document -> 'graderKinds'
               ) AS binding
               WHERE NOT EXISTS (
                 SELECT 1
                 FROM ai_evaluation_definition_release grader
                 WHERE grader.definition_kind = 'grader'
                   AND grader.definition_key = binding ->> 'revision'
                   AND grader.revision = binding ->> 'revision'
                   AND grader.revoked_at IS NULL
                   AND grader.canonical_payload::jsonb ->> 'kind'
                       = binding ->> 'kind'
               )
             ) THEN
            RAISE EXCEPTION
              'evaluation evidence grader calibration authority mismatch'
              USING ERRCODE = '23514';
          END IF;
          IF NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(
              parent.plan_document -> 'graderKinds'
            ) AS binding
            WHERE binding ->> 'kind' <> 'model-judge'
          ) THEN
            RAISE EXCEPTION
              'evaluation evidence requires non-model-judge authority'
              USING ERRCODE = '23514';
          END IF;

          WITH latest AS (
            SELECT DISTINCT ON (case_key)
              case_key, case_digest, result_digest, status,
              grader_outputs, metric_outputs
            FROM ai_evaluation_case_result
            WHERE run_key = NEW.run_key
            ORDER BY case_key, attempt DESC
          ),
          expected AS (
            SELECT binding ->> 'case_id' AS case_key,
                   binding ->> 'case_digest' AS case_digest
            FROM jsonb_array_elements(
              suite_document -> 'case_bindings'
            ) AS binding
          ),
          required_graders AS (
            SELECT jsonb_array_elements_text(
              parent.plan_document -> 'graderRevisions'
            ) AS revision
          ),
          required_metrics AS (
            SELECT jsonb_array_elements_text(
              parent.plan_document -> 'metricRevisions'
            ) AS revision
          )
          SELECT
            (SELECT count(*)::integer FROM expected),
            (SELECT count(*)::integer FROM latest),
            (
              SELECT count(*)::integer FROM latest WHERE status <> 'valid'
            ),
            (
              SELECT count(*)::integer FROM (
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
                SELECT array_agg(item ->> 'grader_revision' ORDER BY 1)
                FROM jsonb_array_elements(latest.grader_outputs) AS item
              ) IS DISTINCT FROM (
                SELECT array_agg(revision ORDER BY revision)
                FROM required_graders
              )
            ),
            (
              SELECT count(*)::integer
              FROM latest
              WHERE (
                SELECT array_agg(
                  DISTINCT item ->> 'metric_revision'
                  ORDER BY item ->> 'metric_revision'
                )
                FROM jsonb_array_elements(latest.metric_outputs) AS item
              ) IS DISTINCT FROM (
                SELECT array_agg(revision ORDER BY revision)
                FROM required_metrics
              )
            ),
            (
              SELECT 'sha256:' || encode(
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
              FROM latest
            )
          INTO expected_count, observed_count, invalid_count,
               binding_mismatch_count, grader_mismatch_count,
               metric_mismatch_count, observed_case_results_digest;

          SELECT
            coalesce(sum((usage ->> 'input_tokens')::bigint), 0),
            coalesce(sum((usage ->> 'output_tokens')::bigint), 0),
            coalesce(sum(latency_ms), 0),
            coalesce(sum((usage ->> 'cost_usd')::numeric), 0)
          INTO input_tokens, output_tokens, duration_ms, cost_usd
          FROM ai_evaluation_case_result
          WHERE run_key = NEW.run_key;

          WITH latest AS (
            SELECT DISTINCT ON (case_key) grader_outputs
            FROM ai_evaluation_case_result
            WHERE run_key = NEW.run_key
            ORDER BY case_key, attempt DESC
          ),
          gates AS (
            SELECT item ->> 'gate_revision' AS revision
            FROM jsonb_array_elements(policy_document -> 'hard_gates') AS item
          )
          SELECT coalesce(jsonb_agg(revision ORDER BY revision), '[]'::jsonb)
          INTO hard_gate_failures
          FROM gates
          WHERE EXISTS (
            SELECT 1 FROM latest
            WHERE NOT EXISTS (
              SELECT 1
              FROM jsonb_array_elements(latest.grader_outputs) AS output
              WHERE output ->> 'grader_revision' = gates.revision
                AND output ->> 'outcome' = 'pass'
            )
          );
          expected_recommendation := CASE
            WHEN jsonb_array_length(hard_gate_failures) > 0 THEN 'reject'
            ELSE 'needs-human-decision'
          END;

          WITH latest AS (
            SELECT DISTINCT ON (case_key) case_key, metric_outputs
            FROM ai_evaluation_case_result
            WHERE run_key = NEW.run_key
            ORDER BY case_key, attempt DESC
          ),
          values AS (
            SELECT output ->> 'metric_revision' AS revision,
                   output ->> 'slice' AS slice_name,
                   (output ->> 'value')::numeric AS value
            FROM latest, jsonb_array_elements(metric_outputs) AS output
          ),
          protected AS (
            SELECT metric ->> 'metric_revision' AS revision,
                   jsonb_array_elements_text(
                     metric -> 'required_slices'
                   ) AS slice_name
            FROM jsonb_array_elements(
              policy_document -> 'protected_metrics'
            ) AS metric
          ),
          aggregated AS (
            SELECT revision, slice_name, count(*)::integer AS sample_size,
                   avg(value) AS raw_value,
                   bool_and(value IN (0, 1)) AS binary_samples
            FROM values GROUP BY revision, slice_name
          )
          SELECT jsonb_agg(
            jsonb_build_object(
              'lower_95', CASE
                WHEN protected.revision IS NULL THEN NULL
                ELSE round(greatest(
                  0::numeric,
                  (
                    aggregated.raw_value
                    + (3.8414588206941254 / (2 * aggregated.sample_size))
                    - 1.959963984540054 * sqrt(
                      (
                        aggregated.raw_value * (1 - aggregated.raw_value)
                        / aggregated.sample_size
                      )
                      + (
                        3.8414588206941254
                        / (
                          4 * aggregated.sample_size
                          * aggregated.sample_size
                        )
                      )
                    )
                  )
                  / (
                    1
                    + (3.8414588206941254 / aggregated.sample_size)
                  )
                ), 15)
              END,
              'metric_revision', aggregated.revision,
              'sample_size', aggregated.sample_size,
              'slice', aggregated.slice_name,
              'upper_95', CASE
                WHEN protected.revision IS NULL THEN NULL
                ELSE round(least(
                  1::numeric,
                  (
                    aggregated.raw_value
                    + (3.8414588206941254 / (2 * aggregated.sample_size))
                    + 1.959963984540054 * sqrt(
                      (
                        aggregated.raw_value * (1 - aggregated.raw_value)
                        / aggregated.sample_size
                      )
                      + (
                        3.8414588206941254
                        / (
                          4 * aggregated.sample_size
                          * aggregated.sample_size
                        )
                      )
                    )
                  )
                  / (
                    1
                    + (3.8414588206941254 / aggregated.sample_size)
                  )
                ), 15)
              END,
              'value', round(aggregated.raw_value, 15)
            )
            ORDER BY aggregated.revision, aggregated.slice_name
          ),
          (
            SELECT count(*)::integer
            FROM protected
            LEFT JOIN aggregated
              ON aggregated.revision = protected.revision
             AND aggregated.slice_name = protected.slice_name
            WHERE aggregated.revision IS NULL
               OR aggregated.binary_samples IS NOT TRUE
          )
          INTO expected_metrics, protected_metric_mismatch_count
          FROM aggregated
          LEFT JOIN protected
            ON aggregated.revision = protected.revision
           AND aggregated.slice_name = protected.slice_name;

          expected_evidence_digest := 'sha256:' || encode(
            digest(
              convert_to(
                '{"baseline_policy_digest":' ||
                to_json(parent.plan_document ->> 'baselinePolicyDigest')::text ||
                ',"case_results_digest":' ||
                to_json(observed_case_results_digest)::text ||
                ',"plan_digest":' || to_json(parent.plan_digest)::text ||
                ',"suite_digest":' ||
                to_json(parent.plan_document #>> '{suite,digest}')::text ||
                '}',
                'UTF8'
              ),
              'sha256'
            ),
            'hex'
          );
          expected_run_result := jsonb_build_object(
            'budget_usage', jsonb_build_object(
              'cost_usd', cost_usd,
              'duration_seconds', duration_ms::numeric / 1000,
              'input_tokens', input_tokens,
              'output_tokens', output_tokens
            ),
            'case_counts', jsonb_build_object(
              'cancelled', 0,
              'evaluated', observed_count,
              'expected', expected_count,
              'failed', 0,
              'invalid', 0,
              'valid', observed_count
            ),
            'case_results_digest', observed_case_results_digest,
            'completed_at', NEW.canonical_document ->> 'created_at',
            'evidence_digest', expected_evidence_digest,
            'hard_gate_failures', hard_gate_failures,
            'metrics', expected_metrics,
            'request_digest', parent.plan_digest,
            'run_id', parent.run_key,
            'started_at', parent.plan_document ->> 'requestedAt',
            'state', 'decision_ready'
          );
          expected_report_digest := 'sha256:' || encode(
            digest(
              convert_to(
                '{"case_results_digest":' ||
                to_json(observed_case_results_digest)::text ||
                ',"evidence_digest":' ||
                to_json(expected_evidence_digest)::text ||
                ',"run_result_digest":' ||
                to_json(NEW.run_result_digest)::text ||
                '}',
                'UTF8'
              ),
              'sha256'
            ),
            'hex'
          );
          SELECT jsonb_agg(
            jsonb_build_object(
              'calibration_digest', item ->> 'calibrationDigest',
              'grader_revision', item ->> 'graderRevision'
            )
            ORDER BY item ->> 'graderRevision'
          )
          INTO expected_calibrations
          FROM jsonb_array_elements(
            parent.plan_document -> 'graderCalibrations'
          ) AS item;
          expected_bundle := jsonb_build_object(
            'authority_class', parent.authority_class,
            'baseline_policy_digest',
              parent.plan_document ->> 'baselinePolicyDigest',
            'baseline_release', CASE
              WHEN parent.baseline_release_ref IS NULL THEN NULL
              ELSE jsonb_build_object(
                'manifest_digest', parent.baseline_manifest_digest,
                'release_id', parent.baseline_release_ref
              )
            END,
            'benchmark_definition_digest',
              parent.benchmark_definition_digest,
            'bundle_id', 'bundle:' || encode(
              digest(convert_to(parent.run_key, 'UTF8'), 'sha256'),
              'hex'
            ),
            'candidate_release', jsonb_build_object(
              'manifest_digest', parent.candidate_manifest_digest,
              'release_id', parent.candidate_release_ref
            ),
            'case_results_digest', observed_case_results_digest,
            'case_set_complete', true,
            'created_at', run_result ->> 'completed_at',
            'grader_calibrations', expected_calibrations,
            'hard_gate_failures', hard_gate_failures,
            'human_approval_included', false,
            'recommendation', expected_recommendation,
            'required_grader_revisions',
              parent.plan_document -> 'graderRevisions',
            'run_request_digest', parent.plan_digest,
            'run_result', expected_run_result,
            'run_result_digest', NEW.run_result_digest,
            'sanitized_report_digest', expected_report_digest,
            'suite_revision', jsonb_build_object(
              'suite_digest', parent.plan_document #>> '{suite,digest}',
              'suite_id', parent.plan_document #>> '{suite,id}'
            )
          );

          IF NEW.suite_snapshot_payload
                <> evaluation_canonical_json(suite_document)
             OR NEW.baseline_policy_payload
                <> evaluation_canonical_json(policy_document)
             OR NEW.run_result_payload
                <> evaluation_canonical_json(expected_run_result)
             OR NEW.canonical_payload
                <> evaluation_canonical_json(expected_bundle)
             OR expected_count = 0
             OR observed_count <> expected_count
             OR observed_count <> parent.completed_case_count
             OR invalid_count <> 0
             OR binding_mismatch_count <> 0
             OR grader_mismatch_count <> 0
             OR metric_mismatch_count <> 0
             OR protected_metric_mismatch_count <> 0
             OR EXISTS (
               SELECT 1 FROM ai_evaluation_case_task
               WHERE run_key = NEW.run_key AND status <> 'completed'
             )
             OR observed_case_results_digest <> NEW.case_results_digest
             OR run_result <> expected_run_result
             OR NEW.run_result_digest <> (
               'sha256:' || encode(
                 digest(
                   convert_to(NEW.run_result_payload, 'UTF8'),
                   'sha256'
                 ),
                 'hex'
               )
             )
             OR NEW.recommendation <> expected_recommendation
             OR NEW.canonical_document -> 'hard_gate_failures'
                <> hard_gate_failures
             OR NEW.canonical_document -> 'run_result'
                <> expected_run_result
             OR NEW.canonical_document ->> 'run_result_digest'
                <> NEW.run_result_digest
             OR NEW.canonical_document ->> 'recommendation'
                <> expected_recommendation
             OR NEW.canonical_document - 'bundle_digest'
                <> expected_bundle
          THEN
            RAISE EXCEPTION 'evaluation evidence semantic recomputation failed'
              USING DETAIL = concat_ws(
                ',',
                CASE WHEN NEW.suite_snapshot_payload
                  <> evaluation_canonical_json(suite_document)
                  THEN 'suite-canonical' END,
                CASE WHEN NEW.baseline_policy_payload
                  <> evaluation_canonical_json(policy_document)
                  THEN 'policy-canonical' END,
                CASE WHEN NEW.run_result_payload
                  <> evaluation_canonical_json(expected_run_result)
                  THEN 'run-result-canonical' END,
                CASE WHEN NEW.canonical_payload
                  <> evaluation_canonical_json(expected_bundle)
                  THEN 'bundle-canonical' END,
                CASE WHEN run_result <> expected_run_result
                  THEN 'run-result-semantic' END,
                CASE WHEN NEW.canonical_document - 'bundle_digest'
                  <> expected_bundle THEN 'bundle-semantic' END
              ),
              ERRCODE = '23514';
          END IF;
          IF NEW.canonical_payload::jsonb
                <> (NEW.canonical_document - 'bundle_digest')
             OR NEW.bundle_digest <> (
               'sha256:' || encode(
                 digest(
                   convert_to(NEW.canonical_payload, 'UTF8'),
                   'sha256'
                 ),
                 'hex'
               )
             )
             OR NEW.canonical_document ->> 'bundle_digest'
                <> NEW.bundle_digest THEN
            RAISE EXCEPTION 'evaluation evidence canonical digest mismatch'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE ai_evaluation_run, ai_evaluation_case_task, "
            "ai_evaluation_case_result, ai_evaluation_evidence_bundle, "
            "ai_evaluation_definition_release "
            "IN ACCESS EXCLUSIVE MODE"
        )
    )
    retained = connection.execute(
        sa.text(
            """
            SELECT
              EXISTS (
                SELECT 1 FROM ai_evaluation_run WHERE run_key IS NOT NULL
              )
              OR EXISTS (SELECT 1 FROM ai_evaluation_case_task)
              OR EXISTS (SELECT 1 FROM ai_evaluation_case_result)
              OR EXISTS (SELECT 1 FROM ai_evaluation_evidence_bundle)
              OR EXISTS (SELECT 1 FROM ai_evaluation_definition_release)
            """
        )
    ).scalar_one()
    if retained:
        raise RuntimeError("cannot downgrade 20260731_0022 after governed evaluation use")

    op.execute("DROP SCHEMA IF EXISTS vfbiz_eval_runner CASCADE")
    op.execute("DROP SCHEMA IF EXISTS vfbiz_eval_sealer CASCADE")
    op.execute("DROP SCHEMA IF EXISTS vfbiz_eval_reader CASCADE")
    op.execute(
        """
        DO $$
        BEGIN
          EXECUTE format(
            'ALTER ROLE vfbiz_ai_evaluation_runner IN DATABASE %I '
            'RESET search_path',
            current_database()
          );
          EXECUTE format(
            'ALTER ROLE vfbiz_ai_evaluation_sealer IN DATABASE %I '
            'RESET search_path',
            current_database()
          );
          EXECUTE format(
            'ALTER ROLE vfbiz_ai_evaluation_reader IN DATABASE %I '
            'RESET search_path',
            current_database()
          );
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_ai_evaluation_run_authority ON ai_evaluation_run")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_evaluation_case_task_guard ON ai_evaluation_case_task"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_evaluation_case_task_reject_truncate "
        "ON ai_evaluation_case_task"
    )
    op.execute("DROP FUNCTION IF EXISTS evaluation_run_guard_authority()")
    op.execute("DROP FUNCTION IF EXISTS evaluation_case_task_validate_mutation()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_evaluation_definition_release_guard "
        "ON ai_evaluation_definition_release"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_evaluation_definition_release_no_truncate "
        "ON ai_evaluation_definition_release"
    )
    op.execute("DROP FUNCTION IF EXISTS evaluation_definition_release_validate()")
    op.drop_table("ai_evaluation_definition_release")
    op.execute("DROP FUNCTION IF EXISTS evaluation_calibration_metrics_valid(jsonb)")
    op.execute("DROP FUNCTION IF EXISTS evaluation_baseline_policy_valid(jsonb)")
    op.execute("DROP FUNCTION IF EXISTS evaluation_canonical_json(jsonb)")
    op.drop_constraint(
        "ck_ai_evaluation_case_result_metric_outputs",
        "ai_evaluation_case_result",
        type_="check",
    )
    op.drop_column("ai_evaluation_evidence_bundle", "run_result_payload")
    op.drop_column("ai_evaluation_case_result", "metric_outputs")
    op.drop_column("ai_evaluation_case_result", "lease_token")
    op.drop_column("ai_evaluation_case_result", "lease_owner")
