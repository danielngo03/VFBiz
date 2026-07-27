import asyncio
import json
import signal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.knowledge.application import (
    KnowledgeIngestionRunner,
    KnowledgeSourceApprovalGate,
)
from app.modules.knowledge.domain import (
    KnowledgeConcurrencyConflict,
    KnowledgeIngestionJob,
)
from app.modules.knowledge.infrastructure import (
    PostgresIngestionRepository,
    PostgresSourceRegisterReader,
)
from app.modules.knowledge.infrastructure.local_ingestion import (
    DeterministicContentScanner,
    DeterministicDuplicateDetector,
    DeterministicKnowledgeEmbedder,
    LocalIngestionArtifactStore,
    LocalQuarantineStore,
    PackagedSyntheticSourceStore,
    SemanticParagraphChunker,
    Utf8MarkdownParser,
)
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory


class SyntheticSourceMapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    source_revision: str = Field(min_length=1, max_length=160)
    relative_path: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9/_.-]{0,511}$")


class KnowledgeIngestionWorkerRuntime:
    def __init__(self, engine: AsyncEngine, runner: KnowledgeIngestionRunner) -> None:
        self._engine = engine
        self._runner = runner

    async def process_one(self) -> KnowledgeIngestionJob | None:
        return await self._runner.run_once()

    async def run_until_stopped(
        self,
        stop_event: asyncio.Event,
        *,
        idle_delay_seconds: float = 0.25,
        max_idle_delay_seconds: float = 5.0,
    ) -> None:
        """Poll the durable queue with bounded idle backoff and graceful shutdown."""
        delay = idle_delay_seconds
        while not stop_event.is_set():
            try:
                processed = await self.process_one()
            except KnowledgeConcurrencyConflict:
                # Another fenced worker won the lease; continue without killing the process.
                processed = None
            if processed is not None:
                delay = idle_delay_seconds
                continue
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
            except TimeoutError:
                delay = min(max_idle_delay_seconds, delay * 2)

    async def close(self) -> None:
        await self._engine.dispose()


def build_knowledge_ingestion_worker(
    settings: Settings,
) -> KnowledgeIngestionWorkerRuntime:
    if settings.knowledge_ingestion_profile != "synthetic_local":
        raise RuntimeError("knowledge ingestion worker profile is disabled")
    database_url = settings.database_url
    source_root = settings.knowledge_synthetic_source_root
    artifact_root = settings.knowledge_artifact_root
    source_map_path = settings.knowledge_source_map_path
    if (
        database_url is None
        or source_root is None
        or artifact_root is None
        or source_map_path is None
    ):
        raise RuntimeError("knowledge ingestion worker settings are incomplete")
    entries = _read_source_map(source_map_path)
    sources = {(entry.source_id, entry.source_revision): entry.relative_path for entry in entries}
    engine = create_engine(database_url)
    sessions = create_session_factory(engine)
    source_reader = PostgresSourceRegisterReader(sessions)
    repository = PostgresIngestionRepository(sessions)
    runner = KnowledgeIngestionRunner(
        repository,
        KnowledgeSourceApprovalGate(source_reader),
        PackagedSyntheticSourceStore(source_root, sources),
        LocalQuarantineStore(artifact_root),
        DeterministicContentScanner(
            scanner_revision=settings.knowledge_scanner_revision,
            policy_revision=settings.knowledge_policy_revision,
        ),
        Utf8MarkdownParser(artifact_root),
        SemanticParagraphChunker(),
        DeterministicDuplicateDetector(),
        DeterministicKnowledgeEmbedder(settings.knowledge_embedding_dimension),
        LocalIngestionArtifactStore(artifact_root),
    )
    return KnowledgeIngestionWorkerRuntime(engine, runner)


def _read_source_map(path: Path) -> tuple[SyntheticSourceMapEntry, ...]:
    resolved = path.resolve(strict=True)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    entries = TypeAdapter(tuple[SyntheticSourceMapEntry, ...]).validate_python(payload)
    if not entries or len({(entry.source_id, entry.source_revision) for entry in entries}) != len(
        entries
    ):
        raise ValueError("synthetic source map must be non-empty and unique")
    return entries


async def _main() -> None:
    settings = Settings()
    runtime = build_knowledge_ingestion_worker(settings)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for event in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(event, stop_event.set)
    try:
        await runtime.run_until_stopped(stop_event)
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(_main())
