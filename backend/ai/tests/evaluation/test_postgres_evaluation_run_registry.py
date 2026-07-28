import asyncio
import os
from dataclasses import replace

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from app.modules.evaluation.application.execution import (
    EvaluationRunLifecycleService,
    EvaluationRunRegistrationService,
    RunRegistrationConflict,
)
from app.modules.evaluation.application.ports import EvaluationRunConcurrencyError
from app.modules.evaluation.domain import (
    AuthorityClass,
    BudgetPolicy,
    EvaluationRun,
    EvaluationRunPlan,
    EvaluationRunState,
)
from app.modules.evaluation.infrastructure.models import EvaluationRunRecord
from app.modules.evaluation.infrastructure.postgres_run_registry import (
    PostgresEvaluationRunRegistry,
)
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)

SHA_A = f"sha256:{'a' * 64}"
SHA_B = f"sha256:{'b' * 64}"
SHA_C = f"sha256:{'c' * 64}"


class BarrierRunRegistry:
    def __init__(
        self,
        delegate: PostgresEvaluationRunRegistry,
        *,
        run_id: str,
    ) -> None:
        self._delegate = delegate
        self._run_id = run_id
        self._arrivals = 0
        self._release = asyncio.Event()

    async def add_or_get(
        self,
        run: EvaluationRun,
        *,
        plan_document: dict[str, object],
    ) -> EvaluationRun:
        return await self._delegate.add_or_get(
            run,
            plan_document=plan_document,
        )

    async def get(self, run_id: str) -> EvaluationRun | None:
        current = await self._delegate.get(run_id)
        if run_id == self._run_id and self._arrivals < 2:
            self._arrivals += 1
            if self._arrivals == 2:
                self._release.set()
            await self._release.wait()
        return current

    async def save(self, run: EvaluationRun, *, expected_version: int) -> None:
        await self._delegate.save(
            run,
            expected_version=expected_version,
        )


def plan(run_id: str) -> EvaluationRunPlan:
    return EvaluationRunPlan(
        run_id=run_id,
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
        environment_revision="integration-v1",
        random_seed=20260728,
        budgets=BudgetPolicy(
            max_input_tokens=10_000,
            max_output_tokens=5_000,
            max_duration_seconds=600,
            max_cost_usd=10,
        ),
    )


@pytest.mark.asyncio
async def test_postgres_run_registration_resume_cancellation_and_occ() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    registry = PostgresEvaluationRunRegistry(sessions)
    service = EvaluationRunRegistrationService(registry)
    run_id = "eval:integration:resumable-0001"
    tamper_run_id = "eval:integration:tamper-0001"
    try:
        requested = await service.register(plan(run_id))
        assert await service.register(plan(run_id)) == requested

        queued = requested.transition(EvaluationRunState.QUEUED)
        await registry.save(queued, expected_version=requested.row_version)
        running = queued.transition(EvaluationRunState.RUNNING)
        await registry.save(running, expected_version=queued.row_version)
        progressed = running.record_progress(completed_case_count=37)
        await registry.save(progressed, expected_version=running.row_version)

        resumed = await registry.get(run_id)
        assert resumed is not None
        assert resumed == progressed
        barrier_registry = BarrierRunRegistry(registry, run_id=run_id)
        lifecycle = EvaluationRunLifecycleService(barrier_registry)
        first_cancel, duplicate_cancel = await asyncio.gather(
            lifecycle.cancel(run_id),
            lifecycle.cancel(run_id),
        )
        cancelled = first_cancel
        assert duplicate_cancel == cancelled
        assert await EvaluationRunLifecycleService(registry).cancel(run_id) == cancelled
        assert (await registry.get(run_id)) == cancelled

        with pytest.raises(EvaluationRunConcurrencyError, match="optimistic"):
            await registry.save(cancelled, expected_version=resumed.row_version)

        with pytest.raises(RunRegistrationConflict, match="RUN_PLAN_CONFLICT"):
            await service.register(replace(plan(run_id), random_seed=7))

        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                await session.execute(
                    update(EvaluationRunRecord)
                    .where(EvaluationRunRecord.run_key == run_id)
                    .values(
                        status=EvaluationRunState.DECISION_READY.value,
                        evidence_bundle_digest=None,
                    )
                )

        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                await session.execute(
                    update(EvaluationRunRecord)
                    .where(EvaluationRunRecord.run_key == run_id)
                    .values(baseline_manifest_digest=None)
                )

        tamper_requested = await service.register(plan(tamper_run_id))
        tamper_queued = tamper_requested.transition(EvaluationRunState.QUEUED)
        await registry.save(
            tamper_queued,
            expected_version=tamper_requested.row_version,
        )
        async with sessions() as session, session.begin():
            await session.execute(
                update(EvaluationRunRecord)
                .where(EvaluationRunRecord.run_key == tamper_run_id)
                .values(plan_document={"tampered": True})
            )
        with pytest.raises(EvaluationRunConcurrencyError, match="plan integrity"):
            await registry.save(
                tamper_queued.transition(EvaluationRunState.RUNNING),
                expected_version=tamper_queued.row_version,
            )
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                delete(EvaluationRunRecord).where(
                    EvaluationRunRecord.run_key.in_((run_id, tamper_run_id))
                )
            )
        await engine.dispose()
