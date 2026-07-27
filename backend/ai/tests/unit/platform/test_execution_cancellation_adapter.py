from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from app.platform.cancellation import (
    CancellationCommand,
    FenceRecordLike,
    PostgresExecutionCancellationAdapter,
)


@dataclass(frozen=True, slots=True)
class _FakeRecord:
    fencing_token: int
    cancelled: bool


class FakeFenceStore:
    def __init__(self, *, wins: bool) -> None:
        self._wins = wins

    async def advance_cancellation(
        self, *, session_id: UUID, turn_id: UUID, fencing_token: int
    ) -> FenceRecordLike:
        if self._wins:
            return _FakeRecord(fencing_token=fencing_token, cancelled=True)
        return _FakeRecord(fencing_token=fencing_token + 1, cancelled=False)


def command(*, fencing_token: int = 3) -> CancellationCommand:
    return CancellationCommand(
        request_id=uuid4(),
        session_id=uuid4(),
        turn_id=uuid4(),
        conversation_version=1,
        fencing_token=fencing_token,
        reason="user_interrupt",
    )


@pytest.mark.asyncio
async def test_receipt_echoes_the_command_when_the_cancellation_wins() -> None:
    adapter = PostgresExecutionCancellationAdapter(FakeFenceStore(wins=True))
    cmd = command(fencing_token=3)

    receipt = await adapter.accept_durably(cmd)

    assert receipt.request_id == cmd.request_id
    assert receipt.turn_id == cmd.turn_id
    assert receipt.fencing_token == cmd.fencing_token
    assert receipt.durability == "durable"
    assert receipt.persisted_at.tzinfo is not None


@pytest.mark.asyncio
async def test_receipt_reflects_the_superseding_token_when_the_cancellation_is_stale() -> None:
    adapter = PostgresExecutionCancellationAdapter(FakeFenceStore(wins=False))
    cmd = command(fencing_token=3)

    receipt = await adapter.accept_durably(cmd)

    # A caller must compare the receipt to its own command: a mismatch here
    # signals this cancellation was already superseded by a newer attempt.
    assert receipt.fencing_token != cmd.fencing_token
