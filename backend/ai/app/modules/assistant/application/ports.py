from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.modules.assistant.domain import (
    ActiveTaskState,
    ConfirmedGlobalEntity,
    EvidenceReference,
    GlobalEntityReference,
    GraphControlState,
    OpaqueSlotName,
    TaskIntent,
)
from app.modules.inference.application import Citation

WorkerResultKind = Literal[
    "completed",
    "needs_clarification",
    "retryable_failure",
    "non_retryable_failure",
    "policy_denied",
    "handoff_required",
]


@dataclass(frozen=True, slots=True)
class ResumeClaim:
    token: str
    native_checkpoint_id: str
    envelope_digest: str


@dataclass(frozen=True, slots=True)
class RouteDecision:
    intent: TaskIntent
    required_arguments: tuple[OpaqueSlotName, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkerResult:
    kind: WorkerResultKind
    code: str
    fencing_token: int
    final_answer: str | None = None
    evidence: tuple[EvidenceReference, ...] = ()
    cost_microusd: int = 0
    model_tokens: int = 0
    # Full citation content for the HTTP response contract only; never
    # checkpointed. Must correspond 1:1, in order, with `evidence`'s digests.
    citations: tuple[Citation, ...] = ()

    def __post_init__(self) -> None:
        if self.cost_microusd < 0 or self.model_tokens < 0:
            raise ValueError("worker usage cannot be negative")


class SupervisorPort(Protocol):
    async def route(
        self,
        *,
        message: str,
        global_entities: tuple[ConfirmedGlobalEntity, ...],
        previous_task: ActiveTaskState | None,
    ) -> RouteDecision: ...


class TaskWorkerPort(Protocol):
    async def execute(
        self,
        *,
        message: str,
        task: ActiveTaskState,
        global_entities: tuple[ConfirmedGlobalEntity, ...],
        control: GraphControlState,
    ) -> WorkerResult: ...


class ExecutionControlPort(Protocol):
    async def is_current(self, control: GraphControlState) -> bool: ...

    async def wait_invalidated(self, control: GraphControlState) -> None: ...


class EvidenceAuthorityPort(Protocol):
    async def validate(
        self,
        *,
        references: tuple[EvidenceReference, ...],
        control: GraphControlState,
    ) -> bool: ...


class ResumeClaimPort(Protocol):
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
    ) -> ResumeClaim | None: ...

    async def finalize(
        self,
        *,
        key: str,
        claim_token: str,
        succeeded: bool,
    ) -> None: ...


class EntityRevalidationPort(Protocol):
    async def revalidate(
        self,
        entities: tuple[GlobalEntityReference, ...],
        *,
        control: GraphControlState,
    ) -> tuple[GlobalEntityReference, ...]: ...
