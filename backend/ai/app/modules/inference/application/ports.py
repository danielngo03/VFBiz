from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Evidence:
    """Untrusted evidence supplied to a generation deployment."""

    evidence_id: str
    source_uri: str
    source_revision: str
    title: str
    excerpt: str
    freshness: str


@dataclass(frozen=True, slots=True)
class Citation:
    """Provider-neutral citation emitted by the inference boundary."""

    evidence_id: str
    source_uri: str
    source_revision: str
    title: str
    freshness: str


class CancellationSignal(Protocol):
    @property
    def is_cancelled(self) -> bool: ...

    async def wait(self) -> None: ...


class InferenceFailureCode(StrEnum):
    CANCELLED = "cancelled"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    INPUT_BUDGET_EXCEEDED = "input_budget_exceeded"
    OUTPUT_BUDGET_EXCEEDED = "output_budget_exceeded"
    PROVIDER_AUTHENTICATION_FAILED = "provider_authentication_failed"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_INVALID_RESPONSE = "provider_invalid_response"
    PROVIDER_REJECTED_REQUEST = "provider_rejected_request"
    PROVIDER_BUSY = "provider_busy"
    PROVIDER_ADAPTER_FAILURE = "provider_adapter_failure"
    MODEL_REVISION_MISMATCH = "model_revision_mismatch"
    RESPONSE_TOO_LARGE = "response_too_large"
    COST_BUDGET_EXCEEDED = "cost_budget_exceeded"
    GROUNDING_NOT_VERIFIED = "grounding_not_verified"
    NO_SAFE_DEPLOYMENT = "no_safe_deployment"


