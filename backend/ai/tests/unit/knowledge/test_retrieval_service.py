from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.modules.knowledge.application import (
    KnowledgeRetrievalService,
    RetrievalBackendUnavailable,
)
from app.modules.knowledge.domain import (
    KnowledgeScope,
    RerankScore,
    RetrievalCandidate,
    RetrievalCandidateQuery,
    RetrievalSnapshot,
    RetrievalSourcePin,
    RetrievalStatus,
    SnapshotResolution,
    SnapshotStatus,
)

NOW = datetime(2026, 7, 25, tzinfo=UTC)
INDEX_GENERATION_ID = UUID("00000000-0000-4000-8000-000000000311")
SCOPE = KnowledgeScope(
    domain="synthetic-support",
    locale="vi-VN",
    assistant_profile="public_customer",
    acl_namespace="public_customer:synthetic-support:vi-VN",
)


@dataclass
class MemorySnapshotReader:
    resolution: SnapshotResolution
    candidates: tuple[RetrievalCandidate, ...] = ()
    unavailable_on_resolve: bool = False
    unavailable_on_candidates: bool = False
    received_acl: frozenset[str] | None = None
    received_query: RetrievalCandidateQuery | None = None

    async def resolve(self, scope: KnowledgeScope) -> SnapshotResolution:
        assert scope == SCOPE
        if self.unavailable_on_resolve:
            raise RetrievalBackendUnavailable("synthetic outage")
        return self.resolution

    async def search_candidates(
        self,
        snapshot: RetrievalSnapshot,
        *,
        authorized_acl_namespaces: frozenset[str],
        query: RetrievalCandidateQuery,
    ) -> tuple[RetrievalCandidate, ...]:
        assert snapshot == self.resolution.snapshot
        assert query.candidate_limit == 200
        self.received_acl = authorized_acl_namespaces
        self.received_query = query
        if self.unavailable_on_candidates:
            raise RetrievalBackendUnavailable("synthetic outage")
        return self.candidates


@dataclass
class DeterministicEmbedder:
    vector: tuple[float, ...] = (1.0, 0.0, 0.0)
    revision: str = "synthetic-embed-v1"
    dimension: int = 3
    unavailable: bool = False
    queries: list[str] = field(default_factory=lambda: [])

    async def embed_query(self, query: str) -> tuple[float, ...]:
        self.queries.append(query)
        if self.unavailable:
            raise RetrievalBackendUnavailable("synthetic embedder outage")
        return self.vector


@dataclass
class DeterministicReranker:
    scores: dict[UUID, float]
    retriever_revision: str = "hybrid-v1"
    unavailable: bool = False
    received: tuple[RetrievalCandidate, ...] = ()

    async def rerank(
        self,
        query: str,
        candidates: tuple[RetrievalCandidate, ...],
    ) -> tuple[RerankScore, ...]:
        assert query
        self.received = candidates
        if self.unavailable:
            raise RetrievalBackendUnavailable("synthetic reranker outage")
        return tuple(
            RerankScore(chunk_id=chunk_id, score=score) for chunk_id, score in self.scores.items()
        )


def snapshot(
    *,
    release_id: UUID | None = None,
    embedding_dimension: int = 3,
    embedding_revision: str = "synthetic-embed-v1",
    effective_at: datetime = NOW - timedelta(minutes=1),
    freshness_expires_at: datetime = NOW + timedelta(hours=1),
    retriever_revision: str = "hybrid-v1",
) -> RetrievalSnapshot:
    source_id = uuid4()
    return RetrievalSnapshot(
        release_id=release_id or uuid4(),
        pointer_version=7,
        barrier_generation=4,
        scope=SCOPE,
        sources=(
            RetrievalSourcePin(
                source_id=source_id,
                source_revision="synthetic-source-v1",
            ),
        ),
        effective_at=effective_at,
        freshness_expires_at=freshness_expires_at,
        index_generation_id=INDEX_GENERATION_ID,
        embedding_revision=embedding_revision,
        embedding_dimension=embedding_dimension,
        retriever_revision=retriever_revision,
        index_checksum="a" * 64,
        materialization_checksum="c" * 64,
        materialized_chunk_count=1,
    )


