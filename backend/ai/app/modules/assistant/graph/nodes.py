import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Literal, cast

from app.modules.assistant.application import (
    EvidenceAuthorityPort,
    ExecutionControlPort,
    SupervisorPort,
    TaskWorkerPort,
    WorkerResult,
)
from app.modules.assistant.domain import (
    ActiveTaskState,
    GraphOutcome,
    intent_requires_grounding,
)
from app.modules.assistant.graph.state import ConversationGraphState

_MAX_ATTEMPTS = 3


class ConversationNodes:
    def __init__(
        self,
        *,
        supervisor: SupervisorPort,
        worker: TaskWorkerPort,
        execution_control: ExecutionControlPort,
        evidence_authority: EvidenceAuthorityPort,
    ) -> None:
        self._supervisor = supervisor
        self._worker = worker
        self._execution_control = execution_control
        self._evidence_authority = evidence_authority

    async def supervise(self, state: ConversationGraphState) -> dict[str, object]:
        terminal = terminal_control_outcome(state)
        if terminal is not None:
            return {"outcome": terminal}
        if not state["message"].strip() or len(state["message"]) > 8_000:
            return {"outcome": GraphOutcome(kind="refused", code="INVALID_MESSAGE")}
        try:
            decision = await _await_before_deadline(
                self._supervisor.route(
                    message=state["message"],
                    global_entities=state["global_entities"],
                    previous_task=state["active_task"],
                ),
                state,
            )
        except TimeoutError:
            return {
                "outcome": GraphOutcome(
                    kind="handoff_required", code="SUPERVISOR_DEADLINE_EXCEEDED"
                )
            }
        if decision.abuse_signals:
            return {
                "outcome": GraphOutcome(kind="refused", code="ABUSE_SIGNAL_DETECTED")
            }
        if decision.out_of_domain:
            return {"outcome": GraphOutcome(kind="refused", code="OUT_OF_DOMAIN")}
        if decision.multi_intent:
            return {
                "outcome": GraphOutcome(
                    kind="needs_clarification",
                    code="MULTIPLE_INTENTS_REQUIRE_CLARIFICATION",
                    pending_slots=("primary_intent",),
                )
            }
        if decision.missing_slots:
            return {
                "outcome": GraphOutcome(
                    kind="needs_clarification",
                    code="MISSING_REQUIRED_ARGUMENTS",
                    pending_slots=decision.missing_slots,
                )
            }
        retry_count = (
            state["active_task"].retry_count
            if state["active_task"] is not None
            and state["active_task"].intent == decision.intent
            else 0
        )
        return {
            "active_task": ActiveTaskState(
                intent=decision.intent,
                required_arguments=decision.required_arguments,
                retry_count=retry_count,
            ),
            "route_history": (*state["route_history"], decision.intent)[-16:],
            "outcome": None,
        }

    async def execute(self, state: ConversationGraphState) -> dict[str, object]:
        terminal = terminal_control_outcome(state)
        if terminal is not None:
            return {"outcome": terminal}
        task = state["active_task"]
        if task is None:
            return {
                "outcome": GraphOutcome(
                    kind="handoff_required", code="MISSING_ACTIVE_TASK"
                )
            }
        result = await self._execute_bounded(state, task)
        if isinstance(result, GraphOutcome):
            return {"outcome": result}
        terminal = terminal_control_outcome(state)
        try:
            execution_is_current = await _await_before_deadline(
                self._execution_control.is_current(state["control"]), state
            )
        except TimeoutError:
            return {
                "outcome": GraphOutcome(
                    kind="cancelled", code="EXECUTION_CONTROL_TIMEOUT"
                )
            }
        if terminal is not None:
            return {"outcome": terminal}
        if not execution_is_current or result.fencing_token != state["control"].fencing_token:
            return {
                "outcome": GraphOutcome(kind="cancelled", code="STALE_FENCING_TOKEN")
            }
        return await self._map_worker_result(state, task, result)

    async def _execute_bounded(
        self,
        state: ConversationGraphState,
        task: ActiveTaskState,
    ) -> WorkerResult | GraphOutcome:
        remaining = (state["control"].deadline_at - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            return GraphOutcome(kind="cancelled", code="TURN_DEADLINE_EXCEEDED")
        worker_task = asyncio.create_task(
            self._worker.execute(
                message=state["message"],
                task=task,
                global_entities=state["global_entities"],
                control=state["control"],
            )
        )
        invalidated_task = asyncio.create_task(
            self._execution_control.wait_invalidated(state["control"])
        )
        try:
            done, _ = await asyncio.wait(
                {worker_task, invalidated_task},
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if worker_task in done:
                return worker_task.result()
            await _cancel_with_grace(worker_task)
            code = (
                "STALE_FENCING_TOKEN"
                if invalidated_task in done
                else "TURN_DEADLINE_EXCEEDED"
            )
            return GraphOutcome(kind="cancelled", code=code)
        finally:
            await _cancel_with_grace(invalidated_task)

    async def _map_worker_result(
        self,
        state: ConversationGraphState,
        task: ActiveTaskState,
        result: WorkerResult,
    ) -> dict[str, object]:
        attempts = state["worker_attempts"] + 1
        if result.kind == "retryable_failure":
            if attempts >= _MAX_ATTEMPTS:
                return {
                    "worker_attempts": attempts,
                    "cost_microusd": result.cost_microusd,
                    "model_tokens": result.model_tokens,
                    "active_task": task.model_copy(
                        update={"retry_count": _MAX_ATTEMPTS, "last_failure": result.code}
                    ),
                    "outcome": GraphOutcome(
                        kind="handoff_required", code="RETRY_EXHAUSTED"
                    ),
                }
            return {
                "worker_attempts": attempts,
                "cost_microusd": result.cost_microusd,
                "model_tokens": result.model_tokens,
                "active_task": task.model_copy(
                    update={"retry_count": attempts, "last_failure": result.code}
                ),
                "outcome": None,
            }
        outcome_kind = {
            "completed": "completed",
            "needs_clarification": "needs_clarification",
            "non_retryable_failure": "refused",
            "policy_denied": "refused",
            "handoff_required": "handoff_required",
        }[result.kind]
        if len(result.evidence) > 32:
            return self._refused(attempts, "EVIDENCE_LIMIT_EXCEEDED", result)
        if result.kind == "completed" and intent_requires_grounding(task.intent):
            if not result.evidence:
                return self._refused(
                    attempts,
                    "MISSING_GROUNDED_EVIDENCE",
                    result,
                )
            try:
                evidence_is_valid = await _await_before_deadline(
                    self._evidence_authority.validate(
                        references=result.evidence,
                        control=state["control"],
                    ),
                    state,
                )
            except TimeoutError:
                return self._refused(
                    attempts,
                    "EVIDENCE_AUTHORITY_TIMEOUT",
                    result,
                )
            if not evidence_is_valid:
                return self._refused(
                    attempts,
                    "UNAPPROVED_GROUNDED_EVIDENCE",
                    result,
                )
        if result.kind == "completed" and (
            result.final_answer is None
            or not result.final_answer.strip()
            or len(result.final_answer) > 16_000
        ):
            return self._refused(attempts, "INVALID_FINAL_ANSWER", result)
        update: dict[str, object] = {
            "worker_attempts": attempts,
            "cost_microusd": result.cost_microusd,
            "model_tokens": result.model_tokens,
            "evidence": result.evidence,
            "outcome": GraphOutcome(
                kind=cast(
                    Literal[
                        "completed",
                        "needs_clarification",
                        "refused",
                        "handoff_required",
                    ],
                    outcome_kind,
                ),
                code=result.code,
                pending_slots=(
                    task.required_arguments if outcome_kind == "needs_clarification" else ()
                ),
            ),
        }
        if result.kind == "completed":
            update["final_answer"] = result.final_answer
            update["citations"] = result.citations
        return update

    @staticmethod
    def _refused(
        attempts: int,
        code: str,
        result: WorkerResult,
    ) -> dict[str, object]:
        return {
            "worker_attempts": attempts,
            "cost_microusd": result.cost_microusd,
            "model_tokens": result.model_tokens,
            "outcome": GraphOutcome(kind="refused", code=code),
        }

def terminal_control_outcome(state: ConversationGraphState) -> GraphOutcome | None:
    if state["control"].cancelled:
        return GraphOutcome(kind="cancelled", code="TURN_CANCELLED")
    if state["control"].deadline_at <= datetime.now(UTC):
        return GraphOutcome(kind="cancelled", code="TURN_DEADLINE_EXCEEDED")
    return None


async def _await_before_deadline[T](
    awaitable: Awaitable[T],
    state: ConversationGraphState,
) -> T:
    remaining = (state["control"].deadline_at - datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        if hasattr(awaitable, "close"):
            awaitable.close()  # type: ignore[union-attr]
        raise TimeoutError
    async with asyncio.timeout(remaining):
        return await awaitable


async def _cancel_with_grace(task: asyncio.Task[object], grace_seconds: float = 0.05) -> None:
    if task.done():
        return
    task.cancel()
    done, _ = await asyncio.wait({task}, timeout=grace_seconds)
    if task not in done:
        task.add_done_callback(_consume_late_task)


def _consume_late_task(task: asyncio.Task[object]) -> None:
    try:
        task.exception()
    except (asyncio.CancelledError, Exception):
        return
