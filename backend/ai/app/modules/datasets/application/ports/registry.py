from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.datasets.domain import DatasetArtifact, DatasetFetch, DatasetSource


@dataclass(frozen=True, slots=True)
class DatasetSourceProvenance:
    source: DatasetSource
    scan_passed_fetch: DatasetFetch | None


class DatasetProvenanceRegistry(Protocol):
    async def resolve_source_provenance(
        self,
        *,
        source_key: str,
        source_revision: str,
        artifact_sha256: str,
    ) -> DatasetSourceProvenance | None: ...


class DatasetRegistry(Protocol):
    async def add_source(self, source: DatasetSource) -> None: ...

    async def get_source(self, source_id: UUID) -> DatasetSource | None: ...

    async def save_source(self, source: DatasetSource, *, expected_version: int) -> None: ...

    async def add_fetch(self, fetch: DatasetFetch) -> None: ...

    async def get_fetch(self, fetch_id: UUID) -> DatasetFetch | None: ...

    async def save_fetch(self, fetch: DatasetFetch, *, expected_version: int) -> None: ...

    async def add_artifact(
        self, artifact: DatasetArtifact, *, provenance: dict[str, object]
    ) -> None: ...