def resolution(active: RetrievalSnapshot) -> SnapshotResolution:
    return SnapshotResolution(
        status=SnapshotStatus.ACTIVE,
        snapshot=active,
        reason="ACTIVE_RELEASE_RESOLVED",
    )


def candidate(
    active: RetrievalSnapshot,
    *,
    excerpt: str,
    embedding: tuple[float, ...],
    chunk_id: UUID | None = None,
    release_id: UUID | None = None,
    source_id: UUID | None = None,
    acl_namespace: str | None = None,
    source_revision: str | None = None,
    embedding_revision: str | None = None,
) -> RetrievalCandidate:
    resolved_source = source_id or active.source_ids[0]
    return RetrievalCandidate(
        chunk_id=chunk_id or uuid4(),
        release_id=release_id or active.release_id,
        source_id=resolved_source,
        acl_namespace=acl_namespace or SCOPE.acl_namespace,
        source_uri="https://example.test/synthetic/source",
        source_revision=source_revision
        or active.source_revision_for(resolved_source)
        or "synthetic-source-v1",
        title="Synthetic approved source",
        excerpt=excerpt,
        content_checksum="b" * 64,
        index_generation_id=active.index_generation_id,
        embedding_revision=embedding_revision or active.embedding_revision,
        embedding=embedding,
    )


def service(
    reader: MemorySnapshotReader,
    embedder: DeterministicEmbedder | None = None,
    *,
    reranker: DeterministicReranker | None = None,
    max_rerank_candidates: int = 40,
    max_results: int = 8,
) -> KnowledgeRetrievalService:
    return KnowledgeRetrievalService(
        reader,
        reader,
        embedder or DeterministicEmbedder(),
        reranker=reranker,
        max_rerank_candidates=max_rerank_candidates,
        max_results=max_results,
        clock=lambda: NOW,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("snapshot_status", "expected_status", "reason"),
    [
        (
            SnapshotStatus.UPDATING,
            RetrievalStatus.KNOWLEDGE_UPDATING,
            "KNOWLEDGE_REVISION_SYNCING",
        ),
        (
            SnapshotStatus.BLOCKED,
            RetrievalStatus.KNOWLEDGE_UNAVAILABLE,
            "KNOWLEDGE_REVISION_BLOCKED",
        ),
        (
            SnapshotStatus.MISSING,
            RetrievalStatus.NO_APPROVED_EVIDENCE,
            "NO_ACTIVE_RELEASE",
        ),
    ],
)
async def test_maps_non_active_snapshot_to_typed_fail_closed_outcome(
    snapshot_status: SnapshotStatus,
    expected_status: RetrievalStatus,
    reason: str,
) -> None:
    reader = MemorySnapshotReader(SnapshotResolution(status=snapshot_status, reason=reason))

    result = await service(reader).retrieve(
        query="synthetic question",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace}),
    )

    assert result.status is expected_status
    assert result.reason == reason
    assert result.evidence == ()


@pytest.mark.asyncio
async def test_denies_scope_before_snapshot_or_embedding_work() -> None:
    active = snapshot()
    reader = MemorySnapshotReader(resolution(active))
    embedder = DeterministicEmbedder()

    result = await service(reader, embedder).retrieve(
        query="synthetic question",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({"public_customer:other:vi-VN"}),
    )

    assert result.status is RetrievalStatus.KNOWLEDGE_UNAVAILABLE
    assert result.reason == "ACL_SCOPE_DENIED"
    assert embedder.queries == []
    assert reader.received_acl is None


