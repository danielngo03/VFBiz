from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

import pytest

from app.modules.knowledge.application import CandidateMaterializationService
from app.modules.knowledge.application.ingestion_ports import (
    ArtifactDescriptor,
    ChunkUnit,
    EmbeddedChunk,
)
from app.modules.knowledge.domain import (
    ApprovedKnowledgeSource,
    CandidateChunkMaterialization,
    CandidateMaterializationRejected,
    CandidateMaterializationResult,
    IngestionLimits,
    KnowledgeIngestionJob,
    KnowledgeRelease,
    KnowledgeScope,
    ScanEvidence,
    source_set_digest,
)
from app.modules.knowledge.infrastructure import PatternBasedTextRedactor

NOW = datetime(2026, 7, 25, tzinfo=UTC)
INDEX_GENERATION_ID = UUID("00000000-0000-4000-8000-000000000211")
SCOPE = KnowledgeScope(
    domain="synthetic-materialization",
    locale="vi-VN",
    assistant_profile="public_customer",
    acl_namespace="public_customer:synthetic-materialization:vi-VN",
)


def source(*, acl: tuple[str, ...] = (SCOPE.acl_namespace,)) -> ApprovedKnowledgeSource:
    return ApprovedKnowledgeSource(
        source_id="synthetic-source",
        source_type="synthetic",
        locator_ref="objects/synthetic-source",
        owner_role="data-owner",
        custodian_role="knowledge-steward",
        version="v1",
        source_revision="synthetic-source-v1",
        checksum_sha256="a" * 64,
        registry_document_hash="b" * 64,
        approved_purposes=("knowledge",),
        acl_namespaces=acl,
        classification="public",
        rights_approved=True,
        rights_license_id="Synthetic-Test-License",
        rights_commercial_use="permitted",
        rights_derivatives="permitted",
        rights_redistribution="prohibited",
        rights_access_conditions="Synthetic test use only",
        rights_evidence_urls=("urn:vfbiz:evidence:synthetic-rights",),
        rights_legal_review="approved",
        retention_policy_id="synthetic-1d",
        retention_duration_days=1,
        deletion_method="test-delete",
        approval_evidence_hashes=("c" * 64,),
        review_date=NOW + timedelta(days=1),
    )


def release(approved: ApprovedKnowledgeSource) -> KnowledgeRelease:
    return KnowledgeRelease(
        scope=SCOPE,
        status="candidate",
        criticality="non_critical",
        sources=(approved,),
        source_set_hash=source_set_digest((approved,)),
        transform_revision="synthetic-transform-v1",
        chunking_revision="synthetic-chunker-v1",
        index_generation_id=INDEX_GENERATION_ID,
        embedding_revision="synthetic-embed-v1",
        embedding_dimension=3,
        retriever_revision="hybrid-v1",
        policy_revision="synthetic-policy-v1",
        index_checksum="d" * 64,
        proposer_ref="synthetic-maker",
        effective_at=NOW,
        freshness_expires_at=NOW + timedelta(days=1),
        barrier_generation=0,
        version=1,
    )


def candidate_job(approved: ApprovedKnowledgeSource) -> KnowledgeIngestionJob:
    return KnowledgeIngestionJob(
        job_id=uuid4(),
        source_id=approved.source_id,
        source_revision=approved.source_revision,
        source_snapshot_hash=approved.digest(),
        expected_checksum_sha256=approved.checksum_sha256,
        scope=SCOPE,
        parser_revision="synthetic-parser-v1",
        chunker_revision="synthetic-chunker-v1",
        scanner_revision="synthetic-scanner-v1",
        embedding_revision="synthetic-embed-v1",
        embedding_dimension=3,
        policy_revision="synthetic-policy-v1",
        code_revision="1" * 40,
        candidate_namespace="candidate/synthetic/materialization",
        limits=IngestionLimits(
            max_source_bytes=1_000,
            max_units=10,
            max_decoded_pixels_per_unit=1_000,
            max_expansion_ratio=10,
            max_archive_depth=1,
            max_extracted_files=10,
            max_stage_seconds=30,
            max_attempts_per_stage=2,
        ),
        status="candidate_ready",
        current_stage="verify",
        scan_evidence=(
            ScanEvidence(
                phase="pre_parse",
                scanner_revision="synthetic-scanner-v1",
                policy_revision="synthetic-policy-v1",
                result="passed",
                finding_count=0,
                evidence_hash="e" * 64,
            ),
            ScanEvidence(
                phase="post_parse",
                scanner_revision="synthetic-scanner-v1",
                policy_revision="synthetic-policy-v1",
                result="passed",
                finding_count=0,
                evidence_hash="f" * 64,
            ),
        ),
        final_manifest_ref="candidate/synthetic/manifest.json",
        final_manifest_hash="0" * 64,
        created_at=NOW,
        updated_at=NOW,
    )


