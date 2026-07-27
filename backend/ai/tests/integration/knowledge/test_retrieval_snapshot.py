import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, update

from app.modules.knowledge.application import KnowledgeRetrievalService
from app.modules.knowledge.domain import (
    CandidateChunkMaterialization,
    KnowledgeScope,
    RetrievalStatus,
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
    materialization_checksum,
)
from app.modules.knowledge.infrastructure.postgres_retrieval import (
    PostgresRetrievalSnapshotReader,
)
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


@dataclass(frozen=True)
class IntegrationEmbedder:
    revision: str = "synthetic-embed-1536-v1"
    dimension: int = 1536

    async def embed_query(self, query: str) -> tuple[float, ...]:
        assert query == "approved active evidence"
        return (1.0, *([0.0] * 1535))


@pytest.mark.asyncio
async def test_postgres_retrieval_reads_only_active_release_acl_materialization() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    source_id = uuid4()
    release_id = uuid4()
    candidate_release_id = uuid4()
    generation_id = uuid4()
    candidate_generation_id = uuid4()
    chunk_ids = (
        UUID(int=(1 << 128) - 1),
        UUID(int=(1 << 128) - 2),
        UUID(int=(1 << 128) - 3),
        *(UUID(int=value) for value in range(1, 206)),
    )
    now = datetime.now(UTC)
    scope = KnowledgeScope(
        domain=f"synthetic-retrieval-{source_id.hex}",
        locale="vi-VN",
        assistant_profile="public_customer",
        acl_namespace=f"public_customer:synthetic-{source_id.hex}:vi-VN",
    )
    try:
        active_chunks = (
            CandidateChunkMaterialization(
                chunk_id=chunk_ids[0],
                chunk_key="chunk-active",
                content_checksum=chunk_ids[0].hex.ljust(64, "0"),
                redacted_text="approved active evidence",
                embedding=(1.0, *([0.0] * 1535)),
            ),
            CandidateChunkMaterialization(
                chunk_id=chunk_ids[2],
                chunk_key="chunk-cross-acl",
                content_checksum=chunk_ids[2].hex.ljust(64, "0"),
                redacted_text="cross namespace evidence must stay isolated",
                embedding=(1.0, *([0.0] * 1535)),
            ),
            *(
                CandidateChunkMaterialization(
                    chunk_id=chunk_id,
                    chunk_key=f"chunk-decoy-{index}",
                    content_checksum=chunk_id.hex.ljust(64, "0"),
                    redacted_text=f"unrelated decoy material {index}",
                    embedding=(0.0, 1.0, *([0.0] * 1534)),
                )
                for index, chunk_id in enumerate(chunk_ids[3:], start=1)
            ),
        )
        async with sessions() as session, session.begin():
            session.add(
                EmbeddingIndexGenerationRecord(
                    id=generation_id,
                    generation_key=f"synthetic-retrieval:{generation_id}",
                    embedding_revision="synthetic-embed-1536-v1",
                    embedding_dimension=1536,
                    distance_metric="cosine",
                    normalization="l2",
                    instruction_digest="1" * 64,
                    tokenizer_digest="2" * 64,
                    lifecycle="ready",
                )
            )
            session.add(
                EmbeddingIndexGenerationRecord(
                    id=candidate_generation_id,
                    generation_key=f"synthetic-retrieval-candidate:{candidate_generation_id}",
                    embedding_revision="synthetic-embed-1536-v2",
                    embedding_dimension=1536,
                    distance_metric="cosine",
                    normalization="l2",
                    instruction_digest="3" * 64,
                    tokenizer_digest="4" * 64,
                    lifecycle="building",
                )
            )
            session.add(
                KnowledgeSource(
                    id=source_id,
                    uri="urn:vfbiz:synthetic:retrieval-source",
                    title="Synthetic retrieval source",
                    classification="public",
                    checksum="a" * 64,
                    source_revision="synthetic-source-v1",
                    status="approved",
                    effective_at=now - timedelta(minutes=1),
                    canonical_source_id=f"synthetic-retrieval-{source_id.hex}",
                    deletion_fenced=False,
                )
            )
            await session.flush()
            for current_release_id in (release_id, candidate_release_id):
                session.add(
                    KnowledgeReleaseRecord(
                        id=current_release_id,
                        domain=scope.domain,
                        locale=scope.locale,
                        assistant_profile=scope.assistant_profile,
                        acl_namespace=scope.acl_namespace,
                        status="candidate",
                        criticality="non_critical",
                        source_set_hash="b" * 64,
                        manifest_hash="c" * 64,
                        transform_revision="synthetic-transform-v1",
                        chunking_revision="synthetic-chunk-v1",
                        index_generation_id=(
                            generation_id
                            if current_release_id == release_id
                            else candidate_generation_id
                        ),
                        embedding_revision=(
                            "synthetic-embed-1536-v1"
                            if current_release_id == release_id
                            else "synthetic-embed-1536-v2"
                        ),
                        embedding_dimension=1536,
                        retriever_revision="hybrid-v1",
                        policy_revision="synthetic-policy-v1",
                        index_checksum="d" * 64,
                        proposer_ref="synthetic-maker",
                        approver_ref="synthetic-checker",
                        effective_at=now - timedelta(minutes=1),
                        freshness_expires_at=now + timedelta(hours=1),
                        barrier_generation=1,
                        version=3,
                    )
                )
            await session.flush()
            for current_release_id in (release_id, candidate_release_id):
                session.add(
                    KnowledgeReleaseSource(
                        release_id=current_release_id,
                        source_id=source_id,
                        source_revision="synthetic-source-v1",
                        checksum_sha256="a" * 64,
                        registry_document_hash="e" * 64,
                        source_snapshot_hash="f" * 64,
                        snapshot={"source_id": f"synthetic-retrieval-{source_id.hex}"},
                    )
                )
            await session.flush()
            for chunk_id, materialized_release, namespace, chunk_key, excerpt in (
                (
                    chunk_ids[0],
                    release_id,
                    scope.acl_namespace,
                    "chunk-active",
                    "approved active evidence",
                ),
                (
                    chunk_ids[1],
                    release_id,
                    scope.acl_namespace,
                    "chunk-foreign-generation",
                    "foreign generation evidence must stay isolated",
                ),
                (
                    chunk_ids[2],
                    release_id,
                    "public_customer:other:vi-VN",
                    "chunk-cross-acl",
                    "cross namespace evidence must stay isolated",
                ),
            ):
                session.add(
                    KnowledgeChunk(
                        id=chunk_id,
                        release_id=materialized_release,
                        source_id=source_id,
                        chunk_revision=chunk_key,
                        index_generation_id=(
                            candidate_generation_id if chunk_id == chunk_ids[1] else generation_id
                        ),
                        embedding_revision=(
                            "synthetic-embed-1536-v2"
                            if chunk_id == chunk_ids[1]
                            else "synthetic-embed-1536-v1"
                        ),
                        embedding_dimension=1536,
                        acl_namespace=namespace,
                        citation_uri="https://example.test/synthetic/retrieval",
                        citation_title="Synthetic retrieval fixture",
                        content_checksum=chunk_id.hex.ljust(64, "0"),
                        redacted_text=excerpt,
                        acl={"namespaces": [namespace]},
                        attributes={
                            "releaseId": str(
                                candidate_release_id
                                if chunk_id == chunk_ids[0]
                                else materialized_release
                            ),
                            "tamperedMetadataMustNotGrantAuthority": True,
                        },
                        embedding=[1.0, *([0.0] * 1535)],
                    )
                )
            for index, chunk_id in enumerate(chunk_ids[3:], start=1):
                session.add(
                    KnowledgeChunk(
                        id=chunk_id,
                        release_id=release_id,
                        source_id=source_id,
                        chunk_revision=f"chunk-decoy-{index}",
                        index_generation_id=generation_id,
                        embedding_revision="synthetic-embed-1536-v1",
                        embedding_dimension=1536,
                        acl_namespace=scope.acl_namespace,
                        citation_uri="https://example.test/synthetic/retrieval",
                        citation_title="Synthetic retrieval decoy",
                        content_checksum=chunk_id.hex.ljust(64, "0"),
                        redacted_text=f"unrelated decoy material {index}",
                        acl={"namespaces": [scope.acl_namespace]},
                        attributes={"syntheticDecoy": True},
                        embedding=[0.0, 1.0, *([0.0] * 1534)],
                    )
                )
        async with sessions() as session, session.begin():
            await session.execute(
                update(KnowledgeReleaseRecord)
                .where(KnowledgeReleaseRecord.id == release_id)
                .values(
                    status="active",
                    materialization_checksum=materialization_checksum(active_chunks),
                    materialized_chunk_count=len(active_chunks),
                )
            )
            session.add(
                KnowledgeRevisionPointer(
                    domain=scope.domain,
                    locale=scope.locale,
                    assistant_profile=scope.assistant_profile,
                    acl_namespace=scope.acl_namespace,
                    active_release_id=release_id,
                    candidate_release_id=None,
                    barrier_state="clear",
                    barrier_generation=1,
                    version=4,
                )
            )

        reader = PostgresRetrievalSnapshotReader(sessions)
        service = KnowledgeRetrievalService(
            reader,
            reader,
            IntegrationEmbedder(),
            clock=lambda: now,
        )
        result = await service.retrieve(
            query="approved active evidence",
            scope=scope,
            authorized_acl_namespaces=frozenset({scope.acl_namespace}),
        )

        assert result.status is RetrievalStatus.EVIDENCE
        assert result.release_id == release_id
        assert len(result.evidence) >= 1
        assert result.evidence[0].excerpt == "approved active evidence"
        assert result.evidence[0].source_revision == "synthetic-source-v1"
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                delete(KnowledgeRevisionPointer).where(
                    KnowledgeRevisionPointer.domain == scope.domain
                )
            )
            await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.id.in_(chunk_ids)))
            await session.execute(
                delete(KnowledgeReleaseSource).where(
                    KnowledgeReleaseSource.release_id.in_((release_id, candidate_release_id))
                )
            )
            await session.execute(
                delete(KnowledgeReleaseRecord).where(
                    KnowledgeReleaseRecord.id.in_((release_id, candidate_release_id))
                )
            )
            await session.execute(delete(KnowledgeSource).where(KnowledgeSource.id == source_id))
        await engine.dispose()
