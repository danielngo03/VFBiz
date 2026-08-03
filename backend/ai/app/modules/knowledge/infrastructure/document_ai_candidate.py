"""Immutable local candidate sink for the Document AI materialization stage.

The sink is intentionally an object-store adapter, not a release repository.
It writes derived page/chunk/embedding artifacts and a content-addressed
manifest into a quarantined candidate namespace.  It never writes active
release rows and it rejects stale deletion generations, stale fences, and
replays whose payload differs from the original receipt.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import cast
from uuid import UUID

from app.modules.knowledge.application.cloud_ingestion_ports import (
    DocumentAiPageExtraction,
)
from app.modules.knowledge.application.cloud_materialization import (
    DocumentAiCandidateSink,
)
from app.modules.knowledge.application.ingestion_ports import (
    ChunkUnit,
    EmbeddedChunk,
    ParsedUnit,
    PermanentIngestionFailure,
)


class LocalDocumentAiCandidateSink(DocumentAiCandidateSink):
    """Persist one extraction candidate with atomic, immutable filesystem writes."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._tombstones = self._root / "tombstones" / "document-ai"
        self._tombstones.mkdir(mode=0o700, parents=True, exist_ok=True)

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
    ) -> None:
        kwargs: dict[str, object] = {
            "job_id": job_id,
            "source_sha256": source_sha256,
            "source_generation": source_generation,
            "source_metageneration": source_metageneration,
            "processor_revision": processor_revision,
            "extraction_digest": extraction_digest,
            "scanner_revision": scanner_revision,
            "policy_revision": policy_revision,
            "chunker_revision": chunker_revision,
            "embedding_revision": embedding_revision,
            "accepted_pages": accepted_pages,
            "review_pages": review_pages,
            "chunks": chunks,
            "embeddings": embeddings,
            "deletion_generation": deletion_generation,
            "fencing_token": fencing_token,
        }
        job_id = _uuid(kwargs, "job_id")
        source_sha256 = _string(kwargs, "source_sha256")
        extraction_digest = _string(kwargs, "extraction_digest")
        source_generation = _positive_int(kwargs, "source_generation")
        source_metageneration = _positive_int(kwargs, "source_metageneration")
        deletion_generation = _nonnegative_int(kwargs, "deletion_generation")
        fencing_token = _positive_int(kwargs, "fencing_token")
        accepted_pages = cast(
            tuple[ParsedUnit, ...],
            _tuple_of(kwargs, "accepted_pages", ParsedUnit),
        )
        review_pages = cast(
            tuple[DocumentAiPageExtraction, ...],
            _tuple_of(kwargs, "review_pages", DocumentAiPageExtraction),
        )
        chunks = cast(tuple[ChunkUnit, ...], _tuple_of(kwargs, "chunks", ChunkUnit))
        embeddings = cast(
            tuple[EmbeddedChunk, ...], _tuple_of(kwargs, "embeddings", EmbeddedChunk)
        )
        if not _is_sha256(source_sha256) or not _is_sha256(extraction_digest):
            raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_IDENTITY_INVALID")
        _assert_embedding_set(chunks, embeddings)

        tombstone = self._tombstones / f"{job_id}.json"
        if tombstone.exists():
            high_water = json.loads(tombstone.read_text(encoding="utf-8"))["generation"]
            if deletion_generation < int(high_water):
                raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_DELETION_FENCE")

        base = (
            self._root
            / "candidate"
            / "knowledge"
            / "document-ai"
            / source_sha256
            / extraction_digest
        )
        source_identity = (
            self._root
            / "candidate"
            / "knowledge"
            / "document-ai"
            / source_sha256
            / "source-identity.json"
        )
        identity_bytes = _json_bytes(
            {
                "schema_revision": "document-ai-source-identity-v1",
                "source_sha256": source_sha256,
                "source_generation": source_generation,
                "source_metageneration": source_metageneration,
            }
        )
        if source_identity.exists() and source_identity.read_bytes() != identity_bytes:
            raise PermanentIngestionFailure("DOCUMENT_AI_SOURCE_GENERATION_CONFLICT")
        manifest_path = base / "manifest.json"
        manifest = _manifest(
            job_id=job_id,
            source_sha256=source_sha256,
            source_generation=source_generation,
            source_metageneration=source_metageneration,
            extraction_digest=extraction_digest,
            deletion_generation=deletion_generation,
            fencing_token=fencing_token,
            processor_revision=_string(kwargs, "processor_revision"),
            scanner_revision=_string(kwargs, "scanner_revision"),
            policy_revision=_string(kwargs, "policy_revision"),
            chunker_revision=_string(kwargs, "chunker_revision"),
            embedding_revision=_string(kwargs, "embedding_revision"),
            accepted_pages=accepted_pages,
            review_pages=review_pages,
            chunks=chunks,
            embeddings=embeddings,
        )
        encoded_manifest = _json_bytes(manifest)

        if manifest_path.exists():
            existing = manifest_path.read_bytes()
            if existing != encoded_manifest:
                raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_REPLAY_CONFLICT")
            return

        # Build all files in a private staging directory and publish the
        # directory with an atomic manifest-last protocol.  A crash can leave
        # only an unreferenced tmp directory; it cannot create a ready claim.
        staging = base.with_name(f".{base.name}.tmp-{job_id.hex}")
        if staging.exists():
            raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_WRITE_IN_PROGRESS")
        staging.mkdir(mode=0o700, parents=True)
        try:
            _write_immutable(source_identity, identity_bytes)
            _write_records(staging / "pages", "page", accepted_pages)
            _write_records(staging / "review", "page", review_pages)
            _write_records(staging / "chunks", "chunk", chunks)
            _write_records(staging / "embeddings", "chunk", embeddings)
            _write_immutable(staging / "manifest.json", encoded_manifest)
            base.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            staging.rename(base)
        except FileExistsError as error:
            raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_REPLAY_CONFLICT") from error
        except OSError as error:
            raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_WRITE_FAILED") from error


