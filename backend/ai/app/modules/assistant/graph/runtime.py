import asyncio
import hashlib
import json
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

from langgraph.types import Command

from app.modules.assistant.application import EntityRevalidationPort, ResumeClaimPort
from app.modules.assistant.domain import GraphControlState
from app.modules.assistant.graph.migrations import (
    MigrationResult,
    migrate_checkpoint_with_authority,
    project_checkpoint,
)
from app.modules.assistant.graph.state import ConversationGraphState
from app.platform.checkpoints import CheckpointIdentity


class StateSnapshot(Protocol):
    values: dict[str, object]
    config: dict[str, object]


class CompiledConversationGraph(Protocol):
    async def ainvoke(
        self,
        input: object,
        *,
        config: dict[str, object],
    ) -> dict[str, object]: ...

    async def aget_state(self, config: dict[str, object]) -> StateSnapshot: ...


@dataclass(frozen=True, slots=True)
class ResumeRejected:
    code: str


class ConversationGraphRuntime:
    """Pins native checkpoints to a trusted identity and single-consume gate."""

    def __init__(
        self,
        graph: CompiledConversationGraph,
        resume_claims: ResumeClaimPort,
        entity_revalidator: EntityRevalidationPort,
    ) -> None:
        self._graph = graph
        self._resume_claims = resume_claims
        self._entity_revalidator = entity_revalidator

    async def inspect_migration(
        self,
        *,
        previous_identity: CheckpointIdentity,
        expected_identity: CheckpointIdentity,
        expected_control: GraphControlState,
    ) -> MigrationResult:
        if expected_identity.graph_version != expected_control.graph_version:
            return MigrationResult(
                global_entities=(),
                active_task=None,
                evidence=(),
                action="discarded",
                reason="expected_graph_identity_control_mismatch",
            )
        snapshot = await _await_until(
            self._graph.aget_state(_native_config(previous_identity)),
            expected_control.deadline_at,
        )
        checkpoint = project_checkpoint(
            cast(ConversationGraphState, snapshot.values),
            identity=previous_identity,
        )
        return await _await_until(
            migrate_checkpoint_with_authority(
                checkpoint,
                expected_identity=expected_identity,
                expected_control=expected_control,
                revalidator=self._entity_revalidator,
            ),
            expected_control.deadline_at,
        )

    async def start(
        self,
        state: ConversationGraphState,
        *,
        identity: CheckpointIdentity,
    ) -> dict[str, object]:
        if state["control"].graph_version != identity.graph_version:
            return {"outcome": ResumeRejected(code="GRAPH_IDENTITY_MISMATCH")}
        key = _resume_key(identity)
        try:
            reservation_token = await _await_until(
                self._resume_claims.reserve_start(
                    key=key,
                    fencing_token=state["control"].fencing_token,
                    deadline_at=state["control"].deadline_at,
                ),
                state["control"].deadline_at,
            )
        except TimeoutError:
            return {"outcome": ResumeRejected(code="TURN_DEADLINE_EXCEEDED")}
        if reservation_token is None:
            return {"outcome": ResumeRejected(code="DUPLICATE_TURN_START")}
        config = _native_config(identity)
        try:
            result = await _await_until(
                self._graph.ainvoke(state, config=config), state["control"].deadline_at
            )
            if "__interrupt__" not in result:
                await _await_repository(
                    self._resume_claims.close_start(
                    key=key,
                    reservation_token=reservation_token,
                    succeeded=True,
                    )
                )
                return result
            snapshot = await _await_until(
                self._graph.aget_state(config), state["control"].deadline_at
            )
            checkpoint_id = _native_checkpoint_id(snapshot.config)
            envelope_digest = _snapshot_digest(snapshot.values, identity)
            interrupt_nonce = _interrupt_nonce(identity, checkpoint_id, envelope_digest)
            await _await_until(
                self._resume_claims.prepare(
                key=key,
                reservation_token=reservation_token,
                native_checkpoint_id=checkpoint_id,
                envelope_digest=envelope_digest,
                interrupt_nonce=interrupt_nonce,
                fencing_token=state["control"].fencing_token,
                deadline_at=state["control"].deadline_at,
                ),
                state["control"].deadline_at,
            )
            return {**result, "resume_nonce": interrupt_nonce}
        except BaseException:
            await _await_repository(
                self._resume_claims.close_start(
                    key=key,
                    reservation_token=reservation_token,
                    succeeded=False,
                )
            )
            raise

    async def resume(
        self,
        *,
        answer: str,
        expected_identity: CheckpointIdentity,
        expected_control: GraphControlState,
        interrupt_nonce: str,
    ) -> dict[str, object] | ResumeRejected:
        if not answer.strip() or len(answer) > 8_000:
            return ResumeRejected(code="INVALID_RESUME_ANSWER")
        if expected_control.graph_version != expected_identity.graph_version:
            return ResumeRejected(code="GRAPH_IDENTITY_MISMATCH")
        try:
            claim = await _await_until(
                self._resume_claims.claim_once(
                    key=_resume_key(expected_identity),
                    interrupt_nonce=interrupt_nonce,
                    fencing_token=expected_control.fencing_token,
                ),
                expected_control.deadline_at,
            )
        except TimeoutError:
            return ResumeRejected(code="TURN_DEADLINE_EXCEEDED")
        if claim is None:
            return ResumeRejected(code="CHECKPOINT_ALREADY_CONSUMED")
        config = _native_config(
            expected_identity,
            checkpoint_id=claim.native_checkpoint_id,
        )
        succeeded = False
        try:
            snapshot = await _await_until(
                self._graph.aget_state(config), expected_control.deadline_at
            )
            if _snapshot_digest(snapshot.values, expected_identity) != claim.envelope_digest:
                return ResumeRejected(code="CHECKPOINT_BINDING_MISMATCH")
            stored_control = snapshot.values.get("control")
            if stored_control != expected_control:
                return ResumeRejected(code="CHECKPOINT_CONTROL_MISMATCH")
            result = await _await_until(
                self._graph.ainvoke(Command(resume=answer), config=config),
                expected_control.deadline_at,
            )
            succeeded = True
            return result
        finally:
            await _await_repository(
                self._resume_claims.finalize(
                    key=_resume_key(expected_identity),
                    claim_token=claim.token,
                    succeeded=succeeded,
                )
            )


