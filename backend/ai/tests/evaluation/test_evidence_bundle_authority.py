import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema.validators import validator_for

from app.modules.evaluation.application.execution import (
    EvidenceAuthorityError,
    EvidenceBundleAuthority,
)
from app.modules.evaluation.application.release_gate import (
    evaluate_sealed_evidence_for_release,
)
from app.modules.evaluation.domain import (
    MANDATORY_HARD_GATE_REVISIONS,
    AuthorityClass,
    BaselinePolicySnapshot,
    BudgetPolicy,
    CalibrationBinding,
    EvaluationCaseResult,
    EvaluationRun,
    EvaluationRunState,
    EvaluationSuiteAuthority,
    EvaluationSuiteSnapshot,
    EvaluationUsage,
    GraderCalibration,
    GraderCaseOutcome,
    GraderDefinition,
    GraderKind,
    MetricCaseOutcome,
    VerifiedEvidenceBundle,
    build_verified_evidence,
    canonical_json,
    evaluation_case_bindings_digest,
)
from app.modules.evaluation.domain.evidence import _wilson_95
from app.modules.evaluation.infrastructure.postgres_execution_repository import (
    _remaining_cost_usd,
)

SHA_A = f"sha256:{'a' * 64}"
SHA_B = f"sha256:{'b' * 64}"
SHA_C = f"sha256:{'c' * 64}"
SHA_D = f"sha256:{'d' * 64}"
NOW = datetime(2026, 7, 30, 12, tzinfo=UTC)
RUN_ID = "eval:authority:0001"


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
                    "metric_revision": "citation-validity-v1",
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


def suite() -> EvaluationSuiteSnapshot:
    bindings = (("golden.001", SHA_A), ("golden.002", SHA_B))
    authority = EvaluationSuiteAuthority.issue(
        suite_id="vivi-golden-v1",
        authority_class=AuthorityClass.PUBLIC_DIAGNOSTIC,
        qualification_profile="public-diagnostic-v1",
        qualification_policy_digest=SHA_A,
        case_bindings_digest=evaluation_case_bindings_digest(bindings),
        case_composition_digest=SHA_B,
        risk_taxonomy_digest=SHA_A,
        provenance_digest=SHA_B,
        provenance_status="verified",
        provenance_evidence_uri="evidence://suite/provenance",
        contamination_scan_digest=SHA_C,
        contamination_status="passed",
        contamination_evidence_uri="evidence://suite/contamination",
        held_out=True,
        author_subject="subject:fixture-author",
        evaluator_subject="subject:fixture-evaluator",
        release_owner_subject="subject:fixture-release-owner",
    )
    return EvaluationSuiteSnapshot.issue(
        suite_id="vivi-golden-v1",
        case_bindings=bindings,
        authority=authority,
    )


def required_graders() -> tuple[str, ...]:
    return tuple(sorted(MANDATORY_HARD_GATE_REVISIONS))


def required_metrics() -> tuple[str, ...]:
    return ("citation-validity-v1",)


def grader_kinds() -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            revision,
            "citation" if revision == "citation-validity-v1" else "deterministic",
        )
        for revision in required_graders()
    )


def calibrations(
    *,
    expires_at: datetime = NOW + timedelta(days=30),
) -> tuple[CalibrationBinding, ...]:
    return tuple(
        CalibrationBinding(
            grader_revision=revision,
            grader_definition_digest=SHA_A,
            implementation_digest=SHA_B,
            calibration_digest=authoritative_calibration(
                revision,
                expires_at=expires_at,
            ).evidence_digest,
            human_labelled_suite_digest=SHA_D,
            calibrated_at=NOW - timedelta(days=1),
            expires_at=expires_at,
        )
        for revision in required_graders()
    )