def _manifest(
    *,
    job_id: UUID,
    source_sha256: str,
    source_generation: int,
    source_metageneration: int,
    extraction_digest: str,
    deletion_generation: int,
    fencing_token: int,
    processor_revision: str,
    scanner_revision: str,
    policy_revision: str,
    chunker_revision: str,
    embedding_revision: str,
    accepted_pages: tuple[ParsedUnit, ...],
    review_pages: tuple[DocumentAiPageExtraction, ...],
    chunks: tuple[ChunkUnit, ...],
    embeddings: tuple[EmbeddedChunk, ...],
) -> dict[str, object]:
    return {
        "schema_revision": "document-ai-candidate-manifest-v1",
        "job_id": str(job_id),
        "source_sha256": source_sha256,
        "source_generation": source_generation,
        "source_metageneration": source_metageneration,
        "extraction_digest": extraction_digest,
        "deletion_generation": deletion_generation,
        "fencing_token": fencing_token,
        "processor_revision": processor_revision,
        "scanner_revision": scanner_revision,
        "policy_revision": policy_revision,
        "chunker_revision": chunker_revision,
        "embedding_revision": embedding_revision,
        "accepted_page_numbers": [page.unit_index for page in accepted_pages],
        "review_required_page_numbers": [page.page_number for page in review_pages],
        "chunk_count": len(chunks),
        "embedding_count": len(embeddings),
        "status": "candidate-ready" if not review_pages else "review-required",
        "artifacts": {
            "pages_sha256": _record_hashes(accepted_pages),
            "review_sha256": _record_hashes(review_pages),
            "chunks_sha256": _record_hashes(chunks),
            "embeddings_sha256": _record_hashes(embeddings),
        },
    }


def _record_hashes(values: Iterable[object]) -> list[str]:
    return [hashlib.sha256(_json_bytes(value)).hexdigest() for value in values]


def _write_records(directory: Path, prefix: str, values: Iterable[object]) -> None:
    for index, value in enumerate(values, start=1):
        _write_immutable(directory / f"{prefix}-{index:06d}.json", _json_bytes(value))


def _write_immutable(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(path)
        return
    temporary = path.with_name(f".{path.name}.tmp")
    flags = "xb"
    with temporary.open(flags) as handle:
        handle.write(data)
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _json_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")  # type: ignore[union-attr]
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _assert_embedding_set(
    chunks: tuple[ChunkUnit, ...], embeddings: tuple[EmbeddedChunk, ...]
) -> None:
    if len(chunks) != len(embeddings) or any(
        chunk.chunk_key != embedding.chunk_key
        or chunk.content_hash != embedding.content_hash
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ):
        raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_EMBEDDING_MISMATCH")


def _tuple_of(kwargs: dict[str, object], key: str, model: type[object]) -> tuple[object, ...]:
    value = kwargs.get(key)
    if not isinstance(value, tuple):
        raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_PAYLOAD_INVALID")
    items = cast(tuple[object, ...], value)
    if any(not isinstance(item, model) for item in items):
        raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_PAYLOAD_INVALID")
    return items


def _string(kwargs: dict[str, object], key: str) -> str:
    value = kwargs.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_PAYLOAD_INVALID")
    return value


def _positive_int(kwargs: dict[str, object], key: str) -> int:
    value = _nonnegative_int(kwargs, key)
    if value < 1:
        raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_PAYLOAD_INVALID")
    return value


def _nonnegative_int(kwargs: dict[str, object], key: str) -> int:
    value = kwargs.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_PAYLOAD_INVALID")
    return value


def _uuid(kwargs: dict[str, object], key: str) -> UUID:
    value = kwargs.get(key)
    if not isinstance(value, UUID):
        raise PermanentIngestionFailure("DOCUMENT_AI_CANDIDATE_PAYLOAD_INVALID")
    return value


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


__all__ = ["LocalDocumentAiCandidateSink"]
