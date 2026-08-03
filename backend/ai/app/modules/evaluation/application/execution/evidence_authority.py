from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import cast

from app.modules.evaluation.application.ports import (
    EvaluationDefinitionRegistry,
    EvaluationEvidenceRepository,
    EvaluationRunRegistry,
)
from app.modules.evaluation.domain import (
    AuthorityClass,
    BudgetPolicy,
    CalibrationBinding,
    EvaluationRun,
    EvaluationRunState,
    build_verified_evidence,
)


class EvidenceAuthorityError(ValueError):
    pass


class EvidenceBundleAuthority:
    def __init__(
        self,
        *,
        runs: EvaluationRunRegistry,
        evidence: EvaluationEvidenceRepository,
        definitions: EvaluationDefinitionRegistry,
        clock: Callable[[], datetime],
    ) -> None:
        self._runs = runs
        self._evidence = evidence
        self._definitions = definitions
        self._clock = clock

    async def seal(
        self,
        *,
        run_id: str,
    ) -> EvaluationRun:
        run = await self._runs.get(run_id)
        plan = await self._runs.get_plan_document(run_id)
        if run is None or plan is None:
            raise EvidenceAuthorityError("EVALUATION_RUN_NOT_FOUND")
        if run.state is not EvaluationRunState.COMPARING:
            raise EvidenceAuthorityError("EVALUATION_RUN_NOT_COMPARING")
        plan_suite = cast(dict[str, object], plan["suite"])
        suite = await self._definitions.get_suite(
            str(plan_suite["id"]),
            str(plan_suite["digest"]),
        )
        baseline_policy_digest = str(plan["baselinePolicyDigest"])
        baseline_policy = await self._definitions.get_baseline_policy(baseline_policy_digest)
        if suite is None or baseline_policy is None:
            raise EvidenceAuthorityError("EVALUATION_ARTIFACT_AUTHORITY_MISSING")
        if run.completed_case_count != len(suite.case_bindings):
            raise EvidenceAuthorityError("EVALUATION_RUN_PROGRESS_INCOMPLETE")
        if (
            plan_suite["id"] != suite.suite_id
            or plan_suite["digest"] != suite.suite_digest
            or str(plan["authorityClass"]) != suite.authority_class.value
            or baseline_policy_digest != baseline_policy.policy_digest
        ):
            raise EvidenceAuthorityError("EVALUATION_ARTIFACT_BINDING_MISMATCH")

        budget_document = cast(dict[str, object], plan["budgets"])
        candidate = cast(dict[str, object], plan["candidate"])
        baseline = cast(dict[str, object] | None, plan["baseline"])
        calibrations = cast(list[dict[str, object]], plan["graderCalibrations"])
        calibration_bindings = tuple(
            CalibrationBinding(
                grader_revision=str(binding["graderRevision"]),
                grader_definition_digest=str(binding["definitionDigest"]),
                implementation_digest=str(binding["implementationDigest"]),
                calibration_digest=str(binding["calibrationDigest"]),
                human_labelled_suite_digest=str(binding["humanLabelledSuiteDigest"]),
                calibrated_at=datetime.fromisoformat(str(binding["calibratedAt"])),
                expires_at=datetime.fromisoformat(str(binding["expiresAt"])),
            )
            for binding in calibrations
        )
        for binding in calibration_bindings:
            grader = await self._definitions.get_grader(binding.grader_revision)
            calibration = await self._definitions.get_calibration(binding.grader_revision)
            if (
                grader is None
                or calibration is None
                or grader.definition_digest != binding.grader_definition_digest
                or grader.implementation_digest != binding.implementation_digest
                or calibration.evidence_digest != binding.calibration_digest
                or calibration.human_labelled_suite_digest != binding.human_labelled_suite_digest
                or calibration.calibrated_at != binding.calibrated_at
                or calibration.expires_at != binding.expires_at
            ):
                raise EvidenceAuthorityError("EVALUATION_CALIBRATION_AUTHORITY_MISMATCH")
        cases = await self._evidence.list_case_results(run_id)
        try:
            bundle = build_verified_evidence(
                run_id=run.run_id,
                plan_digest=run.plan_digest,
                authority_class=AuthorityClass(str(plan["authorityClass"])),
                suite=suite,
                cases=cases,
                required_metrics=tuple(
                    str(value) for value in cast(list[object], plan["metricRevisions"])
                ),
                required_graders=tuple(
                    str(value) for value in cast(list[object], plan["graderRevisions"])
                ),
                grader_kinds=tuple(
                    (
                        str(cast(dict[str, object], value)["revision"]),
                        str(cast(dict[str, object], value)["kind"]),
                    )
                    for value in cast(list[object], plan["graderKinds"])
                ),
                grader_calibrations=calibration_bindings,
                budget=BudgetPolicy(
                    max_input_tokens=int(str(budget_document["maxInputTokens"])),
                    max_output_tokens=int(str(budget_document["maxOutputTokens"])),
                    max_duration_seconds=int(str(budget_document["maxDurationSeconds"])),
                    max_cost_usd=float(str(budget_document["maxCostUsd"])),
                ),
                baseline_policy=baseline_policy,
                benchmark_definition_digest=str(plan["benchmarkDefinitionDigest"]),
                candidate_release_id=str(candidate["releaseId"]),
                candidate_manifest_digest=str(candidate["manifestDigest"]),
                baseline_release_id=(None if baseline is None else str(baseline["releaseId"])),
                baseline_manifest_digest=(
                    None if baseline is None else str(baseline["manifestDigest"])
                ),
                created_at=self._clock(),
                started_at=datetime.fromisoformat(str(plan["requestedAt"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceAuthorityError(str(exc)) from exc

        sealed = run.seal(bundle)
        await self._evidence.seal(
            sealed,
            bundle,
            expected_version=run.row_version,
        )
        return sealed
