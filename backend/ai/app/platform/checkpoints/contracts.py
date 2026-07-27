import re
from datetime import datetime
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_MAX_CHECKPOINT_BYTES = 32_768
OpaqueSlotName = Annotated[
    str,
    Field(pattern=r"^[a-z][a-z0-9_]{0,63}$"),
]
EvidenceReference = Annotated[
    str,
    Field(
        pattern=r"^(citation|retrieval|tool):[a-f0-9]{64}$",
    ),
]


class CheckpointEntityReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["vehicle_model", "vehicle_variant", "market", "language"]
    reference: str = Field(min_length=1, max_length=160)
    source_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    classification: Literal["non_sensitive"]

    @model_validator(mode="after")
    def validate_approved_identifier_shape(self) -> "CheckpointEntityReference":
        if self.kind in {"vehicle_model", "vehicle_variant"}:
            if not re.fullmatch(
                r"[a-z0-9]+(?:-[a-z0-9]+){1,7}",
                self.reference,
            ):
                raise ValueError("vehicle reference must be an approved lowercase slug")
        elif self.kind == "market":
            if not re.fullmatch(r"[A-Z]{2}", self.reference):
                raise ValueError("market reference must be an ISO alpha-2 code")
        elif self.reference not in {"vi", "en"}:
            raise ValueError("language reference is not approved")
        return self


class ActiveTaskCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_kind: str = Field(min_length=1, max_length=80)
    stage: str = Field(min_length=1, max_length=80)
    retry_count: int = Field(strict=True, ge=0, le=3)
    pending_slot_names: tuple[OpaqueSlotName, ...] = Field(default=(), max_length=16)


class CheckpointState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    global_entities: tuple[CheckpointEntityReference, ...] = Field(
        default=(),
        max_length=16,
    )
    active_task: ActiveTaskCheckpoint | None = None
    evidence_refs: tuple[EvidenceReference, ...] = Field(default=(), max_length=32)


class CheckpointControlBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assistant_profile: Literal["public_customer", "authenticated_customer"]
    authorization_context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_revision: str = Field(min_length=1, max_length=160)
    knowledge_revision: str = Field(min_length=1, max_length=160)


class CheckpointIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: UUID
    turn_id: UUID
    graph_version: str = Field(min_length=1, max_length=160)


class CheckpointEnvelope(BaseModel):
    """AI execution state only; never a customer transcript or final-answer authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authority: Literal["ai_execution_only"] = "ai_execution_only"
    schema_version: int = Field(strict=True, ge=1, le=_MAX_SAFE_INTEGER)
    identity: CheckpointIdentity
    conversation_version: int = Field(strict=True, ge=1, le=_MAX_SAFE_INTEGER)
    fencing_token: int = Field(strict=True, ge=1, le=_MAX_SAFE_INTEGER)
    control: CheckpointControlBinding
    state: CheckpointState
    created_at: datetime

    @model_validator(mode="after")
    def validate_execution_boundary(self) -> "CheckpointEnvelope":
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must include a timezone")
        if len(self.model_dump_json().encode()) > _MAX_CHECKPOINT_BYTES:
            raise ValueError("checkpoint exceeds execution-state size limit")
        return self


class ExecutionCheckpointStore(Protocol):
    async def load(self, identity: CheckpointIdentity) -> CheckpointEnvelope | None: ...

    async def save(self, checkpoint: CheckpointEnvelope) -> None: ...

    async def delete(self, identity: CheckpointIdentity) -> None: ...


def assert_checkpoint_control(
    checkpoint: CheckpointEnvelope,
    expected: CheckpointControlBinding,
) -> None:
    if checkpoint.control != expected:
        raise ValueError("checkpoint control binding does not match this execution")
