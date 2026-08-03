from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/20260802_0024_document_ai_runtime_roles.py"
)
BOOTSTRAP_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/20260802_0025_document_ai_database_bootstrap_epoch.py"
)
PROVISIONER = (
    Path(__file__).resolve().parents[2]
    / "scripts/provision_document_ai_database_identities.py"
)


def test_document_ai_runtime_roles_are_nologin_and_disjoint() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'op.execute("CREATE ROLE vfbiz_ai_document_submitter NOLOGIN")' in source
    assert 'op.execute("CREATE ROLE vfbiz_ai_document_reconciler NOLOGIN")' in source
    assert "IF NOT EXISTS" not in source
    assert source.count("NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE") == 2
    assert source.count("NOREPLICATION NOBYPASSRLS") == 2
    assert "public.ai_document_submission" in source
    assert "public.ai_document_reconciliation_claim" in source
    assert "DROP ROLE IF EXISTS vfbiz_ai_document_submitter" in source
    assert "DROP ROLE IF EXISTS vfbiz_ai_document_reconciler" in source
    assert "DELETE, TRUNCATE" not in source


def test_document_ai_runtime_roles_have_exact_table_capabilities() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "REVOKE ALL ON" in source
    assert "GRANT SELECT, INSERT, UPDATE ON public.ai_document_submission" in source
    assert "GRANT SELECT ON public.ai_document_submission" in source
    assert "GRANT UPDATE (id) ON public.ai_document_submission" in source
    assert "GRANT SELECT, INSERT, UPDATE ON " in source
    assert "public.ai_document_reconciliation_claim" in source


def test_document_ai_database_bootstrap_epoch_is_singleton_and_terminal() -> None:
    migration = BOOTSTRAP_MIGRATION.read_text(encoding="utf-8")
    provisioner = PROVISIONER.read_text(encoding="utf-8")

    assert 'down_revision: str | None = "20260802_0024"' in migration
    assert "singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton)" in migration
    assert "bootstrap_epoch text NOT NULL UNIQUE" in migration
    assert "claim_id uuid NOT NULL UNIQUE" in migration
    assert "authority_digest character(64) NOT NULL" in migration
    assert "fencing_token bigint NOT NULL DEFAULT 1 CHECK (fencing_token = 1)" in migration
    assert "OLD.state <> 'reserved'" in migration
    assert "NEW.state NOT IN ('completed', 'failed')" in migration
    assert "BEFORE TRUNCATE" in migration
    assert "database bootstrap downgrade refused: evidence exists" in migration
    assert "GRANT " not in migration
    assert 'EXPECTED_ALEMBIC_HEAD = "20260802_0025"' in provisioner
    assert 'BOOTSTRAP_EPOCH = "document-ai-database-identities-v1"' in provisioner
