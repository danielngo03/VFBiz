import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

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
    CalibrationBinding,
    EvaluationRun,
    EvaluationRunPlan,
    EvaluationRunState,
    EvaluationSuiteAuthority,
    EvaluationSuiteSnapshot,
    GraderCalibration,
    evaluation_case_bindings_digest,
)
from app.modules.evaluation.infrastructure.models import EvaluationRunRecord
from app.modules.evaluation.infrastructure.postgres_run_registry import (
    PostgresEvaluationRunRegistry,
)
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory
from tests.evaluation.postgres_release_fixtures import (
    release_plan_definitions,
)
from tests.evaluation.test_evaluation_planning import baseline_policy

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)

SHA_A = f"sha256:{'a' * 64}"
SHA_B = f"sha256:{'b' * 64}"
SHA_C = f"sha256:{'c' * 64}"
SHA_E = f"sha256:{'e' * 64}"


def suite() -> EvaluationSuiteSnapshot:
    bindings = (("case.001", SHA_A),)
    authority = EvaluationSuiteAuthority.issue(
        suite_id="vivi-golden-v1",
        authority_class=AuthorityClass.PUBLIC_DIAGNOSTIC,
        qualification_profile="integration-diagnostic-v1",
        qualification_policy_digest=SHA_A,
        case_bindings_digest=evaluation_case_bindings_digest(bindings),
        case_composition_digest=SHA_B,
        risk_taxonomy_digest=SHA_A,
        provenance_digest=SHA_B,
        provenance_status="verified",
        provenance_evidence_uri="evidence://suite/provenance",
        contamination_scan_digest=SHA_C,
        contamination_status="passed",
        contamination_evidence_uri="evidence://suite/contamination",
        held_out=True,
        author_subject="subject:integration-author",
        evaluator_subject="subject:integration-evaluator",
        release_owner_subject="subject:integration-release-owner",
    )
    return EvaluationSuiteSnapshot.issue(
        suite_id="vivi-golden-v1",
        case_bindings=bindings,
        authority=authority,
    )


def calibration() -> GraderCalibration:
    return GraderCalibration.issue(
        grader_revision="run-registry-citation-v1",
        grader_definition_digest=SHA_A,
        implementation_digest=SHA_B,
        calibrated_at=datetime(2026, 7, 27, tzinfo=UTC),
        expires_at=datetime(2026, 7, 28, tzinfo=UTC)
        + timedelta(days=30),
        human_labelled_suite_digest=SHA_A,
        sample_size=30,
        confusion_matrix=(15, 15, 0, 0),
        balanced_accuracy=1,
        f1=1,
        slice_metrics=(
            ("all", 30, 1, 1, 15, 15, 0, 0),
            ("high-risk", 30, 1, 1, 15, 15, 0, 0),
        ),
    )


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

    async def get_plan_document(
        self,
        run_id: str,
    ) -> dict[str, object] | None:
        return await self._delegate.get_plan_document(run_id)

    async def save(self, run: EvaluationRun, *, expected_version: int) -> None:
        await self._delegate.save(
            run,
            expected_version=expected_version,
        )


def plan(run_id: str) -> EvaluationRunPlan:
    return EvaluationRunPlan(
        run_id=run_id,
        authority_class=AuthorityClass.PUBLIC_DIAGNOSTIC,
        candidate_release_id="assistant-2.0.0",
        candidate_manifest_digest=SHA_A,
        baseline_release_id="assistant-1.9.0",
        baseline_manifest_digest=SHA_B,
        benchmark_definition_digest=SHA_E,
        suite_id="vivi-golden-v1",
        suite_digest=suite().suite_digest,
        runner_image_digest=SHA_B,
        harness_revision="vivi-harness-v1",
        tool_simulator_revision="tool-simulator-v1",
        metric_revisions=("citation-validity-v1",),
        grader_revisions=("run-registry-citation-v1",),
        grader_calibrations=(
            CalibrationBinding(
                grader_revision="run-registry-citation-v1",
                grader_definition_digest=SHA_A,
                implementation_digest=SHA_B,
                calibration_digest=calibration().evidence_digest,
                human_labelled_suite_digest=SHA_A,
                calibrated_at=datetime(2026, 7, 27, tzinfo=UTC),
                expires_at=datetime(2026, 7, 28, tzinfo=UTC)
                + timedelta(days=30),
            ),
        ),
        environment_revision="integration-v1",
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
        grader_kinds=(("run-registry-citation-v1", "citation"),),
        baseline_policy_digest=baseline_policy().policy_digest,
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
    calibration_tamper_run_id = "eval:integration:calibration-tamper-0001"
    try:
        with pytest.raises(IntegrityError, match="released benchmark"):
            await service.register(plan(run_id))
        await release_plan_definitions(
            sessions,
            plan(run_id).canonical_document,
            suite_document=suite().contract_document,
            policy_document=baseline_policy().contract_document,
        )
        forged_plan = replace(
            plan(tamper_run_id),
            budgets=BudgetPolicy(
                max_input_tokens=99_999,
                max_output_tokens=5_000,
                max_duration_seconds=600,
                max_cost_usd=10,
            ),
        )
        with pytest.raises(
            IntegrityError,
            match="diverges from released benchmark",
        ):
            await service.register(forged_plan)
        forged_calibration = replace(
            plan(calibration_tamper_run_id),
            grader_calibrations=(
                replace(
                    plan(calibration_tamper_run_id).grader_calibrations[0],
                    calibration_digest=SHA_A,
                ),
            ),
        )
        with pytest.raises(
            IntegrityError,
            match="released grader calibration authority",
        ):
            await service.register(forged_calibration)
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
        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                await session.execute(
                    update(EvaluationRunRecord)
                    .where(EvaluationRunRecord.run_key == tamper_run_id)
                    .values(plan_document={"tampered": True})
                )
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                delete(EvaluationRunRecord).where(
                    EvaluationRunRecord.run_key.in_((run_id, tamper_run_id))
                )
            )
        await engine.dispose()
