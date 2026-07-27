from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.internal_v1.conversation_response import (
    ExecutionResponse,
    ExecutionUsage,
    ReleaseCommitReceipt,
    build_execution_response,
    build_failed_safely_response,
)
from app.api.internal_v1.conversation_schemas import (
    ConversationTurnCancellation,
    ConversationTurnRequest,
)
from app.bootstrap.conversation_graph import build_turn_runtime
from app.bootstrap.release_runtime import ReleaseRuntimeUnavailable
from app.modules.assistant.domain import GraphControlState, GraphOutcome
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


def _subject_for(context: ExecutionContext) -> tuple[str, str]:
    """Return (subject, authorization_context_hash). Both authorization
    variants already carry an opaque SHA-256 identifier; reusing it avoids
    inventing a second hash for the same trust boundary.
    """
    authorization = context.claims.authorization
    if authorization.kind == "authenticated_customer":
        return authorization.subject_ref, authorization.subject_ref
    return "anonymous", authorization.capability_hash


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
    )
    dependencies = getattr(http_request.app.state, "conversation_dependencies", None)
    if dependencies is None:
        raise _unavailable("Conversation graph execution is not configured.")

    claims = context.claims
    subject, authorization_context_hash = _subject_for(context)
    control = GraphControlState(
        graph_version=claims.graph_revision,
        policy_revision=claims.policy_revision,
        knowledge_revision=claims.knowledge_revision,
        assistant_profile=claims.assistant_profile,
        authorization_context_hash=authorization_context_hash,
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
        "global_entities": (),
        "active_task": None,
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
