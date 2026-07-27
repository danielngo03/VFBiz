import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.modules.assistant.domain import GraphControlState
from app.modules.assistant.infrastructure.execution_control import (
    FenceRecordLike,
    PostgresExecutionControlAdapter,
)


@dataclass(frozen=True, slots=True)
class _FakeRecord:
    fencing_token: int
    cancelled: bool


class FakeFenceStore:
    def __init__(self) -> None:
        self.record: _FakeRecord | None = None
        self.read_calls = 0

    async def advance_fencing_token(
        self, *, session_id: UUID, turn_id: UUID, fencing_token: int
    ) -> FenceRecordLike:
        if self.record is None or fencing_token > self.record.fencing_token:
            self.record = _FakeRecord(fencing_token=fencing_token, cancelled=False)
        return self.record

    async def read(self, *, session_id: UUID, turn_id: UUID) -> FenceRecordLike | None:
        self.read_calls += 1
        return self.record

    def cancel_current(self) -> None:
        assert self.record is not None
        self.record = _FakeRecord(fencing_token=self.record.fencing_token, cancelled=True)

    def supersede_with(self, fencing_token: int) -> None:
        self.record = _FakeRecord(fencing_token=fencing_token, cancelled=False)


def control(*, fencing_token: int = 1) -> GraphControlState:
    return GraphControlState(
        graph_version="graph-r1",
        policy_revision="policy-r1",
        knowledge_revision="knowledge-r1",
        assistant_profile="public_customer",
        authorization_context_hash="a" * 64,
        conversation_version=1,
        fencing_token=fencing_token,
        deadline_at=datetime.now(UTC) + timedelta(seconds=5),
    )


@pytest.mark.asyncio
async def test_is_current_registers_the_first_fencing_token_it_sees() -> None:
    store = FakeFenceStore()
    adapter = PostgresExecutionControlAdapter(
        session_id=uuid4(), turn_id=uuid4(), store=store
    )

    assert await adapter.is_current(control(fencing_token=5)) is True


@pytest.mark.asyncio
async def test_is_current_is_false_once_a_newer_attempt_registers() -> None:
    store = FakeFenceStore()
    adapter = PostgresExecutionControlAdapter(
        session_id=uuid4(), turn_id=uuid4(), store=store
    )
    await adapter.is_current(control(fencing_token=1))
    store.supersede_with(2)

    assert await adapter.is_current(control(fencing_token=1)) is False


@pytest.mark.asyncio
async def test_is_current_is_false_once_cancelled() -> None:
    store = FakeFenceStore()
    adapter = PostgresExecutionControlAdapter(
        session_id=uuid4(), turn_id=uuid4(), store=store
    )
    await adapter.is_current(control(fencing_token=1))
    store.cancel_current()

    assert await adapter.is_current(control(fencing_token=1)) is False


@pytest.mark.asyncio
async def test_wait_invalidated_returns_promptly_once_cancelled() -> None:
    store = FakeFenceStore()
    adapter = PostgresExecutionControlAdapter(
        session_id=uuid4(), turn_id=uuid4(), store=store
    )
    await adapter.is_current(control(fencing_token=1))

    async def cancel_soon() -> None:
        await asyncio.sleep(0.05)
        store.cancel_current()

    started = asyncio.get_running_loop().time()
    await asyncio.gather(
        adapter.wait_invalidated(control(fencing_token=1)),
        cancel_soon(),
    )
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_wait_invalidated_returns_immediately_for_an_unregistered_turn() -> None:
    store = FakeFenceStore()
    adapter = PostgresExecutionControlAdapter(
        session_id=uuid4(), turn_id=uuid4(), store=store
    )

    await adapter.wait_invalidated(control(fencing_token=1))

    assert store.read_calls == 1
