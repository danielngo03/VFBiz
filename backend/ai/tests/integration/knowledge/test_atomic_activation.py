import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.knowledge.application import (
    CreateKnowledgeCandidate,
    KnowledgeReleaseService,
)
from app.modules.knowledge.domain import (
    CandidateChunkMaterialization,
    KnowledgeActor,
    KnowledgeConcurrencyConflict,
    KnowledgeScope,
)
from app.modules.knowledge.infrastructure.models import (
    EmbeddingIndexGenerationRecord,
    KnowledgeChunk,
    KnowledgeReleaseOutbox,
    KnowledgeReleaseRecord,
    KnowledgeReleaseSource,
    KnowledgeRevisionPointer,
    KnowledgeSource,
)
from app.modules.knowledge.infrastructure.postgres import (
    PostgresKnowledgeReleaseRepository,
    PostgresSourceRegisterReader,
)
from app.modules.knowledge.infrastructure.postgres_materialization import (
    materialization_checksum,
)
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


def actor(capability: str, actor_ref: str) -> KnowledgeActor:
    return KnowledgeActor(
        actor_ref=actor_ref,
        kind="human",
        capability=capability,
        entitlement_revision="integration-v1",
        mfa_verified=True,
    )


async def mark_synthetic_index_materialized(
    sessions: async_sessionmaker[AsyncSession],
    release_id: UUID,
) -> None:
    async with sessions() as session, session.begin():
        link = await session.scalar(
            select(KnowledgeReleaseSource).where(KnowledgeReleaseSource.release_id == release_id)
        )
        assert link is not None
        release = await session.get(KnowledgeReleaseRecord, release_id)
        assert release is not None
        assert release.index_generation_id is not None
        chunk = CandidateChunkMaterialization(
            chunk_id=uuid5(release_id, "synthetic-activation-chunk"),
            chunk_key="synthetic-activation-chunk",
            content_checksum="1" * 64,
            redacted_text="Synthetic activation evidence.",
            embedding=(1.0, *([0.0] * 1535)),
        )
        session.add(
            KnowledgeChunk(
                id=chunk.chunk_id,
                release_id=release_id,
                source_id=link.source_id,
                chunk_revision=chunk.chunk_key,
                index_generation_id=release.index_generation_id,
                embedding_revision="embed-v1",
                embedding_dimension=1536,
                acl_namespace="public_customer:integration-warranty:vi-VN",
                citation_uri="urn:vfbiz:synthetic:activation-source",
                citation_title="Synthetic activation source",
                content_checksum=chunk.content_checksum,
                redacted_text=chunk.redacted_text,
                acl={"namespaces": ["public_customer:integration-warranty:vi-VN"]},
                attributes={"materializationVersion": 1},
                embedding=list(chunk.embedding),
            )
        )
        await session.execute(
            update(KnowledgeReleaseRecord)
            .where(KnowledgeReleaseRecord.id == release_id)
            .values(
                materialization_checksum=materialization_checksum((chunk,)),
                materialized_chunk_count=1,
            )
        )


async def replace_materialized_chunk_without_manifest_update(
    sessions: async_sessionmaker[AsyncSession],
    release_id: UUID,
) -> None:
    """Simulate a privileged out-of-band delete/insert that preserves row count."""
    async with sessions() as session, session.begin():
        original = await session.scalar(
            select(KnowledgeChunk).where(KnowledgeChunk.release_id == release_id)
        )
        assert original is not None
        await session.delete(original)
        await session.flush()
        session.add(
            KnowledgeChunk(
                id=uuid4(),
                release_id=release_id,
                source_id=original.source_id,
                chunk_revision=original.chunk_revision,
                index_generation_id=original.index_generation_id,
                embedding_revision=original.embedding_revision,
                embedding_dimension=original.embedding_dimension,
                acl_namespace=original.acl_namespace,
                citation_uri=original.citation_uri,
                citation_title=original.citation_title,
                content_checksum="2" * 64,
                redacted_text="Tampered replacement with unchanged row count.",
                acl=original.acl,
                attributes={"materializationVersion": 1, "tampered": True},
                embedding=list(original.embedding),
            )
        )


