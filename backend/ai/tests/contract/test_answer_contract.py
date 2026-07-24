from dataclasses import dataclass

import pytest

from app.modules.assistant.application.answer_service import AnswerService
from app.modules.assistant.domain.models import (
    AnswerRequest,
    AssistantProfile,
    Citation,
    DraftAnswer,
    Evidence,
)


@dataclass(frozen=True)
class StubRetriever:
    evidence: tuple[Evidence, ...]

    async def retrieve(
        self,
        query: str,
        profile: AssistantProfile,
        subject: str,
    ) -> tuple[Evidence, ...]:
        return self.evidence


@dataclass(frozen=True)
class StubInference:
    draft: DraftAnswer

    async def generate(self, question: str, evidence: tuple[Evidence, ...]) -> DraftAnswer:
        return self.draft


def request(profile: AssistantProfile = AssistantProfile.PUBLIC_CUSTOMER) -> AnswerRequest:
    return AnswerRequest(
        question="VF 9 có những thông tin nào đã được xác minh?",
        profile=profile,
        subject="customer-123",
    )


@pytest.mark.asyncio
async def test_refuses_when_retrieval_has_no_approved_evidence() -> None:
    service = AnswerService(
        retriever=StubRetriever(()),
        inference=StubInference(DraftAnswer(text="Không được dùng", citations=())),
    )

    result = await service.answer(request())

    assert result.status == "refused"
    assert result.answer is None
    assert result.citations == ()
    assert result.reason == "NO_APPROVED_EVIDENCE"


@pytest.mark.asyncio
async def test_returns_grounded_answer_with_revision_and_freshness() -> None:
    evidence = Evidence(
        evidence_id="ev-1",
        source_uri="https://example.test/vehicles/vf9",
        source_revision="catalog-2026-07-22",
        title="VF 9",
        excerpt="Thông tin đã được duyệt.",
        freshness="2026-07-22T00:00:00Z",
    )
    citation = Citation(
        evidence_id="ev-1",
        source_uri=evidence.source_uri,
        source_revision=evidence.source_revision,
        title=evidence.title,
        freshness=evidence.freshness,
    )
    service = AnswerService(
        retriever=StubRetriever((evidence,)),
        inference=StubInference(
            DraftAnswer(text="Thông tin đã được xác minh.", citations=(citation,))
        ),
    )

    result = await service.answer(request())

    assert result.status == "grounded"
    assert result.answer == "Thông tin đã được xác minh."
    assert result.citations == (citation,)


@pytest.mark.asyncio
async def test_refuses_when_model_cites_evidence_outside_retrieval_set() -> None:
    evidence = Evidence(
        evidence_id="ev-1",
        source_uri="https://example.test/vehicles/vf9",
        source_revision="catalog-2026-07-22",
        title="VF 9",
        excerpt="Thông tin đã được duyệt.",
        freshness="2026-07-22T00:00:00Z",
    )
    invalid = Citation(
        evidence_id="ev-other",
        source_uri="https://untrusted.test",
        source_revision="unknown",
        title="Unknown",
        freshness="unknown",
    )
    service = AnswerService(
        retriever=StubRetriever((evidence,)),
        inference=StubInference(DraftAnswer(text="Không hợp lệ", citations=(invalid,))),
    )

    result = await service.answer(request())

    assert result.status == "refused"
    assert result.reason == "INVALID_CITATION"


@pytest.mark.asyncio
async def test_rejects_profile_escalation_before_retrieval() -> None:
    service = AnswerService(
        retriever=StubRetriever(()),
        inference=StubInference(DraftAnswer(text="", citations=())),
    )

    with pytest.raises(PermissionError, match="assistant profile"):
        await service.answer(
            request(AssistantProfile.EMPLOYEE),
            authorized_profile=AssistantProfile.PUBLIC_CUSTOMER,
        )
