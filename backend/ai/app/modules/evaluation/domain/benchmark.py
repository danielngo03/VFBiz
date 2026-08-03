from dataclasses import dataclass
from enum import StrEnum

from app.modules.evaluation.domain.validation import (
    is_bounded_text,
    is_fixed_usd,
    is_sha256,
)


class AuthorityClass(StrEnum):
    VINFAST_ACCEPTANCE = "vinfast-acceptance"
    PUBLIC_DIAGNOSTIC = "public-diagnostic"


MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991
MAX_PERSISTED_LATENCY_MS = 2_147_483_647
MAX_EVALUATION_DURATION_SECONDS = MAX_PERSISTED_LATENCY_MS // 1000


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    max_input_tokens: int
    max_output_tokens: int
    max_duration_seconds: int
    max_cost_usd: float

    def __post_init__(self) -> None:
        if (
            self.max_input_tokens <= 0
            or self.max_output_tokens <= 0
            or self.max_duration_seconds <= 0
            or self.max_input_tokens > MAX_SAFE_JSON_INTEGER
            or self.max_output_tokens > MAX_SAFE_JSON_INTEGER
            or self.max_duration_seconds > MAX_EVALUATION_DURATION_SECONDS
            or not is_fixed_usd(self.max_cost_usd)
        ):
            raise ValueError("INVALID_EVALUATION_BUDGET")

    @property
    def canonical_document(self) -> dict[str, object]:
        return {
            "max_cost_usd": self.max_cost_usd,
            "max_duration_seconds": self.max_duration_seconds,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkDefinition:
    benchmark_id: str
    revision: str
    authority_class: AuthorityClass
    suite_id: str
    suite_digest: str
    runner_image_digest: str
    harness_revision: str
    tool_simulator_revision: str | None
    metric_revisions: tuple[str, ...]
    grader_revisions: tuple[str, ...]
    environment_revision: str
    budgets: BudgetPolicy
    baseline_policy_digest: str
    max_attempts: int
    retryable_failure_codes: tuple[str, ...]
    definition_digest: str

    def __post_init__(self) -> None:
        required_text = (
            self.benchmark_id,
            self.revision,
            self.suite_id,
            self.harness_revision,
            self.environment_revision,
        )
        if (
            any(not is_bounded_text(value) for value in required_text)
            or (
                self.tool_simulator_revision is not None
                and not is_bounded_text(self.tool_simulator_revision)
            )
            or not is_sha256(self.suite_digest)
            or not is_sha256(self.runner_image_digest)
            or not is_sha256(self.definition_digest)
            or not is_sha256(self.baseline_policy_digest)
            or not 1 <= self.max_attempts <= 3
            or len(set(self.retryable_failure_codes)) != len(self.retryable_failure_codes)
            or any(
                code
                not in {
                    "runner-unavailable",
                    "provider-timeout",
                    "artifact-store-unavailable",
                }
                for code in self.retryable_failure_codes
            )
            or not self.metric_revisions
            or not self.grader_revisions
            or any(
                not is_bounded_text(revision)
                for revision in self.metric_revisions + self.grader_revisions
            )
        ):
            raise ValueError("INVALID_BENCHMARK_DEFINITION")
        if len(set(self.metric_revisions)) != len(self.metric_revisions):
            raise ValueError("DUPLICATE_METRIC_REVISION")
        if len(set(self.grader_revisions)) != len(self.grader_revisions):
            raise ValueError("DUPLICATE_GRADER_REVISION")

    @property
    def canonical_document(self) -> dict[str, object]:
        return {
            "authority_class": self.authority_class.value,
            "baseline_policy_digest": self.baseline_policy_digest,
            "benchmark_id": self.benchmark_id,
            "budgets": self.budgets.canonical_document,
            "definition_digest": self.definition_digest,
            "environment_revision": self.environment_revision,
            "grader_revisions": list(self.grader_revisions),
            "harness_revision": self.harness_revision,
            "max_attempts": self.max_attempts,
            "metric_revisions": list(self.metric_revisions),
            "retryable_failure_codes": list(self.retryable_failure_codes),
            "revision": self.revision,
            "runner_image_digest": self.runner_image_digest,
            "suite_digest": self.suite_digest,
            "suite_id": self.suite_id,
            "tool_simulator_revision": self.tool_simulator_revision,
        }
