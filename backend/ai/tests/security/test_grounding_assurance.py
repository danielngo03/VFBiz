import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from app.modules.evaluation.application.grounding_assurance import (
    AnswerSegment,
    AnswerSegmentKind,
    CitationEvidence,
    ClaimEntailmentDecision,
    ClaimEntailmentEngine,
    ExactEvidenceEntailmentEngine,
    GroundingAssuranceRequest,
    GroundingAssuranceValidator,
    GroundingPolicyContext,
    GroundingPolicyContextAuthority,
    RetrievalSnapshotAuthority,
    SafeTemplateRegistry,
    SegmentedAnswer,
    TrustedRetrievalSnapshot,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)
FACT = "Thời hạn bảo hành là 10 năm"


def evidence() -> CitationEvidence:
    return CitationEvidence(
        evidence_id="evidence-1",
        excerpt=FACT,
        source_uri="knowledge://warranty/source-1",
        source_revision="source-revision-4",
        knowledge_revision="knowledge-release-v4",
        effective_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=1),
        content_sha256=sha256(FACT.encode()).hexdigest(),
    )


def snapshot(item: CitationEvidence | None = None) -> TrustedRetrievalSnapshot:
    return TrustedRetrievalSnapshot(
        snapshot_id="snapshot-1",
        release_id="assistant-release-4",
        pointer_revision=7,
        assistant_profile="customer-assistant",
        acl_namespace="public-vn",
        retriever_revision="hybrid-retriever-v4",
        knowledge_revision="knowledge-release-v4",
        evidence=(item or evidence(),),
    )


def answer(
    *,
    text: str = FACT,
    non_factual_text: str = "Anh/chị có muốn xem thêm điều kiện không ạ?",
) -> SegmentedAnswer:
    return SegmentedAnswer(
        (
            AnswerSegment(
                "claim-1",
                AnswerSegmentKind.FACTUAL,
                text,
                ("evidence-1",),
            ),
            AnswerSegment(
                "discourse-1",
                AnswerSegmentKind.DISCOURSE,
                non_factual_text,
                template_id="offer-more-detail",
            ),
        )
    )


class MemorySnapshots(RetrievalSnapshotAuthority):
    def __init__(self, item: TrustedRetrievalSnapshot | None) -> None:
        self.item = item

    async def resolve(
        self,
        snapshot_id: str,
        context: GroundingPolicyContext,
    ) -> TrustedRetrievalSnapshot | None:
        return self.item if self.item and snapshot_id == self.item.snapshot_id else None


class MemoryContexts(GroundingPolicyContextAuthority):
    def __init__(self, item: GroundingPolicyContext | None) -> None:
        self.item = item

    async def resolve(self, context_id: str) -> GroundingPolicyContext | None:
        return self.item if self.item and context_id == self.item.context_id else None


def context(**changes: object) -> GroundingPolicyContext:
    base = GroundingPolicyContext(
        context_id="grounding-context-1",
        activation_id="assistant-release-4",
        candidate_sha256="a" * 64,
        assistant_profile="customer-assistant",
        authorization_context_sha256=sha256(b"public-vn").hexdigest(),
        retriever_revision="hybrid-retriever-v4",
        knowledge_revision="knowledge-release-v4",
        active_pointer_revision=7,
    )
    return replace(base, **changes)


class Templates(SafeTemplateRegistry):
    def exact_text(self, template_id: str) -> str | None:
        return {
            "offer-more-detail": "Anh/chị có muốn xem thêm điều kiện không ạ?",
            "safe-refusal": "Tôi chưa có nguồn đủ tin cậy để trả lời nội dung này.",
        }.get(template_id)


def request(
    item: TrustedRetrievalSnapshot | None = None,
    response: SegmentedAnswer | None = None,
    **changes: object,
) -> GroundingAssuranceRequest:
    trusted = item or snapshot()
    base = GroundingAssuranceRequest(
        answer=response or answer(),
        policy_context_id="grounding-context-1",
        snapshot_id=trusted.snapshot_id,
        expected_snapshot_sha256=trusted.content_sha256,
        expected_validator_revision="exact-evidence-v2",
    )
    return replace(base, **changes)


