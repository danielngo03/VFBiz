from sqlalchemy import inspect

from app.platform.database.base import Base
from app.platform.database.model_registry import load_models


def test_ai_metadata_contains_only_ai_owned_foundation_tables() -> None:
    load_models()
    table_names = set(Base.metadata.tables)
    assert table_names == {
        "ai_audit_event",
        "ai_dataset_release",
        "ai_evaluation_run",
        "ai_knowledge_chunk",
        "ai_knowledge_source",
        "ai_release",
    }


def test_every_table_has_uuid_primary_key_and_timestamps() -> None:
    load_models()
    for table in Base.metadata.sorted_tables:
        mapper = inspect(table)
        assert [column.name for column in mapper.primary_key] == ["id"]
        assert "created_at" in table.columns
