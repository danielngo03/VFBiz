from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from app.modules.knowledge.application.cloud_ingestion_ports import (
    CloudObjectIdentity,
    DocumentAiExtractionResult,
    DocumentAiOperationReceipt,
    DocumentAiOutputObject,
    DocumentAiPageExtraction,
)
from app.modules.knowledge.application.cloud_materialization import (
    DocumentAiCandidateMaterializationWorker,
    DocumentAiCandidateMaterializer,
)
from app.modules.knowledge.application.ingestion_ports import (
    ChunkUnit,
    EmbeddedChunk,
    ParsedUnit,
    PermanentIngestionFailure,
    SourceObject,
)
from app.modules.knowledge.domain import ScanEvidence
from app.modules.knowledge.infrastructure.document_ai_candidate import (
    LocalDocumentAiCandidateSink,
)

JOB_ID = UUID("00000000-0000-4000-8000-000000000299")
SOURCE_HASH = "a" * 64
OUTPUT_HASH = "b" * 64


def _extraction(*, second_disposition: str = "document-ai") -> DocumentAiExtractionResult:
    source = CloudObjectIdentity(
        uri="gs://vinfast-503003-derived-dev/document-ai-input/materialize.pdf",
        generation=7,
        metageneration=1,
        sha256=SOURCE_HASH,
        byte_size=42,
        crc32c="zUSYPA==",
    )
    output = DocumentAiOutputObject(
        uri="gs://vinfast-503003-ocr-output-dev/document-ai/jobs/0299/output.json",
        generation=9,
        metageneration=1,
        byte_size=512,
        crc32c="zUSYPA==",
        sha256=OUTPUT_HASH,
    )
    return DocumentAiExtractionResult(
        idempotency_key=hashlib.sha256(b"materialize-0299").hexdigest(),
        job_id=JOB_ID,
        source=source,
        processor_revision="pretrained-ocr-v2.1-2024-06-21",
        expected_page_count=2,
        output_objects=(output,),
        pages=(
            DocumentAiPageExtraction(
                source_sha256=SOURCE_HASH,
                page_number=1,
                text="Hướng dẫn sạc xe điện.",
                confidence=0.98,
                disposition="document-ai",
                warnings=(),
                processor_revision="pretrained-ocr-v2.1-2024-06-21",
                output_uri=output.uri,
                output_generation=output.generation,
            ),
            DocumentAiPageExtraction(
                source_sha256=SOURCE_HASH,
                page_number=2,
                text="Trang cần chuyên viên kiểm tra.",
                confidence=0.52,
                disposition=second_disposition,  # type: ignore[arg-type]
                warnings=("LOW_CONFIDENCE",) if second_disposition == "review-required" else (),
                processor_revision="pretrained-ocr-v2.1-2024-06-21",
                output_uri=output.uri,
                output_generation=output.generation,
            ),
        ),
    )


class _Scanner:
    def __init__(
        self,
        *,
        reject_pages: set[int] | None = None,
        scanner_revision: str = "scanner-v1",
        policy_revision: str = "policy-v1",
    ) -> None:
        self.reject_pages = reject_pages or set()
        self.scanner_revision = scanner_revision
        self.policy_revision = policy_revision
        self.pages: list[int] = []

    async def scan_object(self, source: SourceObject) -> ScanEvidence:
        _ = source
        return ScanEvidence(
            phase="pre_parse",
            scanner_revision=self.scanner_revision,
            policy_revision=self.policy_revision,
            result="passed",
            finding_count=0,
            evidence_hash="c" * 64,
        )

    async def scan_text(self, unit: ParsedUnit) -> ScanEvidence:
        self.pages.append(unit.unit_index)
        rejected = unit.unit_index in self.reject_pages
        return ScanEvidence(
            phase="post_parse",
            scanner_revision=self.scanner_revision,
            policy_revision=self.policy_revision,
            result="rejected" if rejected else "passed",
            finding_count=1 if rejected else 0,
            evidence_hash=hashlib.sha256(unit.content_hash.encode()).hexdigest(),
        )


class _Chunker:
    def __init__(self) -> None:
        self.pages: list[int] = []

    async def chunk(self, unit: ParsedUnit) -> tuple[ChunkUnit, ...]:
        self.pages.append(unit.unit_index)
        return (
            ChunkUnit(
                chunk_key=f"document-ai/page/{unit.unit_index}/chunk/1",
                text=unit.text,
                content_hash=unit.content_hash,
                source_unit_key=unit.unit_key,
            ),
        )