def _native_config(
    identity: CheckpointIdentity,
    *,
    checkpoint_id: str | None = None,
) -> dict[str, object]:
    configurable: dict[str, object] = {
        "thread_id": (
            f"assistant:{identity.session_id.hex}:"
            f"{identity.turn_id.hex}:{identity.graph_version}"
        ),
    }
    if checkpoint_id is not None:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


def _native_checkpoint_id(config: dict[str, object]) -> str:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        raise ValueError("native checkpoint is missing configurable metadata")
    metadata = cast(dict[str, object], configurable)
    checkpoint_id = metadata.get("checkpoint_id")
    if not isinstance(checkpoint_id, str) or not checkpoint_id:
        raise ValueError("native checkpoint is missing checkpoint_id")
    return checkpoint_id


def _snapshot_digest(
    values: dict[str, object],
    identity: CheckpointIdentity,
) -> str:
    state = cast(ConversationGraphState, values)
    envelope = project_checkpoint(state, identity=identity)
    canonical = envelope.model_dump(mode="json", exclude={"created_at"})
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _resume_key(identity: CheckpointIdentity) -> str:
    return f"{identity.session_id.hex}:{identity.turn_id.hex}:{identity.graph_version}"


def _interrupt_nonce(
    identity: CheckpointIdentity,
    checkpoint_id: str,
    envelope_digest: str,
) -> str:
    material = f"{_resume_key(identity)}:{checkpoint_id}:{envelope_digest}"
    return hashlib.sha256(material.encode()).hexdigest()


async def _await_until[T](awaitable: Awaitable[T], deadline_at: datetime) -> T:
    remaining = (deadline_at - datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        if hasattr(awaitable, "close"):
            awaitable.close()  # type: ignore[union-attr]
        raise TimeoutError
    async with asyncio.timeout(remaining):
        return await awaitable


async def _await_repository[T](awaitable: Awaitable[T]) -> T:
    async with asyncio.timeout(2.0):
        return await awaitable
