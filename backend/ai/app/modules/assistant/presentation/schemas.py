from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter

from app.modules.assistant.domain import AnswerResult

_http_url = TypeAdapter(HttpUrl)


class AnswerRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=2_000)
    profile: Literal["public_customer", "authenticated_customer", "employee"]


class CitationSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    source_uri: HttpUrl
    source_revision: str
    title: str
    freshness: str


class AnswerResponseSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["grounded", "refused", "handoff"]
    answer: str | None
    citations: tuple[CitationSchema, ...]
    reason: str | None

    @classmethod
    def from_result(cls, result: AnswerResult) -> "AnswerResponseSchema":
        return cls(
            status=result.status,
            answer=result.answer,
            citations=tuple(
                CitationSchema(
                    evidence_id=item.evidence_id,
                    source_uri=_http_url.validate_python(item.source_uri),
                    source_revision=item.source_revision,
                    title=item.title,
                    freshness=item.freshness,
                )
                for item in result.citations
            ),
            reason=result.reason,
        )
