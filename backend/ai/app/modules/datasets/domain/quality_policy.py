from __future__ import annotations

from collections.abc import Iterable

from app.modules.datasets.domain.records import CanonicalDatasetRecord
from app.modules.datasets.domain.registry import RegistryInvariantError

REQUIRED_RELEASE_GATES = frozenset(
    {
        "schema",
        "dlp",
        "dedup",
        "contamination",
        "independent_review",
    }
)


def require_release_eligible(
    records: Iterable[CanonicalDatasetRecord],
) -> tuple[CanonicalDatasetRecord, ...]:
    selected = tuple(records)
    if not selected:
        raise RegistryInvariantError("cannot release an empty dataset")
    for record in selected:
        if record.rejection_reasons:
            raise RegistryInvariantError("rejected records cannot be released")
        missing = REQUIRED_RELEASE_GATES - record.quality_scores.keys()
        if missing:
            raise RegistryInvariantError(
                f"record is missing release quality gates: {', '.join(sorted(missing))}"
            )
        if any(record.quality_scores[gate] != 1.0 for gate in REQUIRED_RELEASE_GATES):
            raise RegistryInvariantError("all release quality gates must pass")
    return selected
