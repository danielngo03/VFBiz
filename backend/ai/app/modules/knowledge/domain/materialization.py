import math
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CandidateMaterializationRejected(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CandidateChunkMaterialization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: UUID
    chunk_key: str = Field(pattern=r"^[a-z0-9][a-z0-9/_=.-]{0,255}$")
    content_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    redacted_text: str = Field(min_length=1, max_length=32_000)
    embedding: tuple[float, ...] = Field(min_length=1, max_length=65_536)

    @model_validator(mode="after")
    def validate_embedding(self) -> "CandidateChunkMaterialization":
        if not any(value != 0.0 for value in self.embedding):
            raise ValueError("candidate embedding must not be a zero vector")
        if any(not math.isfinite(value) for value in self.embedding):
            raise ValueError("candidate embedding must contain finite values")
        return self


class CandidateMaterializationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    release_id: UUID
    source_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    embedding_revision: str = Field(min_length=1, max_length=160)
    acl_namespace: str = Field(min_length=1, max_length=160)
    materialized_count: int = Field(strict=True, ge=0, le=1_000)
    replayed_count: int = Field(strict=True, ge=0, le=1_000)
