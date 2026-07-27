from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.base import Executable

from app.platform.checkpoints.models import ConversationExecutionFence


def advance_fencing_token_statement(
    *,
    turn_hash: str,
    fencing_token: int,
) -> Executable:
    """Register this fencing token as current if it is not already stale.

    Never touches `cancelled`: a live in-flight check must not un-cancel a
    turn, and a fresh turn starts uncancelled only via the insert branch.
    """
    statement = insert(ConversationExecutionFence).values(
        turn_hash=turn_hash,
        fencing_token=fencing_token,
        cancelled=False,
    )
    return (
        statement.on_conflict_do_update(
            index_elements=[ConversationExecutionFence.turn_hash],
            set_={
                "fencing_token": func.greatest(
                    ConversationExecutionFence.fencing_token,
                    statement.excluded.fencing_token,
                ),
                "updated_at": func.now(),
            },
        )
        .returning(
            ConversationExecutionFence.fencing_token,
            ConversationExecutionFence.cancelled,
        )
    )


def advance_cancellation_statement(
    *,
    turn_hash: str,
    fencing_token: int,
) -> Executable:
    """Durably mark a turn cancelled unless a newer fencing token already won.

    A cancellation whose fencing_token is older than the stored value targets
    an already-superseded attempt and must be a no-op: the newer, unaffected
    attempt keeps its own fencing_token and cancelled state unchanged.
    """
    statement = insert(ConversationExecutionFence).values(
        turn_hash=turn_hash,
        fencing_token=fencing_token,
        cancelled=True,
    )
    return (
        statement.on_conflict_do_update(
            index_elements=[ConversationExecutionFence.turn_hash],
            set_={
                "fencing_token": func.greatest(
                    ConversationExecutionFence.fencing_token,
                    statement.excluded.fencing_token,
                ),
                "cancelled": case(
                    (
                        statement.excluded.fencing_token
                        >= ConversationExecutionFence.fencing_token,
                        True,
                    ),
                    else_=ConversationExecutionFence.cancelled,
                ),
                "updated_at": func.now(),
            },
        )
        .returning(
            ConversationExecutionFence.fencing_token,
            ConversationExecutionFence.cancelled,
        )
    )


def read_fence_statement(*, turn_hash: str) -> Executable:
    return select(
        ConversationExecutionFence.fencing_token,
        ConversationExecutionFence.cancelled,
    ).where(ConversationExecutionFence.turn_hash == turn_hash)
