import fcntl
import hashlib
import json
import math
import os
import re
from collections.abc import AsyncIterator, Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from app.modules.knowledge.application.ingestion_ports import (
    ApprovedSourceContentReader,
    ArtifactDescriptor,
    ChunkUnit,
    ContentScanner,
    DocumentParser,
    DuplicateDecision,
    DuplicateDetector,
    EmbeddedChunk,
    IngestionArtifactStore,
    KnowledgeChunker,
    KnowledgeEmbedder,
    ParsedUnit,
    PermanentIngestionFailure,
    QuarantineStore,
    SourceObject,
)
from app.modules.knowledge.domain import KnowledgeIngestionJob, ScanEvidence

_FORBIDDEN_CONTENT = re.compile(
    r"(?i)(ignore (all|any|the) previous instructions|system prompt|"
    r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:\d[ -]*?){13,19}\b)"
)


class PackagedSyntheticSourceStore(ApprovedSourceContentReader):
    """Allowlisted, no-network source adapter for local and CI profiles."""

    def __init__(
        self,
        root: Path,
        sources: dict[tuple[str, str], str],
        *,
        chunk_size: int = 64 * 1024,
    ) -> None:
        self._root = root.resolve(strict=True)
        self._sources = sources
        self._chunk_size = chunk_size
        self.open_count = 0

    async def open_stream(self, *, source_id: str, source_revision: str) -> AsyncIterator[bytes]:
        relative = self._sources.get((source_id, source_revision))
        if relative is None:
            raise PermanentIngestionFailure("SOURCE_LOCATOR_NOT_ALLOWLISTED")
        path = (self._root / relative).resolve(strict=True)
        if not path.is_relative_to(self._root) or not path.is_file():
            raise PermanentIngestionFailure("SOURCE_LOCATOR_ESCAPED_ALLOWLIST")
        self.open_count += 1
        with path.open("rb") as handle:
            while chunk := handle.read(self._chunk_size):
                yield chunk


class LocalQuarantineStore(QuarantineStore):
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    async def write_stream(
        self,
        *,
        job_id: UUID,
        deletion_generation: int,
        fencing_token: int,
        expected_checksum: str,
        max_bytes: int,
        chunks: AsyncIterator[bytes],
    ) -> SourceObject:
        relative = (
            _attempt_prefix("quarantine", job_id, deletion_generation, fencing_token) / "source.bin"
        )
        final = self._root / relative
        pending = final.with_suffix(".pending")
        digest = hashlib.sha256()
        byte_count = 0
        prefix = b""
        with _job_lock(self._root, job_id):
            _assert_generation_writable(self._root, job_id, deletion_generation)
            final.parent.mkdir(parents=True, exist_ok=True)
            if final.exists():
                checksum = _hash_file(final)
                if checksum != expected_checksum:
                    raise PermanentIngestionFailure("IMMUTABLE_ARTIFACT_CONFLICT")
                return self._source_object(
                    relative,
                    checksum,
                    final.stat().st_size,
                    deletion_generation,
                    fencing_token,
                )
            try:
                with pending.open("xb") as handle:
                    async for chunk in chunks:
                        if not chunk:
                            continue
                        byte_count += len(chunk)
                        if byte_count > max_bytes:
                            raise PermanentIngestionFailure("SOURCE_SIZE_LIMIT_EXCEEDED")
                        if len(prefix) < 16:
                            prefix += chunk[: 16 - len(prefix)]
                        digest.update(chunk)
                        handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
                _assert_supported_text(prefix, pending)
                checksum = digest.hexdigest()
                if checksum != expected_checksum:
                    raise PermanentIngestionFailure("SOURCE_CHECKSUM_MISMATCH")
                os.replace(pending, final)
                value = self._source_object(
                    relative,
                    checksum,
                    byte_count,
                    deletion_generation,
                    fencing_token,
                )
                _write_immutable_json(
                    final.with_suffix(".meta.json"), value.model_dump(mode="json")
                )
                return value
            except Exception:
                pending.unlink(missing_ok=True)
                raise

    async def read_object(self, artifact: ArtifactDescriptor) -> SourceObject:
        path = _resolve_artifact(self._root, artifact)
        meta = path.with_suffix(".meta.json")
        if not meta.is_file():
            raise PermanentIngestionFailure("QUARANTINED_SOURCE_METADATA_MISSING")
        value = SourceObject.model_validate_json(meta.read_text(encoding="utf-8"))
        if (
            value.checksum_sha256 != artifact.checksum_sha256
            or value.deletion_generation != artifact.deletion_generation
            or value.fencing_token != artifact.fencing_token
        ):
            raise PermanentIngestionFailure("QUARANTINED_SOURCE_METADATA_MISMATCH")
        return value

    async def delete_job_artifacts(self, job_id: UUID, *, deletion_generation: int) -> str:
        return _delete_job_paths(self._root, job_id, deletion_generation, roots=("quarantine",))

    @staticmethod
    def _source_object(
        relative: Path,
        checksum: str,
        byte_count: int,
        deletion_generation: int,
        fencing_token: int,
    ) -> SourceObject:
        return SourceObject(
            object_ref=relative.as_posix(),
            detected_mime="text/markdown",
            checksum_sha256=checksum,
            byte_count=byte_count,
            magic="UTF8_TEXT",
            deletion_generation=deletion_generation,
            fencing_token=fencing_token,
        )


