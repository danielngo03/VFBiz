from dataclasses import dataclass
from enum import StrEnum

from app.modules.evaluation.domain.validation import (
    is_bounded_text,
    is_finite_non_negative,
    is_sha256,
)


class AuthorityClass(StrEnum):
    VINFAST_ACCEPTANCE = "vinfast-acceptance"
    PUBLIC_DIAGNOSTIC = "public-diagnostic"


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
            or not is_finite_non_negative(self.max_cost_usd)
        ):
            raise ValueError("INVALID_EVALUATION_BUDGET")


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
