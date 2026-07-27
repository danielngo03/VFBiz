import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform.checkpoints.execution_fence import PostgresExecutionFenceStore
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


def db() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    return engine, create_session_factory(engine)


async def clear_fence_table(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session, session.begin():
        await session.execute(text("TRUNCATE TABLE ai_conversation_execution_fence"))


@pytest.mark.asyncio
async def test_first_fencing_token_registers_as_current_and_uncancelled() -> None:
    engine, sessions = db()
    await clear_fence_table(sessions)
    store = PostgresExecutionFenceStore(sessions)
    session_id, turn_id = uuid4(), uuid4()

    record = await store.advance_fencing_token(
        session_id=session_id, turn_id=turn_id, fencing_token=1
    )

    assert record.fencing_token == 1
    assert record.cancelled is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_stale_fencing_token_never_lowers_the_stored_value() -> None:
    engine, sessions = db()
    await clear_fence_table(sessions)
    store = PostgresExecutionFenceStore(sessions)
    session_id, turn_id = uuid4(), uuid4()
    await store.advance_fencing_token(session_id=session_id, turn_id=turn_id, fencing_token=5)

    stale = await store.advance_fencing_token(
        session_id=session_id, turn_id=turn_id, fencing_token=2
    )

    assert stale.fencing_token == 5
    await engine.dispose()


@pytest.mark.asyncio
async def test_cancellation_at_the_current_fencing_token_is_observed_by_is_current_check() -> (
    None
):
    engine, sessions = db()
    await clear_fence_table(sessions)
    store = PostgresExecutionFenceStore(sessions)
    session_id, turn_id = uuid4(), uuid4()
    await store.advance_fencing_token(session_id=session_id, turn_id=turn_id, fencing_token=3)

    cancelled = await store.advance_cancellation(
        session_id=session_id, turn_id=turn_id, fencing_token=3
    )
    still_current = await store.advance_fencing_token(
        session_id=session_id, turn_id=turn_id, fencing_token=3
    )

    assert cancelled.cancelled is True
    assert still_current.fencing_token == 3
    assert still_current.cancelled is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_stale_cancellation_does_not_cancel_a_newer_superseding_attempt() -> None:
    engine, sessions = db()
    await clear_fence_table(sessions)
    store = PostgresExecutionFenceStore(sessions)
    session_id, turn_id = uuid4(), uuid4()
    await store.advance_fencing_token(session_id=session_id, turn_id=turn_id, fencing_token=1)
    await store.advance_fencing_token(session_id=session_id, turn_id=turn_id, fencing_token=9)

    stale_cancel = await store.advance_cancellation(
        session_id=session_id, turn_id=turn_id, fencing_token=1
    )
    current = await store.read(session_id=session_id, turn_id=turn_id)

    assert stale_cancel.fencing_token == 9
    assert stale_cancel.cancelled is False
    assert current is not None
    assert current.fencing_token == 9
    assert current.cancelled is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_future_cancellation_is_observed_once_that_attempt_registers() -> None:
    engine, sessions = db()
    await clear_fence_table(sessions)
    store = PostgresExecutionFenceStore(sessions)
    session_id, turn_id = uuid4(), uuid4()
    await store.advance_fencing_token(session_id=session_id, turn_id=turn_id, fencing_token=4)

    await store.advance_cancellation(session_id=session_id, turn_id=turn_id, fencing_token=6)
    caught_up = await store.advance_fencing_token(
        session_id=session_id, turn_id=turn_id, fencing_token=6
    )

    assert caught_up.fencing_token == 6
    assert caught_up.cancelled is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_fencing_advances_converge_on_the_highest_token() -> None:
    # Each racing UPSERT's own RETURNING reflects only what it observed at the
    # instant it committed, not later concurrent writers — that's expected
    # under row-level locking. The invariant under test is the *final* value
    # after every writer has finished, read back independently.
    engine, sessions = db()
    await clear_fence_table(sessions)
    store = PostgresExecutionFenceStore(sessions)
    session_id, turn_id = uuid4(), uuid4()

    results = await asyncio.gather(
        *(
            store.advance_fencing_token(
                session_id=session_id, turn_id=turn_id, fencing_token=token
            )
            for token in (2, 9, 4, 1, 7)
        )
    )
    final = await store.read(session_id=session_id, turn_id=turn_id)

    assert all(result.fencing_token <= 9 for result in results)
    assert final is not None
    assert final.fencing_token == 9
    await engine.dispose()


@pytest.mark.asyncio
async def test_read_returns_none_for_an_unregistered_turn() -> None:
    engine, sessions = db()
    await clear_fence_table(sessions)
    store = PostgresExecutionFenceStore(sessions)

    record = await store.read(session_id=uuid4(), turn_id=uuid4())

    assert record is None
    await engine.dispose()