class Utf8MarkdownParser(DocumentParser):
    def __init__(self, root: Path, *, max_chars_per_unit: int = 8_000) -> None:
        self._root = root.resolve()
        self._max_chars = max_chars_per_unit

    async def parse_units(
        self,
        source: SourceObject,
        *,
        after_cursor: int,
        next_unit_index: int,
        max_units: int,
    ) -> AsyncIterator[ParsedUnit]:
        if source.detected_mime != "text/markdown" or source.magic != "UTF8_TEXT":
            raise PermanentIngestionFailure("PARSER_MEDIA_TYPE_UNSUPPORTED")
        path = _safe_path(self._root, source.object_ref)
        if next_unit_index > max_units:
            raise PermanentIngestionFailure("PARSED_UNIT_LIMIT_EXCEEDED")
        parsed = _read_text_unit(path, after_cursor, self._max_chars)
        if parsed is None:
            raise PermanentIngestionFailure("EMPTY_DOCUMENT")
        text, continuation_cursor, is_last = parsed
        if not is_last and next_unit_index == max_units:
            raise PermanentIngestionFailure("PARSED_UNIT_LIMIT_EXCEEDED")
        yield ParsedUnit(
            unit_index=next_unit_index,
            continuation_cursor=continuation_cursor,
            is_last=is_last,
            unit_key=f"unit-{next_unit_index:06d}",
            text=text,
            content_hash=_sha256(text.encode()),
        )


class DeterministicContentScanner(ContentScanner):
    def __init__(self, *, scanner_revision: str, policy_revision: str) -> None:
        self._scanner_revision = scanner_revision
        self._policy_revision = policy_revision
        self.object_scan_count = 0
        self.text_scan_count = 0

    async def scan_object(self, source: SourceObject) -> ScanEvidence:
        self.object_scan_count += 1
        passed = source.magic == "UTF8_TEXT" and source.detected_mime == "text/markdown"
        return ScanEvidence(
            phase="pre_parse",
            scanner_revision=self._scanner_revision,
            policy_revision=self._policy_revision,
            result="passed" if passed else "rejected",
            finding_count=0 if passed else 1,
            evidence_hash=_sha256(source.model_dump_json().encode()),
        )

    async def scan_text(self, unit: ParsedUnit) -> ScanEvidence:
        self.text_scan_count += 1
        finding_count = len(_FORBIDDEN_CONTENT.findall(unit.text))
        return ScanEvidence(
            phase="post_parse",
            scanner_revision=self._scanner_revision,
            policy_revision=self._policy_revision,
            result="passed" if finding_count == 0 else "rejected",
            finding_count=finding_count,
            evidence_hash=_sha256(
                f"{unit.content_hash}:{finding_count}:{self._policy_revision}".encode()
            ),
        )


class SemanticParagraphChunker(KnowledgeChunker):
    def __init__(self, *, max_chars: int = 1_500) -> None:
        self._max_chars = max_chars

    async def chunk(self, unit: ParsedUnit) -> tuple[ChunkUnit, ...]:
        paragraphs = [part.strip() for part in unit.text.split("\n\n") if part.strip()]
        output: list[ChunkUnit] = []
        for paragraph in paragraphs:
            for offset in range(0, len(paragraph), self._max_chars):
                text = paragraph[offset : offset + self._max_chars]
                index = len(output) + 1
                output.append(
                    ChunkUnit(
                        chunk_key=f"{unit.unit_key}-chunk-{index:04d}",
                        text=text,
                        content_hash=_sha256(text.encode()),
                        source_unit_key=unit.unit_key,
                    )
                )
        return tuple(output)