def authoritative_calibration(
    revision: str,
    *,
    expires_at: datetime = NOW + timedelta(days=30),
) -> GraderCalibration:
    return GraderCalibration.issue(
        grader_revision=revision,
        grader_definition_digest=SHA_A,
        implementation_digest=SHA_B,
        calibrated_at=NOW - timedelta(days=1),
        expires_at=expires_at,
        human_labelled_suite_digest=SHA_D,
        sample_size=30,
        confusion_matrix=(15, 15, 0, 0),
        balanced_accuracy=1,
        f1=1,
        slice_metrics=(
            ("all", 30, 1, 1, 15, 15, 0, 0),
            ("high-risk", 30, 1, 1, 15, 15, 0, 0),
        ),
    )


def case_result(
    case_id: str,
    case_digest: str,
    *,
    attempt: int = 1,
    failing_grader: str | None = None,
    input_tokens: int = 10,
) -> EvaluationCaseResult:
    return EvaluationCaseResult.issue(
        run_id=RUN_ID,
        case_id=case_id,
        case_digest=case_digest,
        attempt=attempt,
        status="valid",
        output_digest=SHA_C,
        latency_ms=125,
        usage=EvaluationUsage(
            input_tokens=input_tokens,
            output_tokens=5,
            cost_usd=0.01,
        ),
        sanitized_trace_ref="artifact://evaluation/case-redacted",
        metric_outputs=(
            MetricCaseOutcome(
                metric_revision=required_metrics()[0],
                slice="all",
                value=1,
            ),
        ),
        grader_outputs=tuple(
            GraderCaseOutcome(
                grader_revision=revision,
                outcome="fail" if revision == failing_grader else "pass",
                evidence_digest=SHA_D,
            )
            for revision in required_graders()
        ),
    )


def test_case_result_rejects_latency_outside_postgres_integer_domain() -> None:
    with pytest.raises(ValueError, match="INVALID_EVALUATION_CASE_RESULT"):
        EvaluationCaseResult.issue(
            run_id=RUN_ID,
            case_id="golden.latency.overflow",
            case_digest=SHA_A,
            attempt=1,
            status="failed",
            output_digest=None,
            latency_ms=2_147_483_648,
            usage=EvaluationUsage(input_tokens=0, output_tokens=0, cost_usd=0),
            sanitized_trace_ref=None,
            metric_outputs=(),
            grader_outputs=(),
            validity_flags=("runner-unavailable",),
        )


def cases() -> tuple[EvaluationCaseResult, ...]:
    return (
        case_result("golden.001", SHA_A),
        case_result("golden.002", SHA_B),
    )


def build(
    *,
    case_results: tuple[EvaluationCaseResult, ...] | None = None,
    budget: BudgetPolicy | None = None,
    kinds: tuple[tuple[str, str], ...] | None = None,
    bindings: tuple[CalibrationBinding, ...] | None = None,
    policy: BaselinePolicySnapshot | None = None,
) -> VerifiedEvidenceBundle:
    return build_verified_evidence(
        run_id=RUN_ID,
        plan_digest=SHA_A,
        authority_class=AuthorityClass.PUBLIC_DIAGNOSTIC,
        suite=suite(),
        cases=cases() if case_results is None else case_results,
        required_metrics=required_metrics(),
        required_graders=required_graders(),
        grader_kinds=grader_kinds() if kinds is None else kinds,
        grader_calibrations=(calibrations() if bindings is None else bindings),
        budget=budget
        or BudgetPolicy(
            max_input_tokens=100,
            max_output_tokens=100,
            max_duration_seconds=10,
            max_cost_usd=1,
        ),
        baseline_policy=baseline_policy() if policy is None else policy,
        benchmark_definition_digest=SHA_B,
        candidate_release_id="assistant-2.0.0",
        candidate_manifest_digest=SHA_C,
        baseline_release_id="assistant-1.9.0",
        baseline_manifest_digest=SHA_D,
        created_at=NOW,
        started_at=NOW - timedelta(minutes=1),
    )


