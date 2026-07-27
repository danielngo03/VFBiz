from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT / "migrations" / "versions" / "20260725_0010_enforce_embedding_generation_contract.py"
)


def test_contract_migration_fails_closed_before_not_null_cutover() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "20260725_0010"' in source
    assert 'down_revision: str | None = "20260725_0009"' in source
    assert "embedding generation contract preflight failed" in source
    assert "index_generation_id IS NULL" in source
    assert "embedding_dimension IS NULL" in source
    assert (
        'op.alter_column("ai_knowledge_release", "index_generation_id", nullable=False)' in source
    )
    assert 'op.alter_column("ai_knowledge_chunk", "index_generation_id", nullable=False)' in source
    assert 'op.alter_column("ai_knowledge_chunk", "embedding_dimension", nullable=False)' in source


def test_contract_migration_downgrade_only_relaxes_nullability() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:", maxsplit=1)[1]

    assert "DROP TABLE" not in downgrade
    assert "DROP COLUMN" not in downgrade
    assert "UPDATE " not in downgrade
    assert (
        'op.alter_column("ai_knowledge_release", "index_generation_id", nullable=True)' in downgrade
    )
    assert (
        'op.alter_column("ai_knowledge_chunk", "index_generation_id", nullable=True)' in downgrade
    )
    assert (
        'op.alter_column("ai_knowledge_chunk", "embedding_dimension", nullable=True)' in downgrade
    )
