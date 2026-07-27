from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.sql.base import Executable

from app.platform.checkpoints.models import (
    ConversationExecutionFence,
    ConversationResumeGate,
)

_ABANDONED_RESUME_GATE_STATES = ("reserved", "waiting", "claimed")
_TERMINAL_RESUME_GATE_STATES = ("completed", "failed_closed", "expired")


def expire_abandoned_resume_gate_claims_statement(*, now: datetime) -> Executable:
    """Bulk-transition resume-gate rows nobody ever closed out.

    Mirrors `expire_statement`'s single-key reactive transition (used inline
    when a `claim_once` attempt misses), but as a scheduled sweep across
    every row abandoned by a process that crashed before `close_start()` or
    `finalize()` ran — including a reservation that never reached `prepare()`
    at all, which the narrower reactive check does not need to consider.
    """
    return (
        update(ConversationResumeGate)
        .where(
            ConversationResumeGate.state.in_(_ABANDONED_RESUME_GATE_STATES),
            ConversationResumeGate.deadline_at <= now,
        )
        .values(state="expired", updated_at=func.now())
    )


def purge_terminal_resume_gate_claims_statement(
    *, older_than: datetime, limit: int
) -> Executable:
    terminal_ids = (
        select(ConversationResumeGate.id)
        .where(
            ConversationResumeGate.state.in_(_TERMINAL_RESUME_GATE_STATES),
            ConversationResumeGate.updated_at < older_than,
        )
        .limit(limit)
    )
    return delete(ConversationResumeGate).where(
        ConversationResumeGate.id.in_(terminal_ids)
    )


def purge_stale_execution_fences_statement(
    *, older_than: datetime, limit: int
) -> Executable:
    stale_ids = (
        select(ConversationExecutionFence.id)
        .where(ConversationExecutionFence.updated_at < older_than)
        .limit(limit)
    )
    return delete(ConversationExecutionFence).where(
        ConversationExecutionFence.id.in_(stale_ids)
    )
