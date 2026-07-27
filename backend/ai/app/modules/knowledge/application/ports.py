from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.modules.knowledge.domain import (
    ApprovedKnowledgeSource,
    KnowledgeActor,
    KnowledgeRelease,
    KnowledgeScope,
    RevisionBarrier,
)


class KnowledgeAssistantProfile(StrEnum):
    PUBLIC_CUSTOMER = "public_customer"
    AUTHENTICATED_CUSTOMER = "authenticated_customer"


@dataclass(frozen=True, slots=True)
class KnowledgeEvidence:
    evidence_id: str
    source_uri: str
    source_revision: str
    title: str
    excerpt: str
    freshness: str


class KnowledgeRetriever(Protocol):
    async def retrieve(
        self,
        query: str,
        profile: KnowledgeAssistantProfile,
        subject: str,
    ) -> tuple[KnowledgeEvidence, ...]: ...


class SourceRegisterReader(Protocol):
    async def read_approved(
        self, source_ids: tuple[str, ...]
    ) -> tuple[ApprovedKnowledgeSource, ...]: ...


class KnowledgeReleaseRepository(Protocol):
    async def get_idempotent_release_result(
        self, release_id: UUID, *, operation: str, idempotency_key: str
    ) -> KnowledgeRelease | None: ...

    async def get_idempotent_barrier_result(
        self, release_id: UUID, *, idempotency_key: str
    ) -> RevisionBarrier | None: ...

    async def add(
        self,
        release: KnowledgeRelease,
        *,
        actor: KnowledgeActor,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> None: ...

    async def get(self, release_id: UUID) -> KnowledgeRelease | None: ...

    async def save_transition(
        self,
        release: KnowledgeRelease,
        *,
        expected_version: int,
        actor: KnowledgeActor,
        reason: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> None: ...

    async def open_barrier(
        self,
        *,
        scope: KnowledgeScope,
        candidate_release_id: UUID,
        expected_release_version: int,
        current_source_hashes: dict[str, str],
        critical: bool,
        deadline_at: datetime,
        actor: KnowledgeActor,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> RevisionBarrier: ...

    async def activate_atomic(
        self,
        *,
        release_id: UUID,
        expected_release_version: int,
        expected_pointer_version: int,
        expected_barrier_generation: int,
        current_source_hashes: dict[str, str],
        actor: KnowledgeActor,
        reason: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeRelease: ...

    async def rollback_atomic(
        self,
        *,
        target_release_id: UUID,
        expected_pointer_version: int,
        expected_barrier_generation: int,
        current_source_hashes: dict[str, str],
        actor: KnowledgeActor,
        reason: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeRelease: ...

    async def tombstone_atomic(
        self,
        *,
        release_id: UUID,
        expected_release_version: int,
        expected_pointer_version: int | None,
        actor: KnowledgeActor,
        reason: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeRelease: ...
