from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from app.modules.evaluation.domain.evidence import VerifiedEvidenceBundle
from app.modules.evaluation.domain.validation import is_bounded_text, is_sha256


class EvaluationRunState(StrEnum):
    REQUESTED = "requested"
    QUEUED = "queued"
    RUNNING = "running"
    GRADING = "grading"
    COMPARING = "comparing"
    DECISION_READY = "decision_ready"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INVALID = "invalid"


_TRANSITIONS = {
    EvaluationRunState.REQUESTED: frozenset(
        {
            EvaluationRunState.QUEUED,
            EvaluationRunState.CANCELLED,
            EvaluationRunState.INVALID,
        }
    ),
    EvaluationRunState.QUEUED: frozenset(
        {
            EvaluationRunState.RUNNING,
            EvaluationRunState.CANCELLED,
            EvaluationRunState.INVALID,
        }
    ),
    EvaluationRunState.RUNNING: frozenset(
        {
            EvaluationRunState.GRADING,
            EvaluationRunState.FAILED,
            EvaluationRunState.CANCELLED,
            EvaluationRunState.INVALID,
        }
    ),
    EvaluationRunState.GRADING: frozenset(
        {
            EvaluationRunState.COMPARING,
            EvaluationRunState.FAILED,
            EvaluationRunState.CANCELLED,
            EvaluationRunState.INVALID,
        }
    ),
    EvaluationRunState.COMPARING: frozenset(
        {
            EvaluationRunState.FAILED,
            EvaluationRunState.CANCELLED,
            EvaluationRunState.INVALID,
        }
    ),
}
_TERMINAL_STATES = frozenset(
    {
        EvaluationRunState.DECISION_READY,
        EvaluationRunState.FAILED,
        EvaluationRunState.CANCELLED,
        EvaluationRunState.INVALID,
    }
)


class EvaluationRunTransitionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    run_id: str
    plan_digest: str
    state: EvaluationRunState
    completed_case_count: int
    attempt_count: int
    row_version: int
    evidence_bundle_digest: str | None = None
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if (
            not is_bounded_text(self.run_id, maximum=160)
            or not is_sha256(self.plan_digest)
            or self.completed_case_count < 0
            or self.attempt_count < 0
            or self.row_version < 0
            or (
                self.evidence_bundle_digest is not None
                and not is_sha256(self.evidence_bundle_digest)
            )
            or (
                self.failure_code is not None
                and not is_bounded_text(self.failure_code, maximum=160)
            )
        ):
            raise EvaluationRunTransitionError("INVALID_EVALUATION_RUN")
        if self.state is EvaluationRunState.DECISION_READY and (
            self.evidence_bundle_digest is None
        ):
            raise EvaluationRunTransitionError("MISSING_EVALUATION_EVIDENCE")
        if self.state in {EvaluationRunState.FAILED, EvaluationRunState.INVALID} and (
            self.failure_code is None
        ):
            raise EvaluationRunTransitionError("RUN_FAILURE_CODE_REQUIRED")

    @classmethod
    def requested(cls, *, run_id: str, plan_digest: str) -> EvaluationRun:
        return cls(
            run_id=run_id,
            plan_digest=plan_digest,
            state=EvaluationRunState.REQUESTED,
            completed_case_count=0,
            attempt_count=0,
            row_version=0,
        )

    def transition(self, target: EvaluationRunState) -> EvaluationRun:
        if target not in _TRANSITIONS.get(self.state, frozenset()):
            raise EvaluationRunTransitionError(
                f"ILLEGAL_RUN_TRANSITION:{self.state.value}:{target.value}"
            )
        return replace(
            self,
            state=target,
            attempt_count=(
                self.attempt_count + 1
                if target is EvaluationRunState.RUNNING
                else self.attempt_count
            ),
            row_version=self.row_version + 1,
        )

    def record_progress(self, *, completed_case_count: int) -> EvaluationRun:
        if self.state is not EvaluationRunState.RUNNING:
            raise EvaluationRunTransitionError("PROGRESS_NOT_RUNNING")
        if completed_case_count < self.completed_case_count:
            raise EvaluationRunTransitionError("PROGRESS_REGRESSION")
        if completed_case_count == self.completed_case_count:
            return self
        return replace(
            self,
            completed_case_count=completed_case_count,
            row_version=self.row_version + 1,
        )

    def cancel(self) -> EvaluationRun:
        if self.state is EvaluationRunState.CANCELLED:
            return self
        if self.state in _TERMINAL_STATES:
            raise EvaluationRunTransitionError("RUN_ALREADY_TERMINAL")
        return self.transition(EvaluationRunState.CANCELLED)

    def seal(self, evidence: VerifiedEvidenceBundle) -> EvaluationRun:
        if self.state is not EvaluationRunState.COMPARING:
            raise EvaluationRunTransitionError("RUN_NOT_COMPARING")
        if evidence.run_id != self.run_id or evidence.plan_digest != self.plan_digest:
            raise EvaluationRunTransitionError("EVIDENCE_RUN_BINDING_MISMATCH")
        return replace(
            self,
            state=EvaluationRunState.DECISION_READY,
            evidence_bundle_digest=evidence.bundle_digest,
            row_version=self.row_version + 1,
        )

    def fail(
        self,
        *,
        failure_code: str,
        invalid: bool = False,
    ) -> EvaluationRun:
        if not is_bounded_text(failure_code, maximum=160):
            raise EvaluationRunTransitionError("RUN_FAILURE_CODE_REQUIRED")
        target = (
            EvaluationRunState.INVALID if invalid else EvaluationRunState.FAILED
        )
        if target not in _TRANSITIONS.get(self.state, frozenset()):
            raise EvaluationRunTransitionError(
                f"ILLEGAL_RUN_TRANSITION:{self.state.value}:{target.value}"
            )
        return replace(
            self,
            state=target,
            failure_code=failure_code,
            row_version=self.row_version + 1,
        )
