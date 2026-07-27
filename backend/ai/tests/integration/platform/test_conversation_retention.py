import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform.checkpoints.models import (
    ConversationExecutionFence,
    ConversationResumeGate,
)
from app.platform.checkpoints.retention import ConversationOperationalRetention
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
OLD = NOW - timedelta(days=8)
RECENT = NOW - timedelta(minutes=5)


def db() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    return engine, create_session_factory(engine)


async def clear_tables(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session, session.begin():
        await session.execute(text("TRUNCATE TABLE ai_conversation_resume_gate"))
        await session.execute(text("TRUNCATE TABLE ai_conversation_execution_fence"))


async def insert_resume_gate_row(
    sessions: async_sessionmaker[AsyncSession],
    *,
    key_hash: str,
    state: str,
    deadline_at: datetime,
    updated_at: datetime,
) -> None:
    async with sessions() as session, session.begin():
        await session.execute(
            insert(ConversationResumeGate).values(
                key_hash=key_hash,
                state=state,
                fencing_token=1,
                deadline_at=deadline_at,
                reservation_token_hash="a" * 64,
                updated_at=updated_at,
            )
        )


async def insert_execution_fence_row(
    sessions: async_sessionmaker[AsyncSession],
    *,
    turn_hash: str,
    updated_at: datetime,
) -> None:
    async with sessions() as session, session.begin():
        await session.execute(
            insert(ConversationExecutionFence).values(
                turn_hash=turn_hash,
                fencing_token=1,
                cancelled=False,
                updated_at=updated_at,
            )
        )


@pytest.mark.asyncio
async def test_expire_only_touches_abandoned_claims_past_their_own_deadline() -> None:
    engine, sessions = db()
    await clear_tables(sessions)
    await insert_resume_gate_row(
        sessions,
        key_hash="a" * 64,
        state="reserved",
        deadline_at=NOW - timedelta(minutes=1),
        updated_at=OLD,
    )
    await insert_resume_gate_row(
        sessions,
        key_hash="b" * 64,
        state="reserved",
        deadline_at=NOW + timedelta(minutes=30),
        updated_at=OLD,
    )
    retention = ConversationOperationalRetention(sessions)

    changed = await retention.expire_abandoned_resume_gate_claims(now=NOW)

    assert changed == 1
    async with sessions() as session:
        rows = (
            await session.execute(
                select(ConversationResumeGate.key_hash, ConversationResumeGate.state)
            )
        ).all()
    states_by_key = {row.key_hash: row.state for row in rows}
    assert states_by_key["a" * 64] == "expired"
    assert states_by_key["b" * 64] == "reserved"
    await engine.dispose()


@pytest.mark.asyncio
async def test_purge_terminal_claims_deletes_only_old_terminal_rows() -> None:
    engine, sessions = db()
    await clear_tables(sessions)
    await insert_resume_gate_row(
        sessions,
        key_hash="a" * 64,
        state="completed",
        deadline_at=OLD + timedelta(minutes=5),
        updated_at=OLD,
    )
    await insert_resume_gate_row(
        sessions,
        key_hash="b" * 64,
        state="completed",
        deadline_at=RECENT + timedelta(minutes=5),
        updated_at=RECENT,
    )
    await insert_resume_gate_row(
        sessions,
        key_hash="c" * 64,
        state="reserved",
        deadline_at=OLD + timedelta(minutes=5),
        updated_at=OLD,
    )
    retention = ConversationOperationalRetention(sessions)

    deleted = await retention.purge_terminal_resume_gate_claims(
        older_than=NOW - timedelta(days=1)
    )

    assert deleted == 1
    async with sessions() as session:
        remaining = (
            await session.execute(select(ConversationResumeGate.key_hash))
        ).scalars().all()
    assert set(remaining) == {"b" * 64, "c" * 64}
    await engine.dispose()


@pytest.mark.asyncio
async def test_purge_terminal_claims_respects_the_limit() -> None:
    engine, sessions = db()
    await clear_tables(sessions)
    for index in range(5):
        await insert_resume_gate_row(
            sessions,
            key_hash=f"{index}" * 64,
            state="completed",
            deadline_at=OLD + timedelta(minutes=5),
            updated_at=OLD,
        )
    retention = ConversationOperationalRetention(sessions)

    deleted = await retention.purge_terminal_resume_gate_claims(
        older_than=NOW - timedelta(days=1), limit=2
    )

    assert deleted == 2
    async with sessions() as session:
        remaining_count = (
            await session.execute(select(ConversationResumeGate.id))
        ).all()
    assert len(remaining_count) == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_purge_stale_execution_fences_deletes_only_old_rows() -> None:
    engine, sessions = db()
    await clear_tables(sessions)
    await insert_execution_fence_row(sessions, turn_hash="a" * 64, updated_at=OLD)
    await insert_execution_fence_row(sessions, turn_hash="b" * 64, updated_at=RECENT)
    retention = ConversationOperationalRetention(sessions)

    deleted = await retention.purge_stale_execution_fences(
        older_than=NOW - timedelta(days=1)
    )

    assert deleted == 1
    async with sessions() as session:
        remaining = (
            await session.execute(select(ConversationExecutionFence.turn_hash))
        ).scalars().all()
    assert remaining == ["b" * 64]
    await engine.dispose()
