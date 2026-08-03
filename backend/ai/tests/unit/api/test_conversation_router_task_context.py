from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.api.internal_v1.conversation_router import (
    build_clarification_task_proposal,
    task_receipts_are_current,
)
from app.api.internal_v1.conversation_schemas import ConversationTurnRequest
from app.modules.assistant.domain import ActiveTaskState
from app.platform.security.execution_assertion import (
    AIExecutionAssertionClaims,
    ExecutionContext,
)


def _request(*, with_task: bool) -> ConversationTurnRequest:
    now = datetime.now(UTC)
    session_id = uuid4()
    turn_id = uuid4()
    task_id = uuid4()
    task_context = (
        {
            "authorizationContextDigest": "d" * 64,
            "collectedSlots": {
                "vehicle_model": {
                    "authority": "vehicle_catalog",
                    "authorityDigest": "e" * 64,
                    "confirmedAt": now.isoformat(),
                    "expiresAt": (now + timedelta(minutes=20)).isoformat(),
                    "kind": "receipt",
                    "opaqueReference": f"vehicle:ref/v1/{'1' * 64}",
                    "provenanceDigest": "f" * 64,
                    "slot": "vehicle_model",
                    "sourceRevision": "vehicle-catalog-v1",
                    "taskId": str(task_id),
                }
            },
            "expiresAt": (now + timedelta(minutes=20)).isoformat(),
            "intent": "vehicle_question",
            "intentRevision": "router-r1",
            "lastFencingToken": 6,
            "pendingSlots": ["vehicle_variant"],
            "provenanceDigest": "f" * 64,
            "release": {
                "activationId": "00000000-0000-4000-8000-000000000010",
                "graphRevision": "graph-r1",
                "knowledgeRevision": "knowledge-r1",
                "manifestSha256": "c" * 64,
                "policyRevision": "policy-r1",
            },
            "sourceTurnId": str(uuid4()),
            "state": "awaiting_clarification",
            "taskId": str(task_id),
            "taskVersion": 4,
        }
        if with_task
        else None
    )
    return ConversationTurnRequest.model_validate(
        {
            "authorizationContextDigest": "d" * 64,
            "confirmedEntities": [],
            "conversationVersion": 7,
            "correlationId": str(uuid4()),
            "fencingToken": 8,
            "locale": "vi",
            "message": "Chiếc xe lúc nãy là bản nào?",
            "requestId": str(uuid4()),
            "sessionId": str(session_id),
            "taskContext": task_context,
            "turnId": str(turn_id),
        }
    )


def _execution_context(request: ConversationTurnRequest) -> ExecutionContext:
    now = datetime.now(UTC)
    issued_at = int(now.timestamp())
    return ExecutionContext(
        claims=AIExecutionAssertionClaims.model_validate(
            {
                "activationId": "00000000-0000-4000-8000-000000000010",
                "action": "turn.execute",
                "assistantProfile": "public_customer",
                "aud": "vfbiz-ai",
                "authorization": {
                    "allowedTools": ["search_public_knowledge"],
                    "capabilityHash": "a" * 64,
                    "kind": "public_capability",
                },
                "authorizationContextDigest": request.authorization_context_digest,
                "budget": {
                    "deadlineAt": (now + timedelta(minutes=1)).isoformat(),
                    "maxCostMicros": 10_000,
                    "maxModelTokens": 1_000,
                },
                "conversationVersion": request.conversation_version,
                "correlationId": str(request.correlation_id),
                "exp": issued_at + 60,
                "fencingToken": request.fencing_token,
                "graphRevision": "graph-r1",
                "iat": issued_at,
                "iss": "vfbiz-api",
                "jti": str(uuid4()),
                "knowledgeRevision": "knowledge-r1",
                "locale": request.locale,
                "manifestSha256": "c" * 64,
                "nbf": issued_at,
                "policyRevision": "policy-r1",
                "requestHash": "b" * 64,
                "requestId": str(request.request_id),
                "sessionId": str(request.session_id),
                "turnId": str(request.turn_id),
            }
        )
    )