class DeterministicKnowledgeEmbedder(KnowledgeEmbedder):
    def __init__(self, dimension: int) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, chunks: tuple[ChunkUnit, ...]) -> tuple[EmbeddedChunk, ...]:
        result: list[EmbeddedChunk] = []
        for chunk in chunks:
            seed = hashlib.shake_256(chunk.text.encode()).digest(self._dimension * 2)
            vector = tuple(
                (int.from_bytes(seed[index : index + 2], "big") / 32_767.5) - 1
                for index in range(0, len(seed), 2)
            )
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            result.append(
                EmbeddedChunk(
                    chunk_key=chunk.chunk_key,
                    content_hash=chunk.content_hash,
                    vector=tuple(value / norm for value in vector),
                )
            )
        return tuple(result)


class DeterministicDuplicateDetector(DuplicateDetector):
    def __init__(self, *, revision: str = "token-jaccard-v1", threshold: float = 0.95) -> None:
        self._revision = revision
        self._threshold = threshold

    async def compare(self, chunk: ChunkUnit, candidate: ChunkUnit) -> DuplicateDecision | None:
        if chunk.content_hash == candidate.content_hash:
            method, score = "exact", 1.0
        else:
            left = set(re.findall(r"\w+", chunk.text.casefold()))
            right = set(re.findall(r"\w+", candidate.text.casefold()))
            score = len(left & right) / len(left | right) if left or right else 1.0
            method = "semantic"
        if score < self._threshold:
            return None
        evidence = (
            f"{chunk.content_hash}:{candidate.content_hash}:{method}:"
            f"{self._revision}:{self._threshold:.6f}:{score:.6f}"
        )
        return DuplicateDecision(
            duplicate_chunk_key=chunk.chunk_key,
            canonical_chunk_key=candidate.chunk_key,
            method=method,  # type: ignore[arg-type]
            detector_revision=self._revision,
            threshold=self._threshold,
            score=score,
            evidence_hash=_sha256(evidence.encode()),
        )


