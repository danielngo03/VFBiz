from app.modules.assistant.application import AnswerService
from app.modules.assistant.domain import AssistantProfile, DraftAnswer, Evidence


class DisabledKnowledgeRetriever:
    async def retrieve(
        self,
        query: str,
        profile: AssistantProfile,
        subject: str,
    ) -> tuple[Evidence, ...]:
        return ()


class DisabledInferenceProvider:
    async def generate(self, question: str, evidence: tuple[Evidence, ...]) -> DraftAnswer:
        return DraftAnswer(text="", citations=())


def get_answer_service() -> AnswerService:
    """Fail closed until an approved release supplies both adapters."""
    return AnswerService(
        retriever=DisabledKnowledgeRetriever(),
        inference=DisabledInferenceProvider(),
    )
