import math
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EvaluationOutcome = Literal["evidence", "refusal", "knowledge_unavailable"]


class RetrievalEvaluationCase(BaseModel):
    """Approved, held-out query contract used for provider-neutral bake-offs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    query: str = Field(min_length=1, max_length=4_000)
    locale: str = Field(pattern=r"^[a-z]{2}-[A-Z]{2}$")
    expected_chunk_ids: tuple[UUID, ...] = Field(max_length=100)
    tags: tuple[str, ...] = Field(min_length=1, max_length=20)
    source_approval_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    split: Literal["held-out"]
    expected_outcome: EvaluationOutcome = "evidence"

    @model_validator(mode="after")
    def validate_case(self) -> Self:
        if len(set(self.expected_chunk_ids)) != len(self.expected_chunk_ids):
            raise ValueError("expected chunk IDs must be unique")
        if self.expected_outcome == "evidence" and not self.expected_chunk_ids:
            raise ValueError("evidence case must pin at least one approved chunk")
        if self.expected_outcome != "evidence" and self.expected_chunk_ids:
            raise ValueError("non-evidence case cannot pin relevant chunks")
        return self


class RetrievalBenchmarkObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    expected_chunk_ids: tuple[UUID, ...] = Field(max_length=100)
    retrieved_chunk_ids: tuple[UUID, ...] = Field(max_length=100)
    baseline_retrieved_chunk_ids: tuple[UUID, ...] | None = Field(
        default=None,
        max_length=100,
    )
    expected_outcome: EvaluationOutcome
    actual_outcome: EvaluationOutcome
    citation_valid: bool
    latency_ms: float = Field(ge=0.0)
    normalized_cost: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if len(set(self.retrieved_chunk_ids)) != len(self.retrieved_chunk_ids):
            raise ValueError("retrieved chunk IDs must be unique")
        if self.baseline_retrieved_chunk_ids is not None and len(
            set(self.baseline_retrieved_chunk_ids)
        ) != len(self.baseline_retrieved_chunk_ids):
            raise ValueError("baseline retrieved chunk IDs must be unique")
        values = (self.latency_ms, self.normalized_cost)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("benchmark measurements must be finite")
        return self


class RetrievalBenchmarkSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_count: int = Field(strict=True, ge=1)
    recall_at_5: float = Field(ge=0.0, le=1.0)
    recall_at_20: float = Field(ge=0.0, le=1.0)
    ndcg_at_10: float = Field(ge=0.0, le=1.0)
    reranker_ndcg_lift: float = Field(ge=-1.0, le=1.0)
    mrr: float = Field(ge=0.0, le=1.0)
    citation_correctness: float = Field(ge=0.0, le=1.0)
    refusal_correctness: float = Field(ge=0.0, le=1.0)
    p50_latency_ms: float = Field(ge=0.0)
    p95_latency_ms: float = Field(ge=0.0)
    normalized_cost: float = Field(ge=0.0)
    throughput_cases_per_second: float = Field(ge=0.0)
