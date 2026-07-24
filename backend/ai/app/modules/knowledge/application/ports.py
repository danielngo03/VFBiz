from typing import Protocol

from app.modules.assistant.domain import AssistantProfile, Evidence


class KnowledgeRetriever(Protocol):
    async def retrieve(
        self,
        query: str,
        profile: AssistantProfile,
        subject: str,
    ) -> tuple[Evidence, ...]: ...
