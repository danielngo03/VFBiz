from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.platform.checkpoints.postgres import (
    PostgresResumeClaimStore,
    ResumeGateConflict,
    _digest,
)
from app.platform.checkpoints.statements import (
    claim_once_statement,
    finalize_statement,
    prepare_statement,
    reserve_start_statement,
)

NOW = datetime(2026, 7, 25, tzinfo=UTC)
DEADLINE = NOW + timedelta(minutes=5)
TOKEN = "a" * 64
CLAIM_TOKEN = "b" * 64
NONCE = "c" * 64
ENVELOPE = "d" * 64
KEY = "session:turn:graph-r1"


class FakeResult:
    def __init__(self, *, scalar: object = None, row: object = None) -> None:
        self._scalar = scalar
        self._row = row

    def scalar_one_or_none(self) -> object:
        return self._scalar

    def one_or_none(self) -> object:
        return self._row


class NullAsyncContext(AbstractAsyncContextManager[Any]):
    def __init__(self, value: Any = None) -> None:
        self._value = value

    async def __aenter__(self) -> Any:
        return self._value

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeSession:
    def __init__(self, results: Sequence[FakeResult]) -> None:
        self.results = list(results)
        self.statements: list[object] = []

    def begin(self) -> NullAsyncContext:
        return NullAsyncContext()

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        return self.results.pop(0)


class FakeSessionFactory:
    def __init__(self, results: Sequence[FakeResult]) -> None:
        self.session = FakeSession(results)

    def __call__(self) -> NullAsyncContext:
        return NullAsyncContext(self.session)


def make_store(
    results: Sequence[FakeResult],
    *,
    tokens: Sequence[str] = (TOKEN,),
) -> tuple[PostgresResumeClaimStore, FakeSession]:
    token_values = iter(tokens)
    factory = FakeSessionFactory(results)
    store = PostgresResumeClaimStore(  # type: ignore[arg-type]
        factory,
        clock=lambda: NOW,
        token_factory=lambda: next(token_values),
    )
    return store, factory.session


@pytest.mark.asyncio
async def test_reserve_start_reclaims_only_an_expired_reservation_with_newer_fence() -> None:
    store, session = make_store(
        [FakeResult(scalar=_digest(KEY)), FakeResult(scalar=None)],
        tokens=(TOKEN, CLAIM_TOKEN),
    )

    first = await store.reserve_start(
        key=KEY,
        fencing_token=7,
        deadline_at=DEADLINE,
    )
    duplicate = await store.reserve_start(
        key=KEY,
        fencing_token=7,
        deadline_at=DEADLINE,
    )

    assert first == TOKEN
    assert duplicate is None
    sql = compile_sql(session.statements[0])
    assert "ON CONFLICT (key_hash) DO UPDATE" in sql
    assert "state =" in sql
    assert "deadline_at <=" in sql
    assert "fencing_token <" in sql


@pytest.mark.asyncio
async def test_claim_once_uses_one_waiting_to_claimed_cas() -> None:
    row = SimpleNamespace(native_checkpoint_id="checkpoint-01", envelope_digest=ENVELOPE)
    store, session = make_store(
        [FakeResult(row=row), FakeResult(row=None), FakeResult()],
        tokens=(TOKEN, CLAIM_TOKEN),
    )

    first = await store.claim_once(
        key=KEY,
        interrupt_nonce=NONCE,
        fencing_token=7,
    )
    second = await store.claim_once(
        key=KEY,
        interrupt_nonce=NONCE,
        fencing_token=7,
    )

    assert first is not None
    assert first.token == TOKEN
    assert first.native_checkpoint_id == "checkpoint-01"
    assert second is None
    claim_sql = compile_sql(session.statements[0])
    assert "state =" in claim_sql
    assert "fencing_token =" in claim_sql
    assert "interrupt_nonce_hash =" in claim_sql
    assert "deadline_at >" in claim_sql
    assert "RETURNING" in claim_sql
    assert len(session.statements) == 3


@pytest.mark.asyncio
async def test_expired_waiting_claim_is_failed_closed() -> None:
    store, session = make_store([FakeResult(row=None), FakeResult()])

    claim = await store.claim_once(
        key=KEY,
        interrupt_nonce=NONCE,
        fencing_token=7,
    )

    assert claim is None
    expiry_sql = compile_sql(session.statements[1])
    assert "SET state=" in expiry_sql
    assert "deadline_at <=" in expiry_sql