class LocalIngestionArtifactStore(IngestionArtifactStore):
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    async def persist_parsed_unit(
        self,
        job_id: UUID,
        unit: ParsedUnit,
        *,
        parent_checksum: str,
        deletion_generation: int,
        fencing_token: int,
    ) -> ArtifactDescriptor:
        relative = (
            _attempt_prefix("derived-quarantine", job_id, deletion_generation, fencing_token)
            / "parsed"
            / f"{unit.unit_key}.json"
        )
        return self._persist(
            job_id,
            deletion_generation,
            fencing_token,
            relative,
            "parsed-unit",
            "parse",
            unit.unit_key,
            unit,
            parent_checksum=parent_checksum,
        )

    async def read_parsed_units(
        self, artifacts: tuple[ArtifactDescriptor, ...]
    ) -> AsyncIterator[ParsedUnit]:
        for artifact in sorted(artifacts, key=lambda item: item.unit_key):
            yield ParsedUnit.model_validate_json(
                _read_verified(self._root, artifact).decode("utf-8")
            )

    async def persist_chunks(
        self,
        job_id: UUID,
        chunks: tuple[ChunkUnit, ...],
        *,
        parent_checksum: str,
        deletion_generation: int,
        fencing_token: int,
    ) -> tuple[ArtifactDescriptor, ...]:
        prefix = _attempt_prefix("candidate", job_id, deletion_generation, fencing_token)
        return tuple(
            self._persist(
                job_id,
                deletion_generation,
                fencing_token,
                prefix / "chunks" / f"{chunk.chunk_key}.json",
                "knowledge-chunk",
                "chunk",
                chunk.chunk_key,
                chunk,
                parent_checksum=parent_checksum,
            )
            for chunk in chunks
        )

    async def read_chunks(
        self, artifacts: tuple[ArtifactDescriptor, ...]
    ) -> AsyncIterator[ChunkUnit]:
        for artifact in sorted(artifacts, key=lambda item: item.unit_key):
            yield ChunkUnit.model_validate_json(
                _read_verified(self._root, artifact).decode("utf-8")
            )

    async def persist_duplicate_decisions(
        self,
        job_id: UUID,
        decisions: tuple[DuplicateDecision, ...],
        *,
        parent_checksum: str,
        deletion_generation: int,
        fencing_token: int,
    ) -> tuple[ArtifactDescriptor, ...]:
        prefix = _attempt_prefix("candidate", job_id, deletion_generation, fencing_token)
        return tuple(
            self._persist(
                job_id,
                deletion_generation,
                fencing_token,
                prefix / "duplicates" / f"{decision.duplicate_chunk_key}.json",
                "duplicate-decision",
                "chunk",
                decision.duplicate_chunk_key,
                decision,
                parent_checksum=parent_checksum,
            )
            for decision in decisions
        )

    async def persist_embeddings(
        self,
        job_id: UUID,
        chunks: tuple[EmbeddedChunk, ...],
        *,
        parent_checksum: str,
        deletion_generation: int,
        fencing_token: int,
    ) -> tuple[ArtifactDescriptor, ...]:
        prefix = _attempt_prefix("candidate", job_id, deletion_generation, fencing_token)
        return tuple(
            self._persist(
                job_id,
                deletion_generation,
                fencing_token,
                prefix / "embeddings" / f"{chunk.chunk_key}.json",
                "embedding",
                "embed",
                chunk.chunk_key,
                chunk,
                parent_checksum=parent_checksum,
            )
            for chunk in chunks
        )

    async def read_embeddings(
        self, artifacts: tuple[ArtifactDescriptor, ...]
    ) -> AsyncIterator[EmbeddedChunk]:
        for artifact in sorted(artifacts, key=lambda item: item.unit_key):
            yield EmbeddedChunk.model_validate_json(
                _read_verified(self._root, artifact).decode("utf-8")
            )

    async def build_manifest(
        self,
        job: KnowledgeIngestionJob,
        committed_artifacts: tuple[ArtifactDescriptor, ...],
    ) -> tuple[str, str, ArtifactDescriptor]:
        entries: list[dict[str, object]] = []
        for artifact in sorted(committed_artifacts, key=lambda item: item.artifact_ref):
            data = _read_verified(self._root, artifact)
            entries.append(
                {
                    "ref": artifact.artifact_ref,
                    "sha256": artifact.checksum_sha256,
                    "bytes": len(data),
                    "kind": artifact.kind,
                    "parentChecksum": artifact.parent_checksum,
                }
            )
        manifest: dict[str, object] = {
            "jobId": str(job.job_id),
            "sourceSnapshotHash": job.source_snapshot_hash,
            "candidateNamespace": job.candidate_namespace,
            "policyRevision": job.policy_revision,
            "embeddingRevision": job.embedding_revision,
            "embeddingDimension": job.embedding_dimension,
            "checkpoints": [
                checkpoint.model_dump(mode="json")
                for checkpoint in sorted(job.checkpoints, key=lambda item: item.stage)
            ],
            "entries": entries,
        }
        relative = (
            _attempt_prefix("candidate", job.job_id, job.deletion_generation, job.fencing_token)
            / "manifest.json"
        )
        artifact = self._persist(
            job.job_id,
            job.deletion_generation,
            job.fencing_token,
            relative,
            "candidate-manifest",
            "verify",
            "manifest",
            manifest,
            parent_checksum=_descriptor_digest(committed_artifacts),
        )
        return relative.as_posix(), artifact.checksum_sha256, artifact

    async def delete_job_artifacts(self, job_id: UUID, *, deletion_generation: int) -> str:
        return _delete_job_paths(
            self._root,
            job_id,
            deletion_generation,
            roots=("derived-quarantine", "candidate"),
        )

    def _persist(
        self,
        job_id: UUID,
        deletion_generation: int,
        fencing_token: int,
        relative: Path,
        kind: str,
        stage: str,
        unit_key: str,
        value: BaseModel | Mapping[str, object],
        *,
        parent_checksum: str,
    ) -> ArtifactDescriptor:
        data = _json_bytes(value.model_dump(mode="json") if isinstance(value, BaseModel) else value)
        path = self._root / relative
        with _job_lock(self._root, job_id):
            _assert_generation_writable(self._root, job_id, deletion_generation)
            _write_immutable(path, data)
        return ArtifactDescriptor(
            artifact_ref=relative.as_posix(),
            kind=kind,
            stage=stage,
            unit_key=unit_key,
            checksum_sha256=_sha256(data),
            byte_count=len(data),
            record_count=1,
            parent_checksum=parent_checksum,
            deletion_generation=deletion_generation,
            fencing_token=fencing_token,
        )


