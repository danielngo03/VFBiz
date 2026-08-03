import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EvaluationOutcome = Literal["evidence", "refusal", "knowledge_unavailable"]
RetrievalAuthorityClass = Literal["approved-vietnamese-held-out"]
_DIGEST_PATTERN = r"^[a-f0-9]{64}$"
_REVISION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$"


class RetrievalEvaluationCase(BaseModel):
    """Approved, held-out query contract used for provider-neutral bake-offs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    query: str = Field(min_length=1, max_length=4_000)
    locale: str = Field(pattern=r"^[a-z]{2}-[A-Z]{2}$")
    expected_chunk_ids: tuple[UUID, ...] = Field(max_length=100)
    tags: tuple[str, ...] = Field(min_length=1, max_length=20)
    source_approval_digest: str = Field(pattern=_DIGEST_PATTERN)
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


class RetrievalBakeoffManifest(BaseModel):
    """Immutable, ordered authority envelope for one retrieval bake-off."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_revision: str = Field(pattern=_REVISION_PATTERN)
    suite_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    suite_digest: str = Field(pattern=_DIGEST_PATTERN)
    source_release_digest: str = Field(pattern=_DIGEST_PATTERN)
    index_generation_digest: str = Field(pattern=_DIGEST_PATTERN)
    evaluator_revision: str = Field(pattern=_REVISION_PATTERN)
    cases: tuple[RetrievalEvaluationCase, ...] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        case_ids = tuple(case.case_id for case in self.cases)
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("retrieval bake-off manifest case IDs must be unique")
        if any(
            case.source_approval_digest != self.source_release_digest
            for case in self.cases
        ):
            raise ValueError("retrieval bake-off cases must bind one source release")
        if any(case.split != "held-out" for case in self.cases):
            raise ValueError("retrieval bake-off manifest must be held-out")
        if self.computed_suite_digest() != self.suite_digest:
            raise ValueError("retrieval bake-off suite digest mismatch")
        return self

    def computed_suite_digest(self) -> str:
        payload = {
            "manifest_revision": self.manifest_revision,
            "suite_id": self.suite_id,
            "source_release_digest": self.source_release_digest,
            "index_generation_digest": self.index_generation_digest,
            "evaluator_revision": self.evaluator_revision,
            "cases": [case.model_dump(mode="json") for case in self.cases],
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def validate_integrity(self) -> None:
        """Re-run authority validation for values crossing an untrusted boundary."""
        type(self).model_validate(
            {
                "manifest_revision": self.manifest_revision,
                "suite_id": self.suite_id,
                "suite_digest": self.suite_digest,
                "source_release_digest": self.source_release_digest,
                "index_generation_digest": self.index_generation_digest,
                "evaluator_revision": self.evaluator_revision,
                "cases": self.cases,
            }
        )


@dataclass(frozen=True, slots=True)
class RetrievalSuiteAuthority:
    """External authority record required before a retrieval suite can release.

    The bake-off manifest is intentionally self-contained for deterministic
    qualification, but its digest alone is not an approval. This record is
    supplied by the governed authority registry and binds the exact manifest
    to provenance, held-out status and three distinct human roles.
    """

    suite_id: str
    suite_digest: str
    source_release_digest: str
    index_generation_digest: str
    evaluator_revision: str
    authority_class: RetrievalAuthorityClass
    provenance_digest: str
    provenance_status: str
    provenance_evidence_uri: str
    held_out: bool
    data_owner_subject: str
    evaluator_subject: str
    release_owner_subject: str
    authority_digest: str

    def __post_init__(self) -> None:
        subjects = (
            self.data_owner_subject,
            self.evaluator_subject,
            self.release_owner_subject,
        )
        if (
            re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,79}", self.suite_id) is None
            or re.fullmatch(_REVISION_PATTERN, self.evaluator_revision) is None
            or self.authority_class != "approved-vietnamese-held-out"
            or any(not _is_digest(value) for value in (
                self.suite_digest,
                self.source_release_digest,
                self.index_generation_digest,
                self.provenance_digest,
                self.authority_digest,
            ))
            or self.provenance_status != "verified"
            or not 12 <= len(self.provenance_evidence_uri) <= 2048
            or not self.provenance_evidence_uri.startswith("evidence://")
            or not self.held_out
            or any(not subject or len(subject) > 200 for subject in subjects)
            or len(set(subjects)) != 3
            or self.authority_digest != digest_retrieval_authority(self.semantic_document)
        ):
            raise ValueError("INVALID_RETRIEVAL_SUITE_AUTHORITY")

    @property
    def semantic_document(self) -> dict[str, object]:
        return {
            "authority_class": self.authority_class,
            "data_owner_subject": self.data_owner_subject,
            "evaluator_revision": self.evaluator_revision,
            "evaluator_subject": self.evaluator_subject,
            "held_out": self.held_out,
            "index_generation_digest": self.index_generation_digest,
            "provenance_digest": self.provenance_digest,
            "provenance_evidence_uri": self.provenance_evidence_uri,
            "provenance_status": self.provenance_status,
            "release_owner_subject": self.release_owner_subject,
            "source_release_digest": self.source_release_digest,
            "suite_digest": self.suite_digest,
            "suite_id": self.suite_id,
        }

    @property
    def contract_document(self) -> dict[str, object]:
        return {**self.semantic_document, "authority_digest": self.authority_digest}

    @classmethod
    def issue(
        cls,
        *,
        suite_id: str,
        suite_digest: str,
        source_release_digest: str,
        index_generation_digest: str,
        evaluator_revision: str,
        provenance_digest: str,
        provenance_evidence_uri: str,
        data_owner_subject: str,
        evaluator_subject: str,
        release_owner_subject: str,
    ) -> "RetrievalSuiteAuthority":
        document: dict[str, object] = {
            "authority_class": "approved-vietnamese-held-out",
            "data_owner_subject": data_owner_subject,
            "evaluator_revision": evaluator_revision,
            "evaluator_subject": evaluator_subject,
            "held_out": True,
            "index_generation_digest": index_generation_digest,
            "provenance_digest": provenance_digest,
            "provenance_evidence_uri": provenance_evidence_uri,
            "provenance_status": "verified",
            "release_owner_subject": release_owner_subject,
            "source_release_digest": source_release_digest,
            "suite_digest": suite_digest,
            "suite_id": suite_id,
        }
        return cls(
            suite_id=suite_id,
            suite_digest=suite_digest,
            source_release_digest=source_release_digest,
            index_generation_digest=index_generation_digest,
            evaluator_revision=evaluator_revision,
            authority_class="approved-vietnamese-held-out",
            provenance_digest=provenance_digest,
            provenance_status="verified",
            provenance_evidence_uri=provenance_evidence_uri,
            held_out=True,
            data_owner_subject=data_owner_subject,
            evaluator_subject=evaluator_subject,
            release_owner_subject=release_owner_subject,
            authority_digest=digest_retrieval_authority(document),
        )


def digest_retrieval_authority(document: dict[str, object]) -> str:
    canonical = json.dumps(
        document,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _is_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


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
        if self.expected_outcome == "evidence" and not self.expected_chunk_ids:
            raise ValueError("evidence observation must pin expected chunks")
        if self.expected_outcome != "evidence" and self.expected_chunk_ids:
            raise ValueError("non-evidence observation cannot pin expected chunks")
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
