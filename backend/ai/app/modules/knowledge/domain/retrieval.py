import math
from datetime import datetime
from enum import StrEnum
from typing import Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.knowledge.domain.release import KnowledgeScope

_REVISION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$"
_DIGEST_PATTERN = r"^[a-f0-9]{64}$"


class RetrievalStatus(StrEnum):
    EVIDENCE = "evidence"
    KNOWLEDGE_UPDATING = "knowledge_updating"
    KNOWLEDGE_UNAVAILABLE = "knowledge_unavailable"
    NO_APPROVED_EVIDENCE = "no_approved_evidence"


class SnapshotStatus(StrEnum):
    ACTIVE = "active"
    UPDATING = "updating"
    BLOCKED = "blocked"
    MISSING = "missing"


class RetrievalSourcePin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    source_revision: str = Field(pattern=_REVISION_PATTERN)


class RetrievalSnapshot(BaseModel):
    """Immutable read boundary pinned to one active knowledge release."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    release_id: UUID
    pointer_version: int = Field(strict=True, ge=0)
    barrier_generation: int = Field(strict=True, ge=0)
    scope: KnowledgeScope
    sources: tuple[RetrievalSourcePin, ...] = Field(min_length=1, max_length=64)
    effective_at: datetime
    freshness_expires_at: datetime
    index_generation_id: UUID
    embedding_revision: str = Field(pattern=_REVISION_PATTERN)
    embedding_dimension: int = Field(strict=True, ge=1, le=65_536)
    retriever_revision: str = Field(pattern=_REVISION_PATTERN)
    index_checksum: str = Field(pattern=_DIGEST_PATTERN)
    materialization_checksum: str = Field(pattern=_DIGEST_PATTERN)
    materialized_chunk_count: int = Field(strict=True, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if self.effective_at.tzinfo is None or self.freshness_expires_at.tzinfo is None:
            raise ValueError("retrieval snapshot timestamps must include a timezone")
        if self.freshness_expires_at <= self.effective_at:
            raise ValueError("retrieval snapshot freshness window is invalid")
        source_ids = [source.source_id for source in self.sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("retrieval snapshot source IDs must be unique")
        return self

    @property
    def source_ids(self) -> tuple[UUID, ...]:
        return tuple(source.source_id for source in self.sources)

    def source_revision_for(self, source_id: UUID) -> str | None:
        return next(
            (source.source_revision for source in self.sources if source.source_id == source_id),
            None,
        )


class SnapshotResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: SnapshotStatus
    snapshot: RetrievalSnapshot | None = None
    reason: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")

    @model_validator(mode="after")
    def require_consistent_snapshot(self) -> Self:
        if (self.status is SnapshotStatus.ACTIVE) != (self.snapshot is not None):
            raise ValueError("only an active resolution may include a snapshot")
        return self


class RetrievalCandidate(BaseModel):
    """Unranked candidate returned after storage-level release and ACL filtering."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: UUID
    release_id: UUID
    source_id: UUID
    acl_namespace: str = Field(min_length=1, max_length=160)
    source_uri: str = Field(min_length=1, max_length=2_048)
    source_revision: str = Field(pattern=_REVISION_PATTERN)
    title: str = Field(min_length=1, max_length=255)
    excerpt: str = Field(min_length=1, max_length=8_000)
    content_checksum: str = Field(pattern=_DIGEST_PATTERN)
    index_generation_id: UUID
    embedding_revision: str = Field(pattern=_REVISION_PATTERN)
    embedding: tuple[float, ...] = Field(min_length=1, max_length=65_536)

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        parsed = urlsplit(self.source_uri)
        if (
            parsed.scheme not in {"https", "urn"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("citation URI must be an approved credential-free URI")
        if any(not math.isfinite(value) for value in self.embedding):
            raise ValueError("candidate embedding values must be finite")
        return self


class RetrievalCandidateQuery(BaseModel):
    """Provider-neutral query used for storage-level hybrid candidate selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    normalized_text: str = Field(min_length=1, max_length=4_000)
    embedding: tuple[float, ...] = Field(min_length=1, max_length=65_536)
    candidate_limit: int = Field(strict=True, ge=1, le=1_000)
    lexical_weight: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_query(self) -> Self:
        if not any(value != 0.0 for value in self.embedding):
            raise ValueError("retrieval query embedding cannot be a zero vector")
        if any(not math.isfinite(value) for value in self.embedding):
            raise ValueError("retrieval query embedding values must be finite")
        return self


class RerankScore(BaseModel):
    """Untrusted reranker output keyed to an already-authorized candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: UUID
    score: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_score(self) -> Self:
        if not math.isfinite(self.score):
            raise ValueError("reranker score must be finite")
        return self


class RetrievedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    release_id: UUID
    pointer_version: int = Field(strict=True, ge=0)
    source_id: UUID
    source_uri: str
    source_revision: str = Field(pattern=_REVISION_PATTERN)
    title: str
    excerpt: str
    freshness: datetime
    score: float = Field(ge=0.0, le=1.0)


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: RetrievalStatus
    reason: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    release_id: UUID | None = None
    pointer_version: int | None = Field(default=None, strict=True, ge=0)
    evidence: tuple[RetrievedEvidence, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        has_evidence = self.status is RetrievalStatus.EVIDENCE
        if has_evidence != bool(self.evidence):
            raise ValueError("evidence status and payload must be consistent")
        if has_evidence and (self.release_id is None or self.pointer_version is None):
            raise ValueError("evidence must pin release and pointer revision")
        if not has_evidence and self.evidence:
            raise ValueError("non-evidence outcome cannot include evidence")
        return self