def test_clarification_proposal_resumes_the_authoritative_task_version() -> None:
    request = _request(with_task=True)
    proposal = build_clarification_task_proposal(
        request=request,
        context=_execution_context(request),
        result={
            "active_task": ActiveTaskState(
                intent="vehicle_question",
                required_arguments=("vehicle_variant",),
                retry_count=0,
            )
        },
    )

    assert request.task_context is not None
    assert proposal.task_id == request.task_context.task_id
    assert proposal.expected_task_version == 4
    assert proposal.authorization_context_digest == request.authorization_context_digest
    assert proposal.slot_candidates == ()
    assert proposal.source_turn_id == request.turn_id


def test_clarification_proposal_creates_a_deterministic_new_task_identity() -> None:
    request = _request(with_task=False)
    context = _execution_context(request)
    active_task = ActiveTaskState(
        intent="vehicle_question",
        required_arguments=("vehicle_variant",),
        retry_count=0,
    )

    first = build_clarification_task_proposal(
        request=request,
        context=context,
        result={"active_task": active_task},
    )
    second = build_clarification_task_proposal(
        request=request,
        context=context,
        result={"active_task": active_task},
    )

    assert first.task_id == second.task_id
    assert first.expected_task_version == 0
    assert first.pending_slots == ("vehicle_variant",)
    assert first.provenance_digest == second.provenance_digest


def test_clarification_proposal_replaces_active_task_on_explicit_topic_switch() -> None:
    request = _request(with_task=True)
    assert request.task_context is not None

    proposal = build_clarification_task_proposal(
        request=request,
        context=_execution_context(request),
        result={
            "active_task": ActiveTaskState(
                intent="charging_question",
                required_arguments=("market",),
                retry_count=0,
            )
        },
    )

    assert proposal.task_id != request.task_context.task_id
    assert proposal.expected_task_version == 0
    assert proposal.intent == "charging_question"
    assert proposal.slot_candidates == ()


def test_unknown_multi_intent_clarification_preserves_active_task_authority() -> None:
    request = _request(with_task=True)
    assert request.task_context is not None

    proposal = build_clarification_task_proposal(
        request=request,
        context=_execution_context(request),
        result={
            "active_task": ActiveTaskState(
                intent="unknown",
                required_arguments=("primary_intent",),
                retry_count=0,
            )
        },
    )

    assert proposal.task_id == request.task_context.task_id
    assert proposal.expected_task_version == request.task_context.task_version
    assert proposal.intent == request.task_context.intent
    assert proposal.pending_slots == ("primary_intent",)


def test_clarification_proposal_emits_only_a_transient_bounded_slot_candidate() -> None:
    request = _request(with_task=True).model_copy(update={"message": "VF 8"})
    assert request.task_context is not None
    request = request.model_copy(
        update={
            "task_context": request.task_context.model_copy(
                update={"pending_slots": ("vehicle_model",)}
            )
        }
    )

    proposal = build_clarification_task_proposal(
        request=request,
        context=_execution_context(request),
        result={
            "active_task": ActiveTaskState(
                intent="vehicle_question",
                required_arguments=("vehicle_model",),
                retry_count=0,
            )
        },
    )

    assert len(proposal.slot_candidates) == 1
    candidate = proposal.slot_candidates[0]
    assert candidate.kind == "candidate"
    assert candidate.proposed_value == "VF 8"
    serialized = proposal.model_dump(by_alias=True, mode="json")
    assert "collectedSlots" not in serialized
    assert "authorityDigest" not in str(serialized)


def test_expired_authority_receipt_fails_closed_before_graph_execution() -> None:
    request = _request(with_task=True)
    assert request.task_context is not None
    receipt = request.task_context.collected_slots["vehicle_model"]

    assert task_receipts_are_current(
        request,
        receipt.expires_at - timedelta(microseconds=1),
    )
    assert not task_receipts_are_current(request, receipt.expires_at)