def descriptor(kind: str, stage: str, unit_key: str) -> ArtifactDescriptor:
    return ArtifactDescriptor(
        artifact_ref=f"candidate/synthetic/{kind}/{unit_key}.json",
        kind=kind,
        stage=stage,
        unit_key=unit_key,
        checksum_sha256="1" * 64,
        byte_count=10,
        record_count=1,
        deletion_generation=0,
        fencing_token=1,
    )


@dataclass
class MemoryIngestionRepository:
    job: KnowledgeIngestionJob

    async def get(self, job_id: UUID) -> KnowledgeIngestionJob | None:
        return self.job if job_id == self.job.job_id else None

    async def list_artifacts(
        self,
        job_id: UUID,
        *,
        deletion_generation: int,
        stage: str | None = None,
        kind: str | None = None,
    ) -> tuple[ArtifactDescriptor, ...]:
        assert job_id == self.job.job_id
        assert deletion_generation == self.job.deletion_generation
        if (stage, kind) == ("chunk", "knowledge-chunk"):
            return (descriptor("knowledge-chunk", "chunk", "chunk-1"),)
        if (stage, kind) == ("embed", "embedding"):
            return (descriptor("embedding", "embed", "chunk-1"),)
        return ()


@dataclass
class MemoryArtifactStore:
    chunk: ChunkUnit
    embedding: EmbeddedChunk

    async def read_chunks(self, artifacts: tuple[ArtifactDescriptor, ...]):
        assert len(artifacts) == 1
        yield self.chunk

    async def read_embeddings(self, artifacts: tuple[ArtifactDescriptor, ...]):
        assert len(artifacts) == 1
        yield self.embedding


@dataclass
class MemoryReleaseRepository:
    release: KnowledgeRelease

    async def get(self, release_id: UUID) -> KnowledgeRelease | None:
        return self.release if self.release.release_id == release_id else None


class MemoryMaterializations:
    def __init__(self) -> None:
        self.persisted: tuple[CandidateChunkMaterialization, ...] | None = None
        self.calls = 0

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
        self.calls += 1
        assert index_generation_id == INDEX_GENERATION_ID
        assert embedding_dimension == 3
        if self.persisted is not None and self.persisted != chunks:
            raise CandidateMaterializationRejected("MATERIALIZATION_REPLAY_MISMATCH")
        replayed = len(chunks) if self.persisted is not None else 0
        materialized = 0 if self.persisted is not None else len(chunks)
        self.persisted = chunks
        return CandidateMaterializationResult(
            release_id=release_id,
            source_id=canonical_source_id,
            embedding_revision=embedding_revision,
            acl_namespace=acl_namespace,
            materialized_count=materialized,
            replayed_count=replayed,
        )


def build_service(
    *,
    current_release: KnowledgeRelease | None = None,
    job: KnowledgeIngestionJob | None = None,
    chunk: ChunkUnit | None = None,
    embedding: EmbeddedChunk | None = None,
) -> tuple[
    CandidateMaterializationService,
    MemoryMaterializations,
    KnowledgeRelease,
    KnowledgeIngestionJob,
]:
    approved = source()
    selected_release = current_release or release(approved)
    selected_job = job or candidate_job(approved)
    selected_chunk = chunk or ChunkUnit(
        chunk_key="chunk-1",
        text="Synthetic approved evidence.",
        content_hash="2" * 64,
        source_unit_key="unit-1",
    )
    selected_embedding = embedding or EmbeddedChunk(
        chunk_key="chunk-1",
        content_hash=selected_chunk.content_hash,
        vector=(1.0, 0.0, 0.0),
    )
    materializations = MemoryMaterializations()
    service = CandidateMaterializationService(
        MemoryIngestionRepository(selected_job),  # type: ignore[arg-type]
        MemoryArtifactStore(selected_chunk, selected_embedding),  # type: ignore[arg-type]
        MemoryReleaseRepository(selected_release),  # type: ignore[arg-type]
        materializations,
        PatternBasedTextRedactor(),
    )
    return service, materializations, selected_release, selected_job


@pytest.mark.asyncio
async def test_materializes_candidate_idempotently_without_activation() -> None:
    service, repository, current_release, job = build_service()

    first = await service.materialize(
        release_id=current_release.release_id,
        ingestion_job_id=job.job_id,
    )
    second = await service.materialize(
        release_id=current_release.release_id,
        ingestion_job_id=job.job_id,
    )

    assert first.materialized_count == 1
    assert first.replayed_count == 0
    assert second.materialized_count == 0
    assert second.replayed_count == 1
    assert current_release.status == "candidate"
    assert repository.calls == 2
    assert repository.persisted is not None
    assert repository.persisted[0].chunk_id == uuid5(
        current_release.release_id,
        "synthetic-source:chunk-1",
    )