def test_bundle_recomputes_case_run_report_and_bundle_digests() -> None:
    evidence = build()

    assert evidence.recommendation == "needs-human-decision"
    assert evidence.authority_class is AuthorityClass.PUBLIC_DIAGNOSTIC
    assert evidence.contract_document["case_set_complete"] is True
    assert evidence.contract_document["human_approval_included"] is False
    assert evidence.bundle_digest.startswith("sha256:")
    assert (
        evidence.semantic_document["sanitized_report_digest"]
        != evidence.semantic_document["run_result_digest"]
    )
    run_result = cast(dict[str, object], evidence.semantic_document["run_result"])
    metrics = cast(list[dict[str, object]], run_result["metrics"])
    assert metrics == [
        {
            "lower_95": 0.342380227506653,
            "metric_revision": "citation-validity-v1",
            "sample_size": 2,
            "slice": "all",
            "upper_95": 1.0,
            "value": 1.0,
        }
    ]


def test_bundle_rejects_missing_protected_metric_slice() -> None:
    document = deepcopy(baseline_policy().semantic_document)
    protected = cast(list[dict[str, object]], document["protected_metrics"])
    protected[0]["required_slices"] = ["all", "vi-VN"]
    stricter_policy = BaselinePolicySnapshot.issue(document)

    with pytest.raises(
        ValueError,
        match="EVIDENCE_PROTECTED_METRIC_SLICE_MISSING",
    ):
        build(policy=stricter_policy)


def test_case_and_bundle_documents_match_canonical_contracts() -> None:
    root = Path(__file__).parents[4]
    for relative, document in (
        (
            "contracts/ai/evaluation/case-result.schema.json",
            cases()[0].contract_document,
        ),
        (
            "contracts/ai/evaluation/evidence-bundle.schema.json",
            build().contract_document,
        ),
        (
            "contracts/ai/evaluation/run-result.schema.json",
            build().semantic_document["run_result"],
        ),
        (
            "contracts/ai/evaluation/baseline-policy.schema.json",
            baseline_policy().contract_document,
        ),
    ):
        schema = json.loads((root / relative).read_text())
        validator = validator_for(schema)(schema, format_checker=None)
        assert list(validator.iter_errors(cast(Any, document))) == []


def test_exact_suite_budget_calibration_and_grader_authority_fail_closed() -> None:
    with pytest.raises(ValueError, match="CASE_SET_INCOMPLETE"):
        build(case_results=cases()[:1])
    with pytest.raises(ValueError, match="BUDGET_EXCEEDED"):
        build(
            budget=BudgetPolicy(
                max_input_tokens=1,
                max_output_tokens=100,
                max_duration_seconds=10,
                max_cost_usd=1,
            )
        )
    with pytest.raises(ValueError, match="GRADER_AUTHORITY_INCOMPLETE"):
        build(bindings=calibrations(expires_at=NOW))
    with pytest.raises(ValueError, match="GRADER_AUTHORITY_INCOMPLETE"):
        build(kinds=tuple((revision, "model-judge") for revision in required_graders()))


def test_hard_gate_failure_rejects_but_does_not_fake_human_approval() -> None:
    failing = (
        case_result(
            "golden.001",
            SHA_A,
            failing_grader="acl-leakage-v1",
        ),
        case_result("golden.002", SHA_B),
    )

    evidence = build(case_results=failing)

    assert evidence.recommendation == "reject"
    assert evidence.contract_document["hard_gate_failures"] == ["acl-leakage-v1"]
    assert evidence.contract_document["human_approval_included"] is False


def test_release_integration_stays_human_gated_and_never_promotes() -> None:
    evidence = build()

    decision = evaluate_sealed_evidence_for_release(
        evidence,
        candidate_release_id="assistant-2.0.0",
        candidate_manifest_digest=SHA_C,
    )

    assert decision.passed is False
    assert decision.failures == (
        "NON_ACCEPTANCE_EVIDENCE",
        "HUMAN_DECISION_REQUIRED",
    )
    assert decision.evidence_ids == (evidence.bundle_digest,)
    assert decision.promoted is False


