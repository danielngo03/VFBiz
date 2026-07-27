from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_MAX_SAFE_INTEGER = 9_007_199_254_740_991


class ConfirmedEntityReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["vehicle_model", "vehicle_variant", "market", "language"]
    reference: str = Field(min_length=1, max_length=160)
    source_revision: str = Field(alias="sourceRevision", min_length=1, max_length=160)
    classification: Literal["non_sensitive"]


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
    locale: Literal["vi", "en"]
    message: str = Field(min_length=1, max_length=12_000)
    confirmed_entities: tuple[ConfirmedEntityReference, ...] = Field(
        default=(),
        alias="confirmedEntities",
        max_length=16,
    )


class ConversationTurnCancellation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID = Field(alias="requestId")
    conversation_version: int = Field(
        alias="conversationVersion", strict=True, ge=1, le=_MAX_SAFE_INTEGER
    )
    fencing_token: int = Field(alias="fencingToken", strict=True, ge=1, le=_MAX_SAFE_INTEGER)
    reason: Literal["budget_exhausted", "system_shutdown", "timeout", "user_interrupt"]
