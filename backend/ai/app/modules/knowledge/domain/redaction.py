from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RedactionCategory = Literal["email", "phone", "vin", "address", "name"]


class RedactionFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: RedactionCategory
    count: int = Field(strict=True, ge=1, le=10_000)


class RedactionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Placeholder substitution can grow the text beyond its 32,000-char
    # input bound (`ChunkUnit.text`'s own limit) when the input is dense
    # with short PII matches. The real persistence-layer limit belongs on
    # `CandidateChunkMaterialization.redacted_text`, which fails closed if a
    # redacted chunk is still too large to store — this bound only guards
    # against unbounded growth, not against every realistic redaction.
    redacted_text: str = Field(max_length=64_000)
    findings: tuple[RedactionFinding, ...] = Field(default=(), max_length=5)
