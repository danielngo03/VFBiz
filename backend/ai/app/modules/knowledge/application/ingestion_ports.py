from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.knowledge.domain import (
    KnowledgeIngestionJob,
    ScanEvidence,
    StageCheckpoint,
)


class ArtifactDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_ref: str = Field(pattern=r"^[a-z0-9][a-z0-9/_=.-]{0,511}$")
    kind: str = Field(pattern=r"^[a-z][a-z0-9-]{1,79}$")
    stage: str = Field(pattern=r"^[a-z][a-z0-9-]{1,79}$")
    unit_key: str = Field(pattern=r"^[a-z0-9][a-z0-9/_=.-]{0,255}$")
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_count: int = Field(strict=True, ge=0)
    record_count: int = Field(strict=True, ge=0)
    parent_checksum: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    deletion_generation: int = Field(strict=True, ge=0)
    fencing_token: int = Field(strict=True, ge=1)


class SourceObject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    object_ref: str = Field(pattern=r"^[a-z0-9][a-z0-9/_=.-]{0,511}$")
    detected_mime: str = Field(pattern=r"^[a-z0-9.+-]+/[a-z0-9.+-]+$")
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_count: int = Field(strict=True, ge=0)
    magic: str = Field(pattern=r"^[A-Z0-9_-]{2,40}$")
    deletion_generation: int = Field(strict=True, ge=0)
    fencing_token: int = Field(strict=True, ge=1)


class PermanentIngestionFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TransientIngestionFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ParsedUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    unit_index: int = Field(strict=True, ge=1)
    continuation_cursor: int = Field(strict=True, ge=0)
    is_last: bool
    unit_key: str = Field(pattern=r"^[a-z0-9][a-z0-9/_=.-]{0,255}$")
    text: str = Field(max_length=250_000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ChunkUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_key: str = Field(pattern=r"^[a-z0-9][a-z0-9/_=.-]{0,255}$")
    text: str = Field(max_length=32_000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_unit_key: str = Field(pattern=r"^[a-z0-9][a-z0-9/_=.-]{0,255}$")


class EmbeddedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_key: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    vector: tuple[float, ...]


class DuplicateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    duplicate_chunk_key: str = Field(pattern=r"^[a-z0-9][a-z0-9/_=.-]{0,255}$")
    canonical_chunk_key: str = Field(pattern=r"^[a-z0-9][a-z0-9/_=.-]{0,255}$")
    method: Literal["exact", "semantic"]
    detector_revision: str = Field(min_length=1, max_length=160)
    threshold: float = Field(ge=0, le=1)
    score: float = Field(ge=0, le=1)
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class IngestionRepository(Protocol):
    async def add_idempotent(
        self, job: KnowledgeIngestionJob, *, idempotency_key: str, actor_ref: str
    ) -> KnowledgeIngestionJob: ...

    async def get(self, job_id: UUID) -> KnowledgeIngestionJob | None: ...

    async def list_artifacts(
        self,
        job_id: UUID,
        *,
        deletion_generation: int,
        stage: str | None = None,
        kind: str | None = None,
    ) -> tuple[ArtifactDescriptor, ...]: ...

    async def get_idempotent_control_result(
        self,
        job_id: UUID,
        *,
        operation: Literal["request-deletion", "replay-dead-letter"],
        idempotency_key: str,
    ) -> KnowledgeIngestionJob | None: ...

    async def save_control_transition(
        self,
        job: KnowledgeIngestionJob,
        *,
        expected_version: int,
        operation: Literal["request-deletion", "replay-dead-letter"],
        idempotency_key: str,
        actor_ref: str,
    ) -> KnowledgeIngestionJob: ...

    async def claim_next(
        self, *, now: datetime, lease_expires_at: datetime
    ) -> KnowledgeIngestionJob | None: ...

    async def renew_lease(
        self,
        job_id: UUID,
        *,
        expected_version: int,
        fencing_token: int,
        lease_expires_at: datetime,
    ) -> bool: ...

    async def commit_stage(
        self,
        job: KnowledgeIngestionJob,
        *,
        expected_version: int,
        fencing_token: int,
        attempt_number: int,
        checkpoint: StageCheckpoint | None,
        artifacts: tuple[ArtifactDescriptor, ...],
        event_type: str,
    ) -> KnowledgeIngestionJob: ...


class ApprovedSourceContentReader(Protocol):
    def open_stream(self, *, source_id: str, source_revision: str) -> AsyncIterator[bytes]: ...


class QuarantineStore(Protocol):
    async def write_stream(
        self,
        *,
        job_id: UUID,
        deletion_generation: int,
        fencing_token: int,
        expected_checksum: str,
        max_bytes: int,
        chunks: AsyncIterator[bytes],
    ) -> SourceObject: ...

    async def read_object(self, artifact: ArtifactDescriptor) -> SourceObject: ...

    async def delete_job_artifacts(self, job_id: UUID, *, deletion_generation: int) -> str: ...


class SourceApprovalGate(Protocol):
    async def assert_current(self, job: KnowledgeIngestionJob) -> None: ...


class ContentScanner(Protocol):
    async def scan_object(self, source: SourceObject) -> ScanEvidence: ...

    async def scan_text(self, unit: ParsedUnit) -> ScanEvidence: ...


class DocumentParser(Protocol):
    def parse_units(
        self,
        source: SourceObject,
        *,
        after_cursor: int,
        next_unit_index: int,
        max_units: int,
    ) -> AsyncIterator[ParsedUnit]: ...


class KnowledgeChunker(Protocol):
    async def chunk(self, unit: ParsedUnit) -> tuple[ChunkUnit, ...]: ...


class KnowledgeEmbedder(Protocol):
    @property
    def dimension(self) -> int: ...

    async def embed(self, chunks: tuple[ChunkUnit, ...]) -> tuple[EmbeddedChunk, ...]: ...


class DuplicateDetector(Protocol):
    async def compare(self, chunk: ChunkUnit, candidate: ChunkUnit) -> DuplicateDecision | None: ...


class IngestionArtifactStore(Protocol):
    async def persist_parsed_unit(
        self,
        job_id: UUID,
        unit: ParsedUnit,
        *,
        parent_checksum: str,
        deletion_generation: int,
        fencing_token: int,
    ) -> ArtifactDescriptor: ...

    def read_parsed_units(
        self, artifacts: tuple[ArtifactDescriptor, ...]
    ) -> AsyncIterator[ParsedUnit]: ...

    async def persist_chunks(
        self,
        job_id: UUID,
        chunks: tuple[ChunkUnit, ...],
        *,
        parent_checksum: str,
        deletion_generation: int,
        fencing_token: int,
    ) -> tuple[ArtifactDescriptor, ...]: ...

    async def persist_duplicate_decisions(
        self,
        job_id: UUID,
        decisions: tuple[DuplicateDecision, ...],
        *,
        parent_checksum: str,
        deletion_generation: int,
        fencing_token: int,
    ) -> tuple[ArtifactDescriptor, ...]: ...

    def read_chunks(
        self, artifacts: tuple[ArtifactDescriptor, ...]
    ) -> AsyncIterator[ChunkUnit]: ...

    async def persist_embeddings(
        self,
        job_id: UUID,
        chunks: tuple[EmbeddedChunk, ...],
        *,
        parent_checksum: str,
        deletion_generation: int,
        fencing_token: int,
    ) -> tuple[ArtifactDescriptor, ...]: ...

    def read_embeddings(
        self, artifacts: tuple[ArtifactDescriptor, ...]
    ) -> AsyncIterator[EmbeddedChunk]: ...

    async def build_manifest(
        self,
        job: KnowledgeIngestionJob,
        committed_artifacts: tuple[ArtifactDescriptor, ...],
    ) -> tuple[str, str, ArtifactDescriptor]: ...

    async def delete_job_artifacts(self, job_id: UUID, *, deletion_generation: int) -> str: ...
