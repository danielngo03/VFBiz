from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.modules.evaluation.application.ports import EvaluationDefinitionRegistry
from app.modules.evaluation.domain import (
    AuthorityClass,
    CalibrationBinding,
    EvaluationRunPlan,
)
from app.modules.evaluation.domain.validation import is_bounded_text, is_sha256


class EvaluationPlanningError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PlanEvaluationRequest:
    run_id: str
    benchmark_id: str
    benchmark_revision: str
    candidate_release_id: str
    candidate_manifest_digest: str
    baseline_release_id: str | None
    baseline_manifest_digest: str | None
    evaluation_claim: str
    subject_under_test: str
    required_authority: AuthorityClass
    random_seed: int

    def __post_init__(self) -> None:
        required_text = (
            self.run_id,
            self.benchmark_id,
            self.benchmark_revision,
            self.candidate_release_id,
        )
        baseline_is_complete = (self.baseline_release_id is None) == (
            self.baseline_manifest_digest is None
        )
        if (
            any(not is_bounded_text(value) for value in required_text)
            or not is_sha256(self.candidate_manifest_digest)
            or not is_bounded_text(self.evaluation_claim, maximum=1000)
            or len(self.evaluation_claim) < 8
            or not is_bounded_text(self.subject_under_test, maximum=200)
            or not baseline_is_complete
            or (
                self.baseline_release_id is not None
                and (
                    not is_bounded_text(self.baseline_release_id)
                    or self.baseline_manifest_digest is None
                    or not is_sha256(self.baseline_manifest_digest)
                )
            )
            or not 0 <= self.random_seed <= 2_147_483_647
        ):
            raise ValueError("INVALID_EVALUATION_REQUEST")


class EvaluationPlanner:
    def __init__(
        self,
        *,
        registry: EvaluationDefinitionRegistry,
        clock: Callable[[], datetime],
    ) -> None:
        self._registry = registry
        self._clock = clock

    async def plan(self, request: PlanEvaluationRequest) -> EvaluationRunPlan:
        benchmark = await self._registry.get_benchmark(
            request.benchmark_id,
            request.benchmark_revision,
        )
        if benchmark is None:
            raise EvaluationPlanningError("MISSING_BENCHMARK_DEFINITION")
        if (
            benchmark.benchmark_id != request.benchmark_id
            or benchmark.revision != request.benchmark_revision
        ):
            raise EvaluationPlanningError("BENCHMARK_IDENTITY_MISMATCH")
        if benchmark.authority_class != request.required_authority:
            raise EvaluationPlanningError("BENCHMARK_AUTHORITY_MISMATCH")

        for metric_revision in benchmark.metric_revisions:
            metric = await self._registry.get_metric(metric_revision)
            if metric is None:
                raise EvaluationPlanningError(f"MISSING_METRIC_DEFINITION:{metric_revision}")
            if metric.revision != metric_revision:
                raise EvaluationPlanningError(f"METRIC_IDENTITY_MISMATCH:{metric_revision}")

        calibration_bindings: list[CalibrationBinding] = []
        grader_kinds: list[tuple[str, str]] = []
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise EvaluationPlanningError("INVALID_EVALUATION_CLOCK")
        for grader_revision in benchmark.grader_revisions:
            grader = await self._registry.get_grader(grader_revision)
            if grader is None:
                raise EvaluationPlanningError(f"MISSING_GRADER_DEFINITION:{grader_revision}")
            if grader.revision != grader_revision:
                raise EvaluationPlanningError(f"GRADER_IDENTITY_MISMATCH:{grader_revision}")
            grader_kinds.append((grader.revision, grader.kind.value))

            calibration = await self._registry.get_calibration(grader_revision)
            if calibration is None:
                raise EvaluationPlanningError(f"MISSING_GRADER_CALIBRATION:{grader_revision}")
            if (
                calibration.grader_revision != grader.revision
                or calibration.grader_definition_digest != grader.definition_digest
                or calibration.implementation_digest != grader.implementation_digest
            ):
                raise EvaluationPlanningError(f"MISMATCHED_GRADER_CALIBRATION:{grader_revision}")
            if not calibration.calibrated_at <= now < calibration.expires_at:
                raise EvaluationPlanningError(f"EXPIRED_GRADER_CALIBRATION:{grader_revision}")
            calibration_bindings.append(
                CalibrationBinding(
                    grader_revision=grader.revision,
                    grader_definition_digest=grader.definition_digest,
                    implementation_digest=grader.implementation_digest,
                    calibration_digest=calibration.evidence_digest,
                    human_labelled_suite_digest=(calibration.human_labelled_suite_digest),
                    calibrated_at=calibration.calibrated_at,
                    expires_at=calibration.expires_at,
                )
            )

        suite = await self._registry.get_suite(
            benchmark.suite_id,
            benchmark.suite_digest,
        )
        if (
            suite is None
            or suite.suite_id != benchmark.suite_id
            or suite.suite_digest != benchmark.suite_digest
            or suite.authority_class is not benchmark.authority_class
        ):
            raise EvaluationPlanningError("MISSING_RELEASED_SUITE")
        baseline_policy = await self._registry.get_baseline_policy(benchmark.baseline_policy_digest)
        if (
            baseline_policy is None
            or baseline_policy.policy_digest != benchmark.baseline_policy_digest
        ):
            raise EvaluationPlanningError("MISSING_BASELINE_POLICY")

        return EvaluationRunPlan(
            run_id=request.run_id,
            authority_class=benchmark.authority_class,
            candidate_release_id=request.candidate_release_id,
            candidate_manifest_digest=request.candidate_manifest_digest,
            baseline_release_id=request.baseline_release_id,
            baseline_manifest_digest=request.baseline_manifest_digest,
            benchmark_definition_digest=benchmark.definition_digest,
            suite_id=benchmark.suite_id,
            suite_digest=benchmark.suite_digest,
            runner_image_digest=benchmark.runner_image_digest,
            harness_revision=benchmark.harness_revision,
            tool_simulator_revision=benchmark.tool_simulator_revision,
            metric_revisions=benchmark.metric_revisions,
            grader_revisions=benchmark.grader_revisions,
            grader_calibrations=tuple(calibration_bindings),
            environment_revision=benchmark.environment_revision,
            random_seed=request.random_seed,
            budgets=benchmark.budgets,
            evaluation_claim=request.evaluation_claim,
            subject_under_test=request.subject_under_test,
            requested_at=now,
            max_attempts=benchmark.max_attempts,
            retryable_failure_codes=benchmark.retryable_failure_codes,
            grader_kinds=tuple(grader_kinds),
            baseline_policy_digest=baseline_policy.policy_digest,
        )
