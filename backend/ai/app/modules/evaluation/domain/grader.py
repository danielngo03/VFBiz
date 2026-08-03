from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction

from app.modules.evaluation.domain.benchmark import MAX_SAFE_JSON_INTEGER
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

    @property
    def canonical_document(self) -> dict[str, object]:
        return {
            "calibration_required": self.calibration_required,
            "definition_digest": self.definition_digest,
            "implementation_digest": self.implementation_digest,
            "kind": self.kind.value,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class GraderCalibration:
    grader_revision: str
    grader_definition_digest: str
    implementation_digest: str
    calibrated_at: datetime
    expires_at: datetime
    evidence_digest: str
    human_labelled_suite_digest: str
    sample_size: int
    confusion_matrix: tuple[int, int, int, int]
    balanced_accuracy: float
    f1: float
    slice_metrics: tuple[
        tuple[str, int, float, float, int, int, int, int],
        ...,
    ]

    def __post_init__(self) -> None:
        if self.calibrated_at.tzinfo is not None and self.calibrated_at.utcoffset() is not None:
            object.__setattr__(
                self,
                "calibrated_at",
                self.calibrated_at.astimezone(UTC).replace(microsecond=0),
            )
        if self.expires_at.tzinfo is not None and self.expires_at.utcoffset() is not None:
            object.__setattr__(
                self,
                "expires_at",
                self.expires_at.astimezone(UTC).replace(microsecond=0),
            )
        true_positive, true_negative, false_positive, false_negative = (
            self.confusion_matrix if len(self.confusion_matrix) == 4 else (-1, -1, -1, -1)
        )
        if (
            not is_bounded_text(self.grader_revision)
            or not is_sha256(self.grader_definition_digest)
            or not is_sha256(self.implementation_digest)
            or not is_sha256(self.evidence_digest)
            or not is_sha256(self.human_labelled_suite_digest)
            or self.sample_size < 30
            or self.sample_size > MAX_SAFE_JSON_INTEGER
            or len(self.confusion_matrix) != 4
            or any(
                value < 0 or value > MAX_SAFE_JSON_INTEGER
                for value in self.confusion_matrix
            )
            or sum(self.confusion_matrix) != self.sample_size
            or not 0 <= self.balanced_accuracy <= 1
            or not 0 <= self.f1 <= 1
            or not _metrics_match_matrix(
                self.balanced_accuracy,
                self.f1,
                true_positive,
                true_negative,
                false_positive,
                false_negative,
            )
            or not {"all", "high-risk"}.issubset({item[0] for item in self.slice_metrics})
            or len({item[0] for item in self.slice_metrics}) != len(self.slice_metrics)
            or next(
                (
                    item[1:]
                    for item in self.slice_metrics
                    if item[0] == "all"
                ),
                None,
            )
            != (
                self.sample_size,
                self.balanced_accuracy,
                self.f1,
                *self.confusion_matrix,
            )
            or any(
                not is_bounded_text(item[0], maximum=200)
                or item[1] < 1
                or item[1] > self.sample_size
                or item[1] > MAX_SAFE_JSON_INTEGER
                or not 0 <= item[2] <= 1
                or not 0 <= item[3] <= 1
                or any(
                    value < 0 or value > MAX_SAFE_JSON_INTEGER
                    for value in item[4:8]
                )
                or sum(item[4:8]) != item[1]
                or not _metrics_match_matrix(
                    item[2],
                    item[3],
                    item[4],
                    item[5],
                    item[6],
                    item[7],
                )
                for item in self.slice_metrics
            )
            or self.calibrated_at.tzinfo is None
            or self.calibrated_at.utcoffset() is None
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
            or self.expires_at <= self.calibrated_at
        ):
            raise ValueError("INVALID_CALIBRATION_WINDOW")
        from app.modules.evaluation.domain.evidence import digest_document

        if self.evidence_digest != digest_document(self.semantic_document):
            raise ValueError("CALIBRATION_EVIDENCE_DIGEST_MISMATCH")

    @property
    def semantic_document(self) -> dict[str, object]:
        true_positive, true_negative, false_positive, false_negative = self.confusion_matrix
        return {
            "balanced_accuracy": self.balanced_accuracy,
            "calibrated_at": self.calibrated_at.astimezone(UTC).isoformat(
                timespec="seconds"
            ).replace(
                "+00:00",
                "Z",
            ),
            "confusion_matrix": {
                "false_negative": false_negative,
                "false_positive": false_positive,
                "true_negative": true_negative,
                "true_positive": true_positive,
            },
            "expires_at": self.expires_at.astimezone(UTC).isoformat(
                timespec="seconds"
            ).replace(
                "+00:00",
                "Z",
            ),
            "f1": self.f1,
            "grader_definition_digest": self.grader_definition_digest,
            "grader_revision": self.grader_revision,
            "human_labelled_suite_digest": self.human_labelled_suite_digest,
            "implementation_digest": self.implementation_digest,
            "sample_size": self.sample_size,
            "slice_metrics": [
                {
                    "balanced_accuracy": balanced_accuracy,
                    "confusion_matrix": {
                        "false_negative": false_negative,
                        "false_positive": false_positive,
                        "true_negative": true_negative,
                        "true_positive": true_positive,
                    },
                    "f1": f1,
                    "sample_size": sample_size,
                    "slice": slice_name,
                }
                for (
                    slice_name,
                    sample_size,
                    balanced_accuracy,
                    f1,
                    true_positive,
                    true_negative,
                    false_positive,
                    false_negative,
                ) in self.slice_metrics
            ],
        }

    @property
    def contract_document(self) -> dict[str, object]:
        return {
            **self.semantic_document,
            "evidence_digest": self.evidence_digest,
        }

    @classmethod
    def issue(
        cls,
        *,
        grader_revision: str,
        grader_definition_digest: str,
        implementation_digest: str,
        calibrated_at: datetime,
        expires_at: datetime,
        human_labelled_suite_digest: str,
        sample_size: int,
        confusion_matrix: tuple[int, int, int, int],
        balanced_accuracy: float,
        f1: float,
        slice_metrics: tuple[
            tuple[str, int, float, float, int, int, int, int],
            ...,
        ],
    ) -> GraderCalibration:
        from app.modules.evaluation.domain.evidence import digest_document

        provisional = cls.__new__(cls)
        object.__setattr__(provisional, "grader_revision", grader_revision)
        object.__setattr__(
            provisional,
            "grader_definition_digest",
            grader_definition_digest,
        )
        object.__setattr__(
            provisional,
            "implementation_digest",
            implementation_digest,
        )
        object.__setattr__(provisional, "calibrated_at", calibrated_at)
        object.__setattr__(provisional, "expires_at", expires_at)
        object.__setattr__(
            provisional,
            "human_labelled_suite_digest",
            human_labelled_suite_digest,
        )
        object.__setattr__(provisional, "sample_size", sample_size)
        object.__setattr__(
            provisional,
            "confusion_matrix",
            confusion_matrix,
        )
        object.__setattr__(
            provisional,
            "balanced_accuracy",
            balanced_accuracy,
        )
        object.__setattr__(provisional, "f1", f1)
        object.__setattr__(provisional, "slice_metrics", slice_metrics)
        return cls(
            grader_revision=grader_revision,
            grader_definition_digest=grader_definition_digest,
            implementation_digest=implementation_digest,
            calibrated_at=calibrated_at,
            expires_at=expires_at,
            evidence_digest=digest_document(provisional.semantic_document),
            human_labelled_suite_digest=human_labelled_suite_digest,
            sample_size=sample_size,
            confusion_matrix=confusion_matrix,
            balanced_accuracy=balanced_accuracy,
            f1=f1,
            slice_metrics=slice_metrics,
        )


def _metrics_match_matrix(
    balanced_accuracy: float,
    f1: float,
    true_positive: int,
    true_negative: int,
    false_positive: int,
    false_negative: int,
) -> bool:
    positive_total = true_positive + false_negative
    negative_total = true_negative + false_positive
    f1_denominator = (2 * true_positive) + false_positive + false_negative
    if positive_total <= 0 or negative_total <= 0:
        return False
    balanced_numerator = (
        true_positive * negative_total + true_negative * positive_total
    )
    balanced_denominator = 2 * positive_total * negative_total
    return _metric_matches_ratio(
        balanced_accuracy,
        balanced_numerator,
        balanced_denominator,
    ) and _metric_matches_ratio(
        f1,
        2 * true_positive,
        f1_denominator,
    )


def _metric_matches_ratio(observed: float, numerator: int, denominator: int) -> bool:
    observed_ratio = Fraction(Decimal(str(observed)))
    expected_ratio = Fraction(numerator, denominator)
    return abs(observed_ratio - expected_ratio) <= Fraction(1, 10**12)
