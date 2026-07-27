from datetime import datetime

import pytest

from app.modules.assistant.application import ResumeClaim, ResumeClaimPort
from app.modules.assistant.infrastructure import PostgresResumeClaimAdapter
from app.platform.checkpoints.postgres import ResumeClaimRecord


class FakeDurableResumeGate:
    def __init__(self, record: ResumeClaimRecord | None) -> None:
        self.record = record

    async def reserve_start(
        self, *, key: str, fencing_token: int, deadline_at: datetime
    ) -> str | None:
        return "a" * 64

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
        return None

    async def close_start(
        self, *, key: str, reservation_token: str, succeeded: bool
    ) -> None:
        return None

    async def claim_once(
        self, *, key: str, interrupt_nonce: str, fencing_token: int
    ) -> ResumeClaimRecord | None:
        return self.record

    async def finalize(
        self, *, key: str, claim_token: str, succeeded: bool
    ) -> None:
        return None


def require_application_port(port: ResumeClaimPort) -> ResumeClaimPort:
    return port


@pytest.mark.asyncio
async def test_postgres_adapter_satisfies_application_port_and_maps_claim() -> None:
    gate = FakeDurableResumeGate(
        ResumeClaimRecord(
            token="a" * 64,
            native_checkpoint_id="checkpoint-01",
            envelope_digest="b" * 64,
        )
    )
    adapter = PostgresResumeClaimAdapter(gate)
    port = require_application_port(adapter)

    claim = await port.claim_once(
        key="assistant:session:turn:graph",
        interrupt_nonce="c" * 64,
        fencing_token=1,
    )

    assert isinstance(claim, ResumeClaim)
    assert claim.native_checkpoint_id == "checkpoint-01"


@pytest.mark.asyncio
async def test_postgres_adapter_preserves_no_claim_result() -> None:
    adapter = PostgresResumeClaimAdapter(FakeDurableResumeGate(None))

    claim = await adapter.claim_once(
        key="assistant:session:turn:graph",
        interrupt_nonce="c" * 64,
        fencing_token=1,
    )

    assert claim is None
