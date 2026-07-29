from datetime import UTC, datetime, timedelta

import pytest

from app.api.internal_v1.conversation_response import (
    AnsweredResponse,
    ClarificationResponse,
    ConversationTaskDeltaResponse,
    ExecutionUsage,
    HandoffResponse,
    RefusedResponse,
    ReleaseCommitReceipt,
    TaskReleaseBindingResponse,
    build_execution_response,
    handoff_reason_for,
)
from app.modules.assistant.domain import GraphControlState, GraphOutcome
from app.modules.inference.application import Citation

USAGE = ExecutionUsage(costMicros=1_000, modelTokens=200)
RELEASE_REVISION = "00000000-0000-4000-8000-000000000010"
RECEIPT = ReleaseCommitReceipt(
    activationId=RELEASE_REVISION,
    leaseId="00000000-0000-4000-8000-000000000001",
    candidateSha256="a" * 64,
    activationEnvelopeSha256="b" * 64,
    pointerRevision=1,
    sessionId="00000000-0000-4000-8000-000000000002",
    turnId="00000000-0000-4000-8000-000000000003",
    requestId="00000000-0000-4000-8000-000000000004",
    conversationVersion=1,
    fencingToken=1,
    issuedAt=datetime(2026, 7, 27, tzinfo=UTC),
    expiresAt=datetime(2026, 7, 27, 0, 0, 15, tzinfo=UTC),
)
TASK_DELTA = ConversationTaskDeltaResponse(
    authorizationContextDigest="a" * 64,
    collectedSlots={},
    expectedTaskVersion=0,
    expiresAt=datetime(2026, 7, 27, 0, 30, tzinfo=UTC),
    intent="vehicle_question",
    intentRevision="graph-r1",
    pendingSlots=("vehicle_variant",),
    provenanceDigest="d" * 64,
    release=TaskReleaseBindingResponse(
        activationId=RELEASE_REVISION,
        graphRevision="graph-r1",
        knowledgeRevision="knowledge-r1",
        manifestSha256="c" * 64,
        policyRevision="policy-r1",
    ),
    sourceTurnId=RECEIPT.turn_id,
    taskId="00000000-0000-4000-8000-000000000005",
)


def control() -> GraphControlState:
    return GraphControlState(
        graph_version="graph-r1",
        policy_revision="policy-r1",
        knowledge_revision="knowledge-r1",
        assistant_profile="public_customer",
        authorization_context_hash="a" * 64,
        conversation_version=1,
        fencing_token=1,
        deadline_at=datetime.now(UTC) + timedelta(seconds=5),
    )


def test_completed_outcome_builds_an_answered_response_with_exact_alias_keys() -> None:
    citation = Citation(
        evidence_id="b" * 64,
        source_uri="https://vinfast.vn/vf8",
        source_revision="catalog-r1",
        title="VF 8 specs",
        freshness="2026-07-01T00:00:00Z",
    )

    response = build_execution_response(
        outcome=GraphOutcome(kind="completed", code="ANSWERED"),
        control=control(),
        final_answer="VF 8 có phạm vi hoạt động khoảng 470km.",
        citations=(citation,),
        usage=USAGE,
        release_revision=RELEASE_REVISION,
        release_commit_receipt=RECEIPT,
    )

    assert isinstance(response, AnsweredResponse)
    dumped = response.model_dump(by_alias=True)
    assert set(dumped.keys()) == {
        "citations",
        "message",
        "outcome",
        "releaseRevision",
        "releaseCommitReceipt",
        "revisions",
        "usage",
    }
    assert dumped["citations"] == [
        {
            "knowledgeRevision": "knowledge-r1",
            "retrievedAt": "2026-07-01T00:00:00Z",
            "revision": "catalog-r1",
            "sourceId": "b" * 64,
            "title": "VF 8 specs",
            "uri": "https://vinfast.vn/vf8",
        }
    ]
    assert dumped["revisions"] == {
        "graph": "graph-r1",
        "knowledge": "knowledge-r1",
        "policy": "policy-r1",
    }


def test_completed_outcome_without_citations_or_answer_is_rejected() -> None:
    with pytest.raises(ValueError, match="answer and citations"):
        build_execution_response(
            outcome=GraphOutcome(kind="completed", code="ANSWERED"),
            control=control(),
            final_answer=None,
            citations=(),
            usage=USAGE,
            release_revision=RELEASE_REVISION,
            release_commit_receipt=RECEIPT,
        )


def test_refused_outcome_builds_a_refused_response_with_empty_citations() -> None:
    response = build_execution_response(
        outcome=GraphOutcome(kind="refused", code="MISSING_GROUNDED_EVIDENCE"),
        control=control(),
        final_answer=None,
        citations=(),
        usage=USAGE,
        release_revision=RELEASE_REVISION,
        release_commit_receipt=RECEIPT,
    )

    assert isinstance(response, RefusedResponse)
    dumped = response.model_dump(by_alias=True)
    assert dumped["citations"] == []
    assert set(dumped.keys()) == {
        "citations",
        "message",
        "outcome",
        "releaseRevision",
        "releaseCommitReceipt",
        "revisions",
        "usage",
    }


def test_clarification_is_a_terminal_typed_response() -> None:
    response = build_execution_response(
        outcome=GraphOutcome(
            kind="needs_clarification",
            code="MISSING_VARIANT",
            pending_slots=("vehicle_variant",),
        ),
        control=control(),
        final_answer=None,
        citations=(),
        usage=USAGE,
        release_revision=RELEASE_REVISION,
        release_commit_receipt=RECEIPT,
        task_delta=TASK_DELTA,
    )

    assert isinstance(response, ClarificationResponse)
    dumped = response.model_dump(by_alias=True)
    assert dumped["pendingSlots"] == ("vehicle_variant",)
    assert dumped["taskDelta"]["expectedTaskVersion"] == 0
    assert dumped["taskDelta"]["authorizationContextDigest"] == "a" * 64


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("NO_KNOWLEDGE_EVIDENCE", "insufficient_evidence"),
        ("MISSING_GROUNDED_EVIDENCE", "insufficient_evidence"),
        ("REFUSED", "safety_risk"),
        ("POLICY_DENIED", "safety_risk"),
        ("NO_SAFE_DEPLOYMENT", "policy_required"),
        ("RETRY_EXHAUSTED", "policy_required"),
    ],
)
def test_handoff_reason_mapping(code: str, expected: str) -> None:
    assert handoff_reason_for(code) == expected


def test_handoff_required_outcome_builds_a_handoff_response() -> None:
    response = build_execution_response(
        outcome=GraphOutcome(kind="handoff_required", code="NO_SAFE_DEPLOYMENT"),
        control=control(),
        final_answer=None,
        citations=(),
        usage=USAGE,
        release_revision=RELEASE_REVISION,
        release_commit_receipt=RECEIPT,
    )

    assert isinstance(response, HandoffResponse)
    dumped = response.model_dump(by_alias=True)
    assert dumped["reason"] == "policy_required"
    assert set(dumped.keys()) == {
        "customerMessage",
        "outcome",
        "reason",
        "releaseRevision",
        "releaseCommitReceipt",
        "revisions",
        "usage",
    }


def test_cancelled_outcome_falls_back_to_handoff_response() -> None:
    response = build_execution_response(
        outcome=GraphOutcome(kind="cancelled", code="TURN_DEADLINE_EXCEEDED"),
        control=control(),
        final_answer=None,
        citations=(),
        usage=USAGE,
        release_revision=RELEASE_REVISION,
        release_commit_receipt=RECEIPT,
    )

    assert isinstance(response, HandoffResponse)
