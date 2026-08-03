from dataclasses import dataclass
from datetime import UTC, datetime

from app.modules.evaluation.domain.benchmark import AuthorityClass, BudgetPolicy
from app.modules.evaluation.domain.canonical import digest_document
from app.modules.evaluation.domain.validation import is_bounded_text, is_sha256


@dataclass(frozen=True, slots=True)
class CalibrationBinding:
    grader_revision: str
    grader_definition_digest: str
    implementation_digest: str
    calibration_digest: str
    human_labelled_suite_digest: str | None = None
    calibrated_at: datetime | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.calibrated_at is not None and self.calibrated_at.tzinfo is not None:
            object.__setattr__(
                self,
                "calibrated_at",
                self.calibrated_at.astimezone(UTC).replace(microsecond=0),
            )
        if self.expires_at is not None and self.expires_at.tzinfo is not None:
            object.__setattr__(
                self,
                "expires_at",
                self.expires_at.astimezone(UTC).replace(microsecond=0),
            )
        if (
            not is_bounded_text(self.grader_revision)
            or not is_sha256(self.grader_definition_digest)
            or not is_sha256(self.implementation_digest)
            or not is_sha256(self.calibration_digest)
            or (
                self.human_labelled_suite_digest is not None
                and not is_sha256(self.human_labelled_suite_digest)
            )
            or (
                self.calibrated_at is not None
                and (self.calibrated_at.tzinfo is None or self.calibrated_at.utcoffset() is None)
            )
            or (
                self.expires_at is not None
                and (self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None)
            )
            or (
                self.calibrated_at is not None
                and self.expires_at is not None
                and self.expires_at <= self.calibrated_at
            )
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
    evaluation_claim: str
    subject_under_test: str
    requested_at: datetime
    max_attempts: int
    retryable_failure_codes: tuple[str, ...]
    grader_kinds: tuple[tuple[str, str], ...] = ()
    baseline_policy_digest: str | None = None

    def __post_init__(self) -> None:
        if (
            not is_bounded_text(self.run_id, maximum=160)
            or not is_bounded_text(self.candidate_release_id, maximum=200)
            or not is_sha256(self.candidate_manifest_digest)
            or (self.baseline_release_id is None) != (self.baseline_manifest_digest is None)
            or (
                self.baseline_release_id is not None
                and (
                    not is_bounded_text(
                        self.baseline_release_id,
                        maximum=200,
                    )
                    or self.baseline_manifest_digest is None
                    or not is_sha256(self.baseline_manifest_digest)
                )
            )
            or not is_sha256(self.benchmark_definition_digest)
            or not is_bounded_text(self.suite_id, maximum=200)
            or not is_sha256(self.suite_digest)
            or not is_sha256(self.runner_image_digest)
            or not self.metric_revisions
            or not self.grader_revisions
            or len(set(self.metric_revisions)) != len(self.metric_revisions)
            or len(set(self.grader_revisions)) != len(self.grader_revisions)
            or self.baseline_policy_digest is None
            or not is_sha256(self.baseline_policy_digest)
            or not is_bounded_text(self.evaluation_claim, maximum=1000)
            or len(self.evaluation_claim) < 8
            or not is_bounded_text(self.subject_under_test, maximum=200)
            or self.requested_at.tzinfo is None
            or self.requested_at.utcoffset() is None
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
        ):
            raise ValueError("INVALID_EVALUATION_RUN_PLAN")

    @property
    def canonical_document(self) -> dict[str, object]:
        return {
            "authorityClass": self.authority_class.value,
            "attemptPolicy": {
                "maxAttempts": self.max_attempts,
                "retryableFailureCodes": list(self.retryable_failure_codes),
            },
            "baseline": (
                None
                if self.baseline_release_id is None
                else {
                    "manifestDigest": self.baseline_manifest_digest,
                    "releaseId": self.baseline_release_id,
                }
            ),
            "benchmarkDefinitionDigest": self.benchmark_definition_digest,
            "baselinePolicyDigest": self.baseline_policy_digest,
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
            "evaluationClaim": self.evaluation_claim,
            "graderCalibrations": [
                {
                    "calibrationDigest": binding.calibration_digest,
                    "definitionDigest": binding.grader_definition_digest,
                    "graderRevision": binding.grader_revision,
                    "implementationDigest": binding.implementation_digest,
                    "humanLabelledSuiteDigest": (binding.human_labelled_suite_digest),
                    "calibratedAt": (
                        None
                        if binding.calibrated_at is None
                        else binding.calibrated_at.astimezone(UTC)
                        .isoformat(timespec="seconds")
                        .replace("+00:00", "Z")
                    ),
                    "expiresAt": (
                        None
                        if binding.expires_at is None
                        else binding.expires_at.astimezone(UTC)
                        .isoformat(timespec="seconds")
                        .replace("+00:00", "Z")
                    ),
                }
                for binding in self.grader_calibrations
            ],
            "graderRevisions": list(self.grader_revisions),
            "graderKinds": [
                {"kind": kind, "revision": revision} for revision, kind in self.grader_kinds
            ],
            "harnessRevision": self.harness_revision,
            "metricRevisions": list(self.metric_revisions),
            "randomSeed": self.random_seed,
            "requestedAt": self.requested_at.isoformat(),
            "runId": self.run_id,
            "runnerImageDigest": self.runner_image_digest,
            "suite": {
                "digest": self.suite_digest,
                "id": self.suite_id,
            },
            "subjectUnderTest": self.subject_under_test,
            "toolSimulatorRevision": self.tool_simulator_revision,
        }

    @property
    def contract_document(self) -> dict[str, object]:
        return {
            **self.canonical_document,
            "requestDigest": self.content_digest,
        }

    @property
    def content_digest(self) -> str:
        return digest_plan_document(self.canonical_document)


def digest_plan_document(document: dict[str, object]) -> str:
    return digest_document(document)
