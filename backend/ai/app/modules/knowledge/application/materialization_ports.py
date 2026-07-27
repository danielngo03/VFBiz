from typing import Protocol
from uuid import UUID

from app.modules.knowledge.domain import (
    CandidateChunkMaterialization,
    CandidateMaterializationResult,
    RedactionResult,
)


class CandidateMaterializationRepository(Protocol):
    async def materialize(
        self,
        *,
        release_id: UUID,
        canonical_source_id: str,
        source_revision: str,
        source_snapshot_hash: str,
        index_generation_id: UUID,
        embedding_revision: str,
        embedding_dimension: int,
        acl_namespace: str,
        chunks: tuple[CandidateChunkMaterialization, ...],
    ) -> CandidateMaterializationResult: ...


class TextRedactor(Protocol):
    def redact(self, text: str) -> RedactionResult: ...
