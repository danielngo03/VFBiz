"""Turn Document AI page output into an isolated, review-gated candidate.

This service is deliberately downstream of reconciliation and upstream of any
Knowledge Release. It never changes an active retriever, accepts only pages
that pass the deterministic text scan, and commits page/chunk/embedding
artifacts through one sink operation so partial candidate writes cannot look
ready.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.knowledge.application.cloud_ingestion_ports import (
    DocumentAiExtractionResult,
    DocumentAiOperationReceipt,
    DocumentAiOutputReader,
    DocumentAiPageExtraction,
)
from app.modules.knowledge.application.ingestion_ports import (
    ChunkUnit,
    ContentScanner,
    EmbeddedChunk,
    KnowledgeChunker,
    KnowledgeEmbedder,
    ParsedUnit,
    PermanentIngestionFailure,
)
from app.modules.knowledge.domain import ScanEvidence


class DocumentAiCandidateSink(Protocol):
    """Atomic private-store boundary for derived candidate artifacts."""

    async def persist_extraction_candidate(
        self,
        *,
        job_id: UUID,
        source_sha256: str,
        source_generation: int,
        source_metageneration: int,
        processor_revision: str,
        extraction_digest: str,
        scanner_revision: str,
        policy_revision: str,
        chunker_revision: str,
        embedding_revision: str,
        accepted_pages: tuple[ParsedUnit, ...],
        review_pages: tuple[DocumentAiPageExtraction, ...],
        chunks: tuple[ChunkUnit, ...],
        embeddings: tuple[EmbeddedChunk, ...],
        deletion_generation: int,
        fencing_token: int,
    ) -> None: ...


class DocumentAiCandidateSummary(BaseModel):
    """Content-free receipt emitted after the atomic candidate write."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_revision: Literal["document-ai-candidate-summary-v1"] = (
        "document-ai-candidate-summary-v1"
    )
    job_id: UUID
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_generation: int = Field(strict=True, ge=1)
    source_metageneration: int = Field(strict=True, ge=1)
    processor_revision: str = Field(min_length=1, max_length=160)
    extraction_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    scanner_revision: str = Field(min_length=1, max_length=160)
    policy_revision: str = Field(min_length=1, max_length=160)
    chunker_revision: str = Field(min_length=1, max_length=160)
    embedding_revision: str = Field(min_length=1, max_length=160)
    accepted_page_numbers: tuple[int, ...]
    review_required_page_numbers: tuple[int, ...]
    chunk_count: int = Field(strict=True, ge=0)
    embedding_count: int = Field(strict=True, ge=0)
    status: Literal["candidate-ready", "review-required"]


class DocumentAiCandidateMaterializer:
    """Scan, chunk and embed reconciled pages without activating them."""

    def __init__(
        self,
        *,
        scanner: ContentScanner,
        scanner_revision: str,
        policy_revision: str,
        chunker: KnowledgeChunker,
        chunker_revision: str,
        embedder: KnowledgeEmbedder,
        embedding_revision: str,
        sink: DocumentAiCandidateSink,
    ) -> None:
        revisions = (
            scanner_revision,
            policy_revision,
            chunker_revision,
            embedding_revision,
        )
        if any(not revision.strip() for revision in revisions):
            raise ValueError("candidate pipeline authority revisions are required")
        if any(len(revision) > 160 for revision in revisions):
            raise ValueError("candidate pipeline authority revisions are too long")
        if embedder.dimension < 1:
            raise ValueError("candidate embedding dimension must be positive")
        self._scanner = scanner
        self._scanner_revision = scanner_revision
        self._policy_revision = policy_revision
        self._chunker = chunker
        self._chunker_revision = chunker_revision
        self._embedder = embedder
        self._embedding_revision = embedding_revision
        self._sink = sink

    async def materialize(
        self,
        extraction: DocumentAiExtractionResult,
        *,
        deletion_generation: int = 0,
        fencing_token: int = 1,
    ) -> DocumentAiCandidateSummary:
        if deletion_generation < 0 or fencing_token < 1:
            raise ValueError("candidate lineage fence is invalid")
        parsed_pages: list[ParsedUnit] = []
        review_pages: list[DocumentAiPageExtraction] = []
        chunks: list[ChunkUnit] = []
        for page in extraction.pages:
            if page.disposition != "document-ai":
                review_pages.append(page)
                continue
            parsed = _parsed_page(extraction, page)
            evidence = await self._scanner.scan_text(parsed)
            if not _scan_passed(
                evidence,
                scanner_revision=self._scanner_revision,
                policy_revision=self._policy_revision,
            ):
                review_pages.append(
                    _review_page(page, f"DOCUMENT_AI_PAGE_SCAN_REJECTED_{page.page_number}")
                )
                continue
            page_chunks = await self._chunker.chunk(parsed)
            if not page_chunks:
                review_pages.append(
                    _review_page(page, f"DOCUMENT_AI_PAGE_EMPTY_CHUNKS_{page.page_number}")
                )
                continue
            parsed_pages.append(parsed)
            chunks.extend(page_chunks)

        embeddings = await self._embedder.embed(tuple(chunks)) if chunks else ()
        _assert_embedding_lineage(tuple(chunks), embeddings, self._embedder.dimension)
        status = (
            "candidate-ready"
            if parsed_pages and chunks and not review_pages
            else "review-required"
        )
        await self._sink.persist_extraction_candidate(
            job_id=extraction.job_id,
            source_sha256=extraction.source.sha256,
            source_generation=extraction.source.generation,
            source_metageneration=extraction.source.metageneration,
            processor_revision=extraction.processor_revision,
            extraction_digest=_extraction_digest(extraction),
            scanner_revision=self._scanner_revision,
            policy_revision=self._policy_revision,
            chunker_revision=self._chunker_revision,
            embedding_revision=self._embedding_revision,
            accepted_pages=tuple(parsed_pages),
            review_pages=tuple(review_pages),
            chunks=tuple(chunks),
            embeddings=tuple(embeddings),
            deletion_generation=deletion_generation,
            fencing_token=fencing_token,
        )
        return DocumentAiCandidateSummary(
            job_id=extraction.job_id,
            source_sha256=extraction.source.sha256,
            source_generation=extraction.source.generation,
            source_metageneration=extraction.source.metageneration,
            processor_revision=extraction.processor_revision,
            extraction_digest=_extraction_digest(extraction),
            scanner_revision=self._scanner_revision,
            policy_revision=self._policy_revision,
            chunker_revision=self._chunker_revision,
            embedding_revision=self._embedding_revision,
            accepted_page_numbers=tuple(page.unit_index for page in parsed_pages),
            review_required_page_numbers=tuple(page.page_number for page in review_pages),
            chunk_count=len(chunks),
            embedding_count=len(embeddings),
            status=status,
        )


