"""Enforce Dataset Release provenance at the PostgreSQL promotion boundary.

Revision ID: 20260729_0018
Revises: 20260728_0017
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260729_0018"
down_revision: str | None = "20260728_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Guards are installed and used to validate existing governed rows before
    # SERIALIZABLE becomes mandatory. This keeps migration validation atomic
    # without leaving a caller-controlled bypass in the final schema.
    op.execute(
        """
        CREATE FUNCTION vfbiz_require_dataset_release_serializable()
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RETURN;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION vfbiz_guard_dataset_release_provenance()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            source_ref jsonb;
            source_row_id uuid;
            fetch_row_id uuid;
            requested_use text;
            source_digest text;
        BEGIN
            IF NEW.status NOT IN ('approved', 'released') THEN
                RETURN NEW;
            END IF;
            PERFORM vfbiz_require_dataset_release_serializable();
            IF NEW.approved IS NOT TRUE
               OR NEW.manifest_sha256 IS NULL
               OR jsonb_typeof(NEW.allowed_uses) IS DISTINCT FROM 'array'
               OR jsonb_array_length(NEW.allowed_uses) <> 1 THEN
                RAISE EXCEPTION
                    'dataset release provenance requires approved canonical manifest'
                    USING ERRCODE = '23514';
            END IF;
            requested_use := NEW.allowed_uses ->> 0;
            IF requested_use IS NULL
               OR requested_use = ''
               OR requested_use NOT IN (
                    'knowledge-index',
                    'classifier-training',
                    'sft',
                    'preference',
                    'embedding',
                    'reranker',
                    'evaluation',
                    'red-team'
               )
               OR NEW.purpose IS DISTINCT FROM requested_use
               OR jsonb_typeof(NEW.provenance -> 'sources') IS DISTINCT FROM 'array'
               OR jsonb_array_length(NEW.provenance -> 'sources') = 0 THEN
                RAISE EXCEPTION
                    'dataset release provenance requires one canonical use and sources'
                    USING ERRCODE = '23514';
            END IF;

            FOR source_ref IN
                SELECT value
                FROM jsonb_array_elements(NEW.provenance -> 'sources')
            LOOP
                IF btrim(COALESCE(source_ref ->> 'source_id', '')) = ''
                   OR btrim(COALESCE(source_ref ->> 'source_revision', '')) = ''
                   OR COALESCE(source_ref ->> 'artifact_digest', '')
                        !~ '^sha256:[a-f0-9]{64}$' THEN
                    RAISE EXCEPTION
                        'dataset release provenance source identity is invalid'
                        USING ERRCODE = '23514';
                END IF;
                source_digest := substring(
                    source_ref ->> 'artifact_digest'
                    FROM 8
                );
                source_row_id := NULL;
                SELECT src.id
                INTO source_row_id
                FROM ai_dataset_source AS src
                WHERE src.source_key = source_ref ->> 'source_id'
                  AND src.source_revision = source_ref ->> 'source_revision'
                  AND src.status = 'purpose-approved'
                  AND jsonb_typeof(src.proposed_uses) = 'array'
                  AND src.proposed_uses @> jsonb_build_array(requested_use)
                  AND jsonb_typeof(src.approved_uses) = 'array'
                  AND src.approved_uses @> jsonb_build_array(requested_use)
                  AND btrim(COALESCE(src.rights_evidence_ref, '')) <> ''
                  AND src.rights_evidence_sha256 ~ '^[a-f0-9]{64}$'
                  AND src.terms_sha256 ~ '^[a-f0-9]{64}$'
                FOR SHARE;
                IF source_row_id IS NULL THEN
                    RAISE EXCEPTION
                        'dataset release provenance source is not purpose-approved'
                        USING ERRCODE = '23514';
                END IF;

                fetch_row_id := NULL;
                SELECT fch.id
                INTO fetch_row_id
                FROM ai_dataset_fetch AS fch
                WHERE fch.source_id = source_row_id
                  AND fch.state = 'scan-passed'
                  AND btrim(COALESCE(fch.approval_evidence_ref, '')) <> ''
                  AND fch.approval_evidence_sha256 ~ '^[a-f0-9]{64}$'
                  AND fch.observed_sha256 = source_digest
                  AND fch.scan_evidence ->> 'artifact_sha256' = source_digest
                  AND btrim(
                        COALESCE(fch.scan_evidence ->> 'evidence_ref', '')
                      ) <> ''
                  AND fch.scan_evidence ->> 'evidence_sha256'
                        ~ '^[a-f0-9]{64}$'
                  AND btrim(
                        COALESCE(fch.scan_evidence ->> 'scanner_revision', '')
                      ) <> ''
                  AND btrim(
                        COALESCE(fch.scan_evidence ->> 'signature_revision', '')
                      ) <> ''
                  AND COALESCE(
                        (fch.scan_evidence ->> 'structural_valid')::boolean,
                        false
                      )
                  AND COALESCE(
                        (fch.scan_evidence ->> 'malware_passed')::boolean,
                        false
                      )
                  AND fch.scan_evidence ->> 'dlp_decision' = 'passed'
                ORDER BY fch.created_at DESC, fch.id DESC
                LIMIT 1
                FOR SHARE;
                IF fetch_row_id IS NULL THEN
                    RAISE EXCEPTION
                        'dataset release provenance has no scan-passed artifact'
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
        CREATE TRIGGER trg_ai_dataset_release_provenance_guard
        BEFORE INSERT OR UPDATE OF status, approved, manifest_sha256,
            purpose, provenance, allowed_uses
        ON ai_dataset_release
        FOR EACH ROW
        EXECUTE FUNCTION vfbiz_guard_dataset_release_provenance();
        """
    )
    op.execute(
        """
        CREATE FUNCTION vfbiz_guard_dataset_release_pointer()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            release_found boolean;
        BEGIN
            PERFORM vfbiz_require_dataset_release_serializable();
            SELECT true
            INTO release_found
            FROM ai_dataset_release AS rel
            WHERE rel.id = NEW.release_id
              AND rel.status = 'released'
              AND rel.approved IS TRUE
              AND rel.manifest_sha256 = NEW.manifest_sha256
              AND rel.purpose = NEW.purpose
              AND rel.allowed_uses = jsonb_build_array(NEW.purpose)
            FOR SHARE;
            IF release_found IS NOT TRUE THEN
                RAISE EXCEPTION
                    'dataset release pointer does not resolve to released manifest'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_dataset_release_pointer_guard
        BEFORE INSERT OR UPDATE
        ON ai_dataset_release_pointer
        FOR EACH ROW
        EXECUTE FUNCTION vfbiz_guard_dataset_release_pointer();
        """
    )
    op.execute(
        """
        CREATE FUNCTION vfbiz_guard_dataset_release_pointer_dependency()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            active_pointer boolean;
        BEGIN
            IF NEW.manifest_ref = OLD.manifest_ref
               AND NEW.owner_ref = OLD.owner_ref
               AND NEW.status = OLD.status
               AND NEW.approved = OLD.approved
               AND NEW.manifest_sha256 IS NOT DISTINCT FROM OLD.manifest_sha256
               AND NEW.purpose = OLD.purpose
               AND NEW.provenance = OLD.provenance
               AND NEW.classification = OLD.classification
               AND NEW.allowed_uses = OLD.allowed_uses
               AND NEW.artifact_ids = OLD.artifact_ids
               AND NEW.released_at IS NOT DISTINCT FROM OLD.released_at
               AND NEW.tombstoned_at IS NOT DISTINCT FROM OLD.tombstoned_at THEN
                RETURN NEW;
            END IF;
            PERFORM vfbiz_require_dataset_release_serializable();
            SELECT true
            INTO active_pointer
            FROM ai_dataset_release_pointer AS ptr
            WHERE ptr.release_id = OLD.id
            LIMIT 1
            FOR SHARE;
            IF active_pointer IS TRUE THEN
                RAISE EXCEPTION
                    'active dataset release pointer must move before release change'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_dataset_release_pointer_dependency_guard
        BEFORE UPDATE OF manifest_ref, owner_ref, status, approved,
            manifest_sha256, purpose, provenance, classification, allowed_uses,
            artifact_ids, released_at, tombstoned_at
        ON ai_dataset_release
        FOR EACH ROW
        EXECUTE FUNCTION vfbiz_guard_dataset_release_pointer_dependency();
        """
    )
    op.execute(
        """
        CREATE FUNCTION vfbiz_guard_dataset_source_evidence_change()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            dependent_release boolean;
        BEGIN
            IF TG_OP = 'UPDATE'
               AND NEW.status = OLD.status
               AND NEW.source_key = OLD.source_key
               AND NEW.source_revision = OLD.source_revision
               AND NEW.origin_uri = OLD.origin_uri
               AND NEW.owner_ref = OLD.owner_ref
               AND NEW.classification = OLD.classification
               AND NEW.proposed_uses = OLD.proposed_uses
               AND NEW.approved_uses = OLD.approved_uses
               AND NEW.rights_evidence_ref
                    IS NOT DISTINCT FROM OLD.rights_evidence_ref
               AND NEW.rights_evidence_sha256
                    IS NOT DISTINCT FROM OLD.rights_evidence_sha256
               AND NEW.terms_sha256 IS NOT DISTINCT FROM OLD.terms_sha256 THEN
                RETURN NEW;
            END IF;
            PERFORM vfbiz_require_dataset_release_serializable();
            SELECT true
            INTO dependent_release
            FROM ai_dataset_release AS rel,
                 LATERAL jsonb_array_elements(rel.provenance -> 'sources') AS item
            WHERE rel.status IN ('approved', 'released')
              AND item ->> 'source_id' = OLD.source_key
              AND item ->> 'source_revision' = OLD.source_revision
            LIMIT 1;
            IF dependent_release IS TRUE THEN
                RAISE EXCEPTION
                    'dependent dataset release must be rolled back before source change'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_dataset_source_release_guard
        BEFORE UPDATE OF status, source_key, source_revision, origin_uri,
            owner_ref, classification, proposed_uses, approved_uses,
            rights_evidence_ref, rights_evidence_sha256, terms_sha256
            OR DELETE
        ON ai_dataset_source
        FOR EACH ROW
        EXECUTE FUNCTION vfbiz_guard_dataset_source_evidence_change();
        """
    )
    op.execute(
        """
        CREATE FUNCTION vfbiz_guard_dataset_fetch_evidence_change()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            source_key_value text;
            source_revision_value text;
            dependent_release boolean;
        BEGIN
            IF TG_OP = 'UPDATE'
               AND NEW.source_id = OLD.source_id
               AND NEW.state = OLD.state
               AND NEW.requested_by = OLD.requested_by
               AND NEW.approval_evidence_ref = OLD.approval_evidence_ref
               AND NEW.approval_evidence_sha256 = OLD.approval_evidence_sha256
               AND NEW.observed_sha256 IS NOT DISTINCT FROM OLD.observed_sha256
               AND NEW.observed_tree_sha256
                    IS NOT DISTINCT FROM OLD.observed_tree_sha256
               AND NEW.media_type IS NOT DISTINCT FROM OLD.media_type
               AND NEW.byte_size IS NOT DISTINCT FROM OLD.byte_size
               AND NEW.quarantine_uri IS NOT DISTINCT FROM OLD.quarantine_uri
               AND NEW.scan_evidence = OLD.scan_evidence THEN
                RETURN NEW;
            END IF;
            PERFORM vfbiz_require_dataset_release_serializable();
            IF OLD.state <> 'scan-passed' OR OLD.observed_sha256 IS NULL THEN
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END IF;
            SELECT src.source_key, src.source_revision
            INTO source_key_value, source_revision_value
            FROM ai_dataset_source AS src
            WHERE src.id = OLD.source_id;
            SELECT true
            INTO dependent_release
            FROM ai_dataset_release AS rel,
                 LATERAL jsonb_array_elements(rel.provenance -> 'sources') AS item
            WHERE rel.status IN ('approved', 'released')
              AND item ->> 'source_id' = source_key_value
              AND item ->> 'source_revision' = source_revision_value
              AND item ->> 'artifact_digest' =
                    'sha256:' || OLD.observed_sha256
            LIMIT 1;
            IF dependent_release IS TRUE THEN
                RAISE EXCEPTION
                    'dependent dataset release must be rolled back before fetch change'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ai_dataset_fetch_release_guard
        BEFORE UPDATE OF source_id, state, requested_by, approval_evidence_ref,
            approval_evidence_sha256, observed_sha256, observed_tree_sha256,
            media_type, byte_size, quarantine_uri, scan_evidence
            OR DELETE
        ON ai_dataset_fetch
        FOR EACH ROW
        EXECUTE FUNCTION vfbiz_guard_dataset_fetch_evidence_change();
        """
    )
    # Validate every pre-existing governed row while the migration is atomic.
    # A bad legacy row aborts the migration instead of being grandfathered in.
    op.execute(
        """
        UPDATE ai_dataset_release
        SET provenance = provenance
        WHERE status IN ('approved', 'released');
        """
    )
    op.execute(
        """
        UPDATE ai_dataset_release_pointer
        SET manifest_sha256 = manifest_sha256;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION vfbiz_require_dataset_release_serializable()
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF current_setting('transaction_isolation') <> 'serializable' THEN
                RAISE EXCEPTION
                    'dataset release authority requires serializable transaction'
                    USING ERRCODE = '25001';
            END IF;
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        LOCK TABLE ai_dataset_release_pointer, ai_dataset_release
        IN ACCESS EXCLUSIVE MODE;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM ai_dataset_release_pointer)
               OR EXISTS (
                    SELECT 1
                    FROM ai_dataset_release
                    WHERE status IN ('approved', 'released')
               ) THEN
                RAISE EXCEPTION
                    'cannot downgrade 20260729_0018 while governed dataset releases exist';
            END IF;
        END;
        $$;
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_dataset_fetch_release_guard "
        "ON ai_dataset_fetch"
    )
    op.execute("DROP FUNCTION IF EXISTS vfbiz_guard_dataset_fetch_evidence_change()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_dataset_source_release_guard "
        "ON ai_dataset_source"
    )
    op.execute("DROP FUNCTION IF EXISTS vfbiz_guard_dataset_source_evidence_change()")
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trg_ai_dataset_release_pointer_dependency_guard "
        "ON ai_dataset_release"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "vfbiz_guard_dataset_release_pointer_dependency()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_dataset_release_pointer_guard "
        "ON ai_dataset_release_pointer"
    )
    op.execute("DROP FUNCTION IF EXISTS vfbiz_guard_dataset_release_pointer()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ai_dataset_release_provenance_guard "
        "ON ai_dataset_release"
    )
    op.execute("DROP FUNCTION IF EXISTS vfbiz_guard_dataset_release_provenance()")
    op.execute(
        "DROP FUNCTION IF EXISTS vfbiz_require_dataset_release_serializable()"
    )
