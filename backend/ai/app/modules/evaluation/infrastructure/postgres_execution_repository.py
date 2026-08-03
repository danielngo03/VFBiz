from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Numeric, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.evaluation.application.ports import EvaluationRunConcurrencyError
from app.modules.evaluation.domain import (
    EvaluationCaseLease,
    EvaluationCaseResult,
    EvaluationRunState,
    EvaluationSuiteSnapshot,
    EvaluationUsage,
)
from app.modules.evaluation.infrastructure.models import (
    EvaluationCaseResultRecord,
    EvaluationCaseTaskRecord,
    EvaluationRunRecord,
)


class PostgresEvaluationExecutionRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def materialize_suite(
        self,
        *,
        run_id: str,
        suite: EvaluationSuiteSnapshot,
        shard_count: int,
        max_attempts: int,
    ) -> None:
        async with self._sessions() as session, session.begin():
            run = await session.scalar(
                select(EvaluationRunRecord)
                .where(EvaluationRunRecord.run_key == run_id)
                .with_for_update()
            )
            if (
                run is None
                or run.status != EvaluationRunState.QUEUED.value
                or run.plan_document is None
                or run.plan_document.get("suite")
                != {
                    "digest": suite.suite_digest,
                    "id": suite.suite_id,
                }
            ):
                raise EvaluationRunConcurrencyError(
                    "released evaluation suite does not match queued run"
                )
            for case_id, case_digest in suite.case_bindings:
                shard_index = int(sha256(case_id.encode()).hexdigest()[:16], 16) % shard_count
                await session.execute(
                    insert(EvaluationCaseTaskRecord)
                    .values(
                        run_key=run_id,
                        case_key=case_id,
                        case_digest=case_digest,
                        suite_digest=suite.suite_digest,
                        shard_index=shard_index,
                        status="pending",
                        attempt_count=0,
                        max_attempts=max_attempts,
                    )
                    .on_conflict_do_nothing(index_elements=["run_key", "case_key"])
                )
            observed = (
                await session.execute(
                    select(
                        EvaluationCaseTaskRecord.case_key,
                        EvaluationCaseTaskRecord.case_digest,
                        EvaluationCaseTaskRecord.suite_digest,
                        EvaluationCaseTaskRecord.max_attempts,
                    ).where(EvaluationCaseTaskRecord.run_key == run_id)
                )
            ).all()
            expected = {
                (case_id, digest, suite.suite_digest, max_attempts)
                for case_id, digest in suite.case_bindings
            }
            if set(observed) != expected:
                raise EvaluationRunConcurrencyError(
                    "materialized evaluation suite conflicts with immutable plan"
                )

    async def claim_case(
        self,
        *,
        run_id: str,
        worker_id: str,
        lease_expires_at: datetime,
        shard_index: int | None = None,
    ) -> EvaluationCaseLease | None:
        async with self._sessions() as session, session.begin():
            run = await session.scalar(
                select(EvaluationRunRecord)
                .where(EvaluationRunRecord.run_key == run_id)
                .with_for_update()
            )
            if run is None:
                raise EvaluationRunConcurrencyError("evaluation run is unavailable for case claim")
            if run.status == EvaluationRunState.CANCELLED.value:
                return None
            if run.status != EvaluationRunState.RUNNING.value:
                raise EvaluationRunConcurrencyError("evaluation case claim requires running run")
            now_value = await session.scalar(select(func.clock_timestamp()))
            if now_value is None:
                raise EvaluationRunConcurrencyError("database clock is unavailable")
            expired_tasks = (
                await session.scalars(
                    select(EvaluationCaseTaskRecord)
                    .where(
                        EvaluationCaseTaskRecord.run_key == run_id,
                        EvaluationCaseTaskRecord.status == "running",
                        EvaluationCaseTaskRecord.lease_expires_at <= now_value,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
            if run.plan_document is None:
                raise EvaluationRunConcurrencyError("evaluation retry policy is unavailable")
            budgets = cast(dict[str, object], run.plan_document["budgets"])
            for expired in expired_tasks:
                if (
                    expired.lease_owner is None
                    or expired.lease_token is None
                    or expired.lease_expires_at is None
                ):
                    raise EvaluationRunConcurrencyError("expired evaluation lease is incomplete")
                consumed = (
                    await session.execute(
                        select(
                            func.coalesce(
                                func.sum(
                                    EvaluationCaseResultRecord.usage["input_tokens"].as_integer()
                                ),
                                0,
                            ),
                            func.coalesce(
                                func.sum(
                                    EvaluationCaseResultRecord.usage["output_tokens"].as_integer()
                                ),
                                0,
                            ),
                            func.coalesce(
                                func.sum(
                                    EvaluationCaseResultRecord.usage["cost_usd"].astext.cast(
                                        Numeric
                                    )
                                ),
                                0,
                            ),
                            func.coalesce(
                                func.sum(EvaluationCaseResultRecord.latency_ms),
                                0,
                            ),
                        ).where(EvaluationCaseResultRecord.run_key == run_id)
                    )
                ).one()
                expired_result = EvaluationCaseResult.issue(
                    run_id=expired.run_key,
                    case_id=expired.case_key,
                    case_digest=expired.case_digest,
                    attempt=expired.attempt_count,
                    status="failed",
                    output_digest=None,
                    latency_ms=max(
                        0,
                        int(str(budgets["maxDurationSeconds"])) * 1000
                        - int(cast(int, consumed[3])),
                    ),
                    usage=EvaluationUsage(
                        input_tokens=max(
                            0,
                            int(str(budgets["maxInputTokens"])) - int(cast(int, consumed[0])),
                        ),
                        output_tokens=max(
                            0,
                            int(str(budgets["maxOutputTokens"])) - int(cast(int, consumed[1])),
                        ),
                        cost_usd=_remaining_cost_usd(
                            budget=Decimal(str(budgets["maxCostUsd"])),
                            consumed=cast(Decimal, consumed[2]),
                        ),
                    ),
                    sanitized_trace_ref=None,
                    metric_outputs=(),
                    grader_outputs=(),
                    validity_flags=("runner-unavailable", "usage-unknown"),
                )
                expired_lease = EvaluationCaseLease(
                    run_id=expired.run_key,
                    case_id=expired.case_key,
                    case_digest=expired.case_digest,
                    suite_digest=expired.suite_digest,
                    shard_index=expired.shard_index,
                    attempt=expired.attempt_count,
                    lease_owner=expired.lease_owner,
                    lease_token=str(expired.lease_token),
                    lease_expires_at=expired.lease_expires_at,
                    max_input_tokens=expired_result.usage.input_tokens,
                    max_output_tokens=expired_result.usage.output_tokens,
                    max_duration_ms=expired_result.latency_ms,
                    max_cost_usd=expired_result.usage.cost_usd,
                )
                await session.execute(
                    insert(EvaluationCaseResultRecord)
                    .values(**_result_values(expired_result, lease=expired_lease))
                    .on_conflict_do_nothing(index_elements=["run_key", "case_key", "attempt"])
                )
                expired.status = "failed"
                expired.lease_owner = None
                expired.lease_token = None
                expired.lease_expires_at = None
            if expired_tasks:
                # A provider may have consumed the full remaining budget before
                # the worker disappeared. Reserve that worst case and terminate
                # the run; retrying would make the durable cost ledger dishonest.
                await session.execute(
                    update(EvaluationRunRecord)
                    .where(EvaluationRunRecord.id == run.id)
                    .values(
                        status=EvaluationRunState.FAILED.value,
                        failure_code="EVALUATION_USAGE_UNKNOWN",
                        row_version=EvaluationRunRecord.row_version + 1,
                    )
                )
                return None
            active_count = await session.scalar(
                select(func.count())
                .select_from(EvaluationCaseTaskRecord)
                .where(
                    EvaluationCaseTaskRecord.run_key == run_id,
                    EvaluationCaseTaskRecord.status == "running",
                )
            )
            if int(active_count or 0) > 0:
                return None
            pending_criteria = (
                EvaluationCaseTaskRecord.run_key == run_id,
                EvaluationCaseTaskRecord.status == "pending",
                EvaluationCaseTaskRecord.attempt_count < EvaluationCaseTaskRecord.max_attempts,
            )
            pending_count = await session.scalar(
                select(func.count()).select_from(EvaluationCaseTaskRecord).where(*pending_criteria)
            )
            if int(pending_count or 0) == 0:
                # Exhausting a cap on the final case is a valid completed run.
                # Budget exhaustion is terminal only when provider work remains.
                return None
            consumed = (
                await session.execute(
                    select(
                        func.coalesce(
                            func.sum(EvaluationCaseResultRecord.usage["input_tokens"].as_integer()),
                            0,
                        ),
                        func.coalesce(
                            func.sum(
                                EvaluationCaseResultRecord.usage["output_tokens"].as_integer()
                            ),
                            0,
                        ),
                        func.coalesce(
                            func.sum(
                                EvaluationCaseResultRecord.usage["cost_usd"].astext.cast(Numeric)
                            ),
                            0,
                        ),
                        func.coalesce(func.sum(EvaluationCaseResultRecord.latency_ms), 0),
                    ).where(EvaluationCaseResultRecord.run_key == run_id)
                )
            ).one()
            remaining_input_tokens = max(
                0,
                int(str(budgets["maxInputTokens"])) - int(cast(int, consumed[0])),
            )
            remaining_output_tokens = max(
                0,
                int(str(budgets["maxOutputTokens"])) - int(cast(int, consumed[1])),
            )
            remaining_cost_usd = _remaining_cost_usd(
                budget=Decimal(str(budgets["maxCostUsd"])),
                consumed=cast(Decimal, consumed[2]),
            )
            remaining_duration_ms = max(
                0,
                int(str(budgets["maxDurationSeconds"])) * 1000 - int(cast(int, consumed[3])),
            )
            if (
                remaining_input_tokens == 0
                or remaining_output_tokens == 0
                or remaining_duration_ms == 0
                or remaining_cost_usd == 0
            ):
                await session.execute(
                    update(EvaluationRunRecord)
                    .where(EvaluationRunRecord.id == run.id)
                    .values(
                        status=EvaluationRunState.FAILED.value,
                        failure_code="EVALUATION_BUDGET_EXHAUSTED",
                        row_version=EvaluationRunRecord.row_version + 1,
                    )
                )
                return None
            statement = (
                select(EvaluationCaseTaskRecord)
                .where(*pending_criteria)
                .order_by(
                    EvaluationCaseTaskRecord.shard_index,
                    EvaluationCaseTaskRecord.case_key,
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if shard_index is not None:
                statement = statement.where(EvaluationCaseTaskRecord.shard_index == shard_index)
            task = await session.scalar(statement)
            if task is None:
                return None
            token = uuid4()
            attempt = task.attempt_count + 1
            await session.execute(
                update(EvaluationCaseTaskRecord)
                .where(EvaluationCaseTaskRecord.id == task.id)
                .values(
                    status="running",
                    attempt_count=attempt,
                    lease_owner=worker_id,
                    lease_token=token,
                    lease_expires_at=lease_expires_at,
                )
            )
            return EvaluationCaseLease(
                run_id=task.run_key,
                case_id=task.case_key,
                case_digest=task.case_digest,
                suite_digest=task.suite_digest,
                shard_index=task.shard_index,
                attempt=attempt,
                lease_owner=worker_id,
                lease_token=str(token),
                lease_expires_at=lease_expires_at,
                max_input_tokens=remaining_input_tokens,
                max_output_tokens=remaining_output_tokens,
                max_duration_ms=remaining_duration_ms,
                max_cost_usd=remaining_cost_usd,
            )

    async def complete_case(
        self,
        *,
        lease: EvaluationCaseLease,
        result: EvaluationCaseResult,
        completed_at: datetime,
    ) -> None:
        async with self._sessions() as session, session.begin():
            run = await session.scalar(
                select(EvaluationRunRecord)
                .where(EvaluationRunRecord.run_key == lease.run_id)
                .with_for_update()
            )
            task = await session.scalar(
                select(EvaluationCaseTaskRecord)
                .where(
                    EvaluationCaseTaskRecord.run_key == lease.run_id,
                    EvaluationCaseTaskRecord.case_key == lease.case_id,
                )
                .with_for_update()
            )
            if run is None or task is None:
                raise EvaluationRunConcurrencyError("evaluation case lease no longer exists")
            if task.status == "completed":
                persisted = await session.scalar(
                    select(EvaluationCaseResultRecord).where(
                        EvaluationCaseResultRecord.run_key == lease.run_id,
                        EvaluationCaseResultRecord.case_key == lease.case_id,
                        EvaluationCaseResultRecord.attempt == lease.attempt,
                    )
                )
                if persisted is not None and persisted.result_digest == result.result_digest:
                    return
            if (
                run.status != EvaluationRunState.RUNNING.value
                or run.plan_document is None
                or task.status != "running"
                or task.attempt_count != lease.attempt
                or task.lease_owner != lease.lease_owner
                or task.lease_token != UUID(lease.lease_token)
                or task.lease_expires_at is None
                or task.lease_expires_at < completed_at
            ):
                raise EvaluationRunConcurrencyError("stale evaluation case lease cannot commit")
            await session.execute(
                insert(EvaluationCaseResultRecord).values(**_result_values(result, lease=lease))
            )
            retryable = _is_retryable_result(
                result=result,
                plan_document=run.plan_document,
                attempt=task.attempt_count,
                max_attempts=task.max_attempts,
            )
            await session.execute(
                update(EvaluationCaseTaskRecord)
                .where(EvaluationCaseTaskRecord.id == task.id)
                .values(
                    status="pending" if retryable else "completed",
                    lease_owner=None,
                    lease_token=None,
                    lease_expires_at=None,
                    completed_at=None if retryable else completed_at,
                )
            )
            completed_count = await session.scalar(
                select(func.count())
                .select_from(EvaluationCaseTaskRecord)
                .where(
                    EvaluationCaseTaskRecord.run_key == lease.run_id,
                    EvaluationCaseTaskRecord.status == "completed",
                )
            )
            await session.execute(
                update(EvaluationRunRecord)
                .where(EvaluationRunRecord.id == run.id)
                .values(
                    completed_case_count=int(completed_count or 0),
                    row_version=EvaluationRunRecord.row_version + 1,
                )
            )


def _is_retryable_result(
    *,
    result: EvaluationCaseResult,
    plan_document: dict[str, object],
    attempt: int,
    max_attempts: int,
) -> bool:
    attempt_policy_value = plan_document.get("attemptPolicy")
    if not isinstance(attempt_policy_value, dict):
        return False
    attempt_policy = cast(dict[str, object], attempt_policy_value)
    retry_codes_value = attempt_policy.get("retryableFailureCodes")
    if not isinstance(retry_codes_value, list):
        return False
    retry_codes = {
        value for value in cast(list[object], retry_codes_value) if isinstance(value, str)
    }
    return (
        result.status == "failed"
        and len(result.validity_flags) == 1
        and result.validity_flags[0] in retry_codes
        and "usage-unknown" not in result.validity_flags
        and attempt < max_attempts
    )


def _remaining_cost_usd(*, budget: Decimal, consumed: Decimal) -> float:
    remaining = max(Decimal("0"), budget - consumed)
    if remaining != remaining.quantize(Decimal("0.000001")):
        raise EvaluationRunConcurrencyError("evaluation monetary usage exceeds fixed precision")
    return float(remaining)


def _result_values(
    result: EvaluationCaseResult,
    *,
    lease: EvaluationCaseLease,
) -> dict[str, object]:
    return {
        "run_key": result.run_id,
        "case_key": result.case_id,
        "case_digest": result.case_digest,
        "attempt": result.attempt,
        "lease_owner": lease.lease_owner,
        "lease_token": UUID(lease.lease_token),
        "status": result.status,
        "output_digest": result.output_digest,
        "latency_ms": result.latency_ms,
        "usage": {
            "cost_usd": result.usage.cost_usd,
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
        },
        "sanitized_trace_ref": result.sanitized_trace_ref,
        "grader_outputs": [outcome.canonical_document for outcome in result.grader_outputs],
        "metric_outputs": [outcome.canonical_document for outcome in result.metric_outputs],
        "validity_flags": list(result.validity_flags),
        "result_digest": result.result_digest,
        "canonical_payload": result.canonical_payload,
    }