@pytest.mark.asyncio
async def test_persisted_redacted_text_never_contains_raw_pii() -> None:
    pii_chunk = ChunkUnit(
        chunk_key="chunk-1",
        text=(
            "Khách hàng Nguyễn Văn An, số điện thoại 0912345678, "
            "email an.nguyen@example.com đã đặt cọc xe."
        ),
        content_hash="2" * 64,
        source_unit_key="unit-1",
    )
    pii_embedding = EmbeddedChunk(
        chunk_key="chunk-1",
        content_hash=pii_chunk.content_hash,
        vector=(1.0, 0.0, 0.0),
    )
    service, repository, current_release, job = build_service(
        chunk=pii_chunk,
        embedding=pii_embedding,
    )

    await service.materialize(
        release_id=current_release.release_id,
        ingestion_job_id=job.job_id,
    )

    assert repository.persisted is not None
    persisted_text = repository.persisted[0].redacted_text
    assert "Nguyễn Văn An" not in persisted_text
    assert "0912345678" not in persisted_text
    assert "an.nguyen@example.com" not in persisted_text
    assert "[NAME_REDACTED]" in persisted_text
    assert "[PHONE_REDACTED]" in persisted_text
    assert "[EMAIL_REDACTED]" in persisted_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("release_change", "job_change", "expected_code"),
    [
        ({"embedding_revision": "other-embed"}, {}, "EMBEDDING_REVISION_MISMATCH"),
        ({"embedding_dimension": 4}, {}, "EMBEDDING_DIMENSION_MISMATCH"),
        ({"chunking_revision": "other-chunker"}, {}, "CHUNKING_REVISION_MISMATCH"),
        ({"policy_revision": "other-policy"}, {}, "POLICY_REVISION_MISMATCH"),
        ({"status": "active"}, {}, "RELEASE_NOT_MATERIALIZABLE"),
        ({}, {"source_revision": "other-source"}, "RELEASE_SOURCE_MISMATCH"),
    ],
)
async def test_rejects_release_job_contract_mismatch(
    release_change: dict[str, object],
    job_change: dict[str, object],
    expected_code: str,
) -> None:
    approved = source()
    current_release = release(approved).model_copy(update=release_change)
    job = candidate_job(approved).model_copy(update=job_change)
    service, _, _, _ = build_service(current_release=current_release, job=job)

    with pytest.raises(CandidateMaterializationRejected) as captured:
        await service.materialize(
            release_id=current_release.release_id,
            ingestion_job_id=job.job_id,
        )

    assert captured.value.code == expected_code


@pytest.mark.asyncio
async def test_rejects_chunk_embedding_hash_or_dimension_mismatch() -> None:
    approved = source()
    current_release = release(approved)
    job = candidate_job(approved)
    bad_hash = EmbeddedChunk(
        chunk_key="chunk-1",
        content_hash="9" * 64,
        vector=(1.0, 0.0, 0.0),
    )
    service, _, _, _ = build_service(
        current_release=current_release,
        job=job,
        embedding=bad_hash,
    )

    with pytest.raises(CandidateMaterializationRejected) as captured:
        await service.materialize(
            release_id=current_release.release_id,
            ingestion_job_id=job.job_id,
        )
    assert captured.value.code == "CHUNK_EMBEDDING_HASH_MISMATCH"

    wrong_dimension = bad_hash.model_copy(update={"content_hash": "2" * 64, "vector": (1.0, 0.0)})
    service, _, _, _ = build_service(
        current_release=current_release,
        job=job,
        embedding=wrong_dimension,
    )
    with pytest.raises(CandidateMaterializationRejected) as captured:
        await service.materialize(
            release_id=current_release.release_id,
            ingestion_job_id=job.job_id,
        )
    assert captured.value.code == "EMBEDDING_DIMENSION_MISMATCH"


@pytest.mark.asyncio
async def test_rejects_source_snapshot_or_acl_mismatch() -> None:
    approved = source()
    current_release = release(approved)
    snapshot_changed = candidate_job(approved).model_copy(update={"source_snapshot_hash": "9" * 64})
    service, _, _, _ = build_service(
        current_release=current_release,
        job=snapshot_changed,
    )

    with pytest.raises(CandidateMaterializationRejected) as captured:
        await service.materialize(
            release_id=current_release.release_id,
            ingestion_job_id=snapshot_changed.job_id,
        )
    assert captured.value.code == "SOURCE_SNAPSHOT_MISMATCH"

    wrong_acl_source = source(acl=("public_customer:other:vi-VN",))
    with pytest.raises(ValueError, match="not eligible"):
        release(wrong_acl_source)
