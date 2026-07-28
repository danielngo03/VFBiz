from sqlalchemy import inspect

from app.platform.database.base import Base
from app.platform.database.model_registry import load_models


def test_ai_metadata_contains_only_ai_owned_foundation_tables() -> None:
    load_models()
    table_names = set(Base.metadata.tables)
    assert table_names == {
        "ai_audit_event",
        "ai_conversation_execution_fence",
        "ai_conversation_resume_gate",
        "ai_dataset_artifact",
        "ai_dataset_fetch",
        "ai_dataset_fetch_artifact",
        "ai_dataset_lineage_edge",
        "ai_dataset_quality_run",
        "ai_dataset_release",
        "ai_dataset_release_pointer",
        "ai_dataset_source",
        "ai_dataset_tombstone",
        "ai_embedding_index_generation",
        "ai_evaluation_run",
        "ai_knowledge_chunk",
        "ai_knowledge_ingestion_artifact",
        "ai_knowledge_ingestion_control_command",
        "ai_knowledge_ingestion_job",
        "ai_knowledge_ingestion_outbox",
        "ai_knowledge_ingestion_stage_attempt",
        "ai_knowledge_release",
        "ai_knowledge_release_decision",
        "ai_knowledge_release_outbox",
        "ai_knowledge_release_source",
        "ai_knowledge_release_transition",
        "ai_knowledge_revision_pointer",
        "ai_knowledge_source",
        "ai_release",
    }


def test_every_table_has_uuid_primary_key_and_timestamps() -> None:
    load_models()
    structural_tables = {
        "ai_dataset_fetch_artifact",
        "ai_dataset_release_pointer",
    }
    for table in Base.metadata.sorted_tables:
        mapper = inspect(table)
        if table.name in structural_tables:
            assert len(mapper.primary_key) == 2
        else:
            assert [column.name for column in mapper.primary_key] == ["id"]
            assert "created_at" in table.columns