class DocumentAiCandidateMaterializationWorker:
    """Explicit post-reconciliation worker boundary.

    Reconciliation persists content-free evidence. This worker is the only
    application entry point that reads a succeeded Document AI output and
    invokes scan → chunk → embedding → candidate persistence. It does not
    mutate a Knowledge Release or an active retriever.
    """

    def __init__(
        self,
        *,
        output_reader: DocumentAiOutputReader,
        materializer: DocumentAiCandidateMaterializer,
    ) -> None:
        self._output_reader = output_reader
        self._materializer = materializer

    async def run(
        self,
        receipt: DocumentAiOperationReceipt,
        *,
        deletion_generation: int = 0,
        fencing_token: int | None = None,
    ) -> DocumentAiCandidateSummary:
        if receipt.state != "succeeded":
            raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_REQUIRES_SUCCESS")
        extraction = self._output_reader.read(receipt)
        return await self._materializer.materialize(
            extraction,
            deletion_generation=deletion_generation,
            fencing_token=fencing_token or receipt.fencing_token,
        )


def _parsed_page(
    extraction: DocumentAiExtractionResult,
    page: DocumentAiPageExtraction,
) -> ParsedUnit:
    return ParsedUnit(
        unit_index=page.page_number,
        continuation_cursor=page.page_number,
        is_last=page.page_number == extraction.expected_page_count,
        unit_key=f"document-ai/page/{page.page_number}",
        text=page.text,
        content_hash=hashlib.sha256(page.text.encode("utf-8")).hexdigest(),
    )


def _scan_passed(
    evidence: ScanEvidence,
    *,
    scanner_revision: str,
    policy_revision: str,
) -> bool:
    return (
        evidence.phase == "post_parse"
        and evidence.result == "passed"
        and evidence.scanner_revision == scanner_revision
        and evidence.policy_revision == policy_revision
    )


def _review_page(page: DocumentAiPageExtraction, warning: str) -> DocumentAiPageExtraction:
    warnings = page.warnings
    if warning not in warnings:
        warnings = (*warnings[:19], warning)
    return page.model_copy(update={"disposition": "review-required", "warnings": warnings})


def _assert_embedding_lineage(
    chunks: Sequence[ChunkUnit],
    embeddings: Sequence[EmbeddedChunk],
    dimension: int,
) -> None:
    if len(chunks) != len(embeddings) or any(
        len(embedding.vector) != dimension
        or embedding.chunk_key != chunk.chunk_key
        or embedding.content_hash != chunk.content_hash
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ):
        raise PermanentIngestionFailure("DOCUMENT_AI_EMBEDDING_LINEAGE_MISMATCH")


def _extraction_digest(extraction: DocumentAiExtractionResult) -> str:
    payload = extraction.model_dump(mode="json")
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


__all__ = [
    "DocumentAiCandidateMaterializer",
    "DocumentAiCandidateMaterializationWorker",
    "DocumentAiCandidateSink",
    "DocumentAiCandidateSummary",
]
