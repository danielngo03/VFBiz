import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.internal_v1.conversation_response import (
    ConversationTaskProposalResponse,
    ExecutionResponse,
    ExecutionUsage,
    ReleaseCommitReceipt,
    TaskReleaseBindingResponse,
    TaskSlotCandidateResponse,
    build_execution_response,
    build_failed_safely_response,
)
from app.api.internal_v1.conversation_schemas import (
    ConversationTurnCancellation,
    ConversationTurnRequest,
)
from app.bootstrap.conversation_graph import build_turn_runtime
from app.bootstrap.release_runtime import ReleaseRuntimeUnavailable
from app.modules.assistant.domain import (
    ActiveTaskState,
    ConfirmedGlobalEntity,
    GraphControlState,
    GraphOutcome,
)
from app.modules.assistant.graph.runtime import ResumeRejected
from app.modules.assistant.graph.state import ConversationGraphState
from app.modules.inference.application import Citation, InferenceBudget
from app.platform.cancellation import (
    CancellationCommand,
    execution_cancellation_port,
)
from app.platform.checkpoints import CheckpointIdentity
from app.platform.security.execution_assertion import (
    ExecutionContext,
    assert_request_matches_claims,
    require_execution_context,
)

conversation_router = APIRouter(prefix="/conversation", tags=["conversation"])


def _unavailable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "INTERNAL_FAILURE", "message": message, "retryable": True},
    )


def _release_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "RELEASE_UNAVAILABLE",
            "message": "The approved assistant runtime is temporarily unavailable.",
            "retryable": True,
        },
    )


def _stale(code: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": "This turn was superseded.", "retryable": False},
    )


def _subject_for(context: ExecutionContext) -> str:
    """Return (subject, authorization_context_hash). Both authorization
    variants already carry an opaque SHA-256 identifier; reusing it avoids
    inventing a second hash for the same trust boundary.
    """
    authorization = context.claims.authorization
    if authorization.kind == "authenticated_customer":
        return authorization.subject_ref
    return "anonymous"


