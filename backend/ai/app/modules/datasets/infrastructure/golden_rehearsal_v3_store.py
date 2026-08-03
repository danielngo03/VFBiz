"""Storage boundary that always dispatches the v3 semantic verifier."""

from __future__ import annotations

from pathlib import Path

from app.modules.datasets.application.evaluation.golden_rehearsal import (
    RehearsalBundle,
)
from app.modules.datasets.application.evaluation.golden_rehearsal_v3 import (
    verify_rehearsal_bundle_v3,
)
from app.modules.datasets.infrastructure.golden_rehearsal_store import (
    LocalGoldenRehearsalStore,
)


class LocalGoldenRehearsalV3Store:
    """Compose private filesystem checks with mandatory v3 semantic checks."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._base = LocalGoldenRehearsalStore(root)

    def put(self, bundle: RehearsalBundle) -> Path:
        verify_rehearsal_bundle_v3(
            manifest_bytes=bundle.manifest_json,
            cases_bytes=bundle.cases_jsonl,
            expected_digest=bundle.bundle_digest,
        )
        target = self._base.put(bundle)
        self.verify(bundle.bundle_digest)
        return target

    def verify(self, bundle_digest: str) -> dict[str, object]:
        self._base.verify(bundle_digest)
        target = self._root / bundle_digest
        return verify_rehearsal_bundle_v3(
            manifest_bytes=(target / "manifest.json").read_bytes(),
            cases_bytes=(target / "cases.jsonl").read_bytes(),
            expected_digest=bundle_digest,
        )