@pytest.mark.asyncio
async def test_rejects_stale_or_future_active_release_without_ranking() -> None:
    stale = snapshot(freshness_expires_at=NOW)
    stale_reader = MemorySnapshotReader(resolution(stale))
    future = snapshot(effective_at=NOW + timedelta(seconds=1))
    future_reader = MemorySnapshotReader(resolution(future))

    stale_result = await service(stale_reader).retrieve(
        query="synthetic",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace}),
    )
    future_result = await service(future_reader).retrieve(
        query="synthetic",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace}),
    )

    assert stale_result.status is RetrievalStatus.KNOWLEDGE_UNAVAILABLE
    assert stale_result.reason == "ACTIVE_RELEASE_STALE"
    assert future_result.status is RetrievalStatus.NO_APPROVED_EVIDENCE
    assert future_result.reason == "NOT_EFFECTIVE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("active", "embedder", "expected_reason"),
    [
        (
            snapshot(embedding_dimension=4),
            DeterministicEmbedder(),
            "EMBEDDING_RUNTIME_MISMATCH",
        ),
        (
            snapshot(embedding_revision="synthetic-embed-v2"),
            DeterministicEmbedder(),
            "EMBEDDING_RUNTIME_MISMATCH",
        ),
        (
            snapshot(),
            DeterministicEmbedder(vector=(0.0, 0.0, 0.0)),
            "INVALID_QUERY_EMBEDDING",
        ),
    ],
)
async def test_rejects_embedding_revision_dimension_or_vector_mismatch(
    active: RetrievalSnapshot,
    embedder: DeterministicEmbedder,
    expected_reason: str,
) -> None:
    result = await service(MemorySnapshotReader(resolution(active)), embedder).retrieve(
        query="synthetic",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace}),
    )

    assert result.status is RetrievalStatus.KNOWLEDGE_UNAVAILABLE
    assert result.reason == expected_reason


@pytest.mark.asyncio
async def test_filters_candidate_and_active_release_mismatches_before_ranking() -> None:
    active = snapshot()
    other_source = uuid4()
    candidates = (
        candidate(
            active,
            excerpt="perfect synthetic match",
            embedding=(1.0, 0.0, 0.0),
            release_id=uuid4(),
        ),
        candidate(
            active,
            excerpt="perfect synthetic match",
            embedding=(1.0, 0.0, 0.0),
            source_id=other_source,
        ),
        candidate(
            active,
            excerpt="perfect synthetic match",
            embedding=(1.0, 0.0, 0.0),
            acl_namespace="public_customer:other:vi-VN",
        ),
        candidate(
            active,
            excerpt="perfect synthetic match",
            embedding=(1.0, 0.0, 0.0),
            source_revision="candidate-source-v2",
        ),
    )
    reader = MemorySnapshotReader(resolution(active), candidates)

    result = await service(reader).retrieve(
        query="perfect synthetic match",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace, "public_customer:other:vi-VN"}),
    )

    assert result.status is RetrievalStatus.NO_APPROVED_EVIDENCE
    assert result.reason == "NO_MATCHING_EVIDENCE"
    assert reader.received_acl is not None


@pytest.mark.asyncio
async def test_hybrid_ranking_is_deterministic_and_pins_citation_to_release() -> None:
    active = snapshot()
    lexical = candidate(
        active,
        excerpt="alpha beta synthetic policy",
        embedding=(0.0, 1.0, 0.0),
        chunk_id=UUID("00000000-0000-0000-0000-000000000002"),
    )
    semantic = candidate(
        active,
        excerpt="unrelated words",
        embedding=(1.0, 0.0, 0.0),
        chunk_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
    reader = MemorySnapshotReader(resolution(active), (lexical, semantic))

    result = await service(reader).retrieve(
        query="alpha beta",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace}),
    )

    assert result.status is RetrievalStatus.EVIDENCE
    assert result.release_id == active.release_id
    assert result.pointer_version == active.pointer_version
    assert len(result.evidence) == 2
    assert result.evidence[0].release_id == active.release_id
    assert result.evidence[0].source_revision == "synthetic-source-v1"
    assert result.evidence[0].freshness == active.freshness_expires_at
    assert result.evidence[0].score >= result.evidence[1].score
    assert all(len(item.evidence_id) == 64 for item in result.evidence)
    assert reader.received_query is not None
    assert reader.received_query.normalized_text == "alpha beta"
    assert reader.received_query.embedding == (1.0, 0.0, 0.0)
    assert reader.received_query.lexical_weight == 0.35


