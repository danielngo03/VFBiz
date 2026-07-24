from typing import Protocol

from app.modules.assistant.domain import DraftAnswer, Evidence


class InferenceProvider(Protocol):
    async def generate(self, question: str, evidence: tuple[Evidence, ...]) -> DraftAnswer: ...
