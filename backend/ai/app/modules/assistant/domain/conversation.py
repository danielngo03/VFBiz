from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OpaqueSlotName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]

ConversationAssistantProfile = Literal["public_customer", "authenticated_customer"]
GraphOutcomeKind = Literal[
    "completed",
    "needs_clarification",
    "refused",
    "handoff_required",
    "cancelled",
]
TaskIntent = Literal[
    "public_knowledge",
    "vehicle_question",
    "financing_question",
    "charging_question",
    "unknown",
]


class GlobalEntityReference(BaseModel):
    """Opaque non-sensitive reference eligible for authority revalidation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["vehicle_model", "vehicle_variant", "market", "language"]
    reference: str = Field(pattern=r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+){0,7}$")
    source_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    classification: Literal["non_sensitive"] = "non_sensitive"

    @model_validator(mode="after")
    def validate_reference(self) -> "GlobalEntityReference":
        import re

        if self.kind in {"vehicle_model", "vehicle_variant"} and not re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+){1,7}", self.reference
        ):
            raise ValueError("vehicle reference must be an approved lowercase slug")
        if self.kind == "market" and not re.fullmatch(r"[A-Z]{2}", self.reference):
            raise ValueError("market reference must be an ISO alpha-2 code")
        if self.kind == "language" and self.reference not in {"vi", "en"}:
            raise ValueError("language reference is not approved")
        return self


class ConfirmedGlobalEntity(GlobalEntityReference):
    """A reference promoted after authoritative confirmation."""

    authority_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed_at: datetime
    expires_at: datetime
    confidence: float = Field(strict=True, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def require_confirmation_timezone(self) -> "ConfirmedGlobalEntity":
        if self.confirmed_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("confirmed_at and expires_at must include a timezone")
        if self.expires_at <= self.confirmed_at:
            raise ValueError("expires_at must be after confirmed_at")
        return self


class ActiveTaskState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: TaskIntent
    required_arguments: tuple[OpaqueSlotName, ...] = Field(default=(), max_length=16)
    retry_count: int = Field(strict=True, ge=0, le=3)
    last_failure: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,79}$")


class GraphControlState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    graph_version: str = Field(min_length=1, max_length=160)
    policy_revision: str = Field(min_length=1, max_length=160)
    knowledge_revision: str = Field(min_length=1, max_length=160)
    assistant_profile: ConversationAssistantProfile
    authorization_context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    conversation_version: int = Field(strict=True, ge=1, le=9_007_199_254_740_991)
    fencing_token: int = Field(strict=True, ge=1, le=9_007_199_254_740_991)
    deadline_at: datetime
    cancelled: bool = False

    @model_validator(mode="after")
    def require_timezone(self) -> "GraphControlState":
        if self.deadline_at.tzinfo is None:
            raise ValueError("deadline_at must include a timezone")
        return self


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["citation", "retrieval", "tool"]
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class GraphOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: GraphOutcomeKind
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    pending_slots: tuple[OpaqueSlotName, ...] = Field(default=(), max_length=16)


def intent_requires_grounding(intent: TaskIntent) -> bool:
    """The baseline assistant only releases grounded customer-facing answers."""

    _ = intent
    return True