def _read_text_unit(path: Path, start_offset: int, max_chars: int) -> tuple[str, int, bool] | None:
    """Read one semantic unit from an opaque byte cursor without rescanning prior data."""
    buffer: list[str] = []
    length = 0
    with path.open("rb") as handle:
        handle.seek(start_offset)
        while True:
            line_offset = handle.tell()
            raw = handle.readline()
            if not raw:
                text = "".join(buffer).strip()
                return (text, handle.tell(), True) if text else None
            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError as error:
                raise PermanentIngestionFailure("SOURCE_ENCODING_UNSUPPORTED") from error
            if buffer and (length + len(line) > max_chars or line.startswith("# ")):
                handle.seek(line_offset)
                text = "".join(buffer).strip()
                if text:
                    return text, line_offset, False
                buffer, length = [], 0
            buffer.append(line)
            length += len(line)


def _assert_supported_text(prefix: bytes, path: Path) -> None:
    if prefix.startswith((b"%PDF", b"PK\x03\x04", b"\x1f\x8b")):
        raise PermanentIngestionFailure("SOURCE_MEDIA_TYPE_UNSUPPORTED")
    try:
        with path.open("r", encoding="utf-8") as handle:
            for block in iter(lambda: handle.read(64 * 1024), ""):
                if "\x00" in block:
                    raise PermanentIngestionFailure("SOURCE_BINARY_CONTENT_REJECTED")
    except UnicodeDecodeError as error:
        raise PermanentIngestionFailure("SOURCE_ENCODING_UNSUPPORTED") from error


def _attempt_prefix(kind: str, job_id: UUID, generation: int, fence: int) -> Path:
    return Path(kind) / str(job_id) / f"g{generation:08d}" / f"f{fence:020d}"


@contextmanager
def _job_lock(root: Path, job_id: UUID) -> Generator[None, None, None]:
    path = root / ".locks" / f"{job_id}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _assert_generation_writable(root: Path, job_id: UUID, generation: int) -> None:
    path = root / ".deletion-fences" / f"{job_id}.json"
    if not path.exists():
        return
    high_water = int(json.loads(path.read_text(encoding="utf-8"))["generation"])
    if generation < high_water:
        raise PermanentIngestionFailure("DELETION_FENCE_REJECTED_WRITE")


def _delete_job_paths(root: Path, job_id: UUID, generation: int, *, roots: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    with _job_lock(root, job_id):
        fence_path = root / ".deletion-fences" / f"{job_id}.json"
        current = -1
        if fence_path.exists():
            current = int(json.loads(fence_path.read_text(encoding="utf-8"))["generation"])
        if generation < current:
            raise PermanentIngestionFailure("DELETION_GENERATION_STALE")
        _write_json_replace(fence_path, {"generation": generation})
        for namespace in roots:
            base = root / namespace / str(job_id)
            if not base.exists():
                continue
            files = sorted(path for path in base.rglob("*") if path.is_file())
            for path in files:
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(_hash_file(path).encode())
                path.unlink()
            directories = sorted(
                (path for path in base.rglob("*") if path.is_dir()),
                key=lambda path: len(path.parts),
                reverse=True,
            )
            for directory in directories:
                directory.rmdir()
            base.rmdir()
    return digest.hexdigest()


def _read_verified(root: Path, artifact: ArtifactDescriptor) -> bytes:
    path = _resolve_artifact(root, artifact)
    data = path.read_bytes()
    if _sha256(data) != artifact.checksum_sha256:
        raise PermanentIngestionFailure("ARTIFACT_CHECKSUM_MISMATCH")
    return data


def _resolve_artifact(root: Path, artifact: ArtifactDescriptor) -> Path:
    path = _safe_path(root, artifact.artifact_ref)
    expected = f"/g{artifact.deletion_generation:08d}/f{artifact.fencing_token:020d}/"
    if expected not in f"/{path.relative_to(root).as_posix()}":
        raise PermanentIngestionFailure("ARTIFACT_FENCE_MISMATCH")
    if not path.is_file():
        raise PermanentIngestionFailure("ARTIFACT_MISSING")
    return path


def _safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root):
        raise PermanentIngestionFailure("ARTIFACT_LOCATOR_INVALID")
    return path


def _write_immutable_json(path: Path, value: object) -> None:
    _write_immutable(path, _json_bytes(value))


def _write_immutable(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise PermanentIngestionFailure("IMMUTABLE_ARTIFACT_CONFLICT")
        return
    pending = path.with_suffix(f"{path.suffix}.pending-{os.getpid()}")
    try:
        with pending.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def _write_json_replace(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(f".pending-{os.getpid()}")
    pending.write_bytes(_json_bytes(value))
    os.replace(pending, path)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(64 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _descriptor_digest(artifacts: tuple[ArtifactDescriptor, ...]) -> str:
    return _sha256(":".join(item.checksum_sha256 for item in artifacts).encode())


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
