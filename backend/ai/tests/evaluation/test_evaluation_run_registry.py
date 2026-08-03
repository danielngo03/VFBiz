from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.modules.evaluation.application.execution import (
    EvaluationRunLifecycleService,
    EvaluationRunRegistrationService,
    RunRegistrationConflict,
)
from app.modules.evaluation.domain import (
    AuthorityClass,
    BudgetPolicy,
    EvaluationRun,
    EvaluationRunPlan,
    EvaluationRunState,
    EvaluationRunTransitionError,
)

SHA_A = f"sha256:{'a' * 64}"
SHA_B = f"sha256:{'b' * 64}"
SHA_C = f"sha256:{'c' * 64}"


def plan() -> EvaluationRunPlan:
    return EvaluationRunPlan(
        run_id="eval:assistant:0001",
        authority_class=AuthorityClass.VINFAST_ACCEPTANCE,
        candidate_release_id="assistant-2.0.0",
        candidate_manifest_digest=SHA_A,
        baseline_release_id="assistant-1.9.0",
        baseline_manifest_digest=SHA_B,
        benchmark_definition_digest=SHA_C,
        suite_id="vivi-golden-v1",
        suite_digest=SHA_A,
        runner_image_digest=SHA_B,
        harness_revision="vivi-harness-v1",
        tool_simulator_revision="tool-simulator-v1",
        metric_revisions=("citation-validity-v1",),
        grader_revisions=("citation-membership-v1",),
        grader_calibrations=(),
        environment_revision="staging-v1",
        random_seed=20260728,
        budgets=BudgetPolicy(
            max_input_tokens=10_000,
            max_output_tokens=5_000,
            max_duration_seconds=600,
            max_cost_usd=10,
        ),
        evaluation_claim="Validate the governed assistant candidate.",
        subject_under_test="assistant-2.0.0",
        requested_at=datetime(2026, 7, 28, tzinfo=UTC),
        max_attempts=3,
        retryable_failure_codes=("provider-timeout",),
        baseline_policy_digest=SHA_C,
    )


class FakeRunRegistry:
    def __init__(self) -> None:
        self.runs: dict[str, EvaluationRun] = {}

    async def add_or_get(
        self,
        run: EvaluationRun,
        *,
        plan_document: dict[str, object],
    ) -> EvaluationRun:
        assert plan_document
        existing = self.runs.setdefault(run.run_id, run)
        return existing

    async def get(self, run_id: str) -> EvaluationRun | None:
        return self.runs.get(run_id)

    async def get_plan_document(
        self,
        run_id: str,
    ) -> dict[str, object] | None:
        return None

    async def save(self, run: EvaluationRun, *, expected_version: int) -> None:
        existing = self.runs.get(run.run_id)
        if existing is None or existing.row_version != expected_version:
            raise RuntimeError("lost optimistic concurrency")
        self.runs[run.run_id] = run


def test_run_lifecycle_is_explicit_and_terminal_states_cannot_revive() -> None:
    run = EvaluationRun.requested(
        run_id="eval:assistant:0001",
        plan_digest=plan().content_digest,
    )

    queued = run.transition(EvaluationRunState.QUEUED)
    running = queued.transition(EvaluationRunState.RUNNING)
    grading = running.record_progress(completed_case_count=50).transition(
        EvaluationRunState.GRADING
    )
    comparing = grading.transition(EvaluationRunState.COMPARING)

    assert not hasattr(comparing, "complete")
    with pytest.raises(
        EvaluationRunTransitionError,
        match="ILLEGAL_RUN_TRANSITION",
    ):
        comparing.transition(EvaluationRunState.DECISION_READY)


def test_progress_is_monotonic_and_bound_to_running_state() -> None:
    run = EvaluationRun.requested(
        run_id="eval:assistant:0001",
        plan_digest=plan().content_digest,
    ).transition(EvaluationRunState.QUEUED)

    with pytest.raises(EvaluationRunTransitionError, match="PROGRESS_NOT_RUNNING"):
        run.record_progress(completed_case_count=1)

    running = run.transition(EvaluationRunState.RUNNING)
    progressed = running.record_progress(completed_case_count=10)
    with pytest.raises(EvaluationRunTransitionError, match="PROGRESS_REGRESSION"):
        progressed.record_progress(completed_case_count=9)


