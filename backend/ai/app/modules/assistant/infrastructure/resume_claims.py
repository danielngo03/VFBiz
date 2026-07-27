from datetime import datetime
from typing import Protocol

from app.modules.assistant.application import ResumeClaim
from app.platform.checkpoints.postgres import ResumeClaimRecord


class DurableResumeGate(Protocol):
    async def reserve_start(
        self,
        *,
        key: str,
        fencing_token: int,
        deadline_at: datetime,
    ) -> str | None: ...

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
    ) -> None: ...

    async def close_start(
        self,
        *,
        key: str,
        reservation_token: str,
        succeeded: bool,
    ) -> None: ...

    async def claim_once(
        self,
        *,
        key: str,
        interrupt_nonce: str,
        fencing_token: int,
    ) -> ResumeClaimRecord | None: ...

    async def finalize(
        self,
        *,
        key: str,
        claim_token: str,
        succeeded: bool,
    ) -> None: ...


class PostgresResumeClaimAdapter:
    """Map the platform CAS record into the Assistant application contract."""

    def __init__(self, gate: DurableResumeGate) -> None:
        self._gate = gate

    async def reserve_start(
        self,
        *,
        key: str,
        fencing_token: int,
        deadline_at: datetime,
    ) -> str | None:
        return await self._gate.reserve_start(
            key=key,
            fencing_token=fencing_token,
            deadline_at=deadline_at,
        )

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
        await self._gate.prepare(
            key=key,
            reservation_token=reservation_token,
            native_checkpoint_id=native_checkpoint_id,
            envelope_digest=envelope_digest,
            interrupt_nonce=interrupt_nonce,
            fencing_token=fencing_token,
            deadline_at=deadline_at,
        )

    async def close_start(
        self,
        *,
        key: str,
        reservation_token: str,
        succeeded: bool,
    ) -> None:
        await self._gate.close_start(
            key=key,
            reservation_token=reservation_token,
            succeeded=succeeded,
        )

    async def claim_once(
        self,
        *,
        key: str,
        interrupt_nonce: str,
        fencing_token: int,
    ) -> ResumeClaim | None:
        record = await self._gate.claim_once(
            key=key,
            interrupt_nonce=interrupt_nonce,
            fencing_token=fencing_token,
        )
        if record is None:
            return None
        return ResumeClaim(
            token=record.token,
            native_checkpoint_id=record.native_checkpoint_id,
            envelope_digest=record.envelope_digest,
        )

    async def finalize(
        self,
        *,
        key: str,
        claim_token: str,
        succeeded: bool,
    ) -> None:
        await self._gate.finalize(
            key=key,
            claim_token=claim_token,
            succeeded=succeeded,
        )
