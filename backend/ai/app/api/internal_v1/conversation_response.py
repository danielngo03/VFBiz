from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.assistant.domain import GraphControlState, GraphOutcome
from app.modules.inference.application import Citation

HandoffReason = Literal[
    "insufficient_evidence",
    "policy_required",
    "safety_risk",
    "tool_unavailable",
]

# Codes the graph/worker can produce that mean "the model itself declined or
# was denied", distinct from "no evidence was available at all". Any code not
# listed here falls back to policy_required — a deliberately conservative
# default for operational/config failures (e.g. NO_SAFE_DEPLOYMENT) that are
# not the customer's problem to retry around.
_INSUFFICIENT_EVIDENCE_CODES = frozenset(
    {
        "NO_KNOWLEDGE_EVIDENCE",
        "MISSING_GROUNDED_EVIDENCE",
        "UNAPPROVED_GROUNDED_EVIDENCE",
        "EVIDENCE_LIMIT_EXCEEDED",
        "EVIDENCE_AUTHORITY_TIMEOUT",
        "INSUFFICIENT_EVIDENCE",
    }
)
_SAFETY_CODES = frozenset({"REFUSED", "POLICY_DENIED"})
_CUSTOMER_SAFE_MESSAGE = (
    "Xin lỗi, hiện tại tôi chưa thể trả lời câu hỏi này. Vui lòng liên hệ tổng đài hỗ trợ VinFast."
)


class ExecutionUsage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cost_micros: int = Field(alias="costMicros", ge=0, le=10_000_000)
    model_tokens: int = Field(alias="modelTokens", ge=0)


