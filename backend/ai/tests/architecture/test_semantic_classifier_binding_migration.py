from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    AI_ROOT / "migrations" / "versions" / "20260729_0019_semantic_classifier_binding_authority.py"
)


def test_migration_extends_release_authority_without_replacing_v3() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "20260729_0019"' in source
    assert 'down_revision: str | None = "20260729_0018"' in source
    assert '"ai_semantic_classifier_binding"' in source
    assert '"ai_assistant_release_activation.id"' in source
    assert "classifier_evaluation" in source
    assert "classifier_approval" in source
    assert "ck_ai_trusted_release_evidence_kind" in source


def test_binding_authority_is_fail_closed_and_lifecycle_bearing() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "classification_stack_sha256" in source
    assert "binding_core_sha256" in source
    assert "binding_envelope_sha256" in source
    assert "canonical_document" in source
    assert "uq_ai_semantic_classifier_binding_active_activation" in source
    assert "postgresql_where=sa.text(\"state = 'active'\")" in source
    assert "semantic_classifier_binding_validate" in source
    assert "semantic classifier binding target activation mismatch" in source
    assert "semantic classifier classification stack digest mismatch" in source
    assert "semantic classifier binding core digest mismatch" in source
    assert "semantic classifier binding envelope digest mismatch" in source
    assert "semantic_classifier_binding_guard_lifecycle" in source
    assert "semantic classifier binding identity is immutable" in source
    assert "semantic classifier binding revision must advance exactly once" in source
    assert "semantic classifier binding transition is invalid" in source
    assert "semantic_classifier_binding_reject_delete" in source
    assert "ai_semantic_classifier_binding_history" in source
    assert "ai_semantic_classifier_binding_outbox_event" in source
    assert "semantic_classifier_binding_transition" in source
    assert "semantic_classifier_binding_supersede" in source
    assert "decision_evidence_ref" in source
    assert "semantic classifier binding transition metadata is required" in source
    assert "semantic classifier supersede requires atomic replacement" in source
    assert "NEW.effective_at < activation.effective_at" in source
    assert "NEW.expires_at > activation.expires_at" in source


def test_downgrade_refuses_to_destroy_persisted_binding_or_evidence() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:", maxsplit=1)[1]

    assert "semantic classifier binding downgrade refused: persisted rows exist" in downgrade
    assert "classifier_evaluation" in downgrade
    assert "classifier_approval" in downgrade
    assert "ai_trusted_release_evidence" in downgrade