def test_case_tamper_and_suite_binding_tamper_are_rejected() -> None:
    with pytest.raises(ValueError, match="CASE_RESULT_DIGEST_MISMATCH"):
        replace(
            cases()[0],
            usage=EvaluationUsage(
                input_tokens=999,
                output_tokens=5,
                cost_usd=0.01,
            ),
        )

    released = suite()
    with pytest.raises(ValueError, match="INVALID_EVALUATION_SUITE_SNAPSHOT"):
        EvaluationSuiteSnapshot(
            suite_id=released.suite_id,
            suite_digest=released.suite_digest,
            case_bindings=(released.case_bindings[0],),
            authority_class=released.authority_class,
            qualification_profile=released.qualification_profile,
            qualification_policy_digest=(
                released.qualification_policy_digest
            ),
            case_composition_digest=released.case_composition_digest,
            risk_taxonomy_digest=released.risk_taxonomy_digest,
            provenance_digest=released.provenance_digest,
            provenance_status=released.provenance_status,
            provenance_evidence_uri=released.provenance_evidence_uri,
            contamination_scan_digest=released.contamination_scan_digest,
            contamination_status=released.contamination_status,
            contamination_evidence_uri=(
                released.contamination_evidence_uri
            ),
            held_out=released.held_out,
            author_subject=released.author_subject,
            evaluator_subject=released.evaluator_subject,
            release_owner_subject=released.release_owner_subject,
            authority_record_digest=released.authority_record_digest,
        )


def test_acceptance_suite_requires_held_out_500_case_independent_authority() -> None:
    bindings = tuple(
        (f"acceptance.{index:03d}", f"sha256:{index:064x}")
        for index in range(1, 500)
    )
    authority = EvaluationSuiteAuthority.issue(
        suite_id="vivi-acceptance-v1",
        authority_class=AuthorityClass.VINFAST_ACCEPTANCE,
        qualification_profile="vivi-customer-assistant-v1",
        qualification_policy_digest=SHA_A,
        case_bindings_digest=evaluation_case_bindings_digest(bindings),
        case_composition_digest=SHA_B,
        risk_taxonomy_digest=SHA_A,
        provenance_digest=SHA_B,
        provenance_status="verified",
        provenance_evidence_uri="evidence://suite/provenance",
        contamination_scan_digest=SHA_C,
        contamination_status="passed",
        contamination_evidence_uri="evidence://suite/contamination",
        held_out=True,
        author_subject="subject:dataset-author",
        evaluator_subject="subject:independent-evaluator",
        release_owner_subject="subject:dataset-release-owner",
    )
    with pytest.raises(
        ValueError,
        match="INVALID_EVALUATION_SUITE_SNAPSHOT",
    ):
        EvaluationSuiteSnapshot.issue(
            suite_id="vivi-acceptance-v1",
            case_bindings=bindings,
            authority=authority,
        )
    with pytest.raises(
        ValueError,
        match="INVALID_EVALUATION_SUITE_AUTHORITY",
    ):
        EvaluationSuiteAuthority.issue(
            suite_id="vivi-acceptance-v1",
            authority_class=AuthorityClass.VINFAST_ACCEPTANCE,
            qualification_profile="vivi-customer-assistant-v1",
            qualification_policy_digest=SHA_A,
            case_bindings_digest=SHA_B,
            case_composition_digest=SHA_B,
            risk_taxonomy_digest=SHA_A,
            provenance_digest=SHA_B,
            provenance_status="verified",
            provenance_evidence_uri="evidence://suite/provenance",
            contamination_scan_digest=SHA_C,
            contamination_status="passed",
            contamination_evidence_uri="evidence://suite/contamination",
            held_out=True,
            author_subject="subject:dataset-author",
            evaluator_subject="subject:dataset-author",
            release_owner_subject="subject:dataset-release-owner",
        )


