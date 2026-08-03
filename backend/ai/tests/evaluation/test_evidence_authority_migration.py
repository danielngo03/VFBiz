from importlib import import_module
from pathlib import Path
from types import ModuleType

import pytest


class _ScalarResult:
    def scalar_one(self) -> bool:
        return True


class _RetainedEvidenceConnection:
    def execute(self, _statement: object) -> _ScalarResult:
        return _ScalarResult()


def migration() -> ModuleType:
    return import_module("migrations.versions.20260730_0020_evaluation_evidence_authority")


def hardening_migration() -> ModuleType:
    return import_module("migrations.versions.20260731_0022_evaluation_authority_hardening")


def test_migration_declares_atomic_relational_evidence_fences() -> None:
    revision = migration()
    assert revision.__file__ is not None
    source = Path(revision.__file__).read_text()

    assert revision.down_revision == "20260729_0019"
    for required in (
        "fk_ai_evaluation_run_evidence_binding",
        "evaluation_case_result_validate",
        "ai_evaluation_case_task",
        "evaluation_run_cancel_case_tasks",
        "evaluation_evidence_bundle_validate",
        "evaluation_run_validate_decision_ready",
        "evaluation_evidence_validate_seal_commit",
        "DEFERRABLE INITIALLY DEFERRED",
        "canonical_payload",
        "suite_snapshot_payload",
        "baseline_policy_payload",
        "BEFORE TRUNCATE",
        "sealed_from_row_version + 1",
    ):
        assert required in source


def test_downgrade_refuses_before_destructive_ddl_with_retained_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = migration()
    destructive_calls: list[str] = []

    def record_destructive(*_args: object, **_kwargs: object) -> None:
        destructive_calls.append("destructive")

    monkeypatch.setattr(
        revision.op,
        "get_bind",
        lambda: _RetainedEvidenceConnection(),
    )
    monkeypatch.setattr(
        revision.op,
        "drop_constraint",
        record_destructive,
    )
    monkeypatch.setattr(
        revision.op,
        "drop_table",
        record_destructive,
    )
    monkeypatch.setattr(
        revision.op,
        "drop_index",
        record_destructive,
    )
    monkeypatch.setattr(
        revision.op,
        "execute",
        record_destructive,
    )

    with pytest.raises(RuntimeError, match="immutable evaluation evidence"):
        revision.downgrade()

    assert destructive_calls == []


def test_hardening_migration_fences_lease_budget_plan_and_semantics() -> None:
    revision = hardening_migration()
    assert revision.__file__ is not None
    source = Path(revision.__file__).read_text()

    assert revision.down_revision == "20260730_0021"
    for required in (
        "lease_owner",
        "lease_token",
        "metric_outputs",
        "run_result_payload",
        "evaluation_case_task_validate_mutation",
        "evaluation_run_guard_authority",
        "OLD.status = 'running' AND NEW.status = 'pending'",
        "terminal evaluation run is immutable",
        "active_task_count <> 0",
        "document ->> 'authority_class' = 'vinfast-acceptance'",
        "sum((usage ->> 'input_tokens')::bigint)",
        "hard_gate_failures",
        "expected_recommendation",
        "expected_run_result",
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE",
        "WHERE run_key IS NOT NULL",
    ):
        assert required in source
    assert "OLD.status = 'running' AND NEW.status = 'running'" not in source


def test_hardening_downgrade_refuses_for_any_governed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = hardening_migration()
    destructive_calls: list[str] = []

    def record_destructive(*_args: object, **_kwargs: object) -> None:
        destructive_calls.append("destructive")

    monkeypatch.setattr(
        revision.op,
        "get_bind",
        lambda: _RetainedEvidenceConnection(),
    )
    monkeypatch.setattr(revision.op, "execute", record_destructive)
    monkeypatch.setattr(revision.op, "drop_constraint", record_destructive)
    monkeypatch.setattr(revision.op, "drop_column", record_destructive)

    with pytest.raises(RuntimeError, match="governed evaluation use"):
        revision.downgrade()

    assert destructive_calls == []
