from typing import Protocol

from app.modules.knowledge.domain import KnowledgeScope
from app.modules.knowledge.domain.retrieval import (
    RerankScore,
    RetrievalCandidate,
    RetrievalCandidateQuery,
    RetrievalSnapshot,
    SnapshotResolution,
)


class RetrievalBackendUnavailable(RuntimeError):
    """Expected infrastructure outage mapped to a fail-closed retrieval outcome."""


class RetrievalSnapshotResolver(Protocol):
    async def resolve(self, scope: KnowledgeScope) -> SnapshotResolution: ...


class RetrievalCandidateSearcher(Protocol):
    async def search_candidates(
        self,
        snapshot: RetrievalSnapshot,
        *,
        authorized_acl_namespaces: frozenset[str],
        query: RetrievalCandidateQuery,
    ) -> tuple[RetrievalCandidate, ...]: ...


class QueryEmbedder(Protocol):
    @property
    def revision(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    async def embed_query(self, query: str) -> tuple[float, ...]: ...


class CandidateReranker(Protocol):
    @property
    def retriever_revision(self) -> str: ...

    async def rerank(
        self,
        query: str,
        candidates: tuple[RetrievalCandidate, ...],
    ) -> tuple[RerankScore, ...]: ...
