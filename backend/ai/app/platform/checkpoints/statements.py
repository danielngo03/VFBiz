from datetime import datetime

from sqlalchemy import Update, case, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.base import Executable

from app.platform.checkpoints.models import ConversationResumeGate


def reserve_start_statement(
    *,
    key_hash: str,
    reservation_token_hash: str,
    fencing_token: int,
    deadline_at: datetime,
    now: datetime,
) -> Executable:
    statement = insert(ConversationResumeGate).values(
        key_hash=key_hash,
        state="reserved",
        fencing_token=fencing_token,
        deadline_at=deadline_at,
        reservation_token_hash=reservation_token_hash,
    )
    return (
        statement
        .on_conflict_do_update(
            index_elements=[ConversationResumeGate.key_hash],
            set_={
                "fencing_token": statement.excluded.fencing_token,
                "deadline_at": statement.excluded.deadline_at,
                "reservation_token_hash": statement.excluded.reservation_token_hash,
                "updated_at": func.now(),
            },
            where=(
                (ConversationResumeGate.state == "reserved")
                & (ConversationResumeGate.deadline_at <= now)
                & (ConversationResumeGate.fencing_token < fencing_token)
            ),
        )
        .returning(ConversationResumeGate.key_hash)
    )


def prepare_statement(
    *,
    key_hash: str,
    reservation_token_hash: str,
    native_checkpoint_id: str,
    envelope_digest: str,
    interrupt_nonce_hash: str,
    fencing_token: int,
    deadline_at: datetime,
    now: datetime,
) -> Update:
    return (
        update(ConversationResumeGate)
        .where(
            ConversationResumeGate.key_hash == key_hash,
            ConversationResumeGate.state == "reserved",
            ConversationResumeGate.reservation_token_hash == reservation_token_hash,
            ConversationResumeGate.fencing_token == fencing_token,
            ConversationResumeGate.deadline_at == deadline_at,
            ConversationResumeGate.deadline_at > now,
        )
        .values(
            state="waiting",
            reservation_token_hash=None,
            native_checkpoint_id=native_checkpoint_id,
            envelope_digest=envelope_digest,
            interrupt_nonce_hash=interrupt_nonce_hash,
            deadline_at=deadline_at,
            updated_at=func.now(),
        )
        .returning(ConversationResumeGate.key_hash)
    )


def close_start_statement(
    *, key_hash: str, reservation_token_hash: str, target_state: str
) -> Update:
    return (
        update(ConversationResumeGate)
        .where(
            ConversationResumeGate.key_hash == key_hash,
            ConversationResumeGate.state == "reserved",
            ConversationResumeGate.reservation_token_hash == reservation_token_hash,
        )
        .values(
            state=target_state,
            reservation_token_hash=None,
            updated_at=func.now(),
        )
        .returning(ConversationResumeGate.key_hash)
    )


def claim_once_statement(
    *,
    key_hash: str,
    interrupt_nonce_hash: str,
    claim_token_hash: str,
    fencing_token: int,
    now: datetime,
) -> Update:
    return (
        update(ConversationResumeGate)
        .where(
            ConversationResumeGate.key_hash == key_hash,
            ConversationResumeGate.state == "waiting",
            ConversationResumeGate.interrupt_nonce_hash == interrupt_nonce_hash,
            ConversationResumeGate.fencing_token == fencing_token,
            ConversationResumeGate.deadline_at > now,
        )
        .values(
            state="claimed",
            claim_token_hash=claim_token_hash,
            updated_at=func.now(),
        )
        .returning(
            ConversationResumeGate.native_checkpoint_id,
            ConversationResumeGate.envelope_digest,
        )
    )


def expire_statement(*, key_hash: str, now: datetime) -> Update:
    return (
        update(ConversationResumeGate)
        .where(
            ConversationResumeGate.key_hash == key_hash,
            ConversationResumeGate.state.in_(("waiting", "claimed")),
            ConversationResumeGate.deadline_at <= now,
        )
        .values(state="expired", updated_at=func.now())
    )


def finalize_statement(
    *, key_hash: str, claim_token_hash: str, target_state: str
) -> Update:
    return (
        update(ConversationResumeGate)
        .where(
            ConversationResumeGate.key_hash == key_hash,
            ConversationResumeGate.state.in_(("claimed", "expired")),
            ConversationResumeGate.claim_token_hash == claim_token_hash,
        )
        .values(
            state=case(
                (ConversationResumeGate.state == "expired", "expired"),
                else_=target_state,
            ),
            claim_token_hash=None,
            updated_at=func.now(),
        )
        .returning(ConversationResumeGate.key_hash)
    )
