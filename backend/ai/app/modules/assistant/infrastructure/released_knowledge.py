from uuid import UUID

from app.modules.assistant.domain import EvidenceReference, GraphControlState
from app.modules.assistant.infrastructure.knowledge_worker import citation_digest
from app.modules.knowledge.application import (
    KnowledgeAssistantProfile,
    KnowledgeEvidence,
    KnowledgeRetrievalService,
)
from app.modules.knowledge.application.retrieval_ports import RetrievalSnapshotResolver
from app.modules.knowledge.domain import KnowledgeScope
from app.modules.knowledge.domain.retrieval import RetrievalStatus, SnapshotStatus


class ReleasedKnowledgeRetriever:
    """Turn-scoped adapter from the released knowledge store to Assistant."""

    def __init__(
        self,
        *,
        service: KnowledgeRetrievalService,
        scope: KnowledgeScope,
        expected_release_id: UUID,
    ) -> None:
        self._service = service
        self._scope = scope
        self._expected_release_id = expected_release_id
        self._issued_digests: frozenset[str] = frozenset()
        self._issued_pointer_version: int | None = None

    @property
    def scope(self) -> KnowledgeScope:
        return self._scope

    @property
    def expected_release_id(self) -> UUID:
        return self._expected_release_id

    @property
    def issued_digests(self) -> frozenset[str]:
        return self._issued_digests

    @property
    def issued_pointer_version(self) -> int | None:
        return self._issued_pointer_version

    async def retrieve(
        self,
        query: str,
        profile: KnowledgeAssistantProfile,
    ) -> tuple[KnowledgeEvidence, ...]:
        if profile.value != self._scope.assistant_profile:
            return ()
        result = await self._service.retrieve(
            query=query,
            scope=self._scope,
            authorized_acl_namespaces=frozenset({self._scope.acl_namespace}),
        )
        if (
            result.status is not RetrievalStatus.EVIDENCE
            or result.release_id != self._expected_release_id
            or result.pointer_version is None
        ):
            return ()
        evidence = tuple(
            KnowledgeEvidence(
                evidence_id=item.evidence_id,
                source_uri=item.source_uri,
                source_revision=item.source_revision,
                title=item.title,
                excerpt=item.excerpt,
                freshness=item.freshness.isoformat(),
            )
            for item in result.evidence
        )
        self._issued_digests = frozenset(
            citation_digest(
                evidence_id=item.evidence_id,
                source_revision=item.source_revision,
            )
            for item in evidence
        )
        self._issued_pointer_version = result.pointer_version
        return evidence


class ReleasedEvidenceAuthority:
    """Revalidate the active snapshot immediately before answer release."""

    def __init__(
        self,
        *,
        retriever: ReleasedKnowledgeRetriever,
        snapshots: RetrievalSnapshotResolver,
    ) -> None:
        self._retriever = retriever
        self._snapshots = snapshots

    async def validate(
        self,
        *,
        references: tuple[EvidenceReference, ...],
        control: GraphControlState,
    ) -> bool:
        if (
            not references
            or any(item.kind != "citation" for item in references)
            or len({item.digest for item in references}) != len(references)
            or not frozenset(item.digest for item in references).issubset(
                self._retriever.issued_digests
            )
        ):
            return False
        if control.knowledge_revision != str(self._retriever.expected_release_id):
            return False
        resolution = await self._snapshots.resolve(self._retriever.scope)
        snapshot = resolution.snapshot
        return bool(
            resolution.status is SnapshotStatus.ACTIVE
            and snapshot is not None
            and snapshot.release_id == self._retriever.expected_release_id
            and snapshot.pointer_version == self._retriever.issued_pointer_version
        )
