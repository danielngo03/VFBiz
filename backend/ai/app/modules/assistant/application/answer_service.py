from app.modules.assistant.domain import (
    AnswerRequest,
    AnswerResult,
    AssistantProfile,
    Citation,
    Evidence,
)
from app.modules.inference.application import InferenceProvider
from app.modules.knowledge.application import KnowledgeRetriever


class AnswerService:
    def __init__(
        self,
        retriever: KnowledgeRetriever,
        inference: InferenceProvider,
    ) -> None:
        self._retriever = retriever
        self._inference = inference

    async def answer(
        self,
        request: AnswerRequest,
        authorized_profile: AssistantProfile | None = None,
    ) -> AnswerResult:
        if authorized_profile is not None and request.profile is not authorized_profile:
            raise PermissionError("assistant profile escalation is not allowed")

        evidence = await self._retriever.retrieve(
            query=request.question,
            profile=request.profile,
            subject=request.subject,
        )
        if not evidence:
            return self._refusal("NO_APPROVED_EVIDENCE")

        draft = await self._inference.generate(request.question, evidence)
        if not draft.text.strip() or not draft.citations:
            return self._refusal("UNGROUNDED_RESPONSE")
        if not self._citations_are_valid(draft.citations, evidence):
            return self._refusal("INVALID_CITATION")
        return AnswerResult(
            status="grounded",
            answer=draft.text.strip(),
            citations=draft.citations,
            reason=None,
        )

    def _citations_are_valid(
        self,
        citations: tuple[Citation, ...],
        evidence: tuple[Evidence, ...],
    ) -> bool:
        approved = {
            (item.evidence_id, item.source_uri, item.source_revision, item.freshness)
            for item in evidence
        }
        return all(
            (
                citation.evidence_id,
                citation.source_uri,
                citation.source_revision,
                citation.freshness,
            )
            in approved
            for citation in citations
        )

    def _refusal(self, reason: str) -> AnswerResult:
        return AnswerResult(status="refused", answer=None, citations=(), reason=reason)
