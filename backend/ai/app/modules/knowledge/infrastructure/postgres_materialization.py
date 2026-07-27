import hashlib
from urllib.parse import urlsplit
from uuid import UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.knowledge.application.materialization_ports import (
    CandidateMaterializationRepository,
)
from app.modules.knowledge.domain import (
    CandidateChunkMaterialization,
    CandidateMaterializationRejected,
    CandidateMaterializationResult,
)
from app.modules.knowledge.infrastructure.models import (
    EmbeddingIndexGenerationRecord,
    KnowledgeChunk,
    KnowledgeReleaseRecord,
    KnowledgeReleaseSource,
    KnowledgeSource,
)


class PostgresCandidateMaterializationRepository(CandidateMaterializationRepository):
    """Atomically writes an immutable candidate index without changing release status."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def materialize(
        self,
        *,
        release_id: UUID,
        canonical_source_id: str,
        source_revision: str,
        source_snapshot_hash: str,
        index_generation_id: UUID,
        embedding_revision: str,
        embedding_dimension: int,
        acl_namespace: str,
        chunks: tuple[CandidateChunkMaterialization, ...],
    ) -> CandidateMaterializationResult:
        if not chunks or len(chunks) > 1_000:
            raise CandidateMaterializationRejected("MATERIALIZATION_BATCH_INVALID")
        if any(
            chunk.chunk_id != uuid5(release_id, f"{canonical_source_id}:{chunk.chunk_key}")
            for chunk in chunks
        ):
            raise CandidateMaterializationRejected("CHUNK_IDENTITY_INVALID")
        checksum = materialization_checksum(chunks)
        async with self._sessions() as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"knowledge-materialization:{release_id}"},
            )
            release = await session.scalar(
                select(KnowledgeReleaseRecord)
                .where(KnowledgeReleaseRecord.id == release_id)
                .with_for_update()
            )
            if release is None:
                raise CandidateMaterializationRejected("RELEASE_NOT_FOUND")
            generation = await session.get(EmbeddingIndexGenerationRecord, index_generation_id)
            if generation is None:
                raise CandidateMaterializationRejected("INDEX_GENERATION_NOT_FOUND")
            if generation.lifecycle not in {"building", "ready"}:
                raise CandidateMaterializationRejected("INDEX_GENERATION_NOT_WRITABLE")
            if (
                generation.embedding_revision != embedding_revision
                or generation.embedding_dimension != embedding_dimension
            ):
                raise CandidateMaterializationRejected("INDEX_GENERATION_CONTRACT_MISMATCH")
            if release.status not in {"candidate", "evaluated", "ready"}:
                raise CandidateMaterializationRejected("RELEASE_NOT_MATERIALIZABLE")
            if (
                release.index_generation_id != index_generation_id
                or release.embedding_revision != embedding_revision
                or release.embedding_dimension != embedding_dimension
                or release.acl_namespace != acl_namespace
            ):
                raise CandidateMaterializationRejected("RELEASE_INDEX_CONTRACT_MISMATCH")
            source_row = await session.execute(
                select(KnowledgeReleaseSource, KnowledgeSource)
                .join(KnowledgeSource, KnowledgeSource.id == KnowledgeReleaseSource.source_id)
                .where(
                    KnowledgeReleaseSource.release_id == release_id,
                    KnowledgeSource.canonical_source_id == canonical_source_id,
                )
            )
            membership = source_row.one_or_none()
            if membership is None:
                raise CandidateMaterializationRejected("RELEASE_SOURCE_MISMATCH")
            link, source = membership
            if (
                link.source_revision != source_revision
                or link.source_snapshot_hash != source_snapshot_hash
                or source.source_revision != source_revision
                or source.status != "approved"
                or source.deletion_fenced
                or source.acl_namespaces is None
                or acl_namespace not in source.acl_namespaces
            ):
                raise CandidateMaterializationRejected("SOURCE_MEMBERSHIP_STALE")
            _validate_citation(source.uri, source.title)

            existing_rows = (
                await session.scalars(
                    select(KnowledgeChunk).where(KnowledgeChunk.release_id == release_id)
                )
            ).all()
            persisted_membership = tuple((row.id, row.content_checksum) for row in existing_rows)
            if release.materialization_checksum is not None and (
                release.materialized_chunk_count != len(existing_rows)
                or membership_checksum(persisted_membership) != release.materialization_checksum
            ):
                raise CandidateMaterializationRejected("MATERIALIZATION_INTEGRITY_MISMATCH")
            source_rows = tuple(row for row in existing_rows if row.source_id == link.source_id)
            if source_rows:
                source_membership = tuple((row.id, row.content_checksum) for row in source_rows)
                if (
                    len(source_rows) != len(chunks)
                    or membership_checksum(source_membership) != checksum
                ):
                    raise CandidateMaterializationRejected("MATERIALIZATION_REPLAY_MISMATCH")
                return CandidateMaterializationResult(
                    release_id=release_id,
                    source_id=canonical_source_id,
                    embedding_revision=embedding_revision,
                    acl_namespace=acl_namespace,
                    materialized_count=0,
                    replayed_count=len(source_rows),
                )
            if release.status != "candidate":
                raise CandidateMaterializationRejected("RELEASE_MATERIALIZATION_CLOSED")
            incoming_ids = {chunk.chunk_id for chunk in chunks}
            if incoming_ids & {row.id for row in existing_rows}:
                raise CandidateMaterializationRejected("CHUNK_ID_COLLISION")
            for chunk in chunks:
                session.add(
                    KnowledgeChunk(
                        id=chunk.chunk_id,
                        release_id=release_id,
                        source_id=link.source_id,
                        chunk_revision=chunk.chunk_key,
                        index_generation_id=index_generation_id,
                        embedding_revision=embedding_revision,
                        embedding_dimension=embedding_dimension,
                        acl_namespace=acl_namespace,
                        citation_uri=source.uri,
                        citation_title=source.title,
                        content_checksum=chunk.content_checksum,
                        redacted_text=chunk.redacted_text,
                        acl={"namespaces": [acl_namespace]},
                        attributes={"materializationVersion": 1},
                        embedding=list(chunk.embedding),
                    )
                )
            aggregate_membership = persisted_membership + tuple(
                (chunk.chunk_id, chunk.content_checksum) for chunk in chunks
            )
            release.materialization_checksum = membership_checksum(aggregate_membership)
            release.materialized_chunk_count = len(aggregate_membership)
            await session.flush()
            return CandidateMaterializationResult(
                release_id=release_id,
                source_id=canonical_source_id,
                embedding_revision=embedding_revision,
                acl_namespace=acl_namespace,
                materialized_count=len(chunks),
                replayed_count=0,
            )


def materialization_checksum(
    chunks: tuple[CandidateChunkMaterialization, ...],
) -> str:
    return membership_checksum(tuple((chunk.chunk_id, chunk.content_checksum) for chunk in chunks))


def membership_checksum(entries: tuple[tuple[UUID, str], ...]) -> str:
    payload = "\n".join(
        f"{chunk_id.hex}:{content_checksum}"
        for chunk_id, content_checksum in sorted(entries, key=lambda item: item[0])
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _validate_citation(uri: str, title: str) -> None:
    parsed = urlsplit(uri)
    if (
        parsed.scheme not in {"https", "urn"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not title.strip()
    ):
        raise CandidateMaterializationRejected("SOURCE_CITATION_INVALID")
