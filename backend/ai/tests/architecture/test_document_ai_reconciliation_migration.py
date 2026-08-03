from __future__ import annotations

from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2]
    / "migrations/versions/20260801_0023_document_ai_reconciliation_evidence.py"
)


def test_reconciliation_migration_refuses_downgrade_with_active_claim() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:", maxsplit=1)[1]

    assert "FROM ai_document_reconciliation_claim" in downgrade
    assert "released_at IS NULL" in downgrade
    assert "lease_until > clock_timestamp()" in downgrade
    assert downgrade.index("downgrade refused") < downgrade.index(
        'op.drop_table("ai_document_reconciliation_claim")'
    )