class _Embedder:
    dimension = 3

    def __init__(self, *, mismatch: bool = False) -> None:
        self.mismatch = mismatch
        self.calls = 0

    async def embed(self, chunks: tuple[ChunkUnit, ...]) -> tuple[EmbeddedChunk, ...]:
        self.calls += 1
        if self.mismatch:
            return (
                EmbeddedChunk(
                    chunk_key="document-ai/page/99/chunk/1",
                    content_hash=chunks[0].content_hash,
                    vector=(0.1, 0.2, 0.3),
                ),
            )
        return tuple(
            EmbeddedChunk(
                chunk_key=chunk.chunk_key,
                content_hash=chunk.content_hash,
                vector=(0.1, 0.2, 0.3),
            )
            for chunk in chunks
        )


def _parsed_page(page_number: int, text: str | None = None) -> ParsedUnit:
    text = text or f"Trang {page_number}"
    return ParsedUnit(
        unit_index=page_number,
        continuation_cursor=page_number,
        is_last=page_number == 2,
        unit_key=f"document-ai/page/{page_number}",
        text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )


def _chunk(page_number: int, text: str | None = None) -> ChunkUnit:
    parsed = _parsed_page(page_number, text)
    return ChunkUnit(
        chunk_key=f"document-ai/page/{page_number}/chunk/1",
        text=parsed.text,
        content_hash=parsed.content_hash,
        source_unit_key=parsed.unit_key,
    )


def _embedding(page_number: int, text: str | None = None) -> EmbeddedChunk:
    chunk = _chunk(page_number, text)
    return EmbeddedChunk(
        chunk_key=chunk.chunk_key,
        content_hash=chunk.content_hash,
        vector=(0.1, 0.2, 0.3),
    )


@dataclass
class _Sink:
    calls: int = 0
    source_generation: int = 0
    source_metageneration: int = 0
    processor_revision: str = ""
    scanner_revision: str = ""
    policy_revision: str = ""
    accepted_pages: tuple[ParsedUnit, ...] = ()
    review_pages: tuple[DocumentAiPageExtraction, ...] = ()
    chunks: tuple[ChunkUnit, ...] = ()
    embeddings: tuple[EmbeddedChunk, ...] = ()

    async def persist_extraction_candidate(self, **kwargs: object) -> None:
        self.calls += 1
        self.source_generation = kwargs["source_generation"]  # type: ignore[assignment]
        self.source_metageneration = kwargs["source_metageneration"]  # type: ignore[assignment]
        self.processor_revision = kwargs["processor_revision"]  # type: ignore[assignment]
        self.scanner_revision = kwargs["scanner_revision"]  # type: ignore[assignment]
        self.policy_revision = kwargs["policy_revision"]  # type: ignore[assignment]
        self.accepted_pages = kwargs["accepted_pages"]  # type: ignore[assignment]
        self.review_pages = kwargs["review_pages"]  # type: ignore[assignment]
        self.chunks = kwargs["chunks"]  # type: ignore[assignment]
        self.embeddings = kwargs["embeddings"]  # type: ignore[assignment]


def _service(
    *,
    scanner: _Scanner | None = None,
    embedder: _Embedder | None = None,
    sink: _Sink | None = None,
    scanner_revision: str = "scanner-v1",
    policy_revision: str = "policy-v1",
) -> tuple[DocumentAiCandidateMaterializer, _Scanner, _Chunker, _Embedder, _Sink]:
    selected_scanner = scanner or _Scanner()
    chunker = _Chunker()
    selected_embedder = embedder or _Embedder()
    selected_sink = sink or _Sink()
    return (
        DocumentAiCandidateMaterializer(
            scanner=selected_scanner,
            scanner_revision=scanner_revision,
            policy_revision=policy_revision,
            chunker=chunker,
            chunker_revision="chunker-v1",
            embedder=selected_embedder,
            embedding_revision="embedding-v1",
            sink=selected_sink,
        ),
        selected_scanner,
        chunker,
        selected_embedder,
        selected_sink,
    )


