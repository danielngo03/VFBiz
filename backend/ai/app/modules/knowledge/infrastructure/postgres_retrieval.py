from uuid import UUID

from sqlalchemy import Float, and_, cast, desc, func, literal_column, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.knowledge.application.retrieval_ports import (
    RetrievalBackendUnavailable,
    RetrievalCandidateSearcher,
    RetrievalSnapshotResolver,
)
from app.modules.knowledge.domain import KnowledgeScope
from app.modules.knowledge.domain.retrieval import (
    RetrievalCandidate,
    RetrievalCandidateQuery,
    RetrievalSnapshot,
    RetrievalSourcePin,
    SnapshotResolution,
    SnapshotStatus,
)
from app.modules.knowledge.infrastructure.models import (
    EmbeddingIndexGenerationRecord,
    KnowledgeChunk,
    KnowledgeReleaseRecord,
    KnowledgeReleaseSource,
    KnowledgeRevisionPointer,
    KnowledgeSource,
)
from app.modules.knowledge.infrastructure.postgres_materialization import (
    membership_checksum,
)


class PostgresRetrievalSnapshotReader(
    RetrievalSnapshotResolver,
    RetrievalCandidateSearcher,
):
    """Reads one active release and only chunks materialized for that exact release."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def resolve(self, scope: KnowledgeScope) -> SnapshotResolution:
        try:
            async with self._sessions() as session, session.begin():
                pointer = await session.scalar(
                    select(KnowledgeRevisionPointer).where(
                        KnowledgeRevisionPointer.domain == scope.domain,
                        KnowledgeRevisionPointer.locale == scope.locale,
                        KnowledgeRevisionPointer.assistant_profile == scope.assistant_profile,
                        KnowledgeRevisionPointer.acl_namespace == scope.acl_namespace,
                    )
                )
                if pointer is None:
                    return SnapshotResolution(
                        status=SnapshotStatus.MISSING,
                        reason="NO_ACTIVE_RELEASE",
                    )
                if pointer.barrier_state == "syncing":
                    return SnapshotResolution(
                        status=SnapshotStatus.UPDATING,
                        reason="KNOWLEDGE_REVISION_SYNCING",
                    )
                if pointer.barrier_state == "blocked":
                    return SnapshotResolution(
                        status=SnapshotStatus.BLOCKED,
                        reason="KNOWLEDGE_REVISION_BLOCKED",
                    )
                if pointer.active_release_id is None:
                    return SnapshotResolution(
                        status=SnapshotStatus.MISSING,
                        reason="NO_ACTIVE_RELEASE",
                    )
                release = await session.get(KnowledgeReleaseRecord, pointer.active_release_id)
                if release is None or release.status != "active":
                    return SnapshotResolution(
                        status=SnapshotStatus.BLOCKED,
                        reason="ACTIVE_POINTER_INCONSISTENT",
                    )
                if (
                    release.domain != scope.domain
                    or release.locale != scope.locale
                    or release.assistant_profile != scope.assistant_profile
                    or release.acl_namespace != scope.acl_namespace
                ):
                    return SnapshotResolution(
                        status=SnapshotStatus.BLOCKED,
                        reason="ACTIVE_SCOPE_INCONSISTENT",
                    )
                if release.index_generation_id is None:
                    return SnapshotResolution(
                        status=SnapshotStatus.BLOCKED,
                        reason="INDEX_GENERATION_MISSING",
                    )
                generation = await session.get(
                    EmbeddingIndexGenerationRecord, release.index_generation_id
                )
                if (
                    generation is None
                    or generation.lifecycle != "ready"
                    or generation.embedding_revision != release.embedding_revision
                    or generation.embedding_dimension != release.embedding_dimension
                ):
                    return SnapshotResolution(
                        status=SnapshotStatus.BLOCKED,
                        reason="INDEX_GENERATION_INCOMPATIBLE",
                    )
                if (
                    release.materialization_checksum is None
                    or release.materialized_chunk_count is None
                    or release.materialized_chunk_count <= 0
                ):
                    return SnapshotResolution(
                        status=SnapshotStatus.BLOCKED,
                        reason="ACTIVE_RELEASE_NOT_MATERIALIZED",
                    )
                materialized_rows = (
                    await session.execute(
                        select(
                            KnowledgeChunk.id,
                            KnowledgeChunk.content_checksum,
                            KnowledgeChunk.source_id,
                        ).where(
                            KnowledgeChunk.release_id == release.id,
                            KnowledgeChunk.index_generation_id == release.index_generation_id,
                            KnowledgeChunk.embedding_dimension == release.embedding_dimension,
                        )
                    )
                ).all()
                persisted_checksum = membership_checksum(
                    tuple(
                        (chunk_id, content_checksum)
                        for chunk_id, content_checksum, _ in materialized_rows
                    )
                )
                if (
                    len(materialized_rows) != release.materialized_chunk_count
                    or persisted_checksum != release.materialization_checksum
                ):
                    return SnapshotResolution(
                        status=SnapshotStatus.BLOCKED,
                        reason="ACTIVE_MATERIALIZATION_INTEGRITY_MISMATCH",
                    )
                links = (
                    await session.scalars(
                        select(KnowledgeReleaseSource)
                        .where(KnowledgeReleaseSource.release_id == release.id)
                        .order_by(KnowledgeReleaseSource.source_id)
                    )
                ).all()
                if not links:
                    return SnapshotResolution(
                        status=SnapshotStatus.BLOCKED,
                        reason="ACTIVE_RELEASE_HAS_NO_SOURCES",
                    )
                materialized_source_count = len(
                    {source_id for _, _, source_id in materialized_rows}
                )
                if materialized_source_count != len(links):
                    return SnapshotResolution(
                        status=SnapshotStatus.BLOCKED,
                        reason="ACTIVE_MATERIALIZATION_SOURCE_GAP",
                    )
                snapshot = RetrievalSnapshot(
                    release_id=release.id,
                    pointer_version=pointer.version,
                    barrier_generation=pointer.barrier_generation,
                    scope=scope,
                    sources=tuple(
                        RetrievalSourcePin(
                            source_id=link.source_id,
                            source_revision=link.source_revision,
                        )
                        for link in links
                    ),
                    effective_at=release.effective_at,
                    freshness_expires_at=release.freshness_expires_at,
                    index_generation_id=release.index_generation_id,
                    embedding_revision=release.embedding_revision,
                    embedding_dimension=release.embedding_dimension,
                    retriever_revision=release.retriever_revision,
                    index_checksum=release.index_checksum,
                    materialization_checksum=release.materialization_checksum,
                    materialized_chunk_count=release.materialized_chunk_count,
                )
                return SnapshotResolution(
                    status=SnapshotStatus.ACTIVE,
                    snapshot=snapshot,
                    reason="ACTIVE_RELEASE_RESOLVED",
                )
        except (SQLAlchemyError, ValueError) as error:
            raise RetrievalBackendUnavailable("knowledge snapshot read failed") from error

    async def search_candidates(
        self,
        snapshot: RetrievalSnapshot,
        *,
        authorized_acl_namespaces: frozenset[str],
        query: RetrievalCandidateQuery,
    ) -> tuple[RetrievalCandidate, ...]:
        allowed = authorized_acl_namespaces & {snapshot.scope.acl_namespace}
        if not allowed:
            return ()
        namespace = snapshot.scope.acl_namespace
        vector_distance = KnowledgeChunk.embedding.cosine_distance(list(query.embedding))
        vector_score = func.greatest(
            0.0,
            func.least(1.0, 1.0 - cast(vector_distance, Float) / 2.0),
        )
        lexical_score = func.least(
            1.0,
            func.ts_rank_cd(
                func.to_tsvector(
                    literal_column("'simple'"),
                    KnowledgeChunk.redacted_text,
                ),
                func.plainto_tsquery(
                    literal_column("'simple'"),
                    query.normalized_text,
                ),
            ),
        )
        hybrid_score = (
            query.lexical_weight * lexical_score + (1.0 - query.lexical_weight) * vector_score
        )
        try:
            async with self._sessions() as session:
                rows = (
                    await session.execute(
                        select(
                            KnowledgeChunk,
                            KnowledgeSource,
                            KnowledgeReleaseSource,
                        )
                        .join(
                            KnowledgeReleaseSource,
                            KnowledgeReleaseSource.source_id == KnowledgeChunk.source_id,
                        )
                        .join(
                            KnowledgeReleaseRecord,
                            KnowledgeReleaseRecord.id == KnowledgeReleaseSource.release_id,
                        )
                        .join(
                            KnowledgeRevisionPointer,
                            and_(
                                KnowledgeRevisionPointer.active_release_id
                                == KnowledgeReleaseRecord.id,
                                KnowledgeRevisionPointer.domain == snapshot.scope.domain,
                                KnowledgeRevisionPointer.locale == snapshot.scope.locale,
                                KnowledgeRevisionPointer.assistant_profile
                                == snapshot.scope.assistant_profile,
                                KnowledgeRevisionPointer.acl_namespace
                                == snapshot.scope.acl_namespace,
                            ),
                        )
                        .join(KnowledgeSource, KnowledgeSource.id == KnowledgeChunk.source_id)
                        .where(
                            KnowledgeReleaseSource.release_id == snapshot.release_id,
                            KnowledgeReleaseRecord.status == "active",
                            KnowledgeReleaseRecord.materialization_checksum
                            == snapshot.materialization_checksum,
                            KnowledgeReleaseRecord.materialized_chunk_count
                            == snapshot.materialized_chunk_count,
                            KnowledgeRevisionPointer.version == snapshot.pointer_version,
                            KnowledgeRevisionPointer.barrier_generation
                            == snapshot.barrier_generation,
                            KnowledgeRevisionPointer.barrier_state == "clear",
                            KnowledgeChunk.source_id.in_(snapshot.source_ids),
                            KnowledgeChunk.release_id == snapshot.release_id,
                            KnowledgeChunk.index_generation_id == snapshot.index_generation_id,
                            KnowledgeChunk.acl_namespace == namespace,
                            KnowledgeChunk.embedding_revision == snapshot.embedding_revision,
                            KnowledgeChunk.embedding_dimension == snapshot.embedding_dimension,
                            KnowledgeSource.status == "approved",
                            KnowledgeSource.deletion_fenced.is_(False),
                            KnowledgeSource.source_revision
                            == KnowledgeReleaseSource.source_revision,
                        )
                        .order_by(desc(hybrid_score), KnowledgeChunk.id)
                        .limit(query.candidate_limit)
                    )
                ).all()
                return tuple(
                    _candidate_from_row(
                        chunk,
                        source,
                        link,
                        release_id=snapshot.release_id,
                        acl_namespace=namespace,
                        index_generation_id=snapshot.index_generation_id,
                        embedding_revision=snapshot.embedding_revision,
                    )
                    for chunk, source, link in rows
                )
        except (SQLAlchemyError, ValueError, TypeError) as error:
            raise RetrievalBackendUnavailable("knowledge candidate read failed") from error


def _candidate_from_row(
    chunk: KnowledgeChunk,
    source: KnowledgeSource,
    link: KnowledgeReleaseSource,
    *,
    release_id: UUID,
    acl_namespace: str,
    index_generation_id: UUID,
    embedding_revision: str,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=chunk.id,
        release_id=release_id,
        source_id=source.id,
        acl_namespace=acl_namespace,
        source_uri=chunk.citation_uri,
        source_revision=link.source_revision,
        title=chunk.citation_title,
        excerpt=chunk.redacted_text,
        content_checksum=chunk.content_checksum,
        index_generation_id=index_generation_id,
        embedding_revision=embedding_revision,
        embedding=tuple(float(value) for value in chunk.embedding),
    )
