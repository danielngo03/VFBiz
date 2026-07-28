import json
from dataclasses import dataclass
from hashlib import sha256

from app.modules.evaluation.domain.benchmark import AuthorityClass, BudgetPolicy
from app.modules.evaluation.domain.validation import is_bounded_text, is_sha256


@dataclass(frozen=True, slots=True)
class CalibrationBinding:
    grader_revision: str
    grader_definition_digest: str
    implementation_digest: str
    calibration_digest: str

    def __post_init__(self) -> None:
        if (
            not is_bounded_text(self.grader_revision)
            or not is_sha256(self.grader_definition_digest)
            or not is_sha256(self.implementation_digest)
            or not is_sha256(self.calibration_digest)
        ):
            raise ValueError("INVALID_CALIBRATION_BINDING")


@dataclass(frozen=True, slots=True)
class EvaluationRunPlan:
    run_id: str
    authority_class: AuthorityClass
    candidate_release_id: str
    candidate_manifest_digest: str
    baseline_release_id: str | None
    baseline_manifest_digest: str | None
    benchmark_definition_digest: str
    suite_id: str
    suite_digest: str
    runner_image_digest: str
    harness_revision: str
    tool_simulator_revision: str | None
    metric_revisions: tuple[str, ...]
    grader_revisions: tuple[str, ...]
    grader_calibrations: tuple[CalibrationBinding, ...]
    environment_revision: str
    random_seed: int
    budgets: BudgetPolicy

    @property
    def canonical_document(self) -> dict[str, object]:
        return {
            "authorityClass": self.authority_class.value,
            "baseline": (
                None
                if self.baseline_release_id is None
                else {
                    "manifestDigest": self.baseline_manifest_digest,
                    "releaseId": self.baseline_release_id,
                }
            ),
            "benchmarkDefinitionDigest": self.benchmark_definition_digest,
            "budgets": {
                "maxCostUsd": self.budgets.max_cost_usd,
                "maxDurationSeconds": self.budgets.max_duration_seconds,
                "maxInputTokens": self.budgets.max_input_tokens,
                "maxOutputTokens": self.budgets.max_output_tokens,
            },
            "candidate": {
                "manifestDigest": self.candidate_manifest_digest,
                "releaseId": self.candidate_release_id,
            },
            "environmentRevision": self.environment_revision,
            "graderCalibrations": [
                {
                    "calibrationDigest": binding.calibration_digest,
                    "definitionDigest": binding.grader_definition_digest,
                    "graderRevision": binding.grader_revision,
                    "implementationDigest": binding.implementation_digest,
                }
                for binding in self.grader_calibrations
            ],
            "graderRevisions": list(self.grader_revisions),
            "harnessRevision": self.harness_revision,
            "metricRevisions": list(self.metric_revisions),
            "randomSeed": self.random_seed,
            "runId": self.run_id,
            "runnerImageDigest": self.runner_image_digest,
            "suite": {
                "digest": self.suite_digest,
                "id": self.suite_id,
            },
            "toolSimulatorRevision": self.tool_simulator_revision,
        }

    @property
    def content_digest(self) -> str:
        return digest_plan_document(self.canonical_document)


def digest_plan_document(document: dict[str, object]) -> str:
    canonical = json.dumps(
        document,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return f"sha256:{sha256(canonical).hexdigest()}"