def test_canonical_json_matches_jcs_number_and_unicode_forms() -> None:
    assert canonical_json({"v": "Việt", "x": 1.0}) == '{"v":"Việt","x":1}'
    assert canonical_json({"n": 1e-7}) == '{"n":1e-7}'
    assert canonical_json({"n": 1e21}) == '{"n":1e+21}'
    assert canonical_json({"n": -0.0}) == '{"n":0}'


def test_usage_cost_uses_fixed_precision_for_exact_budget_reservation() -> None:
    with pytest.raises(ValueError, match="INVALID_EVALUATION_USAGE"):
        EvaluationUsage(
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.1234567,
        )
    assert _remaining_cost_usd(
        budget=Decimal("1.000000"),
        consumed=Decimal("0.123457"),
    ) == 0.876543
    with pytest.raises(ValueError, match="INVALID_EVALUATION_USAGE"):
        EvaluationUsage(
            input_tokens=1,
            output_tokens=1,
            cost_usd=1_000_000.000001,
        )


class FakeRuns:
    def __init__(self, run: EvaluationRun, plan: dict[str, object]) -> None:
        self.run = run
        self.plan = plan

    async def get(self, run_id: str) -> EvaluationRun | None:
        return self.run if run_id == self.run.run_id else None

    async def get_plan_document(
        self,
        run_id: str,
    ) -> dict[str, object] | None:
        return self.plan if run_id == self.run.run_id else None


class FakeEvidence:
    def __init__(
        self,
        results: tuple[EvaluationCaseResult, ...],
    ) -> None:
        self.results = results
        self.sealed: VerifiedEvidenceBundle | None = None

    async def list_case_results(
        self,
        run_id: str,
    ) -> tuple[EvaluationCaseResult, ...]:
        return self.results

    async def seal(
        self,
        run: EvaluationRun,
        evidence: VerifiedEvidenceBundle,
        *,
        expected_version: int,
    ) -> None:
        assert expected_version + 1 == run.row_version
        self.sealed = evidence


class FakeDefinitions:
    def __init__(
        self,
        released_suite: EvaluationSuiteSnapshot,
        policy: BaselinePolicySnapshot,
    ) -> None:
        self.suite = released_suite
        self.policy = policy

    async def get_suite(
        self,
        suite_id: str,
        suite_digest: str,
    ) -> EvaluationSuiteSnapshot | None:
        if (suite_id, suite_digest) == (
            self.suite.suite_id,
            self.suite.suite_digest,
        ):
            return self.suite
        return None

    async def get_baseline_policy(
        self,
        policy_digest: str,
    ) -> BaselinePolicySnapshot | None:
        return self.policy if policy_digest == self.policy.policy_digest else None

    async def get_grader(
        self,
        revision: str,
    ) -> GraderDefinition | None:
        binding = next(
            (item for item in calibrations() if item.grader_revision == revision),
            None,
        )
        if binding is None:
            return None
        return GraderDefinition(
            revision=revision,
            kind=(
                GraderKind.CITATION
                if revision == "citation-validity-v1"
                else GraderKind.DETERMINISTIC
            ),
            definition_digest=binding.grader_definition_digest,
            implementation_digest=binding.implementation_digest,
            calibration_required=True,
        )

    async def get_calibration(
        self,
        grader_revision: str,
    ) -> GraderCalibration | None:
        binding = next(
            (item for item in calibrations() if item.grader_revision == grader_revision),
            None,
        )
        if binding is None or binding.calibrated_at is None or binding.expires_at is None:
            return None
        return authoritative_calibration(
            grader_revision,
            expires_at=binding.expires_at,
        )

    async def get_benchmark(self, benchmark_id: str, revision: str) -> None:
        del benchmark_id, revision
        return None

    async def get_metric(self, revision: str) -> None:
        del revision
        return None