def test_cancellation_is_durable_idempotent_and_terminal() -> None:
    running = (
        EvaluationRun.requested(
            run_id="eval:assistant:0001",
            plan_digest=plan().content_digest,
        )
        .transition(EvaluationRunState.QUEUED)
        .transition(EvaluationRunState.RUNNING)
    )

    cancelled = running.cancel()

    assert cancelled.state is EvaluationRunState.CANCELLED
    assert cancelled.cancel() == cancelled
    with pytest.raises(EvaluationRunTransitionError, match="ILLEGAL_RUN_TRANSITION"):
        cancelled.transition(EvaluationRunState.GRADING)


@pytest.mark.asyncio
async def test_duplicate_cancel_command_does_not_write_an_unchanged_run() -> None:
    registry = FakeRunRegistry()
    registration = EvaluationRunRegistrationService(registry)
    lifecycle = EvaluationRunLifecycleService(registry)
    requested = await registration.register(plan())
    queued = requested.transition(EvaluationRunState.QUEUED)
    await registry.save(queued, expected_version=requested.row_version)

    first = await lifecycle.cancel(requested.run_id)
    duplicate = await lifecycle.cancel(requested.run_id)

    assert duplicate == first
    assert duplicate.state is EvaluationRunState.CANCELLED


@pytest.mark.asyncio
async def test_operational_lifecycle_exposes_only_domain_checked_stage_transitions() -> None:
    registry = FakeRunRegistry()
    registration = EvaluationRunRegistrationService(registry)
    lifecycle = EvaluationRunLifecycleService(registry)
    requested = await registration.register(plan())

    queued = await lifecycle.queue(requested.run_id)
    running = await lifecycle.start(requested.run_id)
    grading = await lifecycle.mark_grading(requested.run_id)
    comparing = await lifecycle.mark_comparing(requested.run_id)

    assert queued.state is EvaluationRunState.QUEUED
    assert running.state is EvaluationRunState.RUNNING
    assert grading.state is EvaluationRunState.GRADING
    assert comparing.state is EvaluationRunState.COMPARING
    with pytest.raises(EvaluationRunTransitionError, match="ILLEGAL_RUN_TRANSITION"):
        await lifecycle.start(requested.run_id)


def test_failed_and_invalid_states_require_a_reason_code() -> None:
    running = (
        EvaluationRun.requested(
            run_id="eval:assistant:0001",
            plan_digest=plan().content_digest,
        )
        .transition(EvaluationRunState.QUEUED)
        .transition(EvaluationRunState.RUNNING)
    )

    failed = running.fail(failure_code="provider-timeout")
    assert failed.state is EvaluationRunState.FAILED
    assert failed.failure_code == "provider-timeout"
    with pytest.raises(EvaluationRunTransitionError, match="RUN_FAILURE_CODE_REQUIRED"):
        running.fail(failure_code="")


@pytest.mark.asyncio
async def test_duplicate_registration_is_idempotent_for_the_exact_plan() -> None:
    registry = FakeRunRegistry()
    service = EvaluationRunRegistrationService(registry)

    first = await service.register(plan())
    duplicate = await service.register(plan())

    assert duplicate == first
    assert len(registry.runs) == 1


@pytest.mark.asyncio
async def test_duplicate_run_id_with_another_plan_fails_closed() -> None:
    registry = FakeRunRegistry()
    service = EvaluationRunRegistrationService(registry)
    await service.register(plan())

    changed = replace(plan(), random_seed=7)
    with pytest.raises(RunRegistrationConflict, match="RUN_PLAN_CONFLICT"):
        await service.register(changed)


def test_plan_digest_is_deterministic_and_revision_sensitive() -> None:
    original = plan()

    assert original.content_digest == plan().content_digest
    assert original.content_digest != replace(
        original,
        environment_revision="staging-v2",
    ).content_digest
