from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.api.internal_v1.conversation_router import build_clarification_task_delta
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
    task_context = (
        {
            "authorizationContextDigest": "d" * 64,
            "collectedSlots": {
                "vehicle_model": {
                    "authorityDigest": "e" * 64,
                    "kind": "opaque_reference",
                    "reference": "vehicle:vf-8",
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
            "taskId": str(uuid4()),
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


def test_clarification_delta_resumes_the_authoritative_task_version() -> None:
    request = _request(with_task=True)
    delta = build_clarification_task_delta(
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
    assert delta.task_id == request.task_context.task_id
    assert delta.expected_task_version == 4
    assert delta.authorization_context_digest == request.authorization_context_digest
    assert delta.collected_slots["vehicle_model"].reference == "vehicle:vf-8"
    assert delta.source_turn_id == request.turn_id


def test_clarification_delta_creates_a_deterministic_new_task_identity() -> None:
    request = _request(with_task=False)
    context = _execution_context(request)
    active_task = ActiveTaskState(
        intent="vehicle_question",
        required_arguments=("vehicle_variant",),
        retry_count=0,
    )

    first = build_clarification_task_delta(
        request=request,
        context=context,
        result={"active_task": active_task},
    )
    second = build_clarification_task_delta(
        request=request,
        context=context,
        result={"active_task": active_task},
    )

    assert first.task_id == second.task_id
    assert first.expected_task_version == 0
    assert first.pending_slots == ("vehicle_variant",)
    assert first.provenance_digest == second.provenance_digest


def test_clarification_delta_replaces_active_task_on_explicit_topic_switch() -> None:
    request = _request(with_task=True)
    assert request.task_context is not None

    delta = build_clarification_task_delta(
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

    assert delta.task_id != request.task_context.task_id
    assert delta.expected_task_version == 0
    assert delta.intent == "charging_question"
    assert delta.collected_slots == {}


def test_unknown_multi_intent_clarification_preserves_active_task_authority() -> None:
    request = _request(with_task=True)
    assert request.task_context is not None

    delta = build_clarification_task_delta(
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

    assert delta.task_id == request.task_context.task_id
    assert delta.expected_task_version == request.task_context.task_version
    assert delta.intent == request.task_context.intent
    assert delta.pending_slots == ("primary_intent",)
