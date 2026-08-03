from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast

from app.modules.evaluation.application.ports import (
    EvaluationExecutionRepository,
    EvaluationRunRegistry,
)
from app.modules.evaluation.domain import (
    EvaluationCaseLease,
    EvaluationCaseResult,
    EvaluationRun,
    EvaluationRunState,
    EvaluationSuiteSnapshot,
)


class EvaluationExecutionError(ValueError):
    pass


class EvaluationCaseExecutionService:
    def __init__(
        self,
        *,
        runs: EvaluationRunRegistry,
        execution: EvaluationExecutionRepository,
        clock: Callable[[], datetime],
    ) -> None:
        self._runs = runs
        self._execution = execution
        self._clock = clock

    async def get_run(self, run_id: str) -> EvaluationRun | None:
        return await self._runs.get(run_id)

    async def materialize(
        self,
        *,
        run_id: str,
        suite: EvaluationSuiteSnapshot,
        shard_count: int,
    ) -> None:
        if not 1 <= shard_count <= 1024:
            raise EvaluationExecutionError("INVALID_EXECUTION_PARTITION_POLICY")
        run = await self._runs.get(run_id)
        plan = await self._runs.get_plan_document(run_id)
        if run is None or plan is None:
            raise EvaluationExecutionError("EVALUATION_RUN_NOT_FOUND")
        if run.state is not EvaluationRunState.QUEUED:
            raise EvaluationExecutionError("EVALUATION_RUN_NOT_QUEUED")
        plan_suite = plan.get("suite")
        if not isinstance(plan_suite, dict):
            raise EvaluationExecutionError("EVALUATION_SUITE_NOT_RELEASE_BOUND")
        suite_document = cast(dict[str, object], plan_suite)
        attempt_policy_value = plan.get("attemptPolicy")
        attempt_policy = (
            cast(dict[str, object], attempt_policy_value)
            if isinstance(attempt_policy_value, dict)
            else None
        )
        if (
            suite_document.get("id") != suite.suite_id
            or suite_document.get("digest") != suite.suite_digest
            or not isinstance(attempt_policy, dict)
            or not isinstance(attempt_policy.get("maxAttempts"), int)
            or not 1 <= cast(int, attempt_policy["maxAttempts"]) <= 3
        ):
            raise EvaluationExecutionError("EVALUATION_SUITE_NOT_RELEASE_BOUND")
        await self._execution.materialize_suite(
            run_id=run_id,
            suite=suite,
            shard_count=shard_count,
            max_attempts=cast(int, attempt_policy["maxAttempts"]),
        )

    async def claim(
        self,
        *,
        run_id: str,
        worker_id: str,
        lease_seconds: int,
        shard_index: int | None = None,
    ) -> EvaluationCaseLease | None:
        now = self._clock()
        if (
            now.tzinfo is None
            or now.utcoffset() is None
            or not worker_id.strip()
            or not 1 <= lease_seconds <= 900
            or (shard_index is not None and shard_index < 0)
        ):
            raise EvaluationExecutionError("INVALID_EVALUATION_CASE_CLAIM")
        return await self._execution.claim_case(
            run_id=run_id,
            worker_id=worker_id,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            shard_index=shard_index,
        )

    async def complete(
        self,
        *,
        lease: EvaluationCaseLease,
        result: EvaluationCaseResult,
    ) -> None:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise EvaluationExecutionError("INVALID_EVALUATION_CLOCK")
        if (
            result.run_id != lease.run_id
            or result.case_id != lease.case_id
            or result.case_digest != lease.case_digest
            or result.attempt != lease.attempt
        ):
            raise EvaluationExecutionError("EVALUATION_RESULT_LEASE_MISMATCH")
        if (
            result.usage.input_tokens > lease.max_input_tokens
            or result.usage.output_tokens > lease.max_output_tokens
            or result.latency_ms > lease.max_duration_ms
            or Decimal(str(result.usage.cost_usd)) > Decimal(str(lease.max_cost_usd))
        ):
            raise EvaluationExecutionError("EVALUATION_RESULT_EXCEEDS_LEASE_BUDGET")
        await self._execution.complete_case(
            lease=lease,
            result=result,
            completed_at=now,
        )