def _inference_budget(total_tokens: int, max_cost_micros: int) -> InferenceBudget:
    if total_tokens < 2:
        raise _unavailable("The reserved model-token budget is too small.")
    max_output = min(1_200, max(1, total_tokens // 4))
    max_input = total_tokens - max_output
    return InferenceBudget(
        max_input_tokens=max_input,
        max_output_tokens=max_output,
        max_cost_microusd=max_cost_micros,
    )


def _usage_value(result: dict[str, object], key: str) -> int:
    value = result.get(key, 0)
    return value if isinstance(value, int) and value >= 0 else 0


def _task_release_is_current(
    request: ConversationTurnRequest,
    context: ExecutionContext,
) -> bool:
    task = request.task_context
    if task is None:
        return True
    claims = context.claims
    return (
        task.release.activation_id == claims.activation_id
        and task.release.graph_revision == claims.graph_revision
        and task.release.knowledge_revision == claims.knowledge_revision
        and task.release.manifest_sha256 == claims.manifest_sha256
        and task.release.policy_revision == claims.policy_revision
    )


def task_receipts_are_current(
    request: ConversationTurnRequest,
    now: datetime,
) -> bool:
    task = request.task_context
    return task is None or all(
        receipt.expires_at > now for receipt in task.collected_slots.values()
    )


def build_clarification_task_proposal(
    *,
    request: ConversationTurnRequest,
    context: ExecutionContext,
    result: Mapping[str, object],
) -> ConversationTaskProposalResponse:
    active_task = result.get("active_task")
    if not isinstance(active_task, ActiveTaskState):
        raise _unavailable("Clarification did not produce a bounded task state.")
    claims = context.claims
    previous = request.task_context
    effective_intent = (
        previous.intent
        if previous is not None and active_task.intent == "unknown"
        else active_task.intent
    )
    task_id = (
        previous.task_id
        if previous is not None and previous.intent == effective_intent
        else uuid5(
            NAMESPACE_URL,
            f"vfbiz:conversation-task:{request.session_id}:{request.turn_id}:{effective_intent}",
        )
    )
    expected_version = (
        previous.task_version if previous is not None and previous.task_id == task_id else 0
    )
    issued_at = datetime.fromtimestamp(claims.issued_at, UTC)
    maximum_expiry = issued_at + timedelta(minutes=30)
    expires_at = (
        min(previous.expires_at, maximum_expiry)
        if previous is not None and previous.task_id == task_id
        else maximum_expiry
    )
    release = {
        "activationId": str(claims.activation_id),
        "graphRevision": claims.graph_revision,
        "knowledgeRevision": claims.knowledge_revision,
        "manifestSha256": claims.manifest_sha256,
        "policyRevision": claims.policy_revision,
    }
    material: dict[str, object] = {
        "authorizationContextDigest": request.authorization_context_digest,
        "expectedTaskVersion": expected_version,
        "expiresAt": expires_at.isoformat(),
        "intent": effective_intent,
        "intentRevision": claims.graph_revision,
        "pendingSlots": list(active_task.required_arguments),
        "release": release,
        "sourceTurnId": str(request.turn_id),
        "taskId": str(task_id),
    }
    candidates = _slot_candidates(
        request=request,
        task_id=task_id,
        expected_task_version=expected_version,
        pending_slots=active_task.required_arguments,
    )
    material["slotCandidates"] = [
        candidate.model_dump(by_alias=True, mode="json") for candidate in candidates
    ]
    provenance_digest = hashlib.sha256(
        json.dumps(material, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return ConversationTaskProposalResponse(
        authorizationContextDigest=request.authorization_context_digest,
        expectedTaskVersion=expected_version,
        expiresAt=expires_at,
        intent=effective_intent,
        intentRevision=claims.graph_revision,
        pendingSlots=active_task.required_arguments,
        provenanceDigest=provenance_digest,
        release=TaskReleaseBindingResponse.model_validate(release),
        slotCandidates=candidates,
        sourceTurnId=request.turn_id,
        taskId=task_id,
    )


def _slot_candidates(
    *,
    request: ConversationTurnRequest,
    task_id: UUID,
    expected_task_version: int,
    pending_slots: tuple[str, ...],
) -> tuple[TaskSlotCandidateResponse, ...]:
    previous = request.task_context
    if previous is None or previous.task_id != task_id:
        return ()
    candidates: list[TaskSlotCandidateResponse] = []
    for slot in pending_slots:
        proposed = _bounded_slot_value(slot, request.message)
        if proposed is None:
            continue
        material = {
            "expectedTaskVersion": expected_task_version,
            "proposedValue": proposed,
            "slot": slot,
            "sourceTurnId": str(request.turn_id),
            "taskId": str(task_id),
        }
        provenance = hashlib.sha256(
            json.dumps(
                material,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        candidates.append(
            TaskSlotCandidateResponse(
                candidateId=uuid5(
                    NAMESPACE_URL,
                    f"vfbiz:slot-candidate:{request.request_id}:{slot}",
                ),
                confidence=1.0,
                expectedTaskVersion=expected_task_version,
                proposedValue=proposed,
                provenanceDigest=provenance,
                slot=slot,
                sourceTurnId=request.turn_id,
                taskId=task_id,
            )
        )
    return tuple(candidates)


def _bounded_slot_value(slot: str, message: str) -> str | None:
    normalized = " ".join(message.strip().split())
    if slot == "vehicle_model":
        match = re.search(r"(?i)(?:^|\W)vf\s*([3-9])(?:\W|$)", normalized)
        return f"VF {match.group(1)}" if match is not None else None
    if slot == "primary_intent":
        lowered = normalized.casefold()
        for value, terms in (
            ("financing_question", ("vay", "trả góp", "financing", "loan")),
            ("charging_question", ("sạc", "charging", "battery")),
            ("vehicle_question", ("xe", "vehicle", "vf")),
        ):
            if any(term in lowered for term in terms):
                return value
    return None


@conversation_router.post("/turns", response_model=None)
async def execute_turn(
    request: ConversationTurnRequest,
    http_request: Request,
    context: Annotated[ExecutionContext, Depends(require_execution_context)],
) -> ExecutionResponse:
    assert_request_matches_claims(
        context=context,
        request_id=request.request_id,
        correlation_id=request.correlation_id,
        session_id=request.session_id,
        turn_id=request.turn_id,
        conversation_version=request.conversation_version,
        fencing_token=request.fencing_token,
        locale=request.locale,
        authorization_context_digest=request.authorization_context_digest,
    )
    http_request.state.ai_response_request_id = str(request.request_id)
    dependencies = getattr(http_request.app.state, "conversation_dependencies", None)
    if dependencies is None:
        raise _unavailable("Conversation graph execution is not configured.")

    claims = context.claims
    if not _task_release_is_current(request, context):
        raise _stale("STALE_TASK_RELEASE")
    if request.task_context is not None and request.task_context.expires_at <= datetime.now(UTC):
        raise _stale("EXPIRED_TASK_CONTEXT")
    if not task_receipts_are_current(request, datetime.now(UTC)):
        raise _stale("EXPIRED_TASK_SLOT_RECEIPT")
    subject = _subject_for(context)
    control = GraphControlState(
        graph_version=claims.graph_revision,
        policy_revision=claims.policy_revision,
        knowledge_revision=claims.knowledge_revision,
        assistant_profile=claims.assistant_profile,
        authorization_context_hash=claims.authorization_context_digest,
        conversation_version=claims.conversation_version,
        fencing_token=claims.fencing_token,
        deadline_at=claims.budget.deadline_at,
    )
    budget = _inference_budget(
        claims.budget.max_model_tokens,
        claims.budget.max_cost_micros,
    )
    try:
        runtime = await build_turn_runtime(
            dependencies,
            session_id=request.session_id,
            turn_id=request.turn_id,
            subject=subject,
            assistant_profile=claims.assistant_profile,
            locale=request.locale,
            graph_revision=claims.graph_revision,
            policy_revision=claims.policy_revision,
            knowledge_revision=claims.knowledge_revision,
            expected_activation_id=claims.activation_id,
            expected_manifest_sha256=claims.manifest_sha256,
            budget=budget,
            correlation_id=str(request.correlation_id),
        )
    except Exception as error:
        if isinstance(error, ReleaseRuntimeUnavailable):
            raise _release_unavailable() from error
        raise
    state: ConversationGraphState = {
        "message": request.message,
        "final_answer": "",
        "citations": (),
        "global_entities": tuple(
            ConfirmedGlobalEntity(
                kind=entity.kind,
                reference=entity.reference,
                source_revision=entity.source_revision,
                classification=entity.classification,
                authority_digest=entity.authority_digest,
                confirmed_at=entity.confirmed_at,
                expires_at=entity.expires_at,
                confidence=1.0,
            )
            for entity in request.confirmed_entities
            if entity.expires_at > datetime.now(UTC)
        ),
        "active_task": (
            ActiveTaskState(
                intent=request.task_context.intent,
                required_arguments=request.task_context.pending_slots,
                retry_count=0,
            )
            if request.task_context is not None
            else None
        ),
        "control": control,
        "evidence": (),
        "outcome": None,
        "worker_attempts": 0,
        "route_history": (),
        "cost_microusd": 0,
        "model_tokens": 0,
    }
    identity = CheckpointIdentity(
        session_id=request.session_id,
        turn_id=request.turn_id,
        graph_version=claims.graph_revision,
    )
    try:
        result = await runtime.start(state, identity=identity)
        usage = ExecutionUsage(
            costMicros=_usage_value(result, "cost_microusd"),
            modelTokens=_usage_value(result, "model_tokens"),
        )
        try:
            await runtime.assert_release_current()
        except ReleaseRuntimeUnavailable:
            return build_failed_safely_response(
                control=control,
                usage=usage,
                release_revision=runtime.release.activation_id,
            )

        outcome = result.get("outcome")
        if isinstance(outcome, ResumeRejected):
            if outcome.code == "DUPLICATE_TURN_START":
                raise _stale(outcome.code)
            raise _unavailable(f"Turn could not start: {outcome.code}.")
        if not isinstance(outcome, GraphOutcome):
            raise _unavailable("The conversation graph returned no outcome.")
        if outcome.kind == "cancelled":
            if outcome.code == "STALE_FENCING_TOKEN":
                raise _stale(outcome.code)
            raise _unavailable(f"Turn was cancelled: {outcome.code}.")

        try:
            lease = await runtime.issue_commit_lease(
                session_id=request.session_id,
                turn_id=request.turn_id,
                request_id=request.request_id,
                conversation_version=claims.conversation_version,
                fencing_token=claims.fencing_token,
            )
        except ReleaseRuntimeUnavailable:
            return build_failed_safely_response(
                control=control,
                usage=usage,
                release_revision=runtime.release.activation_id,
            )
        receipt = ReleaseCommitReceipt(
            activationId=UUID(runtime.release.activation_id),
            leaseId=lease.lease_id,
            candidateSha256=runtime.release.candidate_sha256,
            activationEnvelopeSha256=runtime.release.activation_envelope_sha256,
            pointerRevision=runtime.release.pointer_revision,
            sessionId=request.session_id,
            turnId=request.turn_id,
            requestId=request.request_id,
            conversationVersion=claims.conversation_version,
            fencingToken=claims.fencing_token,
            issuedAt=lease.issued_at,
            expiresAt=lease.expires_at,
        )
        return build_execution_response(
            outcome=outcome,
            control=control,
            final_answer=cast("str | None", result.get("final_answer")),
            citations=cast("tuple[Citation, ...]", result.get("citations", ())),
            usage=usage,
            release_revision=runtime.release.activation_id,
            release_commit_receipt=receipt,
            task_proposal=(
                build_clarification_task_proposal(
                    request=request,
                    context=context,
                    result=result,
                )
                if outcome.kind == "needs_clarification"
                else None
            ),
        )
    except ReleaseRuntimeUnavailable as error:
        raise _release_unavailable() from error
    finally:
        await runtime.close()


@conversation_router.post("/turns/{turn_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_turn(
    turn_id: UUID,
    request: ConversationTurnCancellation,
    http_request: Request,
    context: Annotated[ExecutionContext, Depends(require_execution_context)],
) -> Response:
    assert_request_matches_claims(
        context=context,
        request_id=request.request_id,
        correlation_id=context.claims.correlation_id,
        session_id=context.claims.session_id,
        turn_id=turn_id,
        conversation_version=request.conversation_version,
        fencing_token=request.fencing_token,
    )
    http_request.state.ai_response_request_id = str(request.request_id)
    port = execution_cancellation_port(http_request)
    receipt = await port.accept_durably(
        CancellationCommand(
            request_id=request.request_id,
            session_id=context.claims.session_id,
            turn_id=turn_id,
            conversation_version=request.conversation_version,
            fencing_token=request.fencing_token,
            reason=request.reason,
        )
    )
    if (
        receipt.request_id != request.request_id
        or receipt.turn_id != turn_id
        or receipt.fencing_token != request.fencing_token
        or receipt.durability != "durable"
        or receipt.persisted_at.tzinfo is None
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "INTERNAL_FAILURE",
                "message": "Cancellation persistence returned an invalid receipt.",
            },
        )
    return Response(status_code=status.HTTP_202_ACCEPTED)
