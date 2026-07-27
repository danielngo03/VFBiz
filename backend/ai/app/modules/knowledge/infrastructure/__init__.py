"""Knowledge persistence and ingestion adapters."""

from app.modules.knowledge.infrastructure.pii_redaction import (
    PatternBasedTextRedactor,
)
from app.modules.knowledge.infrastructure.postgres import (
    PostgresKnowledgeReleaseRepository,
    PostgresSourceRegisterReader,
)
from app.modules.knowledge.infrastructure.postgres_ingestion import (
    PostgresIngestionRepository,
)
from app.modules.knowledge.infrastructure.postgres_materialization import (
    PostgresCandidateMaterializationRepository,
)
from app.modules.knowledge.infrastructure.postgres_retrieval import (
    PostgresRetrievalSnapshotReader,
)

__all__ = [
    "PatternBasedTextRedactor",
    "PostgresIngestionRepository",
    "PostgresCandidateMaterializationRepository",
    "PostgresKnowledgeReleaseRepository",
    "PostgresRetrievalSnapshotReader",
    "PostgresSourceRegisterReader",
]
