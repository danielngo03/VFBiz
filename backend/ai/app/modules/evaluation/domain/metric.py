from dataclasses import dataclass
from enum import StrEnum

from app.modules.evaluation.domain.validation import is_bounded_text, is_sha256


class MetricDirection(StrEnum):
    HIGHER_IS_BETTER = "higher-is-better"
    LOWER_IS_BETTER = "lower-is-better"


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    revision: str
    direction: MetricDirection
    required_slices: tuple[str, ...]
    definition_digest: str

    def __post_init__(self) -> None:
        if (
            not is_bounded_text(self.revision)
            or not self.required_slices
            or len(set(self.required_slices)) != len(self.required_slices)
            or any(not is_bounded_text(slice_name) for slice_name in self.required_slices)
            or not is_sha256(self.definition_digest)
        ):
            raise ValueError("INVALID_METRIC_DEFINITION")
