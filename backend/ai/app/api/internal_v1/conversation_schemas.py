from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

_MAX_SAFE_INTEGER = 9_007_199_254_740_991


class ConfirmedEntityReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["vehicle_model", "vehicle_variant", "market", "language"]
    reference: str = Field(min_length=1, max_length=160)
    source_revision: str = Field(alias="sourceRevision", pattern=r"^[a-f0-9]{64}$")
    classification: Literal["non_sensitive"]
    authority: str = Field(min_length=1, max_length=80)
    authority_digest: str = Field(alias="authorityDigest", pattern=r"^[a-f0-9]{64}$")
    confirmed_at: datetime = Field(alias="confirmedAt")
    expires_at: datetime = Field(alias="expiresAt")

    @model_validator(mode="after")
    def validate_confirmation_window(self) -> "ConfirmedEntityReference":
        if self.confirmed_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("confirmedAt and expiresAt must include a timezone")
        if self.expires_at <= self.confirmed_at:
            raise ValueError("expiresAt must be after confirmedAt")
        return self


class ConversationTaskReleaseBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    activation_id: UUID = Field(alias="activationId")
    graph_revision: str = Field(alias="graphRevision", min_length=1, max_length=160)
    knowledge_revision: str = Field(alias="knowledgeRevision", min_length=1, max_length=160)
    manifest_sha256: str = Field(alias="manifestSha256", pattern=r"^[a-f0-9]{64}$")
    policy_revision: str = Field(alias="policyRevision", min_length=1, max_length=160)


class TaskSlotReceiptReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["receipt"]
    authority: Literal[
        "business_policy",
        "customer_garage",
        "customer_profile",
        "locale_policy",
        "market_catalog",
        "vehicle_catalog",
    ]
    authority_digest: str = Field(alias="authorityDigest", pattern=r"^[a-f0-9]{64}$")
    confirmed_at: datetime = Field(alias="confirmedAt")
    expires_at: datetime = Field(alias="expiresAt")
    opaque_reference: str = Field(
        alias="opaqueReference",
        pattern=(
            r"^(vehicle|market|locale|profile|garage|policy|product|account):"
            r"ref/v1/[a-f0-9]{64}$"
        ),
    )
    provenance_digest: str = Field(alias="provenanceDigest", pattern=r"^[a-f0-9]{64}$")
    slot: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    source_revision: str = Field(
        alias="sourceRevision",
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$",
    )
    task_id: UUID = Field(alias="taskId")

    @model_validator(mode="after")
    def validate_window(self) -> "TaskSlotReceiptReference":
        if (
            self.confirmed_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or self.expires_at <= self.confirmed_at
        ):
            raise ValueError("task slot receipt window is invalid")
        return self


class ConversationTaskContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_context_digest: str = Field(
        alias="authorizationContextDigest", pattern=r"^[a-f0-9]{64}$"
    )
    collected_slots: dict[
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")],
        TaskSlotReceiptReference,
    ] = Field(alias="collectedSlots", max_length=16)
    expires_at: datetime = Field(alias="expiresAt")
    intent: Literal[
        "public_knowledge",
        "vehicle_question",
        "financing_question",
        "charging_question",
        "unknown",
    ]
    intent_revision: str = Field(alias="intentRevision", min_length=1, max_length=160)
    last_fencing_token: int = Field(
        alias="lastFencingToken", strict=True, ge=1, le=_MAX_SAFE_INTEGER
    )
    pending_slots: tuple[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")], ...] = Field(
        alias="pendingSlots", max_length=16
    )
    provenance_digest: str = Field(alias="provenanceDigest", pattern=r"^[a-f0-9]{64}$")
    release: ConversationTaskReleaseBinding
    source_turn_id: UUID | None = Field(alias="sourceTurnId")
    state: Literal["active", "awaiting_clarification"]
    task_id: UUID = Field(alias="taskId")
    task_version: int = Field(alias="taskVersion", strict=True, ge=1, le=_MAX_SAFE_INTEGER)

    @model_validator(mode="after")
    def validate_task_context(self) -> "ConversationTaskContextRequest":
        if self.expires_at.tzinfo is None:
            raise ValueError("task expiresAt must include a timezone")
        if len(set(self.pending_slots)) != len(self.pending_slots):
            raise ValueError("pendingSlots must not contain duplicates")
        if set(self.pending_slots).intersection(self.collected_slots):
            raise ValueError("pending and collected slots must be disjoint")
        if any(
            receipt.task_id != self.task_id or receipt.slot != slot
            for slot, receipt in self.collected_slots.items()
        ):
            raise ValueError("task slot receipt binding does not match its task context")
        if any(receipt.expires_at > self.expires_at for receipt in self.collected_slots.values()):
            raise ValueError("task slot receipt cannot outlive its task context")
        return self


class ConversationTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID = Field(alias="requestId")
    correlation_id: UUID = Field(alias="correlationId")
    session_id: UUID = Field(alias="sessionId")
    turn_id: UUID = Field(alias="turnId")
    conversation_version: int = Field(
        alias="conversationVersion", strict=True, ge=1, le=_MAX_SAFE_INTEGER
    )
    fencing_token: int = Field(alias="fencingToken", strict=True, ge=1, le=_MAX_SAFE_INTEGER)
    authorization_context_digest: str = Field(
        alias="authorizationContextDigest", pattern=r"^[a-f0-9]{64}$"
    )
    locale: Literal["vi", "en"]
    message: str = Field(min_length=1, max_length=12_000)
    confirmed_entities: tuple[ConfirmedEntityReference, ...] = Field(
        default=(),
        alias="confirmedEntities",
        max_length=16,
    )
    task_context: ConversationTaskContextRequest | None = Field(default=None, alias="taskContext")

    @model_validator(mode="after")
    def validate_task_binding(self) -> "ConversationTurnRequest":
        if (
            self.task_context is not None
            and self.task_context.authorization_context_digest != self.authorization_context_digest
        ):
            raise ValueError("task context authorization binding does not match the request")
        return self


class ConversationTurnCancellation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID = Field(alias="requestId")
    conversation_version: int = Field(
        alias="conversationVersion", strict=True, ge=1, le=_MAX_SAFE_INTEGER
    )
    fencing_token: int = Field(alias="fencingToken", strict=True, ge=1, le=_MAX_SAFE_INTEGER)
    reason: Literal["budget_exhausted", "system_shutdown", "timeout", "user_interrupt"]
