from dataclasses import dataclass
from hashlib import sha256

from app.modules.inference.application.embedding_ports import (
    EmbeddingGenerationIdentity,
    EmbeddingPurpose,
    EmbeddingRequest,
)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(frozen=True, slots=True)
class EmbeddingAdapterPolicy:
    provider_id: str
    model_revision: str
    output_dimension: int
    max_items_per_request: int
    max_input_bytes_per_request: int
    max_input_tokens_per_request: int
    input_microusd_per_million_tokens: int
    fixed_request_cost_microusd: int
    max_concurrency: int
    max_response_bytes: int
    max_output_elements: int
    input_template_revision: str
    query_prefix: str
    document_prefix: str
    tokenizer_revision: str = "provider-managed"
    weights_revision: str = "provider-managed"
    pooling: str = "provider-managed"
    normalization: str = "l2"
    circuit_failure_threshold: int = 3
    circuit_recovery_seconds: float = 30

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.model_revision.strip():
            raise ValueError("embedding provider identity must be non-empty")
        if len(self.provider_id) > 80 or len(self.model_revision) > 160:
            raise ValueError("embedding provider identity must be bounded")
        if (
            min(
                self.output_dimension,
                self.max_items_per_request,
                self.max_input_bytes_per_request,
                self.max_input_tokens_per_request,
                self.max_concurrency,
                self.circuit_failure_threshold,
                self.circuit_recovery_seconds,
                self.max_response_bytes,
                self.max_output_elements,
            )
            < 1
        ):
            raise ValueError("embedding provider limits must be positive")
        if (
            min(
                self.input_microusd_per_million_tokens,
                self.fixed_request_cost_microusd,
            )
            < 0
        ):
            raise ValueError("embedding provider cost cannot be negative")
        if (
            not self.input_template_revision.strip()
            or len(self.input_template_revision) > 160
            or len(self.query_prefix.encode("utf-8")) > 1_024
            or len(self.document_prefix.encode("utf-8")) > 1_024
        ):
            raise ValueError("embedding input template must be non-empty and bounded")
        if any(
            not value.strip() or len(value) > 160
            for value in (
                self.tokenizer_revision,
                self.weights_revision,
                self.pooling,
                self.normalization,
            )
        ):
            raise ValueError("embedding vector-space identity must be bounded")

    def render_inputs(self, request: EmbeddingRequest) -> tuple[str, ...]:
        prefix = (
            self.query_prefix
            if request.purpose is EmbeddingPurpose.RETRIEVAL_QUERY
            else self.document_prefix
        )
        return tuple(f"{prefix}{item.text}" for item in request.inputs)

    def rendered_usage(self, request: EmbeddingRequest) -> tuple[tuple[str, ...], int, int]:
        """Return the exact provider payload plus conservative admission usage."""
        rendered = self.render_inputs(request)
        rendered_bytes = sum(len(text.encode("utf-8")) for text in rendered)
        prefix = (
            self.query_prefix
            if request.purpose is EmbeddingPurpose.RETRIEVAL_QUERY
            else self.document_prefix
        )
        # Input estimates are release-tokenizer estimates. Until a tokenizer is
        # locally composed, every prefix byte counts as a token to fail safely.
        rendered_tokens = request.total_estimated_tokens + (
            len(prefix.encode("utf-8")) * len(request.inputs)
        )
        return rendered, rendered_bytes, rendered_tokens

    @property
    def generation(self) -> EmbeddingGenerationIdentity:
        return EmbeddingGenerationIdentity(
            model_revision=self.model_revision,
            tokenizer_revision=self.tokenizer_revision,
            weights_revision=self.weights_revision,
            dimension=self.output_dimension,
            pooling=self.pooling,
            normalization=self.normalization,
            input_template_revision=self.input_template_revision,
            query_template_sha256=sha256(self.query_prefix.encode("utf-8")).hexdigest(),
            document_template_sha256=sha256(self.document_prefix.encode("utf-8")).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class TeiDeploymentIdentity:
    model_revision: str
    tokenizer_sha256: str
    weights_sha256: str
    input_template_revision: str
    deployment_sha256: str

    def __post_init__(self) -> None:
        if (
            not self.model_revision.strip()
            or not self.input_template_revision.strip()
            or len(self.model_revision) > 160
            or len(self.input_template_revision) > 160
        ):
            raise ValueError("TEI deployment identity must be non-empty and bounded")
        if not all(
            _is_sha256(digest)
            for digest in (
                self.tokenizer_sha256,
                self.weights_sha256,
                self.deployment_sha256,
            )
        ):
            raise ValueError("TEI deployment identity must use SHA-256 hex")