@pytest.mark.asyncio
async def test_materializer_routes_review_pages_and_commits_atomically() -> None:
    service, scanner, chunker, embedder, sink = _service(
        scanner=_Scanner(reject_pages={1})
    )

    summary = await service.materialize(_extraction())

    assert summary.status == "review-required"
    assert summary.accepted_page_numbers == (2,)
    assert summary.review_required_page_numbers == (1,)
    assert summary.chunk_count == summary.embedding_count == 1
    assert summary.chunker_revision == "chunker-v1"
    assert summary.embedding_revision == "embedding-v1"
    assert scanner.pages == [1, 2]
    assert chunker.pages == [2]
    assert embedder.calls == 1
    assert sink.calls == 1
    assert sink.review_pages[0].disposition == "review-required"
    assert "DOCUMENT_AI_PAGE_SCAN_REJECTED_1" in sink.review_pages[0].warnings
    assert "Trang cần chuyên viên" not in summary.model_dump_json()


@pytest.mark.asyncio
async def test_materializer_preserves_provider_review_disposition_without_chunking() -> None:
    service, _scanner, chunker, embedder, sink = _service()

    summary = await service.materialize(_extraction(second_disposition="review-required"))

    assert summary.status == "review-required"
    assert summary.accepted_page_numbers == (1,)
    assert summary.review_required_page_numbers == (2,)
    assert chunker.pages == [1]
    assert embedder.calls == 1
    assert sink.review_pages[0].page_number == 2
    assert sink.review_pages[0].disposition == "review-required"


@pytest.mark.asyncio
async def test_materializer_rejects_scan_evidence_from_wrong_policy_revision() -> None:
    service, scanner, chunker, embedder, sink = _service(
        scanner=_Scanner(scanner_revision="scanner-v0")
    )

    summary = await service.materialize(_extraction())

    assert summary.status == "review-required"
    assert summary.accepted_page_numbers == ()
    assert summary.review_required_page_numbers == (1, 2)
    assert scanner.pages == [1, 2]
    assert chunker.pages == []
    assert embedder.calls == 0
    assert sink.calls == 1


@pytest.mark.asyncio
async def test_materializer_seals_review_only_batch_without_embedding() -> None:
    original = _extraction()
    extraction = original.model_copy(
        update={
            "pages": tuple(
                extraction_page.model_copy(update={"disposition": "review-required"})
                for extraction_page in original.pages
            )
        }
    )
    service, _scanner, chunker, embedder, sink = _service()

    summary = await service.materialize(extraction)

    assert summary.status == "review-required"
    assert summary.accepted_page_numbers == ()
    assert summary.review_required_page_numbers == (1, 2)
    assert chunker.pages == []
    assert embedder.calls == 0
    assert sink.calls == 1


@pytest.mark.asyncio
async def test_materializer_marks_complete_clean_extraction_candidate_ready() -> None:
    service, _scanner, chunker, embedder, sink = _service()

    summary = await service.materialize(_extraction())

    assert summary.status == "candidate-ready"
    assert summary.accepted_page_numbers == (1, 2)
    assert summary.review_required_page_numbers == ()
    assert summary.source_generation == 7
    assert summary.source_metageneration == 1
    assert summary.processor_revision == "pretrained-ocr-v2.1-2024-06-21"
    assert summary.scanner_revision == "scanner-v1"
    assert summary.policy_revision == "policy-v1"
    assert sink.source_generation == 7
    assert sink.source_metageneration == 1
    assert sink.processor_revision == summary.processor_revision
    assert sink.scanner_revision == summary.scanner_revision
    assert sink.policy_revision == summary.policy_revision
    assert chunker.pages == [1, 2]
    assert embedder.calls == 1
    assert sink.calls == 1


@pytest.mark.asyncio
async def test_materializer_rejects_embedding_lineage_before_sink_write() -> None:
    embedder = _Embedder(mismatch=True)
    service, _scanner, _chunker, _embedder, sink = _service(embedder=embedder)

    with pytest.raises(PermanentIngestionFailure, match="DOCUMENT_AI_EMBEDDING_LINEAGE_MISMATCH"):
        await service.materialize(_extraction())

    assert sink.calls == 0


@pytest.mark.asyncio
async def test_materializer_rejects_invalid_lineage_fence() -> None:
    service, _scanner, _chunker, _embedder, sink = _service()

    with pytest.raises(ValueError, match="lineage fence"):
        await service.materialize(_extraction(), fencing_token=0)

    assert sink.calls == 0