class InferenceFailure(RuntimeError):
    def __init__(
        self,
        code: InferenceFailureCode,
        *,
        retryable: bool,
        provider_id: str | None = None,
        status_code: int | None = None,
        incurred_cost_microusd: int | None = None,
        usage: "InferenceUsage | None" = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.retryable = retryable
        self.provider_id = provider_id
        self.status_code = status_code
        if incurred_cost_microusd is not None and incurred_cost_microusd < 0:
            raise ValueError("incurred cost cannot be negative")
        self.incurred_cost_microusd = incurred_cost_microusd
        self.usage = usage
        self.attempts: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class InferenceBudget:
    max_input_tokens: int
    max_output_tokens: int
    max_cost_microusd: int
    max_attempts: int = 1

    def __post_init__(self) -> None:
        if self.max_input_tokens < 1 or self.max_output_tokens < 1:
            raise ValueError("token budgets must be positive")
        if self.max_cost_microusd < 1:
            raise ValueError("cost budget must be positive")
        if not 1 <= self.max_attempts <= 4:
            raise ValueError("max_attempts must be between one and four")


class RetentionPolicy(StrEnum):
    STANDARD = "standard"
    ZERO_DATA_RETENTION = "zero_data_retention"
    MODIFIED_ABUSE_MONITORING = "modified_abuse_monitoring"


@dataclass(frozen=True, slots=True)
class DeploymentPolicyDescriptor:
    revision: str
    profile: str
    safety_tier: str
    residency: str
    retention: RetentionPolicy
    schema_revision: str
    model_release: str
    provider_project_id: str
    provider_organization_id: str | None
    data_controls_approval_reference: str
    data_controls_approval_sha256: str
    release_manifest_sha256: str

    def __post_init__(self) -> None:
        for value in (
            self.revision,
            self.profile,
            self.safety_tier,
            self.residency,
            self.schema_revision,
            self.model_release,
            self.provider_project_id,
            self.data_controls_approval_reference,
        ):
            if not value.strip() or len(value) > 160:
                raise ValueError("deployment policy values must be non-empty and bounded")
        if self.provider_organization_id is not None and (
            not self.provider_organization_id.strip() or len(self.provider_organization_id) > 160
        ):
            raise ValueError("provider organization must be non-empty and bounded when set")
        for digest in (
            self.data_controls_approval_sha256,
            self.release_manifest_sha256,
        ):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("deployment policy evidence must use SHA-256 hex")


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    question: str
    evidence: tuple[Evidence, ...]
    budget: InferenceBudget
    deadline_at: datetime
    required_policy: DeploymentPolicyDescriptor
    correlation_id: str
    expected_prompt_revision: str
    expected_prompt_content_sha256: str
    safety_identifier: str | None = None
    cancellation: CancellationSignal | None = None

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("question must not be blank")
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
        if not self.expected_prompt_revision or len(self.expected_prompt_revision) > 160:
            raise ValueError("expected_prompt_revision must be non-empty and bounded")
        if len(self.expected_prompt_content_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.expected_prompt_content_sha256
        ):
            raise ValueError("expected prompt content hash must be SHA-256 hex")
        if len(self.evidence) > 32:
            raise ValueError("at most 32 evidence items are allowed")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("evidence identifiers must be unique")
        if any(
            len(item.evidence_id) > 128 or len(item.title) > 512 or len(item.excerpt) > 16_000
            for item in self.evidence
        ):
            raise ValueError("evidence fields exceed local limits")
        object.__setattr__(
            self,
            "evidence",
            tuple(sorted(self.evidence, key=lambda item: item.evidence_id)),
        )
        if self.safety_identifier is not None:
            if len(self.safety_identifier) != 64 or any(
                character not in "0123456789abcdef" for character in self.safety_identifier
            ):
                raise ValueError("safety_identifier must be a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class InferenceUsage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int

    def __post_init__(self) -> None:
        if (
            min(
                self.input_tokens,
                self.output_tokens,
                self.cached_input_tokens,
                self.reasoning_tokens,
            )
            < 0
        ):
            raise ValueError("usage values cannot be negative")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError("reasoning tokens cannot exceed output tokens")


class InferenceAttemptDisposition(StrEnum):
    SUCCEEDED = "succeeded"
    RETRYABLE_FAILURE = "retryable_failure"
    TERMINAL_FAILURE = "terminal_failure"


@dataclass(frozen=True, slots=True)
class InferenceAttempt:
    deployment_id: str
    provider_id: str
    disposition: InferenceAttemptDisposition
    reserved_cost_microusd: int
    incurred_cost_microusd: int
    usage: InferenceUsage
    failure_code: InferenceFailureCode | None = None

    def __post_init__(self) -> None:
        if not self.deployment_id or not self.provider_id:
            raise ValueError("attempt identity must be non-empty")
        if min(self.reserved_cost_microusd, self.incurred_cost_microusd) < 0:
            raise ValueError("attempt cost cannot be negative")
        if (
            self.disposition is InferenceAttemptDisposition.SUCCEEDED
            and self.failure_code is not None
        ):
            raise ValueError("successful attempt cannot have a failure code")
        if (
            self.disposition is not InferenceAttemptDisposition.SUCCEEDED
            and self.failure_code is None
        ):
            raise ValueError("failed attempt requires a failure code")


@dataclass(frozen=True, slots=True)
class GenerationResult:
    outcome: "GenerationOutcome"
    answer: str | None
    citations: tuple[Citation, ...]
    usage: InferenceUsage
    estimated_cost_microusd: int
    deployment_id: str
    provider_id: str
    deployment_policy: DeploymentPolicyDescriptor
    model_revision: str
    prompt_revision: str
    prompt_content_sha256: str
    evidence_digest: str
    correlation_id: str
    provider_request_id: str | None
    attempts: tuple[InferenceAttempt, ...] = ()

    def __post_init__(self) -> None:
        if self.estimated_cost_microusd < 0:
            raise ValueError("estimated cost cannot be negative")
        for value in (
            self.deployment_id,
            self.provider_id,
            self.model_revision,
            self.prompt_revision,
            self.correlation_id,
        ):
            if not value or len(value) > 160:
                raise ValueError("generation metadata must be non-empty and bounded")
        for digest in (self.prompt_content_sha256, self.evidence_digest):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("generation digests must use SHA-256 hex")
        if self.provider_request_id is not None and (
            not self.provider_request_id or len(self.provider_request_id) > 256
        ):
            raise ValueError("provider request ID must be bounded")
        if self.outcome is GenerationOutcome.ANSWERED:
            if self.answer is None or not self.answer.strip() or not self.citations:
                raise ValueError("answered result requires an answer and citations")
        elif self.answer is not None or self.citations:
            raise ValueError("non-answer result cannot contain answer or citations")


class GenerationOutcome(StrEnum):
    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class ClaimSupportDecision:
    supported: bool
    validator_revision: str
    evidence_digest: str


class ClaimSupportValidator(Protocol):
    async def validate(
        self,
        request: GenerationRequest,
        result: GenerationResult,
    ) -> ClaimSupportDecision: ...


class ModelDeployment(Protocol):
    @property
    def deployment_id(self) -> str: ...

    @property
    def provider_id(self) -> str: ...

    @property
    def policy(self) -> DeploymentPolicyDescriptor: ...

    def estimate_max_cost_microusd(self, request: GenerationRequest) -> int: ...

    async def generate_response(self, request: GenerationRequest) -> GenerationResult: ...

    async def aclose(self) -> None: ...