def validator(
    item: TrustedRetrievalSnapshot | None = None,
    engine: ClaimEntailmentEngine | None = None,
    policy_context: GroundingPolicyContext | None = None,
) -> GroundingAssuranceValidator:
    return GroundingAssuranceValidator(
        engine=engine or ExactEvidenceEntailmentEngine(),
        policy_context_authority=MemoryContexts(policy_context or context()),
        snapshot_authority=MemorySnapshots(item or snapshot()),
        template_registry=Templates(),
        minimum_score=1.0,
        clock=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_resolves_trusted_snapshot_and_validates_complete_segmented_answer() -> None:
    result = await validator().validate(request())
    assert result.supported is True
    assert result.unsupported_claim_ids == ()
    assert result.rendered_text_sha256 == sha256(answer().rendered_text.encode()).hexdigest()


@pytest.mark.asyncio
async def test_caller_cannot_substitute_snapshot_profile_acl_or_retriever() -> None:
    for trusted_context, trusted_snapshot, failure in (
        (
            context(assistant_profile="employee-assistant"),
            snapshot(),
            "ASSISTANT_PROFILE_MISMATCH",
        ),
        (
            context(authorization_context_sha256=sha256(b"restricted").hexdigest()),
            snapshot(),
            "AUTHORIZATION_CONTEXT_MISMATCH",
        ),
        (
            context(retriever_revision="other"),
            snapshot(),
            "RETRIEVER_REVISION_MISMATCH",
        ),
        (
            context(active_pointer_revision=999),
            snapshot(),
            "POINTER_REVISION_MISMATCH",
        ),
    ):
        result = await validator(
            item=trusted_snapshot,
            policy_context=trusted_context,
        ).validate(request(trusted_snapshot))
        assert failure in result.failure_codes
    result = await validator().validate(request(expected_snapshot_sha256="0" * 64))
    assert result.failure_codes == ("EVIDENCE_SNAPSHOT_MISMATCH",)


@pytest.mark.asyncio
async def test_factual_text_cannot_hide_in_discourse_or_refusal_segment() -> None:
    disguised = SegmentedAnswer(
        (
            AnswerSegment(
                "discourse-1",
                AnswerSegmentKind.DISCOURSE,
                "Giá xe là 1 đồng",
                template_id="offer-more-detail",
            ),
        )
    )
    result = await validator().validate(request(response=disguised))
    assert result.supported is False
    assert result.failure_codes == ("UNSAFE_NON_FACTUAL_SEGMENT",)


def test_duplicate_segment_and_evidence_ids_are_rejected() -> None:
    segment = answer().segments[0]
    with pytest.raises(ValueError, match="unique"):
        SegmentedAnswer((segment, segment))
    item = evidence()
    with pytest.raises(ValueError, match="unique"):
        replace(snapshot(), evidence=(item, item))


@pytest.mark.asyncio
async def test_tampered_stale_or_cross_revision_evidence_fails_closed() -> None:
    tampered = replace(evidence(), excerpt="Thời hạn bảo hành là 100 năm")
    result = await validator(snapshot(tampered)).validate(request(snapshot(tampered)))
    assert "EVIDENCE_CONTENT_DIGEST_MISMATCH" in result.failure_codes

    stale = replace(
        evidence(),
        knowledge_revision="knowledge-release-v3",
        expires_at=NOW - timedelta(seconds=1),
    )
    result = await validator(snapshot(stale)).validate(request(snapshot(stale)))
    assert result.failure_codes == ("EVIDENCE_REVISION_MISMATCH", "EVIDENCE_EXPIRED")


@pytest.mark.asyncio
async def test_entailment_budget_and_deadline_fail_closed() -> None:
    two_claims = SegmentedAnswer(
        (
            answer().segments[0],
            replace(answer().segments[0], segment_id="claim-2"),
        )
    )
    budget = await validator().validate(
        request(response=two_claims, max_entailment_calls=1)
    )
    assert budget.failure_codes == ("VALIDATION_BUDGET_EXHAUSTED",)

    class SlowEngine(ClaimEntailmentEngine):
        revision = "slow-v1"

        async def evaluate(
            self, claim: object, evidence_item: object
        ) -> ClaimEntailmentDecision:
            await asyncio.sleep(0.05)
            return ClaimEntailmentDecision(True, 1.0, self.revision)

    deadline = await validator(engine=SlowEngine()).validate(
        request(expected_validator_revision="slow-v1", deadline_seconds=0.001)
    )
    assert deadline.failure_codes == ("VALIDATION_DEADLINE_EXCEEDED",)


@pytest.mark.asyncio
async def test_snapshot_not_found_and_validator_revision_fail_closed() -> None:
    missing = GroundingAssuranceValidator(
        engine=ExactEvidenceEntailmentEngine(),
        policy_context_authority=MemoryContexts(context()),
        snapshot_authority=MemorySnapshots(None),
        template_registry=Templates(),
        minimum_score=1.0,
        clock=lambda: NOW,
    )
    result = await missing.validate(request())
    assert result.failure_codes == ("SNAPSHOT_NOT_FOUND",)

    missing_context = GroundingAssuranceValidator(
        engine=ExactEvidenceEntailmentEngine(),
        policy_context_authority=MemoryContexts(None),
        snapshot_authority=MemorySnapshots(snapshot()),
        template_registry=Templates(),
        minimum_score=1.0,
        clock=lambda: NOW,
    )
    result = await missing_context.validate(request())
    assert result.failure_codes == ("POLICY_CONTEXT_NOT_FOUND",)

    result = await validator().validate(
        request(expected_validator_revision="unexpected-v3")
    )
    assert result.failure_codes == ("VALIDATOR_REVISION_MISMATCH",)