@pytest.mark.asyncio
async def test_expired_claim_can_be_finalized_idempotently_without_reopening() -> None:
    store, session = make_store([FakeResult(scalar=_digest(KEY))])

    await store.finalize(key=KEY, claim_token=CLAIM_TOKEN, succeeded=True)

    sql = compile_sql(session.statements[0])
    assert "state IN" in sql
    assert "CASE WHEN" in sql
    compiled = session.statements[0].compile(dialect=postgresql.dialect())  # type: ignore[union-attr]
    assert "expired" in compiled.params.values()


@pytest.mark.asyncio
async def test_prepare_fails_closed_on_stale_reservation_or_fencing_token() -> None:
    store, _ = make_store([FakeResult(scalar=None)])

    with pytest.raises(ResumeGateConflict, match="reservation is stale"):
        await store.prepare(
            key=KEY,
            reservation_token=TOKEN,
            native_checkpoint_id="checkpoint-01",
            envelope_digest=ENVELOPE,
            interrupt_nonce=NONCE,
            fencing_token=7,
            deadline_at=DEADLINE,
        )


@pytest.mark.asyncio
async def test_finalize_rejects_wrong_or_replayed_claim_token() -> None:
    store, _ = make_store([FakeResult(scalar=None)])

    with pytest.raises(ResumeGateConflict, match="cannot be finalized"):
        await store.finalize(key=KEY, claim_token=CLAIM_TOKEN, succeeded=True)


@pytest.mark.asyncio
async def test_terminal_key_cannot_be_reopened() -> None:
    store, _ = make_store([FakeResult(scalar=None)])

    assert (
        await store.reserve_start(
            key=KEY,
            fencing_token=7,
            deadline_at=DEADLINE,
        )
        is None
    )


@pytest.mark.asyncio
async def test_prepare_rejects_deadline_extension_before_database_access() -> None:
    store, session = make_store([])

    with pytest.raises(ValueError, match="future"):
        await store.prepare(
            key=KEY,
            reservation_token=TOKEN,
            native_checkpoint_id="checkpoint-01",
            envelope_digest=ENVELOPE,
            interrupt_nonce=NONCE,
            fencing_token=7,
            deadline_at=NOW,
        )
    assert session.statements == []


def test_sql_contracts_pin_state_token_fencing_and_deadline() -> None:
    reserve_statement = reserve_start_statement(
        key_hash=_digest(KEY),
        reservation_token_hash=_digest(TOKEN),
        fencing_token=7,
        deadline_at=DEADLINE,
        now=NOW,
    )
    reserve_sql = compile_sql(reserve_statement)
    prepare_sql = compile_sql(
        prepare_statement(
            key_hash=_digest(KEY),
            reservation_token_hash=_digest(TOKEN),
            native_checkpoint_id="checkpoint-01",
            envelope_digest=ENVELOPE,
            interrupt_nonce_hash=_digest(NONCE),
            fencing_token=7,
            deadline_at=DEADLINE,
            now=NOW,
        )
    )
    claim_sql = compile_sql(
        claim_once_statement(
            key_hash=_digest(KEY),
            interrupt_nonce_hash=_digest(NONCE),
            claim_token_hash=_digest(CLAIM_TOKEN),
            fencing_token=7,
            now=NOW,
        )
    )
    finalize_sql = compile_sql(
        finalize_statement(
            key_hash=_digest(KEY),
            claim_token_hash=_digest(CLAIM_TOKEN),
            target_state="completed",
        )
    )

    assert "ON CONFLICT (key_hash) DO UPDATE" in reserve_sql
    assert "deadline_at <=" in reserve_sql
    assert "fencing_token <" in reserve_sql
    assert "reservation_token_hash =" in prepare_sql
    assert "fencing_token =" in prepare_sql
    assert "deadline_at =" in prepare_sql
    assert "deadline_at >" in prepare_sql
    assert "interrupt_nonce_hash =" in claim_sql
    assert "state =" in claim_sql
    assert "claim_token_hash =" in finalize_sql
    assert "state IN" in finalize_sql
    assert "CASE WHEN" in finalize_sql

    compiled_reserve = reserve_statement.compile(dialect=postgresql.dialect())
    persisted_values = set(compiled_reserve.params.values())
    assert KEY not in persisted_values
    assert TOKEN not in persisted_values
    assert _digest(KEY) in persisted_values
    assert _digest(TOKEN) in persisted_values


def compile_sql(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[union-attr]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )
