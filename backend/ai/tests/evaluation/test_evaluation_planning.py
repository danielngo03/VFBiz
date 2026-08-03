import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema.validators import validator_for

from app.modules.evaluation.application.planning import (
    EvaluationPlanner,
    EvaluationPlanningError,
    PlanEvaluationRequest,
)
from app.modules.evaluation.domain import (
    MANDATORY_HARD_GATE_REVISIONS,
    AuthorityClass,
    BaselinePolicySnapshot,
    BenchmarkDefinition,
    BudgetPolicy,
    CalibrationBinding,
    EvaluationRunPlan,
    EvaluationSuiteAuthority,
    EvaluationSuiteSnapshot,
    GraderCalibration,
    GraderDefinition,
    GraderKind,
    MetricDefinition,
    MetricDirection,
    digest_document,
    evaluation_case_bindings_digest,
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

    async def get_suite(
        self,
        suite_id: str,
        suite_digest: str,
    ) -> EvaluationSuiteSnapshot | None:
        released = released_suite()
        return (
            released
            if (suite_id, suite_digest) == (released.suite_id, released.suite_digest)
            else None
        )

    async def get_baseline_policy(
        self,
        policy_digest: str,
    ) -> BaselinePolicySnapshot | None:
        policy = baseline_policy()
        return policy if policy_digest == policy.policy_digest else None


def released_suite() -> EvaluationSuiteSnapshot:
    bindings = tuple(
        (f"golden.{index:03d}", f"sha256:{index:064x}")
        for index in range(1, 501)
    )
    authority = EvaluationSuiteAuthority.issue(
        suite_id="vivi-golden-v1",
        authority_class=AuthorityClass.VINFAST_ACCEPTANCE,
        qualification_profile="vivi-customer-assistant-v1",
        qualification_policy_digest=SHA_A,
        case_bindings_digest=evaluation_case_bindings_digest(bindings),
        case_composition_digest=SHA_B,
        risk_taxonomy_digest=SHA_B,
        provenance_digest=SHA_C,
        provenance_status="verified",
        provenance_evidence_uri="evidence://suite/provenance",
        contamination_scan_digest=SHA_D,
        contamination_status="passed",
        contamination_evidence_uri="evidence://suite/contamination",
        held_out=True,
        author_subject="subject:dataset-author",
        evaluator_subject="subject:independent-evaluator",
        release_owner_subject="subject:dataset-release-owner",
    )
    return EvaluationSuiteSnapshot.issue(
        suite_id="vivi-golden-v1",
        case_bindings=bindings,
        authority=authority,
    )


def baseline_policy() -> BaselinePolicySnapshot:
    return BaselinePolicySnapshot.issue(
        {
            "binary_interval": "wilson-95",
            "composite_score_authoritative": False,
            "hard_gates": [
                {"gate_revision": revision, "required_value": 0}
                for revision in sorted(MANDATORY_HARD_GATE_REVISIONS)
            ],
            "operational_budgets": {
                "latency_p95_ms": 5000,
                "normalized_cost_usd": 1,
                "provider_failure_rate": 0,
            },
            "paired_comparison": {
                "confidence": 0.95,
                "method": "paired-bootstrap",
                "samples": 10000,
            },
            "policy_id": "assistant-release-baseline",
            "protected_metrics": [
                {
                    "direction": "higher-is-better",
                    "metric_revision": "planning-citation-validity-v1",
                    "non_inferiority_margin": 0,
                    "require_protected_95_bound": True,
                    "required_slices": ["all"],
                }
            ],
            "revision": "v1",
            "waiver_policy": {
                "authority_contract_id": ("https://vfbiz.example/contracts/governance/waiver/v1"),
                "requires_expiry": True,
                "requires_mitigation": True,
                "requires_owner": True,
            },
        }
    )


def definitions() -> tuple[
    BenchmarkDefinition,
    MetricDefinition,
    GraderDefinition,
    GraderCalibration,
]:
    metric = MetricDefinition(
        revision="planning-citation-validity-v1",
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
    calibration = GraderCalibration.issue(
        grader_revision=grader.revision,
        grader_definition_digest=grader.definition_digest,
        implementation_digest=grader.implementation_digest,
        calibrated_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=30),
        human_labelled_suite_digest=SHA_A,
        sample_size=30,
        confusion_matrix=(15, 15, 0, 0),
        balanced_accuracy=1,
        f1=1,
        slice_metrics=(
            ("all", 30, 1, 1, 15, 15, 0, 0),
            ("high-risk", 30, 1, 1, 15, 15, 0, 0),
        ),
    )
    benchmark = BenchmarkDefinition(
        benchmark_id="vivi-customer-assistant",
        revision="v1",
        authority_class=AuthorityClass.VINFAST_ACCEPTANCE,
        suite_id="vivi-golden-v1",
        suite_digest=released_suite().suite_digest,
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
        baseline_policy_digest=baseline_policy().policy_digest,
        max_attempts=3,
        retryable_failure_codes=("provider-timeout",),
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
        evaluation_claim="Candidate remains non-inferior on governed metrics.",
        subject_under_test="assistant-2.0.0",
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
            human_labelled_suite_digest=(calibration.human_labelled_suite_digest),
            calibrated_at=calibration.calibrated_at,
            expires_at=calibration.expires_at,
        ),
    )
    assert not hasattr(plan, "promoted")
    schema = json.loads(
        (Path(__file__).parents[4] / "contracts/ai/evaluation/run-request.schema.json").read_text()
    )
    validator = validator_for(schema)(schema, format_checker=None)
    assert list(validator.iter_errors(cast(Any, plan.contract_document))) == []
    assert plan.contract_document["requestDigest"] == plan.content_digest


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
    expired = GraderCalibration.issue(
        grader_revision=calibration.grader_revision,
        grader_definition_digest=calibration.grader_definition_digest,
        implementation_digest=calibration.implementation_digest,
        calibrated_at=calibration.calibrated_at,
        expires_at=NOW,
        human_labelled_suite_digest=calibration.human_labelled_suite_digest,
        sample_size=calibration.sample_size,
        confusion_matrix=calibration.confusion_matrix,
        balanced_accuracy=calibration.balanced_accuracy,
        f1=calibration.f1,
        slice_metrics=calibration.slice_metrics,
    )
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
    mismatched = GraderCalibration.issue(
        grader_revision=calibration.grader_revision,
        grader_definition_digest=calibration.grader_definition_digest,
        implementation_digest=SHA_A,
        calibrated_at=calibration.calibrated_at,
        expires_at=calibration.expires_at,
        human_labelled_suite_digest=calibration.human_labelled_suite_digest,
        sample_size=calibration.sample_size,
        confusion_matrix=calibration.confusion_matrix,
        balanced_accuracy=calibration.balanced_accuracy,
        f1=calibration.f1,
        slice_metrics=calibration.slice_metrics,
    )
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


def test_budget_policy_rejects_duration_that_cannot_persist_as_milliseconds() -> None:
    with pytest.raises(ValueError, match="INVALID_EVALUATION_BUDGET"):
        BudgetPolicy(
            max_input_tokens=1,
            max_output_tokens=1,
            max_duration_seconds=2_147_484,
            max_cost_usd=0,
        )


def test_calibration_requires_an_aware_ordered_validity_window() -> None:
    _, _, grader, _ = definitions()
    naive = datetime(2026, 7, 28, 12)

    with pytest.raises(ValueError, match="INVALID_CALIBRATION_WINDOW"):
        GraderCalibration.issue(
            grader_revision=grader.revision,
            grader_definition_digest=grader.definition_digest,
            implementation_digest=grader.implementation_digest,
            calibrated_at=naive,
            expires_at=naive + timedelta(days=30),
            human_labelled_suite_digest=SHA_A,
            sample_size=30,
            confusion_matrix=(15, 15, 0, 0),
            balanced_accuracy=1,
            f1=1,
            slice_metrics=(
                ("all", 30, 1, 1, 15, 15, 0, 0),
                ("high-risk", 30, 1, 1, 15, 15, 0, 0),
            ),
        )

    with pytest.raises(ValueError, match="INVALID_CALIBRATION_WINDOW"):
        GraderCalibration.issue(
            grader_revision=grader.revision,
            grader_definition_digest=grader.definition_digest,
            implementation_digest=grader.implementation_digest,
            calibrated_at=NOW,
            expires_at=NOW,
            human_labelled_suite_digest=SHA_A,
            sample_size=30,
            confusion_matrix=(15, 15, 0, 0),
            balanced_accuracy=1,
            f1=1,
            slice_metrics=(
                ("all", 30, 1, 1, 15, 15, 0, 0),
                ("high-risk", 30, 1, 1, 15, 15, 0, 0),
            ),
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


def test_plan_digest_uses_shared_unicode_canonical_json() -> None:
    benchmark, metric, grader, calibration = definitions()
    del metric, grader, calibration
    plan = EvaluationRunPlan(
        run_id="eval:unicode:0001",
        authority_class=benchmark.authority_class,
        candidate_release_id="assistant-2.0.0",
        candidate_manifest_digest=SHA_A,
        baseline_release_id="assistant-1.9.0",
        baseline_manifest_digest=SHA_B,
        benchmark_definition_digest=benchmark.definition_digest,
        suite_id=benchmark.suite_id,
        suite_digest=benchmark.suite_digest,
        runner_image_digest=benchmark.runner_image_digest,
        harness_revision=benchmark.harness_revision,
        tool_simulator_revision=benchmark.tool_simulator_revision,
        metric_revisions=benchmark.metric_revisions,
        grader_revisions=benchmark.grader_revisions,
        grader_calibrations=(),
        environment_revision=benchmark.environment_revision,
        random_seed=1,
        budgets=benchmark.budgets,
        evaluation_claim="Đánh giá trợ lý tiếng Việt chính xác.",
        subject_under_test="trợ-lý-vivi",
        requested_at=NOW,
        max_attempts=benchmark.max_attempts,
        retryable_failure_codes=benchmark.retryable_failure_codes,
        baseline_policy_digest=benchmark.baseline_policy_digest,
    )

    assert plan.content_digest == digest_document(plan.canonical_document)


def test_calibration_rejects_statistics_inconsistent_with_confusion_matrix() -> None:
    _, _, grader, _ = definitions()
    with pytest.raises(ValueError, match="INVALID_CALIBRATION_WINDOW"):
        GraderCalibration.issue(
            grader_revision=grader.revision,
            grader_definition_digest=grader.definition_digest,
            implementation_digest=grader.implementation_digest,
            calibrated_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=30),
            human_labelled_suite_digest=SHA_A,
            sample_size=30,
            confusion_matrix=(15, 15, 0, 0),
            balanced_accuracy=0,
            f1=0,
            slice_metrics=(
                ("all", 30, 0, 0, 0, 0, 15, 15),
                ("high-risk", 30, 0, 0, 0, 0, 15, 15),
            ),
        )
