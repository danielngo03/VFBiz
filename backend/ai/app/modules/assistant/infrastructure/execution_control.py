import asyncio
from typing import Protocol
from uuid import UUID

from app.modules.assistant.domain import GraphControlState

_POLL_INTERVAL_SECONDS = 0.2


class FenceRecordLike(Protocol):
    @property
    def fencing_token(self) -> int: ...

    @property
    def cancelled(self) -> bool: ...


class FenceReader(Protocol):
    async def advance_fencing_token(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        fencing_token: int,
    ) -> FenceRecordLike: ...

    async def read(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
    ) -> FenceRecordLike | None: ...


class PostgresExecutionControlAdapter:
    """Live cancellation/staleness check for one turn's worker execution.

    Constructed per turn (closing over the turn's identity) rather than as an
    app-wide singleton, because `GraphControlState` — the only argument the
    `ExecutionControlPort` protocol receives — carries no session/turn
    identity of its own; only `fencing_token` is comparable across calls.
    """

    def __init__(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        store: FenceReader,
    ) -> None:
        self._session_id = session_id
        self._turn_id = turn_id
        self._store = store

    async def is_current(self, control: GraphControlState) -> bool:
        record = await self._store.advance_fencing_token(
            session_id=self._session_id,
            turn_id=self._turn_id,
            fencing_token=control.fencing_token,
        )
        return record.fencing_token == control.fencing_token and not record.cancelled

    async def wait_invalidated(self, control: GraphControlState) -> None:
        while True:
            record = await self._store.read(
                session_id=self._session_id,
                turn_id=self._turn_id,
            )
            if record is None:
                return
            if record.cancelled or record.fencing_token != control.fencing_token:
                return
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
