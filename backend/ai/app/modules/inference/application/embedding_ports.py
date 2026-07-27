import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from typing import Protocol


class EmbeddingPurpose(StrEnum):
    RETRIEVAL_QUERY = "retrieval_query"
    RETRIEVAL_DOCUMENT = "retrieval_document"


class EmbeddingFailureCode(StrEnum):
    CANCELLED = "cancelled"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    INPUT_BUDGET_EXCEEDED = "input_budget_exceeded"
    COST_BUDGET_EXCEEDED = "cost_budget_exceeded"
    PROVIDER_AUTHENTICATION_FAILED = "provider_authentication_failed"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_REJECTED_REQUEST = "provider_rejected_request"
    PROVIDER_INVALID_RESPONSE = "provider_invalid_response"
    PROVIDER_ADAPTER_FAILURE = "provider_adapter_failure"
    CIRCUIT_OPEN = "circuit_open"
    RESPONSE_ORDER_MISMATCH = "response_order_mismatch"
    RESPONSE_TOO_LARGE = "response_too_large"
    DIMENSION_MISMATCH = "dimension_mismatch"
    MODEL_REVISION_MISMATCH = "model_revision_mismatch"
    NON_FINITE_VECTOR = "non_finite_vector"


class EmbeddingFailure(RuntimeError):
    def __init__(
        self,
        code: EmbeddingFailureCode,
        *,
        retryable: bool,
        provider_id: str | None = None,
        status_code: int | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.retryable = retryable
        self.provider_id = provider_id
        self.status_code = status_code
        self.provider_request_id = provider_request_id


class CancellationSignal(Protocol):
    def is_set(self) -> bool: ...

    async def wait(self) -> object: ...


@dataclass(frozen=True, slots=True)
class EmbeddingGenerationIdentity:
    """Immutable identity of the vector space shared by indexing and retrieval."""

    model_revision: str
    tokenizer_revision: str
    weights_revision: str
    dimension: int
    pooling: str
    normalization: str
    input_template_revision: str
    query_template_sha256: str
    document_template_sha256: str

    def __post_init__(self) -> None:
        bounded = (
            self.model_revision,
            self.tokenizer_revision,
            self.weights_revision,
            self.pooling,
            self.normalization,
            self.input_template_revision,
        )
        if any(not value.strip() or len(value) > 160 for value in bounded):
            raise ValueError("embedding generation identity fields must be bounded")
        if self.dimension < 1:
            raise ValueError("embedding generation dimension must be positive")
        for digest in (self.query_template_sha256, self.document_template_sha256):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("embedding template identity must use SHA-256 hex")

    @property
    def digest(self) -> str:
        payload = {
            "dimension": self.dimension,
            "documentTemplateSha256": self.document_template_sha256,
            "inputTemplateRevision": self.input_template_revision,
            "modelRevision": self.model_revision,
            "normalization": self.normalization,
            "pooling": self.pooling,
            "queryTemplateSha256": self.query_template_sha256,
            "tokenizerRevision": self.tokenizer_revision,
            "weightsRevision": self.weights_revision,
        }
        canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EmbeddingInput:
    index: int
    text: str
    estimated_tokens: int

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("embedding input index cannot be negative")
        if not self.text.strip() or len(self.text.encode("utf-8")) > 1_000_000:
            raise ValueError("embedding input text must be non-empty and bounded")
        if self.estimated_tokens < 1:
            raise ValueError("estimated token count must be positive")


@dataclass(frozen=True, slots=True)
class EmbeddingBudget:
    max_items: int
    max_input_bytes: int
    max_input_tokens: int
    max_cost_microusd: int

    def __post_init__(self) -> None:
        if (
            min(
                self.max_items,
                self.max_input_bytes,
                self.max_input_tokens,
                self.max_cost_microusd,
            )
            < 1
        ):
            raise ValueError("embedding budgets must be positive")


@dataclass(frozen=True, slots=True)
class EmbeddingRequest:
    inputs: tuple[EmbeddingInput, ...]
    purpose: EmbeddingPurpose
    expected_generation: EmbeddingGenerationIdentity
    deadline_at: datetime
    budget: EmbeddingBudget
    correlation_id: str
    cancellation: CancellationSignal | None = None

    def __post_init__(self) -> None:
        if not self.inputs:
            raise ValueError("embedding request must contain at least one input")
        if tuple(item.index for item in self.inputs) != tuple(range(len(self.inputs))):
            raise ValueError("embedding input indices must be contiguous from zero")
        if self.deadline_at.tzinfo is None:
            raise ValueError("deadline_at must include a timezone")
        if (
            not self.correlation_id
            or len(self.correlation_id) > 128
            or any(
                not (character.isalnum() or character in "-_.:")
                for character in self.correlation_id
            )
        ):
            raise ValueError("correlation_id must be opaque, printable and bounded")
        if len(self.inputs) > self.budget.max_items:
            raise ValueError("embedding item budget exceeded")
        if self.total_input_bytes > self.budget.max_input_bytes:
            raise ValueError("embedding input byte budget exceeded")
        if self.total_estimated_tokens > self.budget.max_input_tokens:
            raise ValueError("embedding input token budget exceeded")

    @property
    def total_input_bytes(self) -> int:
        return sum(len(item.text.encode("utf-8")) for item in self.inputs)

    @property
    def total_estimated_tokens(self) -> int:
        return sum(item.estimated_tokens for item in self.inputs)

    @property
    def expected_model_revision(self) -> str:
        return self.expected_generation.model_revision

    @property
    def expected_dimension(self) -> int:
        return self.expected_generation.dimension


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    index: int
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("embedding vector index cannot be negative")
        if not self.values:
            raise ValueError("embedding vector cannot be empty")
        if not all(isfinite(value) for value in self.values):
            raise ValueError("embedding vector values must be finite")


@dataclass(frozen=True, slots=True)
class EmbeddingUsage:
    input_tokens: int
    item_count: int
    input_bytes: int

    def __post_init__(self) -> None:
        if min(self.input_tokens, self.item_count, self.input_bytes) < 0:
            raise ValueError("embedding usage cannot be negative")


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vectors: tuple[EmbeddingVector, ...]
    usage: EmbeddingUsage
    reserved_cost_microusd: int
    incurred_cost_microusd: int | None
    provider_id: str
    generation: EmbeddingGenerationIdentity
    provider_request_id: str | None
    correlation_id: str

    def __post_init__(self) -> None:
        if self.reserved_cost_microusd < 0 or (
            self.incurred_cost_microusd is not None and self.incurred_cost_microusd < 0
        ):
            raise ValueError("embedding cost cannot be negative")
        if not self.provider_id or not self.correlation_id:
            raise ValueError("embedding result identity must be non-empty")
        if tuple(vector.index for vector in self.vectors) != tuple(range(len(self.vectors))):
            raise ValueError("embedding result indices must be contiguous from zero")
        if self.usage.item_count != len(self.vectors):
            raise ValueError("embedding usage item count must match vectors")
        if self.provider_request_id is not None and (
            not self.provider_request_id or len(self.provider_request_id) > 256
        ):
            raise ValueError("provider request identifier must be bounded")

    @property
    def estimated_cost_microusd(self) -> int:
        """Compatibility alias for the pre-request reservation."""
        return self.reserved_cost_microusd

    @property
    def model_revision(self) -> str:
        return self.generation.model_revision


class EmbeddingProvider(Protocol):
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...

    async def aclose(self) -> None: ...
