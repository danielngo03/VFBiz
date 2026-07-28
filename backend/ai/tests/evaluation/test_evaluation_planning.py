from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.evaluation.application.planning import (
    EvaluationPlanner,
    EvaluationPlanningError,
    PlanEvaluationRequest,
)
from app.modules.evaluation.domain import (
    AuthorityClass,
    BenchmarkDefinition,
    BudgetPolicy,
    CalibrationBinding,
    GraderCalibration,
    GraderDefinition,
    GraderKind,
    MetricDefinition,
    MetricDirection,
)

SHA_A = f"sha256:{'a' * 64}"
SHA_B = f"sha256:{'b' * 64}"
SHA_C = f"sha256:{'c' * 64}"
SHA_D = f"sha256:{'d' * 64}"
NOW = datetime(2026, 7, 28, 12, tzinfo=UTC)


class FakeDefinitionRegistry:
    def __init__(
        self,
        *,
        benchmark: BenchmarkDefinition,
        metric: MetricDefinition,
        grader: GraderDefinition,
        calibration: GraderCalibration | None,
    ) -> None:
        self.benchmark = benchmark
        self.metric = metric
        self.grader = grader
        self.calibration = calibration

    async def get_benchmark(self, benchmark_id: str, revision: str) -> BenchmarkDefinition | None:
        if (benchmark_id, revision) == (
            self.benchmark.benchmark_id,
            self.benchmark.revision,
        ):
            return self.benchmark
        return None

    async def get_metric(self, revision: str) -> MetricDefinition | None:
        return self.metric if revision == self.metric.revision else None

    async def get_grader(self, revision: str) -> GraderDefinition | None:
        return self.grader if revision == self.grader.revision else None

    async def get_calibration(self, grader_revision: str) -> GraderCalibration | None:
        if self.calibration and grader_revision == self.calibration.grader_revision:
            return self.calibration
        return None


def definitions() -> tuple[
    BenchmarkDefinition,
    MetricDefinition,
    GraderDefinition,
    GraderCalibration,
]:
    metric = MetricDefinition(
        revision="citation-validity-v1",
        direction=MetricDirection.HIGHER_IS_BETTER,
        required_slices=("all", "vi-VN", "en-US"),
        definition_digest=SHA_A,
    )
    grader = GraderDefinition(
        revision="citation-membership-v1",
        kind=GraderKind.CITATION,
        definition_digest=SHA_B,
        implementation_digest=SHA_C,
        calibration_required=True,
    )
    calibration = GraderCalibration(
        grader_revision=grader.revision,
        grader_definition_digest=grader.definition_digest,
        implementation_digest=grader.implementation_digest,
        calibrated_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=30),
        evidence_digest=SHA_D,
    )
    benchmark = BenchmarkDefinition(
        benchmark_id="vivi-customer-assistant",
        revision="v1",
        authority_class=AuthorityClass.VINFAST_ACCEPTANCE,
        suite_id="vivi-golden-v1",
        suite_digest=SHA_A,
        runner_image_digest=SHA_B,
        harness_revision="vivi-harness-v1",
        tool_simulator_revision="vfbiz-tool-simulator-v1",
        metric_revisions=(metric.revision,),
        grader_revisions=(grader.revision,),
        environment_revision="staging-v1",
        budgets=BudgetPolicy(
            max_input_tokens=100_000,
            max_output_tokens=50_000,
            max_duration_seconds=3_600,
            max_cost_usd=50,
        ),
        definition_digest=SHA_C,
    )
    return benchmark, metric, grader, calibration


def request() -> PlanEvaluationRequest:
    return PlanEvaluationRequest(
        run_id="eval:customer-assistant:0001",
        benchmark_id="vivi-customer-assistant",
        benchmark_revision="v1",
        candidate_release_id="assistant-2.0.0",
        candidate_manifest_digest=SHA_A,
        baseline_release_id="assistant-1.9.0",
        baseline_manifest_digest=SHA_B,
        required_authority=AuthorityClass.VINFAST_ACCEPTANCE,
        random_seed=20260728,
    )


@pytest.mark.asyncio
async def test_planner_resolves_every_revision_into_an_immutable_plan() -> None:
    benchmark, metric, grader, calibration = definitions()
    planner = EvaluationPlanner(
        registry=FakeDefinitionRegistry(
            benchmark=benchmark,
            metric=metric,
            grader=grader,
            calibration=calibration,
        ),
        clock=lambda: NOW,
    )

    plan = await planner.plan(request())

    assert plan.benchmark_definition_digest == benchmark.definition_digest
    assert plan.suite_digest == benchmark.suite_digest
    assert plan.metric_revisions == (metric.revision,)
    assert plan.grader_revisions == (grader.revision,)
    assert plan.grader_calibrations == (
        CalibrationBinding(
            grader_revision=grader.revision,
            grader_definition_digest=grader.definition_digest,
            implementation_digest=grader.implementation_digest,
            calibration_digest=calibration.evidence_digest,
        ),
    )
    assert not hasattr(plan, "promoted")


@pytest.mark.asyncio
async def test_planner_fails_closed_when_required_calibration_is_missing() -> None:
    benchmark, metric, grader, _ = definitions()
    planner = EvaluationPlanner(
        registry=FakeDefinitionRegistry(
            benchmark=benchmark,
            metric=metric,
            grader=grader,
            calibration=None,
        ),
        clock=lambda: NOW,
    )

    with pytest.raises(EvaluationPlanningError, match="MISSING_GRADER_CALIBRATION"):
        await planner.plan(request())


