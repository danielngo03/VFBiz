import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.modules.assistant.application import ResumeClaim, RouteDecision, WorkerResult
from app.modules.assistant.domain import (
    ActiveTaskState,
    ConfirmedGlobalEntity,
    EvidenceReference,
    GlobalEntityReference,
    GraphControlState,
)


class DeterministicSupervisor:
    async def route(
        self,
        *,
        message: str,
        global_entities: tuple[ConfirmedGlobalEntity, ...],
        previous_task: ActiveTaskState | None,
    ) -> RouteDecision:
        _ = previous_task
        normalized = message.casefold()
        if "vay" in normalized or "tài chính" in normalized:
            return RouteDecision(intent="financing_question")
        if "lúc nãy" in normalized and any(
            item.kind == "vehicle_model" for item in global_entities
        ):
            return RouteDecision(intent="vehicle_question")
        if "vf" in normalized:
            return RouteDecision(intent="vehicle_question")
        return RouteDecision(intent="public_knowledge")


class SequenceWorker:
    def __init__(self, results: Iterable[WorkerResult]) -> None:
        self._results = iter(results)
        self.calls = 0

    async def execute(self, **_kwargs: object) -> WorkerResult:
        self.calls += 1
        return next(self._results)


class ExecutionControl:
    def __init__(self) -> None:
        self.invalidated = asyncio.Event()

    async def is_current(self, control: GraphControlState) -> bool:
        _ = control
        return not self.invalidated.is_set()

    async def wait_invalidated(self, control: GraphControlState) -> None:
        _ = control
        await self.invalidated.wait()


class EvidenceAuthority:
    def __init__(self, approved: set[str] | None = None) -> None:
        self._approved = approved or {"b" * 64}

    async def validate(
        self,
        *,
        references: tuple[EvidenceReference, ...],
        control: GraphControlState,
    ) -> bool:
        _ = control
        return bool(references) and all(item.digest in self._approved for item in references)


class EntityRevalidator:
    async def revalidate(
        self,
        entities: tuple[GlobalEntityReference, ...],
        *,
        control: GraphControlState,
    ) -> tuple[GlobalEntityReference, ...]:
        _ = control
        return entities


class MemoryResumeClaims:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, object]] = {}
        self._lock = asyncio.Lock()

    async def reserve_start(
        self,
        *,
        key: str,
        fencing_token: int,
        deadline_at: datetime,
    ) -> str | None:
        async with self._lock:
            if key in self._records:
                return None
            token = uuid4().hex
            self._records[key] = {
                "state": "reserved",
                "token": token,
                "fencing_token": fencing_token,
                "deadline_at": deadline_at,
            }
            return token

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
        async with self._lock:
            record = self._records[key]
            if record["state"] != "reserved" or record["token"] != reservation_token:
                raise ValueError("start reservation mismatch")
            record.update({
                "native_checkpoint_id": native_checkpoint_id,
                "envelope_digest": envelope_digest,
                "interrupt_nonce": interrupt_nonce,
                "fencing_token": fencing_token,
                "deadline_at": deadline_at,
                "state": "waiting",
            })

    async def close_start(
        self,
        *,
        key: str,
        reservation_token: str,
        succeeded: bool,
    ) -> None:
        async with self._lock:
            record = self._records[key]
            if record["state"] != "reserved" or record["token"] != reservation_token:
                raise ValueError("start reservation mismatch")
            record["state"] = "terminal" if succeeded else "failed_closed"

    async def claim_once(
        self,
        *,
        key: str,
        interrupt_nonce: str,
        fencing_token: int,
    ) -> ResumeClaim | None:
        async with self._lock:
            record = self._records.get(key)
            if (
                record is None
                or record["state"] != "waiting"
                or record["interrupt_nonce"] != interrupt_nonce
                or record["fencing_token"] != fencing_token
            ):
                return None
            token = uuid4().hex
            record["state"] = "claimed"
            record["token"] = token
            return ResumeClaim(
                token=token,
                native_checkpoint_id=str(record["native_checkpoint_id"]),
                envelope_digest=str(record["envelope_digest"]),
            )

    async def finalize(
        self,
        *,
        key: str,
        claim_token: str,
        succeeded: bool,
    ) -> None:
        async with self._lock:
            record = self._records[key]
            if record.get("token") != claim_token:
                raise ValueError("resume claim token mismatch")
            record["state"] = "completed" if succeeded else "failed_closed"

    def corrupt_envelope_digest(self, key: str) -> None:
        self._records[key]["envelope_digest"] = "0" * 64


def strict_saver() -> InMemorySaver:
    return InMemorySaver(
        serde=JsonPlusSerializer(
            pickle_fallback=False,
            allowed_json_modules=None,
            allowed_msgpack_modules=None,
        )
    )


def control(
    *,
    cancelled: bool = False,
    fencing_token: int = 7,
    deadline_at: datetime | None = None,
    graph_version: str = "graph-r1",
) -> GraphControlState:
    return GraphControlState(
        graph_version=graph_version,
        policy_revision="policy-r1",
        knowledge_revision="knowledge-r1",
        assistant_profile="authenticated_customer",
        authorization_context_hash="a" * 64,
        conversation_version=1,
        fencing_token=fencing_token,
        deadline_at=deadline_at or datetime(2099, 7, 25, tzinfo=UTC),
        cancelled=cancelled,
    )


def confirmed_entity(
    kind: str = "vehicle_model",
    reference: str = "vf-8",
    *,
    confirmed_at: datetime | None = None,
) -> ConfirmedGlobalEntity:
    confirmation_time = confirmed_at or datetime.now(UTC)
    return ConfirmedGlobalEntity(
        kind=kind,  # type: ignore[arg-type]
        reference=reference,
        source_revision="c" * 64,
        authority_digest="d" * 64,
        confirmed_at=confirmation_time,
        expires_at=confirmation_time + timedelta(days=1),
        confidence=1.0,
    )


def evidence(digest: str = "b" * 64) -> tuple[EvidenceReference, ...]:
    return (EvidenceReference(kind="citation", digest=digest),)


def initial_state(
    message: str,
    *,
    global_entities: tuple[ConfirmedGlobalEntity, ...] = (),
    graph_control: GraphControlState | None = None,
) -> dict[str, object]:
    return {
        "message": message,
        "global_entities": global_entities,
        "active_task": None,
        "control": graph_control or control(),
        "evidence": (),
        "citations": (),
        "outcome": None,
        "worker_attempts": 0,
        "route_history": (),
    }
