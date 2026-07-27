from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

from fastapi import Request, status

from app.platform.security.execution_assertion import assertion_error

CancellationReason = Literal[
    "budget_exhausted",
    "system_shutdown",
    "timeout",
    "user_interrupt",
]


@dataclass(frozen=True, slots=True)
class CancellationCommand:
    request_id: UUID
    session_id: UUID
    turn_id: UUID
    conversation_version: int
    fencing_token: int
    reason: CancellationReason


@dataclass(frozen=True, slots=True)
class DurableCancellationReceipt:
    cancellation_id: UUID
    request_id: UUID
    turn_id: UUID
    fencing_token: int
    persisted_at: datetime
    durability: Literal["durable"] = "durable"


class ExecutionCancellationPort(Protocol):
    async def accept_durably(
        self,
        command: CancellationCommand,
    ) -> DurableCancellationReceipt:
        """Persist the cancellation fence and return its durable receipt."""
        ...


def execution_cancellation_port(request: Request) -> ExecutionCancellationPort:
    configured = getattr(request.app.state, "execution_cancellation_port", None)
    if configured is None or not hasattr(configured, "accept_durably"):
        raise assertion_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "INTERNAL_FAILURE",
            "The execution cancellation boundary is unavailable.",
        )
    return configured


class FenceRecordLike(Protocol):
    @property
    def fencing_token(self) -> int: ...

    @property
    def cancelled(self) -> bool: ...


class FenceCancellationWriter(Protocol):
    async def advance_cancellation(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        fencing_token: int,
    ) -> FenceRecordLike: ...


class PostgresExecutionCancellationAdapter:
    """Durably accept a cancellation fence, fail-closed against a fresher one.

    The returned receipt's `fencing_token` reflects whichever fencing token
    actually won the CAS: it equals `command.fencing_token` only when this
    cancellation was not already superseded by a newer attempt. Callers must
    compare the receipt against the command they sent rather than assume
    success from a non-raising return.
    """

    def __init__(self, store: FenceCancellationWriter) -> None:
        self._store = store

    async def accept_durably(
        self,
        command: CancellationCommand,
    ) -> DurableCancellationReceipt:
        record = await self._store.advance_cancellation(
            session_id=command.session_id,
            turn_id=command.turn_id,
            fencing_token=command.fencing_token,
        )
        return DurableCancellationReceipt(
            cancellation_id=uuid4(),
            request_id=command.request_id,
            turn_id=command.turn_id,
            fencing_token=record.fencing_token,
            persisted_at=datetime.now(UTC),
        )