@pytest.mark.asyncio
async def test_planner_rejects_expired_calibration() -> None:
    benchmark, metric, grader, calibration = definitions()
    expired = replace(calibration, expires_at=NOW)
    planner = EvaluationPlanner(
        registry=FakeDefinitionRegistry(
            benchmark=benchmark,
            metric=metric,
            grader=grader,
            calibration=expired,
        ),
        clock=lambda: NOW,
    )

    with pytest.raises(EvaluationPlanningError, match="EXPIRED_GRADER_CALIBRATION"):
        await planner.plan(request())


@pytest.mark.asyncio
async def test_planner_rejects_calibration_for_another_implementation() -> None:
    benchmark, metric, grader, calibration = definitions()
    mismatched = replace(calibration, implementation_digest=SHA_A)
    planner = EvaluationPlanner(
        registry=FakeDefinitionRegistry(
            benchmark=benchmark,
            metric=metric,
            grader=grader,
            calibration=mismatched,
        ),
        clock=lambda: NOW,
    )

    with pytest.raises(EvaluationPlanningError, match="MISMATCHED_GRADER_CALIBRATION"):
        await planner.plan(request())


@pytest.mark.asyncio
async def test_public_diagnostic_cannot_satisfy_acceptance_authority() -> None:
    benchmark, metric, grader, calibration = definitions()
    diagnostic = replace(benchmark, authority_class=AuthorityClass.PUBLIC_DIAGNOSTIC)
    planner = EvaluationPlanner(
        registry=FakeDefinitionRegistry(
            benchmark=diagnostic,
            metric=metric,
            grader=grader,
            calibration=calibration,
        ),
        clock=lambda: NOW,
    )

    with pytest.raises(EvaluationPlanningError, match="BENCHMARK_AUTHORITY_MISMATCH"):
        await planner.plan(request())


def test_benchmark_rejects_duplicate_definition_revisions() -> None:
    benchmark, _, _, _ = definitions()

    with pytest.raises(ValueError, match="DUPLICATE_METRIC_REVISION"):
        replace(
            benchmark,
            metric_revisions=("citation-validity-v1", "citation-validity-v1"),
        )

    with pytest.raises(ValueError, match="DUPLICATE_GRADER_REVISION"):
        replace(
            benchmark,
            grader_revisions=(
                "citation-membership-v1",
                "citation-membership-v1",
            ),
        )


def test_budget_policy_rejects_non_positive_resource_limits() -> None:
    with pytest.raises(ValueError, match="INVALID_EVALUATION_BUDGET"):
        BudgetPolicy(
            max_input_tokens=0,
            max_output_tokens=50_000,
            max_duration_seconds=3_600,
            max_cost_usd=50,
        )


def test_calibration_requires_an_aware_ordered_validity_window() -> None:
    _, _, grader, _ = definitions()
    naive = datetime(2026, 7, 28, 12)

    with pytest.raises(ValueError, match="INVALID_CALIBRATION_WINDOW"):
        GraderCalibration(
            grader_revision=grader.revision,
            grader_definition_digest=grader.definition_digest,
            implementation_digest=grader.implementation_digest,
            calibrated_at=naive,
            expires_at=naive + timedelta(days=30),
            evidence_digest=SHA_D,
        )

    with pytest.raises(ValueError, match="INVALID_CALIBRATION_WINDOW"):
        GraderCalibration(
            grader_revision=grader.revision,
            grader_definition_digest=grader.definition_digest,
            implementation_digest=grader.implementation_digest,
            calibrated_at=NOW,
            expires_at=NOW,
            evidence_digest=SHA_D,
        )


def test_nli_and_model_judges_cannot_bypass_calibration() -> None:
    for kind in (GraderKind.NLI, GraderKind.MODEL_JUDGE):
        with pytest.raises(ValueError, match="GRADER_CALIBRATION_REQUIRED"):
            GraderDefinition(
                revision=f"{kind.value}-v1",
                kind=kind,
                definition_digest=SHA_A,
                implementation_digest=SHA_B,
                calibration_required=False,
            )


@pytest.mark.asyncio
async def test_planner_rejects_registry_identity_substitution() -> None:
    benchmark, metric, grader, calibration = definitions()

    class SubstitutingRegistry(FakeDefinitionRegistry):
        async def get_metric(self, revision: str) -> MetricDefinition | None:
            del revision
            return replace(metric, revision="another-metric-v1")

    planner = EvaluationPlanner(
        registry=SubstitutingRegistry(
            benchmark=benchmark,
            metric=metric,
            grader=grader,
            calibration=calibration,
        ),
        clock=lambda: NOW,
    )

    with pytest.raises(EvaluationPlanningError, match="METRIC_IDENTITY_MISMATCH"):
        await planner.plan(request())


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_manifest_digest": "not-a-digest"},
        {"random_seed": -1},
        {"baseline_release_id": None, "baseline_manifest_digest": SHA_B},
    ],
)
def test_plan_request_rejects_contract_invalid_values(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="INVALID_EVALUATION_REQUEST"):
        replace(request(), **changes)


def test_domain_rejects_malformed_digests_and_metric_slices() -> None:
    with pytest.raises(ValueError, match="INVALID_METRIC_DEFINITION"):
        MetricDefinition(
            revision="citation-validity-v1",
            direction=MetricDirection.HIGHER_IS_BETTER,
            required_slices=("all", "all"),
            definition_digest=SHA_A,
        )

    with pytest.raises(ValueError, match="INVALID_GRADER_DEFINITION"):
        GraderDefinition(
            revision="citation-membership-v1",
            kind=GraderKind.CITATION,
            definition_digest="not-a-digest",
            implementation_digest=SHA_C,
            calibration_required=True,
        )

    with pytest.raises(ValueError, match="INVALID_BENCHMARK_DEFINITION"):
        replace(definitions()[0], metric_revisions=())
