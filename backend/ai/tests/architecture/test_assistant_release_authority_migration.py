import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parent.parent
MIGRATION = ROOT / "migrations" / "versions" / "20260726_0011_assistant_release_authority.py"

TABLES = (
    "ai_assistant_release_candidate",
    "ai_assistant_static_safe_release",
    "ai_assistant_release_activation",
    "ai_assistant_release_history",
    "ai_assistant_release_pointer",
    "ai_assistant_release_outbox_event",
    "ai_assistant_release_outbox_delivery",
)


def test_release_authority_uses_a_new_immutable_namespace() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "20260726_0011"' in source
    assert 'down_revision: str | None = "20260725_0010"' in source
    for table in TABLES:
        assert f'"{table}"' in source
    assert '"ai_release"' not in source
    assert "legacy" not in source.lower()
    assert "CREATE TRIGGER" in source
    assert "assistant_release_reject_mutation" in source


def test_release_history_pointer_and_outbox_are_fail_closed() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "assistant_release_validate_history" in source
    assert "pg_advisory_xact_lock" in source
    assert "previous_event_sha256" in source
    assert "eligible rollback activation has never been authoritative" in source
    assert "fk_ai_assistant_activation_candidate_scope_digest" in source
    assert "activation source does not match activation-pinned authority" in source
    assert "rollback target does not match activation-pinned authority" in source
    assert "revoke target does not match activation-pinned authority" in source
    assert "assistant_release_guard_pointer" in source
    assert "BEFORE INSERT OR UPDATE OR DELETE" in source
    assert "must initialize on static safe revision zero" in source
    assert "NEW.revision <> OLD.revision + 1" in source
    assert "assistant release pointer scope is immutable" in source
    assert "created_transaction_id = txid_current()" in source
    assert "NEW.created_transaction_id <> txid_current()" in source
    assert "history transition does not match pointer targets" in source
    assert "assistant_release_canonical_jsonb" in source
    assert "canonical event digest mismatch" in source
    assert "assistant_release_validate_outbox_event" in source
    assert "outbox payload is not bound to release history" in source
    assert "CREATE CONSTRAINT TRIGGER" in source
    assert "DEFERRABLE INITIALLY DEFERRED" in source
    assert "history commit requires matching pointer and outbox" in source
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "lease_expires_at" in source
    assert "LEASE_EXPIRED_AFTER_FINAL_ATTEMPT" in source


def test_release_authority_downgrade_refuses_populated_tables() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:", maxsplit=1)[1]

    assert "assistant release authority downgrade refused: persisted rows exist" in downgrade
    assert "IF EXISTS" in downgrade
    for table in TABLES:
        assert table in downgrade


def test_postgres_acceptance_command_fails_closed_instead_of_skipping() -> None:
    package = json.loads((REPOSITORY_ROOT / "package.json").read_text(encoding="utf-8"))
    command = package["scripts"]["verify:ai:integration"]

    assert 'test "${VFBIZ_RUN_DB_INTEGRATION:-}" = "1"' in command
    assert 'test -n "${VFBIZ_AI_DATABASE_URL:-}"' in command
    assert "pytest tests/integration" in command
    assert "|| true" not in command
