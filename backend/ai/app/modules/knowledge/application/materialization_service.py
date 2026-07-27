from uuid import UUID, uuid5

from app.modules.knowledge.application.ingestion_ports import (
    IngestionArtifactStore,
    IngestionRepository,
)
from app.modules.knowledge.application.materialization_ports import (
    CandidateMaterializationRepository,
    TextRedactor,
)
from app.modules.knowledge.application.ports import KnowledgeReleaseRepository
from app.modules.knowledge.domain import (
    CandidateChunkMaterialization,
    CandidateMaterializationRejected,
    CandidateMaterializationResult,
)


class CandidateMaterializationService:
    """Projects a governed candidate into retrieval storage without activating it."""

    def __init__(
        self,
        ingestion: IngestionRepository,
        artifacts: IngestionArtifactStore,
        releases: KnowledgeReleaseRepository,
        materializations: CandidateMaterializationRepository,
        redactor: TextRedactor,
        *,
        max_chunks: int = 500,
    ) -> None:
        if not 1 <= max_chunks <= 1_000:
            raise ValueError("candidate materialization chunk limit is invalid")
        self._ingestion = ingestion
        self._artifacts = artifacts
        self._releases = releases
        self._materializations = materializations
        self._redactor = redactor
        self._max_chunks = max_chunks

    async def materialize(
        self,
        *,
        release_id: UUID,
        ingestion_job_id: UUID,
    ) -> CandidateMaterializationResult:
        release = await self._releases.get(release_id)
        if release is None:
            raise CandidateMaterializationRejected("RELEASE_NOT_FOUND")
        if release.status not in {"candidate", "evaluated", "ready"}:
            raise CandidateMaterializationRejected("RELEASE_NOT_MATERIALIZABLE")
        job = await self._ingestion.get(ingestion_job_id)
        if job is None:
            raise CandidateMaterializationRejected("INGESTION_JOB_NOT_FOUND")
        if job.status != "candidate_ready":
            raise CandidateMaterializationRejected("INGESTION_CANDIDATE_NOT_READY")
        if release.scope != job.scope:
            raise CandidateMaterializationRejected("RELEASE_SCOPE_MISMATCH")
        if release.embedding_revision != job.embedding_revision:
            raise CandidateMaterializationRejected("EMBEDDING_REVISION_MISMATCH")
        if release.embedding_dimension != job.embedding_dimension:
            raise CandidateMaterializationRejected("EMBEDDING_DIMENSION_MISMATCH")
        if release.chunking_revision != job.chunker_revision:
            raise CandidateMaterializationRejected("CHUNKING_REVISION_MISMATCH")
        if release.policy_revision != job.policy_revision:
            raise CandidateMaterializationRejected("POLICY_REVISION_MISMATCH")
        matching_sources = tuple(
            source
            for source in release.sources
            if source.source_id == job.source_id and source.source_revision == job.source_revision
        )
        if len(matching_sources) != 1:
            raise CandidateMaterializationRejected("RELEASE_SOURCE_MISMATCH")
        source = matching_sources[0]
        if source.digest() != job.source_snapshot_hash:
            raise CandidateMaterializationRejected("SOURCE_SNAPSHOT_MISMATCH")
        if release.scope.acl_namespace not in source.acl_namespaces:
            raise CandidateMaterializationRejected("SOURCE_ACL_MISMATCH")

        chunk_artifacts = await self._ingestion.list_artifacts(
            job.job_id,
            deletion_generation=job.deletion_generation,
            stage="chunk",
            kind="knowledge-chunk",
        )
        embedding_artifacts = await self._ingestion.list_artifacts(
            job.job_id,
            deletion_generation=job.deletion_generation,
            stage="embed",
            kind="embedding",
        )
        if (
            not chunk_artifacts
            or len(chunk_artifacts) != len(embedding_artifacts)
            or len(chunk_artifacts) > self._max_chunks
        ):
            raise CandidateMaterializationRejected("CANDIDATE_ARTIFACT_SET_INVALID")
        chunks = {
            chunk.chunk_key: chunk async for chunk in self._artifacts.read_chunks(chunk_artifacts)
        }
        embeddings = {
            embedding.chunk_key: embedding
            async for embedding in self._artifacts.read_embeddings(embedding_artifacts)
        }
        if (
            len(chunks) != len(chunk_artifacts)
            or len(embeddings) != len(embedding_artifacts)
            or set(chunks) != set(embeddings)
        ):
            raise CandidateMaterializationRejected("CANDIDATE_ARTIFACT_SET_INVALID")

        materialized: list[CandidateChunkMaterialization] = []
        for chunk_key in sorted(chunks):
            chunk = chunks[chunk_key]
            embedding = embeddings[chunk_key]
            if chunk.content_hash != embedding.content_hash:
                raise CandidateMaterializationRejected("CHUNK_EMBEDDING_HASH_MISMATCH")
            if len(embedding.vector) != release.embedding_dimension:
                raise CandidateMaterializationRejected("EMBEDDING_DIMENSION_MISMATCH")
            redaction = self._redactor.redact(chunk.text)
            materialized.append(
                CandidateChunkMaterialization(
                    chunk_id=uuid5(
                        release.release_id,
                        f"{source.source_id}:{chunk_key}",
                    ),
                    chunk_key=chunk_key,
                    content_checksum=chunk.content_hash,
                    redacted_text=redaction.redacted_text,
                    embedding=embedding.vector,
                )
            )
        return await self._materializations.materialize(
            release_id=release.release_id,
            canonical_source_id=source.source_id,
            source_revision=source.source_revision,
            source_snapshot_hash=source.digest(),
            index_generation_id=release.index_generation_id,
            embedding_revision=release.embedding_revision,
            embedding_dimension=release.embedding_dimension,
            acl_namespace=release.scope.acl_namespace,
            chunks=tuple(materialized),
        )
