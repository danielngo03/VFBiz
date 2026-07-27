from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "migrations"
    / "versions"
    / "20260725_0009_version_embedding_index_generations.py"
)


def test_embedding_generation_migration_has_governed_identity_and_compatibility_fks() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "20260725_0009"' in source
    assert 'down_revision: str | None = "20260725_0008"' in source
    assert "ai_embedding_index_generation" in source
    assert "embedding_revision" in source
    assert "embedding_dimension" in source
    assert "distance_metric" in source
    assert "normalization" in source
    assert "instruction_digest" in source
    assert "fk_ai_knowledge_release_embedding_generation" in source
    assert "fk_ai_knowledge_chunk_embedding_generation" in source
    assert (
        'op.alter_column("ai_knowledge_release", "index_generation_id", nullable=False)'
        not in source
    )
    assert (
        'op.alter_column("ai_knowledge_chunk", "index_generation_id", nullable=False)'
        not in source
    )


def test_embedding_generation_migration_removes_global_vector_dimension_safely() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ALTER COLUMN embedding TYPE vector USING embedding::vector" in source
    assert "'legacy-pgvector-' || embedding_dimension::text || '-v1:'" in source
    assert "embedding_dimension = vector_dims(chunk.embedding)" in source
    assert "cannot downgrade: non-legacy embedding generations exist" in source
    assert "CREATE TRIGGER trg_ai_embedding_generation_immutable" in source
    assert "embedding generations are tombstoned, not deleted" in source
    assert "invalid embedding generation lifecycle transition" in source
    assert "DROP TRIGGER IF EXISTS trg_ai_embedding_generation_immutable" in source
    assert 'op.drop_table("ai_embedding_index_generation")' in source