@pytest.mark.asyncio
async def test_evidence_bundle_authority_is_only_transition_path() -> None:
    released_suite = suite()
    policy = baseline_policy()
    run = EvaluationRun(
        run_id=RUN_ID,
        plan_digest=SHA_A,
        state=EvaluationRunState.COMPARING,
        completed_case_count=2,
        attempt_count=1,
        row_version=4,
    )
    plan: dict[str, object] = {
        "authorityClass": "public-diagnostic",
        "baseline": {
            "manifestDigest": SHA_D,
            "releaseId": "assistant-1.9.0",
        },
        "baselinePolicyDigest": policy.policy_digest,
        "benchmarkDefinitionDigest": SHA_B,
        "budgets": {
            "maxCostUsd": 1,
            "maxDurationSeconds": 10,
            "maxInputTokens": 100,
            "maxOutputTokens": 100,
        },
        "candidate": {
            "manifestDigest": SHA_C,
            "releaseId": "assistant-2.0.0",
        },
        "graderCalibrations": [
            {
                "calibratedAt": binding.calibrated_at.isoformat(),
                "calibrationDigest": binding.calibration_digest,
                "definitionDigest": binding.grader_definition_digest,
                "expiresAt": binding.expires_at.isoformat(),
                "graderRevision": binding.grader_revision,
                "humanLabelledSuiteDigest": (binding.human_labelled_suite_digest),
                "implementationDigest": binding.implementation_digest,
            }
            for binding in calibrations()
            if binding.calibrated_at is not None and binding.expires_at is not None
        ],
        "graderKinds": [{"kind": kind, "revision": revision} for revision, kind in grader_kinds()],
        "graderRevisions": list(required_graders()),
        "metricRevisions": list(required_metrics()),
        "requestedAt": (NOW - timedelta(minutes=1)).isoformat(),
        "suite": {
            "digest": released_suite.suite_digest,
            "id": released_suite.suite_id,
        },
    }
    evidence_repository = FakeEvidence(cases())
    authority = EvidenceBundleAuthority(
        runs=FakeRuns(run, plan),  # type: ignore[arg-type]
        evidence=evidence_repository,  # type: ignore[arg-type]
        definitions=FakeDefinitions(released_suite, policy),  # type: ignore[arg-type]
        clock=lambda: NOW,
    )

    sealed = await authority.seal(run_id=RUN_ID)

    assert sealed.state is EvaluationRunState.DECISION_READY
    assert evidence_repository.sealed is not None
    assert sealed.evidence_bundle_digest == (evidence_repository.sealed.bundle_digest)


@pytest.mark.asyncio
async def test_authority_rejects_incomplete_progress_before_seal() -> None:
    released_suite = suite()
    run = EvaluationRun(
        run_id=RUN_ID,
        plan_digest=SHA_A,
        state=EvaluationRunState.COMPARING,
        completed_case_count=1,
        attempt_count=1,
        row_version=4,
    )
    authority = EvidenceBundleAuthority(
        runs=FakeRuns(
            run,
            {
                "baselinePolicyDigest": baseline_policy().policy_digest,
                "suite": {
                    "digest": released_suite.suite_digest,
                    "id": released_suite.suite_id,
                },
            },
        ),  # type: ignore[arg-type]
        evidence=FakeEvidence(cases()),  # type: ignore[arg-type]
        definitions=FakeDefinitions(
            released_suite,
            baseline_policy(),
        ),  # type: ignore[arg-type]
        clock=lambda: NOW,
    )

    with pytest.raises(
        EvidenceAuthorityError,
        match="PROGRESS_INCOMPLETE",
    ):
        await authority.seal(run_id=RUN_ID)


def test_wilson_interval_matches_postgres_numeric_rounding_counterexample() -> None:
    assert _wilson_95([Decimal(0), Decimal(0), Decimal(0)]) == (
        0.0,
        0.561497031755045,
    )