@pytest.mark.asyncio
async def test_reranker_is_bounded_and_can_reorder_only_eligible_candidates() -> None:
    active = snapshot()
    first = candidate(
        active,
        excerpt="first eligible result",
        embedding=(1.0, 0.0, 0.0),
        chunk_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
    second = candidate(
        active,
        excerpt="second eligible result",
        embedding=(1.0, 0.0, 0.0),
        chunk_id=UUID("00000000-0000-0000-0000-000000000002"),
    )
    third = candidate(
        active,
        excerpt="third result outside rerank window",
        embedding=(1.0, 0.0, 0.0),
        chunk_id=UUID("00000000-0000-0000-0000-000000000003"),
    )
    reranker = DeterministicReranker(scores={first.chunk_id: 0.1, second.chunk_id: 0.9})

    result = await service(
        MemorySnapshotReader(resolution(active), (first, second, third)),
        reranker=reranker,
        max_rerank_candidates=2,
        max_results=2,
    ).retrieve(
        query="eligible result",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace}),
    )

    assert len(reranker.received) == 2
    assert result.status is RetrievalStatus.EVIDENCE
    assert result.evidence[0].excerpt == second.excerpt
    assert result.evidence[0].score == 0.9


@pytest.mark.asyncio
async def test_reranker_revision_outage_or_foreign_chunk_fails_closed() -> None:
    active = snapshot()
    approved = candidate(
        active,
        excerpt="approved result",
        embedding=(1.0, 0.0, 0.0),
    )
    foreign = uuid4()

    mismatch = await service(
        MemorySnapshotReader(resolution(active), (approved,)),
        reranker=DeterministicReranker(
            scores={approved.chunk_id: 0.9},
            retriever_revision="hybrid-v2",
        ),
    ).retrieve(
        query="approved",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace}),
    )
    malformed = await service(
        MemorySnapshotReader(resolution(active), (approved,)),
        reranker=DeterministicReranker(scores={foreign: 0.9}),
    ).retrieve(
        query="approved",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace}),
    )
    unavailable = await service(
        MemorySnapshotReader(resolution(active), (approved,)),
        reranker=DeterministicReranker(
            scores={approved.chunk_id: 0.9},
            unavailable=True,
        ),
    ).retrieve(
        query="approved",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace}),
    )

    assert mismatch.reason == "RERANKER_RUNTIME_MISMATCH"
    assert malformed.reason == "INVALID_RERANK_RESULT"
    assert unavailable.reason == "RERANKER_RUNTIME_UNAVAILABLE"
    assert {mismatch.status, malformed.status, unavailable.status} == {
        RetrievalStatus.KNOWLEDGE_UNAVAILABLE
    }


@pytest.mark.asyncio
async def test_backend_outages_return_typed_unavailable_outcomes() -> None:
    active = snapshot()
    snapshot_outage = MemorySnapshotReader(
        resolution(active),
        unavailable_on_resolve=True,
    )
    index_outage = MemorySnapshotReader(
        resolution(active),
        unavailable_on_candidates=True,
    )
    embedder_outage = DeterministicEmbedder(unavailable=True)

    first = await service(snapshot_outage).retrieve(
        query="synthetic",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace}),
    )
    second = await service(index_outage).retrieve(
        query="synthetic",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace}),
    )
    third = await service(
        MemorySnapshotReader(resolution(active)),
        embedder_outage,
    ).retrieve(
        query="synthetic",
        scope=SCOPE,
        authorized_acl_namespaces=frozenset({SCOPE.acl_namespace}),
    )

    assert first.reason == "SNAPSHOT_STORE_UNAVAILABLE"
    assert second.reason == "INDEX_UNAVAILABLE"
    assert third.reason == "EMBEDDING_RUNTIME_UNAVAILABLE"
    assert {first.status, second.status, third.status} == {RetrievalStatus.KNOWLEDGE_UNAVAILABLE}


@pytest.mark.parametrize(
    "unsafe_uri",
    [
        "https://example.test/source?X-Goog-Signature=secret",
        "https://example.test/source#access-token",
        "https://user:password@example.test/source",
        "gs://private-bucket/source.pdf",
    ],
)
def test_candidate_rejects_signed_tokenized_or_private_citation_uri(
    unsafe_uri: str,
) -> None:
    active = snapshot()

    with pytest.raises(ValidationError, match="citation URI"):
        RetrievalCandidate(
            chunk_id=uuid4(),
            release_id=active.release_id,
            source_id=active.source_ids[0],
            acl_namespace=SCOPE.acl_namespace,
            source_uri=unsafe_uri,
            source_revision="synthetic-source-v1",
            title="Synthetic source",
            excerpt="Synthetic evidence",
            content_checksum="b" * 64,
            index_generation_id=active.index_generation_id,
            embedding_revision=active.embedding_revision,
            embedding=(1.0, 0.0, 0.0),
        )
