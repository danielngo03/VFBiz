import re
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
_REGISTERED_INTENTS = frozenset(
    {
        "public_knowledge",
        "vehicle_question",
        "financing_question",
        "charging_question",
        "unknown",
    }
)
_REGISTERED_ABUSE_SIGNALS = frozenset(
    {
        "abusive_language",
        "instruction_override",
        "prompt_exfiltration",
        "tool_injection",
    }
)
_SLOT_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# The deterministic router is deliberately below the semantic activation
# threshold.  Keep the policy in the application layer so infrastructure
# fallbacks and release-bound threshold validation cannot drift apart.
DETERMINISTIC_FALLBACK_MAX_CONFIDENCE = 0.6


@dataclass(frozen=True, slots=True)
class ResumeClaim:
    token: str
    native_checkpoint_id: str
    envelope_digest: str


@dataclass(frozen=True, slots=True)
class RouteDecision:
    intent: TaskIntent
    required_arguments: tuple[OpaqueSlotName, ...] = ()
    confidence: float = 1.0
    missing_slots: tuple[OpaqueSlotName, ...] = ()
    multi_intent: bool = False
    out_of_domain: bool = False
    abuse_signals: tuple[str, ...] = ()
    routing_source: Literal["deterministic", "semantic"] = "deterministic"
    fallback_reason: Literal["classifier_unavailable", "classifier_invalid"] | None = None

    def __post_init__(self) -> None:
        if self.intent not in _REGISTERED_INTENTS:
            raise ValueError("route intent is not registered")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("route confidence must be between zero and one")
        if len(self.required_arguments) > 16 or len(self.missing_slots) > 16:
            raise ValueError("route slot limit exceeded")
        all_slots = (*self.required_arguments, *self.missing_slots)
        if any(not _SLOT_NAME.fullmatch(slot) for slot in all_slots):
            raise ValueError("route slot is not a canonical opaque name")
        if len(set(self.required_arguments)) != len(self.required_arguments) or len(
            set(self.missing_slots)
        ) != len(self.missing_slots):
            raise ValueError("route slots must be unique")
        if not set(self.missing_slots).issubset(self.required_arguments):
            raise ValueError("route missing slots must be required")
        if len(self.abuse_signals) > 16:
            raise ValueError("route abuse signal limit exceeded")
        if len(set(self.abuse_signals)) != len(self.abuse_signals):
            raise ValueError("route abuse signals must be unique")
        if any(signal not in _REGISTERED_ABUSE_SIGNALS for signal in self.abuse_signals):
            raise ValueError("route abuse signal is not registered")


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
