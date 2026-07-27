import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.checkpoints.execution_fence_statements import (
    advance_cancellation_statement,
    advance_fencing_token_statement,
    read_fence_statement,
)

_MAX_FENCING_TOKEN = 9_223_372_036_854_775_807


@dataclass(frozen=True, slots=True)
class FenceRecord:
    fencing_token: int
    cancelled: bool


def turn_hash(session_id: UUID, turn_id: UUID) -> str:
    return hashlib.sha256(f"{session_id.hex}:{turn_id.hex}".encode()).hexdigest()


class PostgresExecutionFenceStore:
    """PostgreSQL CAS adapter for cross-process turn fencing and cancellation.

    A single `(session_id, turn_id)` row tracks the highest fencing token
    observed for that turn and whether it has been durably cancelled.
    `fencing_token` only ever advances (GREATEST), so a stale caller —
    superseded by a newer attempt or a newer cancellation — always reads
    back the current winner instead of silently overwriting it.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def advance_fencing_token(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        fencing_token: int,
    ) -> FenceRecord:
        _validate_fencing_token(fencing_token)
        statement = advance_fencing_token_statement(
            turn_hash=turn_hash(session_id, turn_id),
            fencing_token=fencing_token,
        )
        async with self._sessions() as session, session.begin():
            row = (await session.execute(statement)).one()
        return FenceRecord(fencing_token=row.fencing_token, cancelled=row.cancelled)

    async def advance_cancellation(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        fencing_token: int,
    ) -> FenceRecord:
        _validate_fencing_token(fencing_token)
        statement = advance_cancellation_statement(
            turn_hash=turn_hash(session_id, turn_id),
            fencing_token=fencing_token,
        )
        async with self._sessions() as session, session.begin():
            row = (await session.execute(statement)).one()
        return FenceRecord(fencing_token=row.fencing_token, cancelled=row.cancelled)

    async def read(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
    ) -> FenceRecord | None:
        statement = read_fence_statement(turn_hash=turn_hash(session_id, turn_id))
        async with self._sessions() as session:
            row = (await session.execute(statement)).one_or_none()
        if row is None:
            return None
        return FenceRecord(fencing_token=row.fencing_token, cancelled=row.cancelled)


def _validate_fencing_token(value: int) -> None:
    if isinstance(value, bool) or value <= 0 or value > _MAX_FENCING_TOKEN:
        raise ValueError("fencing_token must be a positive signed 64-bit integer")
