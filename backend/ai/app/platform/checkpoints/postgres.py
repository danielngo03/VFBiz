import hashlib
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.checkpoints.statements import (
    claim_once_statement,
    close_start_statement,
    expire_statement,
    finalize_statement,
    prepare_statement,
    reserve_start_statement,
)

_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_OPAQUE_CHECKPOINT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$")
_MAX_FENCING_TOKEN = 9_223_372_036_854_775_807


class ResumeGateConflict(RuntimeError):
    """A resume-gate transition did not match its expected state and token."""


@dataclass(frozen=True, slots=True)
class ResumeClaimRecord:
    token: str
    native_checkpoint_id: str
    envelope_digest: str


class PostgresResumeClaimStore:
    """PostgreSQL CAS adapter for cross-process assistant resume ownership.

    Reservation and claim tokens are unforgeable capabilities created only
    after a matching fencing-token transition. Later close/finalize calls bind
    to that original fencing token through the stored token digest, without
    asking callers to resend mutable fencing metadata.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._sessions = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_factory = token_factory or (lambda: secrets.token_hex(32))

    async def reserve_start(
        self,
        *,
        key: str,
        fencing_token: int,
        deadline_at: datetime,
    ) -> str | None:
        _validate_key(key)
        _validate_fencing_token(fencing_token)
        _validate_deadline(deadline_at, now=self._clock())
        reservation_token = self._new_token()
        statement = reserve_start_statement(
            key_hash=_digest(key),
            reservation_token_hash=_digest(reservation_token),
            fencing_token=fencing_token,
            deadline_at=deadline_at,
            now=self._clock(),
        )
        async with self._sessions() as session, session.begin():
            inserted = (await session.execute(statement)).scalar_one_or_none()
        return reservation_token if inserted is not None else None

    async def prepare(
        self,
        *,
        key: str,
        reservation_token: str,
        native_checkpoint_id: str,
        envelope_digest: str,
        interrupt_nonce: str,
        fencing_token: int,
        deadline_at: datetime,
    ) -> None:
        _validate_key(key)
        _validate_token(reservation_token, name="reservation_token")
        _validate_checkpoint_id(native_checkpoint_id)
        _validate_digest(envelope_digest, name="envelope_digest")
        _validate_digest(interrupt_nonce, name="interrupt_nonce")
        _validate_fencing_token(fencing_token)
        now = self._clock()
        _validate_deadline(deadline_at, now=now)
        statement = prepare_statement(
            key_hash=_digest(key),
            reservation_token_hash=_digest(reservation_token),
            native_checkpoint_id=native_checkpoint_id,
            envelope_digest=envelope_digest,
            interrupt_nonce_hash=_digest(interrupt_nonce),
            fencing_token=fencing_token,
            deadline_at=deadline_at,
            now=now,
        )
        await self._require_transition(statement, "resume start reservation is stale")

    async def close_start(
        self,
        *,
        key: str,
        reservation_token: str,
        succeeded: bool,
    ) -> None:
        _validate_key(key)
        _validate_token(reservation_token, name="reservation_token")
        statement = close_start_statement(
            key_hash=_digest(key),
            reservation_token_hash=_digest(reservation_token),
            target_state="completed" if succeeded else "failed_closed",
        )
        await self._require_transition(statement, "resume start cannot be closed")

    async def claim_once(
        self,
        *,
        key: str,
        interrupt_nonce: str,
        fencing_token: int,
    ) -> ResumeClaimRecord | None:
        _validate_key(key)
        _validate_digest(interrupt_nonce, name="interrupt_nonce")
        _validate_fencing_token(fencing_token)
        claim_token = self._new_token()
        now = self._clock()
        statement = claim_once_statement(
            key_hash=_digest(key),
            interrupt_nonce_hash=_digest(interrupt_nonce),
            claim_token_hash=_digest(claim_token),
            fencing_token=fencing_token,
            now=now,
        )
        async with self._sessions() as session, session.begin():
            row = (await session.execute(statement)).one_or_none()
            if row is None:
                await session.execute(expire_statement(key_hash=_digest(key), now=now))
                return None
        native_checkpoint_id = row.native_checkpoint_id
        envelope_digest = row.envelope_digest
        if not isinstance(native_checkpoint_id, str) or not isinstance(
            envelope_digest, str
        ):
            raise ResumeGateConflict("stored resume claim is incomplete")
        _validate_checkpoint_id(native_checkpoint_id)
        _validate_digest(envelope_digest, name="stored envelope_digest")
        return ResumeClaimRecord(
            token=claim_token,
            native_checkpoint_id=native_checkpoint_id,
            envelope_digest=envelope_digest,
        )

    async def finalize(
        self,
        *,
        key: str,
        claim_token: str,
        succeeded: bool,
    ) -> None:
        _validate_key(key)
        _validate_token(claim_token, name="claim_token")
        statement = finalize_statement(
            key_hash=_digest(key),
            claim_token_hash=_digest(claim_token),
            target_state="completed" if succeeded else "failed_closed",
        )
        await self._require_transition(statement, "resume claim cannot be finalized")

    async def _require_transition(self, statement: Update, message: str) -> None:
        async with self._sessions() as session, session.begin():
            changed = (await session.execute(statement)).scalar_one_or_none()
        if changed is None:
            raise ResumeGateConflict(message)

    def _new_token(self) -> str:
        token = self._token_factory()
        _validate_token(token, name="generated token")
        return token

def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _validate_key(value: str) -> None:
    if not value or len(value) > 512 or any(character.isspace() for character in value):
        raise ValueError("resume key must be a bounded opaque value")


def _validate_digest(value: str, *, name: str) -> None:
    if _HEX_DIGEST.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _validate_token(value: str, *, name: str) -> None:
    _validate_digest(value, name=name)


def _validate_checkpoint_id(value: str) -> None:
    if _OPAQUE_CHECKPOINT_ID.fullmatch(value) is None:
        raise ValueError("native_checkpoint_id must be an opaque identifier")


def _validate_fencing_token(value: int) -> None:
    if isinstance(value, bool) or value <= 0 or value > _MAX_FENCING_TOKEN:
        raise ValueError("fencing_token must be a positive signed 64-bit integer")


def _validate_deadline(value: datetime, *, now: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("deadline_at must include a timezone")
    if value <= now:
        raise ValueError("deadline_at must be in the future")