class ExecutionRevisions(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    graph: str
    knowledge: str
    policy: str


class ReleaseCommitReceipt(BaseModel):
    """Immutable release identity leased for the final API commit."""

    model_config = ConfigDict(populate_by_name=True)

    activation_id: UUID = Field(alias="activationId")
    lease_id: UUID = Field(alias="leaseId")
    candidate_sha256: str = Field(alias="candidateSha256", pattern=r"^[a-f0-9]{64}$")
    activation_envelope_sha256: str = Field(
        alias="activationEnvelopeSha256", pattern=r"^[a-f0-9]{64}$"
    )
    pointer_revision: int = Field(alias="pointerRevision", ge=1)
    session_id: UUID = Field(alias="sessionId")
    turn_id: UUID = Field(alias="turnId")
    request_id: UUID = Field(alias="requestId")
    conversation_version: int = Field(alias="conversationVersion", ge=0)
    fencing_token: int = Field(alias="fencingToken", ge=1)
    issued_at: datetime = Field(alias="issuedAt")
    expires_at: datetime = Field(alias="expiresAt")


class ExecutionCitation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    knowledge_revision: str = Field(alias="knowledgeRevision")
    retrieved_at: str = Field(alias="retrievedAt")
    revision: str
    source_id: str = Field(alias="sourceId")
    title: str
    uri: str


class AnsweredResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    outcome: Literal["answered"] = "answered"
    message: str
    citations: list[ExecutionCitation] = Field(min_length=1, max_length=20)
    release_revision: str = Field(alias="releaseRevision")
    release_commit_receipt: ReleaseCommitReceipt = Field(alias="releaseCommitReceipt")
    revisions: ExecutionRevisions
    usage: ExecutionUsage


class RefusedResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    outcome: Literal["refused"] = "refused"
    message: str
    citations: list[ExecutionCitation] = Field(default=[], max_length=0)
    release_revision: str = Field(alias="releaseRevision")
    release_commit_receipt: ReleaseCommitReceipt = Field(alias="releaseCommitReceipt")
    revisions: ExecutionRevisions
    usage: ExecutionUsage


class HandoffResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    outcome: Literal["handoff_recommended"] = "handoff_recommended"
    customer_message: str = Field(alias="customerMessage")
    reason: HandoffReason
    release_revision: str = Field(alias="releaseRevision")
    release_commit_receipt: ReleaseCommitReceipt = Field(alias="releaseCommitReceipt")
    revisions: ExecutionRevisions
    usage: ExecutionUsage


class ClarificationResponse(BaseModel):
    """A terminal turn outcome; continuation is a new customer message.

    The baseline deliberately does not expose LangGraph's native interrupt or
    checkpoint nonce to API Platform. That contract needs its own durable
    continuation identity and expiry semantics before it can be enabled.
    """

    model_config = ConfigDict(populate_by_name=True)

    outcome: Literal["clarification_required"] = "clarification_required"
    message: str
    pending_slots: tuple[str, ...] = Field(alias="pendingSlots", max_length=16)
    release_revision: str = Field(alias="releaseRevision")
    release_commit_receipt: ReleaseCommitReceipt = Field(alias="releaseCommitReceipt")
    revisions: ExecutionRevisions
    usage: ExecutionUsage


class FailedSafelyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    outcome: Literal["failed_safely"] = "failed_safely"
    code: Literal["RELEASE_SUPPRESSED"] = "RELEASE_SUPPRESSED"
    message: str = _CUSTOMER_SAFE_MESSAGE
    release_revision: str = Field(alias="releaseRevision")
    revisions: ExecutionRevisions
    usage: ExecutionUsage


ExecutionResponse = (
    AnsweredResponse
    | ClarificationResponse
    | FailedSafelyResponse
    | RefusedResponse
    | HandoffResponse
)


def build_failed_safely_response(
    *,
    control: GraphControlState,
    usage: ExecutionUsage,
    release_revision: str,
) -> FailedSafelyResponse:
    return FailedSafelyResponse(
        code="RELEASE_SUPPRESSED",
        message=_CUSTOMER_SAFE_MESSAGE,
        releaseRevision=release_revision,
        revisions=ExecutionRevisions(
            graph=control.graph_version,
            knowledge=control.knowledge_revision,
            policy=control.policy_revision,
        ),
        usage=usage,
    )


def handoff_reason_for(code: str) -> HandoffReason:
    if code in _INSUFFICIENT_EVIDENCE_CODES:
        return "insufficient_evidence"
    if code in _SAFETY_CODES:
        return "safety_risk"
    return "policy_required"


def build_execution_response(
    *,
    outcome: GraphOutcome,
    control: GraphControlState,
    final_answer: str | None,
    citations: tuple[Citation, ...],
    usage: ExecutionUsage,
    release_revision: str,
    release_commit_receipt: ReleaseCommitReceipt,
) -> ExecutionResponse:
    revisions = ExecutionRevisions(
        graph=control.graph_version,
        knowledge=control.knowledge_revision,
        policy=control.policy_revision,
    )
    if outcome.kind == "completed":
        if final_answer is None or not citations:
            raise ValueError("a completed outcome must carry an answer and citations")
        return AnsweredResponse(
            message=final_answer,
            citations=[
                ExecutionCitation(
                    knowledgeRevision=control.knowledge_revision,
                    retrievedAt=citation.freshness,
                    revision=citation.source_revision,
                    sourceId=citation.evidence_id,
                    title=citation.title,
                    uri=citation.source_uri,
                )
                for citation in citations
            ],
            releaseRevision=release_revision,
            releaseCommitReceipt=release_commit_receipt,
            revisions=revisions,
            usage=usage,
        )
    if outcome.kind == "refused":
        return RefusedResponse(
            message=_CUSTOMER_SAFE_MESSAGE,
            releaseRevision=release_revision,
            releaseCommitReceipt=release_commit_receipt,
            revisions=revisions,
            usage=usage,
        )
    if outcome.kind == "needs_clarification":
        return ClarificationResponse(
            message="Vui lòng cung cấp thêm thông tin để tôi có thể hỗ trợ chính xác.",
            pendingSlots=outcome.pending_slots,
            releaseRevision=release_revision,
            releaseCommitReceipt=release_commit_receipt,
            revisions=revisions,
            usage=usage,
        )
    return HandoffResponse(
        customerMessage=_CUSTOMER_SAFE_MESSAGE,
        reason=handoff_reason_for(outcome.code),
        releaseRevision=release_revision,
        releaseCommitReceipt=release_commit_receipt,
        revisions=revisions,
        usage=usage,
    )