@pytest.mark.asyncio
async def test_two_activation_attempts_have_exactly_one_cas_winner() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    source_uuid = uuid4()
    generation_id = uuid4()
    release_ids: list[UUID] = []
    source_key = f"integration-source-{source_uuid.hex}"
    now = datetime.now(UTC)
    scope = KnowledgeScope(
        domain="integration-warranty",
        locale="vi-VN",
        assistant_profile="public_customer",
        acl_namespace="public_customer:integration-warranty:vi-VN",
    )
    try:
        async with sessions() as session, session.begin():
            session.add(
                EmbeddingIndexGenerationRecord(
                    id=generation_id,
                    generation_key=f"integration-activation:{generation_id}",
                    embedding_revision="embed-v1",
                    embedding_dimension=1536,
                    distance_metric="cosine",
                    normalization="l2",
                    instruction_digest="1" * 64,
                    tokenizer_digest="2" * 64,
                    lifecycle="ready",
                )
            )
            session.add(
                KnowledgeSource(
                    id=source_uuid,
                    uri=f"urn:vfbiz:{source_key}",
                    title="Synthetic integration source",
                    classification="public",
                    checksum="a" * 64,
                    source_revision="revision-1",
                    status="approved",
                    effective_at=now,
                    canonical_source_id=source_key,
                    version="v1",
                    source_type="synthetic",
                    locator_ref=f"objects/{source_key}",
                    approved_purposes=["knowledge"],
                    acl_namespaces=[scope.acl_namespace],
                    rights={
                        "license_id": "LicenseRef-Integration-1",
                        "commercial_use": "permitted",
                        "derivatives": "permitted",
                        "redistribution": "prohibited",
                        "access_conditions": "Synthetic integration test only",
                        "evidence_urls": ["urn:vfbiz:evidence:integration-rights"],
                        "legal_review": "approved",
                    },
                    retention={"policy_id": "integration-1d", "duration_days": 1},
                    deletion_method="test-delete",
                    owner_role="data-owner",
                    custodian_role="data-steward",
                    approval_evidence=["b" * 64],
                    review_date=now + timedelta(days=1),
                    registry_document_hash="c" * 64,
                    deletion_fenced=False,
                )
            )
        service = KnowledgeReleaseService(
            PostgresSourceRegisterReader(sessions),
            PostgresKnowledgeReleaseRepository(sessions),
            clock=lambda: now,
        )
        first_command = CreateKnowledgeCandidate(
            scope=scope,
            criticality="critical",
            source_ids=(source_key,),
            transform_revision="transform-v1",
            chunking_revision="chunk-v1",
            index_generation_id=generation_id,
            embedding_revision="embed-v1",
            embedding_dimension=1536,
            retriever_revision="retriever-v1",
            policy_revision="policy-v1",
            index_checksum="d" * 64,
            effective_at=now,
            freshness_expires_at=now + timedelta(days=1),
            barrier_generation=0,
        )
        candidate_results = await asyncio.gather(
            *(
                service.create_candidate(
                    first_command,
                    actor=actor("knowledge.release.submit", "integration-maker"),
                    correlation_id=uuid4(),
                    idempotency_key=f"candidate-{source_uuid.hex}",
                )
                for _ in range(2)
            )
        )
        assert candidate_results[0] == candidate_results[1]
        candidate = candidate_results[0]
        with pytest.raises(KnowledgeConcurrencyConflict, match="different candidate inputs"):
            await service.create_candidate(
                replace(first_command, transform_revision="different-transform"),
                actor=actor("knowledge.release.submit", "integration-maker"),
                correlation_id=uuid4(),
                idempotency_key=f"candidate-{source_uuid.hex}",
            )
        release_ids.append(candidate.release_id)
        await mark_synthetic_index_materialized(sessions, candidate.release_id)
        evaluated = await service.record_evaluation(
            candidate.release_id,
            run_ref="integration-eval",
            suite_revision="integration-suite",
            evidence_hashes=("e" * 64,),
            actor=actor("knowledge.release.evaluate", "integration-evaluator"),
            correlation_id=uuid4(),
            idempotency_key=f"evaluate-{source_uuid.hex}",
        )
        approved = await service.approve(
            evaluated.release_id,
            actor=actor("knowledge.release.approve", "integration-checker"),
            evidence_hash="f" * 64,
            correlation_id=uuid4(),
            idempotency_key=f"approve-{source_uuid.hex}",
        )
        barrier_results = await asyncio.gather(
            *(
                service.open_barrier(
                    approved.release_id,
                    deadline_at=now + timedelta(minutes=5),
                    actor=actor("knowledge.release.submit", "integration-sync"),
                    correlation_id=uuid4(),
                    idempotency_key=f"barrier-{source_uuid.hex}",
                )
                for _ in range(2)
            )
        )
        assert barrier_results[0] == barrier_results[1]
        barrier = barrier_results[0]

        results = await asyncio.gather(
            *(
                service.activate(
                    approved.release_id,
                    expected_pointer_version=barrier.pointer_version,
                    expected_barrier_generation=barrier.generation,
                    actor=actor("knowledge.release.activate", f"integration-release-{i}"),
                    reason="integration-race",
                    correlation_id=uuid4(),
                    idempotency_key=f"activate-{source_uuid.hex}-{i}",
                )
                for i in range(2)
            ),
            return_exceptions=True,
        )

        assert sum(not isinstance(result, Exception) for result in results) == 1
        assert sum(isinstance(result, KnowledgeConcurrencyConflict) for result in results) == 1
        first_active = next(result for result in results if not isinstance(result, Exception))
        assert hasattr(first_active, "release_id")

        second_candidate = await service.create_candidate(
            CreateKnowledgeCandidate(
                scope=scope,
                criticality="critical",
                source_ids=(source_key,),
                transform_revision="transform-v2",
                chunking_revision="chunk-v2",
                index_generation_id=generation_id,
                embedding_revision="embed-v1",
                embedding_dimension=1536,
                retriever_revision="retriever-v1",
                policy_revision="policy-v1",
                index_checksum="9" * 64,
                effective_at=now,
                freshness_expires_at=now + timedelta(days=1),
                barrier_generation=0,
            ),
            actor=actor("knowledge.release.submit", "integration-maker"),
            correlation_id=uuid4(),
            idempotency_key=f"candidate-2-{source_uuid.hex}",
        )
        release_ids.append(second_candidate.release_id)
        await mark_synthetic_index_materialized(sessions, second_candidate.release_id)
        second_evaluated = await service.record_evaluation(
            second_candidate.release_id,
            run_ref="integration-eval-2",
            suite_revision="integration-suite",
            evidence_hashes=("8" * 64,),
            actor=actor("knowledge.release.evaluate", "integration-evaluator"),
            correlation_id=uuid4(),
            idempotency_key=f"evaluate-2-{source_uuid.hex}",
        )
        second_approved = await service.approve(
            second_evaluated.release_id,
            actor=actor("knowledge.release.approve", "integration-checker"),
            evidence_hash="7" * 64,
            correlation_id=uuid4(),
            idempotency_key=f"approve-2-{source_uuid.hex}",
        )
        second_barrier = await service.open_barrier(
            second_approved.release_id,
            deadline_at=now + timedelta(minutes=5),
            actor=actor("knowledge.release.submit", "integration-sync"),
            correlation_id=uuid4(),
            idempotency_key=f"barrier-2-{source_uuid.hex}",
        )
        activation_replays = await asyncio.gather(
            *(
                service.activate(
                    second_approved.release_id,
                    expected_pointer_version=second_barrier.pointer_version,
                    expected_barrier_generation=second_barrier.generation,
                    actor=actor("knowledge.release.activate", "integration-release-owner"),
                    reason="integration-second-activation",
                    correlation_id=uuid4(),
                    idempotency_key=f"activate-2-{source_uuid.hex}",
                )
                for _ in range(2)
            )
        )
        assert activation_replays[0] == activation_replays[1]
        second_active = activation_replays[0]

        restored = await service.rollback(
            first_active.release_id,  # type: ignore[union-attr]
            expected_pointer_version=second_barrier.pointer_version + 1,
            expected_barrier_generation=second_barrier.generation,
            actor=actor("knowledge.release.rollback", "integration-release-owner"),
            reason="integration-rollback",
            correlation_id=uuid4(),
            idempotency_key=f"rollback-{source_uuid.hex}",
        )
        assert restored.status == "active"
        assert restored.rollback_of_release_id == second_active.release_id

        third_candidate = await service.create_candidate(
            CreateKnowledgeCandidate(
                scope=scope,
                criticality="critical",
                source_ids=(source_key,),
                transform_revision="transform-v3",
                chunking_revision="chunk-v3",
                index_generation_id=generation_id,
                embedding_revision="embed-v1",
                embedding_dimension=1536,
                retriever_revision="retriever-v1",
                policy_revision="policy-v1",
                index_checksum="6" * 64,
                effective_at=now,
                freshness_expires_at=now + timedelta(days=1),
                barrier_generation=0,
            ),
            actor=actor("knowledge.release.submit", "integration-maker"),
            correlation_id=uuid4(),
            idempotency_key=f"candidate-3-{source_uuid.hex}",
        )
        release_ids.append(third_candidate.release_id)
        await mark_synthetic_index_materialized(sessions, third_candidate.release_id)
        await replace_materialized_chunk_without_manifest_update(
            sessions,
            third_candidate.release_id,
        )
        third_evaluated = await service.record_evaluation(
            third_candidate.release_id,
            run_ref="integration-eval-3",
            suite_revision="integration-suite",
            evidence_hashes=("5" * 64,),
            actor=actor("knowledge.release.evaluate", "integration-evaluator"),
            correlation_id=uuid4(),
            idempotency_key=f"evaluate-3-{source_uuid.hex}",
        )
        third_approved = await service.approve(
            third_evaluated.release_id,
            actor=actor("knowledge.release.approve", "integration-checker"),
            evidence_hash="4" * 64,
            correlation_id=uuid4(),
            idempotency_key=f"approve-3-{source_uuid.hex}",
        )
        third_barrier = await service.open_barrier(
            third_approved.release_id,
            deadline_at=now + timedelta(minutes=5),
            actor=actor("knowledge.release.submit", "integration-sync"),
            correlation_id=uuid4(),
            idempotency_key=f"barrier-3-{source_uuid.hex}",
        )

        with pytest.raises(
            KnowledgeConcurrencyConflict,
            match="retrieval materialization is incomplete",
        ):
            await service.activate(
                third_approved.release_id,
                expected_pointer_version=third_barrier.pointer_version,
                expected_barrier_generation=third_barrier.generation,
                actor=actor("knowledge.release.activate", "integration-release-owner"),
                reason="integration-tamper-check",
                correlation_id=uuid4(),
                idempotency_key=f"activate-tampered-{source_uuid.hex}",
            )

        with pytest.raises(KnowledgeConcurrencyConflict, match="active knowledge barrier"):
            await service.rollback(
                second_active.release_id,
                expected_pointer_version=third_barrier.pointer_version,
                expected_barrier_generation=third_barrier.generation,
                actor=actor("knowledge.release.rollback", "integration-release-owner"),
                reason="integration-unsafe-rollback",
                correlation_id=uuid4(),
                idempotency_key=f"rollback-blocked-{source_uuid.hex}",
            )

        withdrawn_candidate = await service.tombstone(
            third_approved.release_id,
            expected_pointer_version=third_barrier.pointer_version,
            actor=actor("knowledge.release.tombstone", "integration-release-owner"),
            reason="integration-candidate-withdrawal",
            correlation_id=uuid4(),
            idempotency_key=f"tombstone-candidate-{source_uuid.hex}",
        )
        assert withdrawn_candidate.status == "tombstoned"
        assert withdrawn_candidate.barrier_generation == third_barrier.generation + 1

        withdrawn = await service.tombstone(
            restored.release_id,
            expected_pointer_version=third_barrier.pointer_version + 1,
            actor=actor("knowledge.release.tombstone", "integration-release-owner"),
            reason="integration-emergency-withdrawal",
            correlation_id=uuid4(),
            idempotency_key=f"tombstone-{source_uuid.hex}",
        )
        assert withdrawn.status == "tombstoned"
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                delete(KnowledgeRevisionPointer).where(
                    KnowledgeRevisionPointer.domain == scope.domain
                )
            )
            if release_ids:
                await session.execute(
                    delete(KnowledgeReleaseOutbox).where(
                        KnowledgeReleaseOutbox.aggregate_id.in_(release_ids)
                    )
                )
                await session.execute(
                    delete(KnowledgeReleaseRecord).where(KnowledgeReleaseRecord.id.in_(release_ids))
                )
            await session.execute(delete(KnowledgeSource).where(KnowledgeSource.id == source_uuid))
        await engine.dispose()
