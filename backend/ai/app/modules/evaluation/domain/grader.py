from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.modules.evaluation.domain.validation import is_bounded_text, is_sha256


class GraderKind(StrEnum):
    DETERMINISTIC = "deterministic"
    CITATION = "citation"
    NLI = "nli"
    MODEL_JUDGE = "model-judge"
    HUMAN = "human"


@dataclass(frozen=True, slots=True)
class GraderDefinition:
    revision: str
    kind: GraderKind
    definition_digest: str
    implementation_digest: str
    calibration_required: bool

    def __post_init__(self) -> None:
        if (
            not is_bounded_text(self.revision)
            or not is_sha256(self.definition_digest)
            or not is_sha256(self.implementation_digest)
        ):
            raise ValueError("INVALID_GRADER_DEFINITION")
        if self.kind in {GraderKind.NLI, GraderKind.MODEL_JUDGE} and not (
            self.calibration_required
        ):
            raise ValueError("GRADER_CALIBRATION_REQUIRED")


@dataclass(frozen=True, slots=True)
class GraderCalibration:
    grader_revision: str
    grader_definition_digest: str
    implementation_digest: str
    calibrated_at: datetime
    expires_at: datetime
    evidence_digest: str

    def __post_init__(self) -> None:
        if (
            not is_bounded_text(self.grader_revision)
            or not is_sha256(self.grader_definition_digest)
            or not is_sha256(self.implementation_digest)
            or not is_sha256(self.evidence_digest)
            or self.calibrated_at.tzinfo is None
            or self.calibrated_at.utcoffset() is None
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
            or self.expires_at <= self.calibrated_at
        ):
            raise ValueError("INVALID_CALIBRATION_WINDOW")
