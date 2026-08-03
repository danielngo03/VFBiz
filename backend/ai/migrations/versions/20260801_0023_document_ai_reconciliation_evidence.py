"""Persist immutable Document AI reconciliation and extraction evidence.

Revision ID: 20260801_0023
Revises: 20260731_0022
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0023"
down_revision: str | None = "20260731_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_canonical_json_function()
    _create_reconciliation_claim_table()
    _create_operation_observation_table()
    _create_extraction_evidence_table()
    _create_reconciliation_failure_table()
    _create_immutable_guards()


def _create_canonical_json_function() -> None:
    op.execute(
        """
        CREATE FUNCTION document_ai_canonical_json(value jsonb)
        RETURNS text
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        AS $$
        DECLARE
          kind text;
          rendered text;
        BEGIN
          kind := jsonb_typeof(value);
          IF kind IN ('null', 'boolean', 'number', 'string') THEN
            RETURN value::text;
          END IF;
          IF kind = 'array' THEN
            SELECT '[' || coalesce(
              string_agg(
                document_ai_canonical_json(item),
                ',' ORDER BY ordinal
              ),
              ''
            ) || ']'
            INTO rendered
            FROM jsonb_array_elements(value) WITH ORDINALITY AS entry(item, ordinal);
            RETURN rendered;
          END IF;
          IF kind = 'object' THEN
            SELECT '{' || coalesce(
              string_agg(
                to_json(key)::text || ':' || document_ai_canonical_json(item),
                ',' ORDER BY key
              ),
              ''
            ) || '}'
            INTO rendered
            FROM jsonb_each(value) AS entry(key, item);
            RETURN rendered;
          END IF;
          RAISE EXCEPTION 'unsupported Document AI canonical JSON value'
            USING ERRCODE = '23514';
        END;
        $$;
        """
    )


def _create_operation_observation_table() -> None:
    op.create_table(
        "ai_document_operation_observation",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("operation_name", sa.String(512), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("observation_digest", sa.String(64), nullable=False),
        sa.Column("canonical_payload", sa.Text(), nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["idempotency_key"],
            ["ai_document_submission.idempotency_key"],
            name="fk_ai_document_operation_submission",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            "observation_digest",
            name="uq_ai_document_operation_observation_digest",
        ),
        sa.CheckConstraint(
            "idempotency_key ~ '^[a-f0-9]{64}$' "
            "AND observation_digest ~ '^[a-f0-9]{64}$'",
            name="ck_ai_document_operation_digests",
        ),
        sa.CheckConstraint(
            "state IN ('running','succeeded','failed','cancelled')",
            name="ck_ai_document_operation_state",
        ),
    )
    op.create_index(
        "uq_ai_document_operation_terminal",
        "ai_document_operation_observation",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("state IN ('succeeded','failed','cancelled')"),
    )


def _create_reconciliation_claim_table() -> None:
    op.create_table(
        "ai_document_reconciliation_claim",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("owner_token", sa.String(64), nullable=False),
        sa.Column("fencing_token", sa.Integer(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["idempotency_key"],
            ["ai_document_submission.idempotency_key"],
            name="fk_ai_document_reconciliation_claim_submission",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_ai_document_reconciliation_claim_idempotency_key",
        ),
        sa.CheckConstraint(
            "idempotency_key ~ '^[a-f0-9]{64}$' "
            "AND owner_token ~ '^[a-f0-9]{64}$' "
            "AND fencing_token >= 1 AND lease_until > claimed_at "
            "AND (released_at IS NULL OR released_at >= claimed_at)",
            name="ck_ai_document_reconciliation_claim_values",
        ),
    )


def _create_extraction_evidence_table() -> None:
    op.create_table(
        "ai_document_extraction_evidence",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("canonical_payload", sa.Text(), nullable=False),
        sa.Column("expected_page_count", sa.Integer(), nullable=False),
        sa.Column("review_required_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["idempotency_key"],
            ["ai_document_submission.idempotency_key"],
            name="fk_ai_document_extraction_submission",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_ai_document_extraction_idempotency_key",
        ),
        sa.UniqueConstraint(
            "evidence_digest",
            name="uq_ai_document_extraction_evidence_digest",
        ),
        sa.CheckConstraint(
            "idempotency_key ~ '^[a-f0-9]{64}$' "
            "AND evidence_digest ~ '^[a-f0-9]{64}$'",
            name="ck_ai_document_extraction_digests",
        ),
        sa.CheckConstraint(
            "expected_page_count BETWEEN 1 AND 500 "
            "AND review_required_count BETWEEN 0 AND expected_page_count",
            name="ck_ai_document_extraction_counts",
        ),
    )


def _create_reconciliation_failure_table() -> None:
    op.create_table(
        "ai_document_reconciliation_failure",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(80), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("disposition", sa.String(24), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("canonical_payload", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["idempotency_key"],
            ["ai_document_submission.idempotency_key"],
            name="fk_ai_document_reconciliation_failure_submission",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            "attempt",
            name="uq_ai_document_reconciliation_failure_attempt",
        ),
        sa.UniqueConstraint(
            "evidence_digest",
            name="uq_ai_document_reconciliation_failure_digest",
        ),
        sa.CheckConstraint(
            "idempotency_key ~ '^[a-f0-9]{64}$' "
            "AND evidence_digest ~ '^[a-f0-9]{64}$'",
            name="ck_ai_document_reconciliation_failure_digests",
        ),
        sa.CheckConstraint(
            "attempt BETWEEN 1 AND 3 "
            "AND failure_code ~ '^[A-Z][A-Z0-9_]{2,79}$' "
            "AND disposition IN ('retry-scheduled','quarantined')",
            name="ck_ai_document_reconciliation_failure_values",
        ),
        sa.CheckConstraint(
            "(disposition = 'retry-scheduled' AND retryable "
            "AND next_retry_at IS NOT NULL) "
            "OR (disposition = 'quarantined' AND next_retry_at IS NULL)",
            name="ck_ai_document_reconciliation_failure_schedule",
        ),
    )
    op.create_index(
        "uq_ai_document_reconciliation_failure_quarantine",
        "ai_document_reconciliation_failure",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("disposition = 'quarantined'"),
    )


def _create_immutable_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION document_ai_operation_observation_validate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          document jsonb;
          submitted jsonb;
          latest_reconciled_at timestamptz;
        BEGIN
          document := NEW.canonical_payload::jsonb;
          SELECT receipt_payload
          INTO submitted
          FROM ai_document_submission
          WHERE idempotency_key = NEW.idempotency_key
            AND state = 'submitted'
          FOR SHARE;
          SELECT max(reconciled_at)
          INTO latest_reconciled_at
          FROM ai_document_operation_observation
          WHERE idempotency_key = NEW.idempotency_key;
          IF submitted IS NULL
             OR NEW.canonical_payload <> document_ai_canonical_json(document)
             OR NEW.observation_digest <> encode(
                  digest(convert_to(NEW.canonical_payload, 'UTF8'), 'sha256'),
                  'hex'
                )
             OR NOT (document ?& ARRAY[
                  'schema_revision',
                  'idempotency_key',
                  'job_id',
                  'operation_name',
                  'input',
                  'output_prefix',
                  'processor_revision',
                  'page_count',
                  'fencing_token',
                  'state',
                  'submitted_at',
                  'reconciled_at',
                  'provider_error_code'
                ]::text[])
             OR document - ARRAY[
                  'schema_revision',
                  'idempotency_key',
                  'job_id',
                  'operation_name',
                  'input',
                  'output_prefix',
                  'processor_revision',
                  'page_count',
                  'fencing_token',
                  'state',
                  'submitted_at',
                  'reconciled_at',
                  'provider_error_code'
                ]::text[] <> '{}'::jsonb
             OR NOT ((document -> 'input') ?& ARRAY[
                  'uri',
                  'generation',
                  'metageneration',
                  'sha256',
                  'byte_size',
                  'crc32c'
                ]::text[])
             OR (document -> 'input') - ARRAY[
                  'uri',
                  'generation',
                  'metageneration',
                  'sha256',
                  'byte_size',
                  'crc32c'
                ]::text[] <> '{}'::jsonb
             OR NEW.idempotency_key IS DISTINCT FROM document ->> 'idempotency_key'
             OR NEW.operation_name IS DISTINCT FROM document ->> 'operation_name'
             OR NEW.state IS DISTINCT FROM document ->> 'state'
             OR NEW.reconciled_at IS DISTINCT FROM
                  (document ->> 'reconciled_at')::timestamptz
             OR document ->> 'schema_revision' <> 'document-ai-operation-v1'
             OR document ->> 'idempotency_key'
                  IS DISTINCT FROM submitted ->> 'idempotency_key'
             OR document ->> 'job_id' IS DISTINCT FROM submitted ->> 'job_id'
             OR document ->> 'operation_name'
                  IS DISTINCT FROM submitted ->> 'operation_name'
             OR document -> 'input' IS DISTINCT FROM submitted -> 'input'
             OR document ->> 'output_prefix'
                  IS DISTINCT FROM submitted ->> 'output_prefix'
             OR document ->> 'processor_revision'
                  IS DISTINCT FROM submitted ->> 'processor_revision'
             OR document -> 'page_count' IS DISTINCT FROM submitted -> 'page_count'
             OR document -> 'fencing_token'
                  IS DISTINCT FROM submitted -> 'fencing_token'
             OR (document ->> 'submitted_at')::timestamptz IS DISTINCT FROM
                  (submitted ->> 'submitted_at')::timestamptz
             OR NEW.reconciled_at < (submitted ->> 'submitted_at')::timestamptz
             OR (latest_reconciled_at IS NOT NULL
                 AND NEW.reconciled_at < latest_reconciled_at)
             OR (NEW.state = 'failed') IS DISTINCT FROM
                  (nullif(document ->> 'provider_error_code', '') IS NOT NULL)
             OR EXISTS (
                  SELECT 1
                  FROM ai_document_operation_observation
                  WHERE idempotency_key = NEW.idempotency_key
                    AND state IN ('succeeded','failed','cancelled')
                ) THEN
            RAISE EXCEPTION 'invalid Document AI operation observation'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        EXCEPTION
          WHEN invalid_text_representation OR datetime_field_overflow THEN
            RAISE EXCEPTION 'invalid Document AI operation observation'
              USING ERRCODE = '23514';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_ai_operation_observation_validate
        BEFORE INSERT ON ai_document_operation_observation
        FOR EACH ROW
        EXECUTE FUNCTION document_ai_operation_observation_validate();
        """
    )
    op.execute(
        """
        CREATE FUNCTION document_ai_extraction_evidence_validate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          document jsonb;
          submitted jsonb;
          succeeded jsonb;
          counted_reviews integer;
        BEGIN
          document := NEW.canonical_payload::jsonb;
          SELECT receipt_payload
          INTO submitted
          FROM ai_document_submission
          WHERE idempotency_key = NEW.idempotency_key
            AND state = 'submitted'
          FOR SHARE;
          SELECT canonical_payload::jsonb
          INTO succeeded
          FROM ai_document_operation_observation
          WHERE idempotency_key = NEW.idempotency_key
            AND state = 'succeeded';
          SELECT count(*)
          INTO counted_reviews
          FROM jsonb_array_elements(document -> 'pages') AS page
          WHERE page ->> 'disposition' = 'review-required';
          IF submitted IS NULL
             OR succeeded IS NULL
             OR NEW.canonical_payload <> document_ai_canonical_json(document)
             OR NEW.evidence_digest <> encode(
                  digest(convert_to(NEW.canonical_payload, 'UTF8'), 'sha256'),
                  'hex'
                )
             OR document ->> 'schema_revision'
                  <> 'document-ai-extraction-evidence-v1'
             OR NEW.idempotency_key IS DISTINCT FROM document ->> 'idempotency_key'
             OR NEW.expected_page_count IS DISTINCT FROM
                  (document ->> 'expected_page_count')::integer
             OR NEW.review_required_count IS DISTINCT FROM
                  (document ->> 'review_required_count')::integer
             OR document ->> 'idempotency_key'
                  IS DISTINCT FROM submitted ->> 'idempotency_key'
             OR document ->> 'job_id' IS DISTINCT FROM submitted ->> 'job_id'
             OR document ->> 'source_sha256'
                  IS DISTINCT FROM submitted #>> '{input,sha256}'
             OR document ->> 'processor_revision'
                  IS DISTINCT FROM submitted ->> 'processor_revision'
             OR document -> 'expected_page_count'
                  IS DISTINCT FROM submitted -> 'page_count'
             OR NOT (document ?& ARRAY[
                  'schema_revision',
                  'idempotency_key',
                  'job_id',
                  'source_sha256',
                  'processor_revision',
                  'expected_page_count',
                  'output_objects',
                  'pages',
                  'review_required_count'
                ]::text[])
             OR document - ARRAY[
                  'schema_revision',
                  'idempotency_key',
                  'job_id',
                  'source_sha256',
                  'processor_revision',
                  'expected_page_count',
                  'output_objects',
                  'pages',
                  'review_required_count'
                ]::text[] <> '{}'::jsonb
             OR jsonb_typeof(document -> 'output_objects') <> 'array'
             OR jsonb_array_length(document -> 'output_objects') = 0
             OR jsonb_array_length(document -> 'output_objects') > 1000
             OR jsonb_typeof(document -> 'pages') <> 'array'
             OR jsonb_array_length(document -> 'pages') <> NEW.expected_page_count
             OR counted_reviews <> NEW.review_required_count
             OR EXISTS (
                  SELECT 1
                  FROM generate_series(1, NEW.expected_page_count) AS expected(page_number)
                  WHERE (
                    SELECT count(*)
                    FROM jsonb_array_elements(document -> 'pages') AS page
                    WHERE (page ->> 'page_number')::integer = expected.page_number
                  ) <> 1
                )
             OR EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements(document -> 'pages') AS page
                  WHERE jsonb_typeof(page) IS DISTINCT FROM 'object'
                     OR NOT (page ?& ARRAY[
                          'page_number',
                          'text_sha256',
                          'text_byte_size',
                          'confidence_micros',
                          'disposition',
                          'warnings',
                          'output_uri',
                          'output_generation'
                        ]::text[])
                     OR page - ARRAY[
                          'page_number',
                          'text_sha256',
                          'text_byte_size',
                          'confidence_micros',
                          'disposition',
                          'warnings',
                          'output_uri',
                          'output_generation'
                        ]::text[] <> '{}'::jsonb
                     OR page ? 'text'
                     OR jsonb_typeof(page -> 'page_number')
                        IS DISTINCT FROM 'number'
                     OR jsonb_typeof(page -> 'text_sha256')
                        IS DISTINCT FROM 'string'
                     OR page ->> 'text_sha256' !~ '^[a-f0-9]{64}$'
                     OR jsonb_typeof(page -> 'text_byte_size')
                        IS DISTINCT FROM 'number'
                     OR (page ->> 'text_byte_size')::integer NOT BETWEEN 0 AND 8000000
                     OR NOT (
                          page -> 'confidence_micros' = 'null'::jsonb
                          OR (
                            jsonb_typeof(page -> 'confidence_micros') = 'number'
                            AND (page ->> 'confidence_micros')::integer
                              BETWEEN 0 AND 1000000
                          )
                        )
                     OR jsonb_typeof(page -> 'disposition')
                        IS DISTINCT FROM 'string'
                     OR page ->> 'disposition'
                        NOT IN ('document-ai','review-required')
                     OR jsonb_typeof(page -> 'warnings') <> 'array'
                     OR EXISTS (
                          SELECT 1
                          FROM jsonb_array_elements(page -> 'warnings') AS warning
                          WHERE jsonb_typeof(warning) IS DISTINCT FROM 'string'
                             OR warning #>> '{}' !~ '^[A-Z0-9_]{1,80}$'
                        )
                     OR (page ->> 'disposition' = 'review-required')
                        IS DISTINCT FROM (jsonb_array_length(page -> 'warnings') > 0)
                     OR jsonb_typeof(page -> 'output_uri')
                        IS DISTINCT FROM 'string'
                     OR left(
                          page ->> 'output_uri',
                          length(submitted ->> 'output_prefix')
                        ) IS DISTINCT FROM submitted ->> 'output_prefix'
                     OR jsonb_typeof(page -> 'output_generation')
                        IS DISTINCT FROM 'number'
                     OR NOT EXISTS (
                          SELECT 1
                          FROM jsonb_array_elements(document -> 'output_objects') AS output
                          WHERE output ->> 'uri' = page ->> 'output_uri'
                            AND output -> 'generation' = page -> 'output_generation'
                        )
                )
             OR EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements(document -> 'output_objects') AS output
                  WHERE jsonb_typeof(output) IS DISTINCT FROM 'object'
                     OR NOT (output ?& ARRAY[
                          'uri',
                          'generation',
                          'metageneration',
                          'byte_size',
                          'crc32c',
                          'sha256'
                        ]::text[])
                     OR output - ARRAY[
                          'uri',
                          'generation',
                          'metageneration',
                          'byte_size',
                          'crc32c',
                          'sha256'
                        ]::text[] <> '{}'::jsonb
                     OR jsonb_typeof(output -> 'sha256')
                        IS DISTINCT FROM 'string'
                     OR output ->> 'sha256' !~ '^[a-f0-9]{64}$'
                     OR jsonb_typeof(output -> 'crc32c')
                        IS DISTINCT FROM 'string'
                     OR output ->> 'crc32c' !~ '^[A-Za-z0-9+/]{6}==$'
                     OR jsonb_typeof(output -> 'uri')
                        IS DISTINCT FROM 'string'
                     OR output ->> 'uri' NOT LIKE 'gs://%/%.json'
                     OR left(
                          output ->> 'uri',
                          length(submitted ->> 'output_prefix')
                        ) IS DISTINCT FROM submitted ->> 'output_prefix'
                     OR output ->> 'uri' LIKE '%/../%'
                     OR output ->> 'uri' LIKE '%?%'
                     OR output ->> 'uri' LIKE '%#%'
                     OR jsonb_typeof(output -> 'generation')
                        IS DISTINCT FROM 'number'
                     OR (output ->> 'generation')::bigint < 1
                     OR jsonb_typeof(output -> 'metageneration')
                        IS DISTINCT FROM 'number'
                     OR (output ->> 'metageneration')::bigint < 1
                     OR jsonb_typeof(output -> 'byte_size')
                        IS DISTINCT FROM 'number'
                     OR (output ->> 'byte_size')::bigint NOT BETWEEN 1 AND 536870912
                )
             OR EXISTS (
                  SELECT 1
                  FROM ai_document_reconciliation_failure
                  WHERE idempotency_key = NEW.idempotency_key
                    AND disposition = 'quarantined'
                ) THEN
            RAISE EXCEPTION 'invalid Document AI extraction evidence'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        EXCEPTION
          WHEN invalid_text_representation OR numeric_value_out_of_range THEN
            RAISE EXCEPTION 'invalid Document AI extraction evidence'
              USING ERRCODE = '23514';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_ai_extraction_evidence_validate
        BEFORE INSERT ON ai_document_extraction_evidence
        FOR EACH ROW
        EXECUTE FUNCTION document_ai_extraction_evidence_validate();
        """
    )
    op.execute(
        """
        CREATE FUNCTION document_ai_reconciliation_failure_validate()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          document jsonb;
          submitted jsonb;
          expected_attempt integer;
        BEGIN
          document := NEW.canonical_payload::jsonb;
          SELECT receipt_payload
          INTO submitted
          FROM ai_document_submission
          WHERE idempotency_key = NEW.idempotency_key
            AND state = 'submitted'
          FOR SHARE;
          SELECT coalesce(max(attempt), 0) + 1
          INTO expected_attempt
          FROM ai_document_reconciliation_failure
          WHERE idempotency_key = NEW.idempotency_key;
          IF submitted IS NULL
             OR NEW.canonical_payload <> document_ai_canonical_json(document)
             OR NEW.evidence_digest <> encode(
                  digest(convert_to(NEW.canonical_payload, 'UTF8'), 'sha256'),
                  'hex'
                )
             OR NOT (document ?& ARRAY[
                  'schema_revision',
                  'idempotency_key',
                  'job_id',
                  'operation_name',
                  'attempt',
                  'failure_code',
                  'retryable',
                  'disposition',
                  'observed_at',
                  'next_retry_at'
                ]::text[])
             OR document - ARRAY[
                  'schema_revision',
                  'idempotency_key',
                  'job_id',
                  'operation_name',
                  'attempt',
                  'failure_code',
                  'retryable',
                  'disposition',
                  'observed_at',
                  'next_retry_at'
                ]::text[] <> '{}'::jsonb
             OR document ->> 'schema_revision'
                  <> 'document-ai-reconciliation-failure-v1'
             OR NEW.idempotency_key IS DISTINCT FROM document ->> 'idempotency_key'
             OR NEW.idempotency_key IS DISTINCT FROM submitted ->> 'idempotency_key'
             OR document ->> 'job_id' IS DISTINCT FROM submitted ->> 'job_id'
             OR document ->> 'operation_name'
                  IS DISTINCT FROM submitted ->> 'operation_name'
             OR NEW.attempt IS DISTINCT FROM (document ->> 'attempt')::integer
             OR NEW.attempt IS DISTINCT FROM expected_attempt
             OR NEW.failure_code IS DISTINCT FROM document ->> 'failure_code'
             OR NEW.retryable IS DISTINCT FROM (document ->> 'retryable')::boolean
             OR NEW.disposition IS DISTINCT FROM document ->> 'disposition'
             OR NEW.observed_at IS DISTINCT FROM
                  (document ->> 'observed_at')::timestamptz
             OR NEW.next_retry_at IS DISTINCT FROM
                  (document ->> 'next_retry_at')::timestamptz
             OR NEW.observed_at < (submitted ->> 'submitted_at')::timestamptz
             OR (NEW.retryable AND NEW.attempt < 3) IS DISTINCT FROM
                  (NEW.disposition = 'retry-scheduled')
             OR (NEW.disposition = 'retry-scheduled' AND
                  NEW.next_retry_at IS DISTINCT FROM
                    NEW.observed_at + make_interval(secs => 30 * power(2, NEW.attempt - 1)))
             OR (NEW.disposition = 'quarantined' AND NEW.next_retry_at IS NOT NULL)
             OR EXISTS (
                  SELECT 1
                  FROM ai_document_extraction_evidence
                  WHERE idempotency_key = NEW.idempotency_key
                )
             OR EXISTS (
                  SELECT 1
                  FROM ai_document_reconciliation_failure
                  WHERE idempotency_key = NEW.idempotency_key
                    AND disposition = 'quarantined'
                ) THEN
            RAISE EXCEPTION 'invalid Document AI reconciliation failure evidence'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        EXCEPTION
          WHEN invalid_text_representation
             OR datetime_field_overflow
             OR numeric_value_out_of_range THEN
            RAISE EXCEPTION 'invalid Document AI reconciliation failure evidence'
              USING ERRCODE = '23514';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_ai_reconciliation_failure_validate
        BEFORE INSERT ON ai_document_reconciliation_failure
        FOR EACH ROW
        EXECUTE FUNCTION document_ai_reconciliation_failure_validate();
        """
    )
    op.execute(
        """
        CREATE FUNCTION document_ai_reconciliation_reject_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'Document AI reconciliation evidence mutation refused'
            USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    for table in (
        "ai_document_operation_observation",
        "ai_document_extraction_evidence",
        "ai_document_reconciliation_failure",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_reject_update
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION document_ai_reconciliation_reject_mutation();
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_reject_delete
            BEFORE DELETE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION document_ai_reconciliation_reject_mutation();
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_reject_truncate
            BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT
            EXECUTE FUNCTION document_ai_reconciliation_reject_mutation();
            """
        )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM ai_document_operation_observation)
             OR EXISTS (SELECT 1 FROM ai_document_extraction_evidence)
             OR EXISTS (SELECT 1 FROM ai_document_reconciliation_failure)
             OR EXISTS (
                  SELECT 1
                  FROM ai_document_reconciliation_claim
                  WHERE released_at IS NULL
                    AND lease_until > clock_timestamp()
                ) THEN
            RAISE EXCEPTION
              'Document AI reconciliation evidence downgrade refused: persisted rows exist'
              USING ERRCODE = '55000';
          END IF;
        END;
        $$;
        """
    )
    for table in (
        "ai_document_reconciliation_failure",
        "ai_document_extraction_evidence",
        "ai_document_operation_observation",
    ):
        op.execute(f"DROP TRIGGER trg_{table}_reject_truncate ON {table}")
        op.execute(f"DROP TRIGGER trg_{table}_reject_delete ON {table}")
        op.execute(f"DROP TRIGGER trg_{table}_reject_update ON {table}")
    op.execute(
        "DROP TRIGGER trg_document_ai_reconciliation_failure_validate "
        "ON ai_document_reconciliation_failure"
    )
    op.execute("DROP FUNCTION document_ai_reconciliation_failure_validate()")
    op.execute(
        "DROP TRIGGER trg_document_ai_extraction_evidence_validate "
        "ON ai_document_extraction_evidence"
    )
    op.execute("DROP FUNCTION document_ai_extraction_evidence_validate()")
    op.execute(
        "DROP TRIGGER trg_document_ai_operation_observation_validate "
        "ON ai_document_operation_observation"
    )
    op.execute("DROP FUNCTION document_ai_operation_observation_validate()")
    op.execute("DROP FUNCTION document_ai_reconciliation_reject_mutation()")
    op.drop_index(
        "uq_ai_document_reconciliation_failure_quarantine",
        table_name="ai_document_reconciliation_failure",
    )
    op.drop_table("ai_document_reconciliation_failure")
    op.drop_table("ai_document_extraction_evidence")
    op.drop_index(
        "uq_ai_document_operation_terminal",
        table_name="ai_document_operation_observation",
    )
    op.drop_table("ai_document_operation_observation")
    op.drop_table("ai_document_reconciliation_claim")
    op.execute("DROP FUNCTION document_ai_canonical_json(jsonb)")
