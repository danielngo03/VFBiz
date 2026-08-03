from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.modules.evaluation.application.execution.case_execution import (
    EvaluationCaseExecutionService,
)
from app.modules.evaluation.application.execution.evidence_authority import (
    EvidenceBundleAuthority,
)
from app.modules.evaluation.application.execution.run_lifecycle import (
    EvaluationRunLifecycleService,
)
from app.modules.evaluation.application.execution.run_registration import (
    EvaluationRunRegistrationService,
)
from app.modules.evaluation.application.planning.evaluation_planner import (
    EvaluationPlanner,
    PlanEvaluationRequest,
)
from app.modules.evaluation.domain import (
    EvaluationCaseLease,
    EvaluationCaseResult,
    EvaluationRun,
    EvaluationRunState,
    EvaluationSuiteSnapshot,
)


class QualificationExecutionError(RuntimeError):
    """Raised when a qualification run cannot reach sealed evidence."""


CaseHandler = Callable[[EvaluationCaseLease], Awaitable[EvaluationCaseResult]]


@dataclass(frozen=True, slots=True)
class QualificationRunRequest:
    plan: PlanEvaluationRequest
    suite: EvaluationSuiteSnapshot
    shard_count: int
    worker_id: str
    lease_seconds: int = 120


class EvaluationQualificationRunner:
    """Operational planner → runner → sealer composition.

    The handler is provider-neutral and receives only a fenced case lease. It
    must return a canonical ``EvaluationCaseResult``; it cannot seal or
    promote a release itself.
    """

    def __init__(
        self,
        *,
        planner: EvaluationPlanner,
        registration: EvaluationRunRegistrationService,
        lifecycle: EvaluationRunLifecycleService,
        execution: EvaluationCaseExecutionService,
        evidence: EvidenceBundleAuthority,
    ) -> None:
        self._planner = planner
        self._registration = registration
        self._lifecycle = lifecycle
        self._execution = execution
        self._evidence = evidence

    async def run(
        self,
        request: QualificationRunRequest,
        *,
        handle_case: CaseHandler,
    ) -> EvaluationRun:
        if not request.worker_id.strip():
            raise QualificationExecutionError("INVALID_QUALIFICATION_WORKER")
        plan = await self._planner.plan(request.plan)
        registered = await self._registration.register(plan)
        await self._lifecycle.queue(registered.run_id)
        await self._execution.materialize(
            run_id=registered.run_id,
            suite=request.suite,
            shard_count=request.shard_count,
        )
        await self._lifecycle.start(registered.run_id)
        await self._run_cases(request, handle_case)
        current = await self._require_run(registered.run_id)
        if current.state is not EvaluationRunState.RUNNING:
            raise QualificationExecutionError(
                f"QUALIFICATION_RUN_NOT_COMPLETABLE:{current.state.value}"
            )
        if current.completed_case_count != len(request.suite.case_bindings):
            raise QualificationExecutionError("QUALIFICATION_SUITE_INCOMPLETE")
        await self._lifecycle.mark_grading(registered.run_id)
        await self._lifecycle.mark_comparing(registered.run_id)
        return await self._evidence.seal(run_id=registered.run_id)

    async def _run_cases(
        self,
        request: QualificationRunRequest,
        handle_case: CaseHandler,
    ) -> None:
        while True:
            lease = await self._execution.claim(
                run_id=request.plan.run_id,
                worker_id=request.worker_id,
                lease_seconds=request.lease_seconds,
            )
            if lease is None:
                return
            result = await handle_case(lease)
            await self._execution.complete(lease=lease, result=result)

    async def _require_run(self, run_id: str) -> EvaluationRun:
        run = await self._execution.get_run(run_id)
        if run is None:
            raise QualificationExecutionError("EVALUATION_RUN_NOT_FOUND")
        return run


__all__ = [
    "CaseHandler",
    "EvaluationQualificationRunner",
    "QualificationExecutionError",
    "QualificationRunRequest",
]