@pytest.mark.asyncio
async def test_local_candidate_sink_writes_content_addressed_immutable_manifest(
    tmp_path: Path,
) -> None:
    sink = LocalDocumentAiCandidateSink(tmp_path)
    materializer = DocumentAiCandidateMaterializer(
        scanner=_Scanner(),
        scanner_revision="scanner-v1",
        policy_revision="policy-v1",
        chunker=_Chunker(),
        chunker_revision="chunker-v1",
        embedder=_Embedder(),
        embedding_revision="embedding-v1",
        sink=sink,
    )

    summary = await materializer.materialize(_extraction())

    manifest = (
        tmp_path
        / "candidate"
        / "knowledge"
        / "document-ai"
        / SOURCE_HASH
        / summary.extraction_digest
        / "manifest.json"
    )
    assert manifest.exists()
    assert manifest.stat().st_mode & 0o777 == 0o600
    assert manifest.parent.stat().st_mode & 0o777 == 0o700
    first = manifest.read_bytes()
    await sink.persist_extraction_candidate(
        job_id=JOB_ID,
        source_sha256=SOURCE_HASH,
        source_generation=7,
        source_metageneration=1,
        processor_revision=summary.processor_revision,
        extraction_digest=summary.extraction_digest,
        scanner_revision=summary.scanner_revision,
        policy_revision=summary.policy_revision,
        chunker_revision=summary.chunker_revision,
        embedding_revision=summary.embedding_revision,
            accepted_pages=(
                _parsed_page(1, "Hướng dẫn sạc xe điện."),
                _parsed_page(2, "Trang cần chuyên viên kiểm tra."),
            ),
            review_pages=(),
            chunks=(
                _chunk(1, "Hướng dẫn sạc xe điện."),
                _chunk(2, "Trang cần chuyên viên kiểm tra."),
            ),
            embeddings=(
                _embedding(1, "Hướng dẫn sạc xe điện."),
                _embedding(2, "Trang cần chuyên viên kiểm tra."),
            ),
        deletion_generation=0,
        fencing_token=1,
    )
    assert manifest.read_bytes() == first

    with pytest.raises(PermanentIngestionFailure, match="SOURCE_GENERATION_CONFLICT"):
        await sink.persist_extraction_candidate(
            job_id=JOB_ID,
            source_sha256=SOURCE_HASH,
            source_generation=8,
            source_metageneration=1,
            processor_revision=summary.processor_revision,
            extraction_digest=summary.extraction_digest,
            scanner_revision=summary.scanner_revision,
            policy_revision=summary.policy_revision,
            chunker_revision=summary.chunker_revision,
            embedding_revision=summary.embedding_revision,
            accepted_pages=(_parsed_page(1, "Hướng dẫn sạc xe điện."),),
            review_pages=(),
            chunks=(_chunk(1, "Hướng dẫn sạc xe điện."),),
            embeddings=(_embedding(1, "Hướng dẫn sạc xe điện."),),
            deletion_generation=0,
            fencing_token=1,
        )


@pytest.mark.asyncio
async def test_post_reconciliation_worker_requires_succeeded_receipt() -> None:
    class _Reader:
        def read(self, receipt: DocumentAiOperationReceipt) -> DocumentAiExtractionResult:
            assert receipt.state == "succeeded"
            return _extraction()

    service, _scanner, _chunker, _embedder, sink = _service()
    worker = DocumentAiCandidateMaterializationWorker(
        output_reader=_Reader(),
        materializer=service,
    )
    extraction = _extraction()
    receipt = DocumentAiOperationReceipt(
        idempotency_key=extraction.idempotency_key,
        job_id=JOB_ID,
        operation_name="projects/vinfast-503003/locations/asia-southeast1/operations/299",
        input=extraction.source,
        output_prefix="gs://vinfast-503003-ocr-output-dev/document-ai/jobs/0299/",
        processor_revision=extraction.processor_revision,
        page_count=extraction.expected_page_count,
        fencing_token=1,
        state="succeeded",
        submitted_at=datetime(2026, 8, 3, tzinfo=UTC),
        reconciled_at=datetime(2026, 8, 3, 0, 1, tzinfo=UTC),
    )

    summary = await worker.run(receipt)

    assert summary.status == "candidate-ready"
    assert sink.calls == 1
