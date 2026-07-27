import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4, uuid5

import pytest
from sqlalchemy import delete, update

from app.modules.knowledge.domain import (
    CandidateChunkMaterialization,
    CandidateMaterializationRejected,
)
from app.modules.knowledge.infrastructure.models import (
    EmbeddingIndexGenerationRecord,
    KnowledgeChunk,
    KnowledgeReleaseRecord,
    KnowledgeReleaseSource,
    KnowledgeSource,
)
from app.modules.knowledge.infrastructure.postgres_materialization import (
    PostgresCandidateMaterializationRepository,
)
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


@pytest.mark.asyncio
async def test_candidate_materialization_is_atomic_idempotent_and_state_fenced() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    source_id = uuid4()
    release_id = uuid4()
    generation_id = uuid4()
    canonical_source_id = f"synthetic-materialize-{source_id.hex}"
    acl_namespace = f"public_customer:synthetic-{source_id.hex}:vi-VN"
    now = datetime.now(UTC)
    chunk = CandidateChunkMaterialization(
        chunk_id=uuid5(release_id, f"{canonical_source_id}:chunk-1"),
        chunk_key="chunk-1",
        content_checksum="a" * 64,
        redacted_text="Synthetic candidate evidence.",
        embedding=(1.0, 0.0, 0.0),
    )
    try:
        async with sessions() as session, session.begin():
            session.add(
                EmbeddingIndexGenerationRecord(
                    id=generation_id,
                    generation_key=f"synthetic-materialize:{generation_id}",
                    embedding_revision="synthetic-embed-3-v1",
                    embedding_dimension=3,
                    distance_metric="cosine",
                    normalization="l2",
                    instruction_digest="1" * 64,
                    tokenizer_digest="2" * 64,
                    lifecycle="building",
                )
            )
            session.add(
                KnowledgeSource(
                    id=source_id,
                    uri="https://example.test/synthetic/materialization",
                    title="Synthetic materialization source",
                    classification="public",
                    checksum="b" * 64,
                    source_revision="synthetic-source-v1",
                    status="approved",
                    effective_at=now,
                    canonical_source_id=canonical_source_id,
                    acl_namespaces=[acl_namespace],
                    deletion_fenced=False,
                )
            )
            session.add(
                KnowledgeReleaseRecord(
                    id=release_id,
                    domain=f"synthetic-{source_id.hex}",
                    locale="vi-VN",
                    assistant_profile="public_customer",
                    acl_namespace=acl_namespace,
                    status="candidate",
                    criticality="non_critical",
                    source_set_hash="c" * 64,
                    manifest_hash="d" * 64,
                    transform_revision="synthetic-transform-v1",
                    chunking_revision="synthetic-chunk-v1",
                    index_generation_id=generation_id,
                    embedding_revision="synthetic-embed-3-v1",
                    embedding_dimension=3,
                    retriever_revision="hybrid-v1",
                    policy_revision="synthetic-policy-v1",
                    index_checksum="e" * 64,
                    proposer_ref="synthetic-maker",
                    effective_at=now,
                    freshness_expires_at=now + timedelta(days=1),
                    barrier_generation=0,
                    version=1,
                )
            )
            await session.flush()
            session.add(
                KnowledgeReleaseSource(
                    release_id=release_id,
                    source_id=source_id,
                    source_revision="synthetic-source-v1",
                    checksum_sha256="b" * 64,
                    registry_document_hash="f" * 64,
                    source_snapshot_hash="0" * 64,
                    snapshot={"source_id": canonical_source_id},
                )
            )

        repository = PostgresCandidateMaterializationRepository(sessions)
        first = await repository.materialize(
            release_id=release_id,
            canonical_source_id=canonical_source_id,
            source_revision="synthetic-source-v1",
            source_snapshot_hash="0" * 64,
            index_generation_id=generation_id,
            embedding_revision="synthetic-embed-3-v1",
            embedding_dimension=3,
            acl_namespace=acl_namespace,
            chunks=(chunk,),
        )
        replay = await repository.materialize(
            release_id=release_id,
            canonical_source_id=canonical_source_id,
            source_revision="synthetic-source-v1",
            source_snapshot_hash="0" * 64,
            index_generation_id=generation_id,
            embedding_revision="synthetic-embed-3-v1",
            embedding_dimension=3,
            acl_namespace=acl_namespace,
            chunks=(chunk,),
        )

        assert first.materialized_count == 1
        assert replay.replayed_count == 1

        mismatched = chunk.model_copy(update={"content_checksum": "9" * 64})
        with pytest.raises(
            CandidateMaterializationRejected,
            match="MATERIALIZATION_REPLAY_MISMATCH",
        ):
            await repository.materialize(
                release_id=release_id,
                canonical_source_id=canonical_source_id,
                source_revision="synthetic-source-v1",
                source_snapshot_hash="0" * 64,
                index_generation_id=generation_id,
                embedding_revision="synthetic-embed-3-v1",
                embedding_dimension=3,
                acl_namespace=acl_namespace,
                chunks=(mismatched,),
            )

        async with sessions() as session, session.begin():
            await session.execute(
                update(KnowledgeReleaseRecord)
                .where(KnowledgeReleaseRecord.id == release_id)
                .values(status="active")
            )
        with pytest.raises(
            CandidateMaterializationRejected,
            match="RELEASE_NOT_MATERIALIZABLE",
        ):
            await repository.materialize(
                release_id=release_id,
                canonical_source_id=canonical_source_id,
                source_revision="synthetic-source-v1",
                source_snapshot_hash="0" * 64,
                index_generation_id=generation_id,
                embedding_revision="synthetic-embed-3-v1",
                embedding_dimension=3,
                acl_namespace=acl_namespace,
                chunks=(chunk,),
            )
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.release_id == release_id)
            )
            await session.execute(
                delete(KnowledgeReleaseSource).where(
                    KnowledgeReleaseSource.release_id == release_id
                )
            )
            await session.execute(
                delete(KnowledgeReleaseRecord).where(KnowledgeReleaseRecord.id == release_id)
            )
            await session.execute(delete(KnowledgeSource).where(KnowledgeSource.id == source_id))
        await engine.dispose()
