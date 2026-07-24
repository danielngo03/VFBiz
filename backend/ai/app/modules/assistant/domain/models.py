from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class AssistantProfile(StrEnum):
    PUBLIC_CUSTOMER = "public_customer"
    AUTHENTICATED_CUSTOMER = "authenticated_customer"
    EMPLOYEE = "employee"


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    source_uri: str
    source_revision: str
    title: str
    excerpt: str
    freshness: str


@dataclass(frozen=True, slots=True)
class Citation:
    evidence_id: str
    source_uri: str
    source_revision: str
    title: str
    freshness: str


@dataclass(frozen=True, slots=True)
class AnswerRequest:
    question: str
    profile: AssistantProfile
    subject: str


@dataclass(frozen=True, slots=True)
class DraftAnswer:
    text: str
    citations: tuple[Citation, ...]


@dataclass(frozen=True, slots=True)
class AnswerResult:
    status: Literal["grounded", "refused", "handoff"]
    answer: str | None
    citations: tuple[Citation, ...]
    reason: str | None
