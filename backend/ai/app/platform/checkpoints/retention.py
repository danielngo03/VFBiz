from datetime import datetime
from typing import cast

from sqlalchemy import CursorResult, Delete, Update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.checkpoints.retention_statements import (
    expire_abandoned_resume_gate_claims_statement,
    purge_stale_execution_fences_statement,
    purge_terminal_resume_gate_claims_statement,
)

_DEFAULT_SWEEP_LIMIT = 1_000


class ConversationOperationalRetention:
    """Bounded, idempotent cleanup for the durable resume-gate and
    execution-fence tables that back one assistant turn's cross-process
    coordination (see `ConversationResumeGate`/`ConversationExecutionFence`).

    Neither table stores customer content, raw identity or provider
    output — only opaque hashes, tokens, counters and timestamps — so this
    is an operational storage-hygiene concern, not a DSAR/PII retention
    policy. Callers pick their own cutoffs; nothing here schedules itself.
    Wiring a periodic invocation (cron, Kubernetes CronJob, ops runbook) is
    the same still-open step as backend/api's own `purgeExpiredSessions`,
    which today also has no scheduled caller — this class reaches the same
    "well-tested, callable, not yet scheduled" state, not further behind it.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def expire_abandoned_resume_gate_claims(self, *, now: datetime) -> int:
        """Transition resume-gate rows a crashed process never closed out
        (still `reserved`/`waiting`/`claimed` past their own turn deadline)
        to `expired`, so a later purge pass can delete them. Never touches a
        row whose deadline has not yet passed, matching the same fail-closed
        deadline the graph itself enforces at request time.
        """
        statement = expire_abandoned_resume_gate_claims_statement(now=now)
        async with self._sessions() as session, session.begin():
            result = cast(CursorResult[Update], await session.execute(statement))
            return result.rowcount

    async def purge_terminal_resume_gate_claims(
        self, *, older_than: datetime, limit: int = _DEFAULT_SWEEP_LIMIT
    ) -> int:
        """Delete resume-gate rows already `completed`/`failed_closed`/
        `expired` and untouched since before `older_than`. Bounded by
        `limit` per call so a large backlog is swept over several calls
        rather than one unbounded transaction.
        """
        statement = purge_terminal_resume_gate_claims_statement(
            older_than=older_than, limit=limit
        )
        async with self._sessions() as session, session.begin():
            result = cast(CursorResult[Delete], await session.execute(statement))
            return result.rowcount

    async def purge_stale_execution_fences(
        self, *, older_than: datetime, limit: int = _DEFAULT_SWEEP_LIMIT
    ) -> int:
        """Delete execution-fence rows untouched since before `older_than`.

        This table has no lifecycle state of its own (see
        `ConversationExecutionFence`) — it is only ever a fencing watermark
        for one turn's active execution window, so age since the last
        `advance_fencing_token`/`advance_cancellation` call is the only
        signal needed: a turn still legitimately executing keeps bumping
        `updated_at`, so `older_than` should stay comfortably longer than
        any realistic turn deadline.
        """
        statement = purge_stale_execution_fences_statement(
            older_than=older_than, limit=limit
        )
        async with self._sessions() as session, session.begin():
            result = cast(CursorResult[Delete], await session.execute(statement))
            return result.rowcount
