from sqlalchemy import Index, inspect

from app.modules.knowledge.infrastructure.models import (
    KnowledgeReleaseOutbox,
    KnowledgeReleaseRecord,
    KnowledgeReleaseSource,
    KnowledgeRevisionPointer,
    KnowledgeSource,
)


def test_release_tables_have_uuid_primary_keys_and_required_scope_constraints() -> None:
    for model in (
        KnowledgeReleaseRecord,
        KnowledgeReleaseSource,
        KnowledgeRevisionPointer,
        KnowledgeReleaseOutbox,
    ):
        table = inspect(model).local_table
        assert [column.name for column in table.primary_key] == ["id"]
        assert "created_at" in table.columns

    pointer_constraints = {
        constraint.name for constraint in KnowledgeRevisionPointer.__table__.constraints
    }
    assert "uq_ai_knowledge_revision_pointer_scope" in pointer_constraints


def test_only_one_active_release_is_allowed_per_scope() -> None:
    indexes = {
        index.name: index
        for index in KnowledgeReleaseRecord.__table__.indexes
        if isinstance(index, Index)
    }
    active = indexes["uq_ai_knowledge_release_active_scope"]

    assert active.unique is True
    assert "status = 'active'" in str(active.dialect_options["postgresql"]["where"])


def test_legacy_source_rows_remain_fail_closed_until_v2_projection_is_complete() -> None:
    nullable_projection_fields = {
        "canonical_source_id",
        "version",
        "source_type",
        "locator_ref",
        "approved_purposes",
        "acl_namespaces",
        "rights",
        "retention",
        "deletion_method",
        "approval_evidence",
        "review_date",
        "registry_document_hash",
    }

    assert all(
        KnowledgeSource.__table__.columns[field].nullable for field in nullable_projection_fields
    )
    assert KnowledgeSource.__table__.columns["deletion_fenced"].nullable is False
