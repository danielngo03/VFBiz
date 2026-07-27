import asyncio
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.modules.knowledge.application.ingestion_ports import (
    ApprovedSourceContentReader,
    ArtifactDescriptor,
    ChunkUnit,
    ContentScanner,
    DocumentParser,
    DuplicateDecision,
    DuplicateDetector,
    IngestionArtifactStore,
    IngestionRepository,
    KnowledgeChunker,
    KnowledgeEmbedder,
    PermanentIngestionFailure,
    QuarantineStore,
    SourceApprovalGate,
    SourceObject,
    TransientIngestionFailure,
)
from app.modules.knowledge.domain import (
    KnowledgeConcurrencyConflict,
    KnowledgeIngestionJob,
    ScanEvidence,
    StageCheckpoint,
)


class KnowledgeIngestionRunner:
    """Claims and commits one bounded stage unit per invocation."""

    def __init__(
        self,
        repository: IngestionRepository,
        approval_gate: SourceApprovalGate,
        sources: ApprovedSourceContentReader,
        quarantine: QuarantineStore,
        scanner: ContentScanner,
        parser: DocumentParser,
        chunker: KnowledgeChunker,
        duplicate_detector: DuplicateDetector,
        embedder: KnowledgeEmbedder,
        artifacts: IngestionArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
        lease_duration: timedelta = timedelta(seconds=60),
        heartbeat_interval: timedelta | None = None,
    ) -> None:
        self._repository = repository
        self._approval_gate = approval_gate
        self._sources = sources
        self._quarantine = quarantine
        self._scanner = scanner
        self._parser = parser
        self._chunker = chunker
        self._duplicate_detector = duplicate_detector
        self._embedder = embedder
        self._artifacts = artifacts
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lease_duration = lease_duration
        self._heartbeat_interval = heartbeat_interval or timedelta(
            seconds=max(1.0, min(10.0, lease_duration.total_seconds() / 3))
        )

    async def run_once(self) -> KnowledgeIngestionJob | None:
        started_at = self._clock()
        claimed = await self._repository.claim_next(
            now=started_at,
            lease_expires_at=started_at + self._lease_duration,
        )
        if claimed is None:
            return None
        expected_version = claimed.version
        attempt_number = max(1, claimed.stage_attempt)
        try:
            async with asyncio.timeout(claimed.limits.max_stage_seconds):
                if claimed.current_stage != "delete":
                    await self._approval_gate.assert_current(claimed)
                updated, checkpoint, artifacts, event_type = await self._run_stage_with_heartbeat(
                    claimed, expected_version=expected_version
                )
        except KnowledgeConcurrencyConflict:
            raise
        except PermanentIngestionFailure as error:
            updated = claimed.failed(
                code=error.code,
                disposition="permanent",
                next_attempt_at=None,
                fencing_token=claimed.fencing_token,
                at=self._clock(),
            )
            if claimed.current_stage not in {"quarantine", "pre_scan"}:
                updated = updated.request_deletion(
                    generation=claimed.deletion_generation + 1,
                    at=self._clock(),
                )
                event_type = "knowledge.ingestion.deletion-scheduled"
            else:
                event_type = "knowledge.ingestion.failed-safely"
            checkpoint, artifacts = None, ()
        except TimeoutError:
            updated = self._transient_failure(claimed, "STAGE_TIMEOUT")
            checkpoint, artifacts = None, ()
            event_type = _failure_event(updated)
        except TransientIngestionFailure as error:
            updated = self._transient_failure(claimed, error.code)
            checkpoint, artifacts = None, ()
            event_type = _failure_event(updated)
        except Exception:
            updated = self._transient_failure(claimed, "WORKER_UNEXPECTED")
            checkpoint, artifacts = None, ()
            event_type = _failure_event(updated)
        return await self._repository.commit_stage(
            updated,
            expected_version=expected_version,
            fencing_token=claimed.fencing_token,
            attempt_number=attempt_number,
            checkpoint=checkpoint,
            artifacts=artifacts,
            event_type=event_type,
        )

    async def _run_stage_with_heartbeat(
        self, job: KnowledgeIngestionJob, *, expected_version: int
    ) -> tuple[
        KnowledgeIngestionJob,
        StageCheckpoint,
        tuple[ArtifactDescriptor, ...],
        str,
    ]:
        stage_task = asyncio.create_task(self._run_stage(job))
        heartbeat_task = asyncio.create_task(
            self._heartbeat(job, expected_version=expected_version)
        )
        try:
            done, _ = await asyncio.wait(
                {stage_task, heartbeat_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if heartbeat_task in done:
                error = heartbeat_task.exception()
                if error is not None:
                    raise error
                raise KnowledgeConcurrencyConflict("ingestion lease heartbeat stopped")
            return await stage_task
        finally:
            for task in (stage_task, heartbeat_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(stage_task, heartbeat_task, return_exceptions=True)

    async def _heartbeat(self, job: KnowledgeIngestionJob, *, expected_version: int) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_interval.total_seconds())
            renewed = await self._repository.renew_lease(
                job.job_id,
                expected_version=expected_version,
                fencing_token=job.fencing_token,
                lease_expires_at=self._clock() + self._lease_duration,
            )
            if not renewed:
                raise KnowledgeConcurrencyConflict("ingestion lease fence became stale")

    def _transient_failure(
        self, claimed: KnowledgeIngestionJob, code: str
    ) -> KnowledgeIngestionJob:
        return claimed.failed(
            code=code,
            disposition="transient",
            next_attempt_at=self._clock() + timedelta(seconds=30),
            fencing_token=claimed.fencing_token,
            at=self._clock(),
        )

    async def _run_stage(
        self, job: KnowledgeIngestionJob
    ) -> tuple[
        KnowledgeIngestionJob,
        StageCheckpoint,
        tuple[ArtifactDescriptor, ...],
        str,
    ]:
        stage = job.current_stage
        if stage == "delete":
            return await self._delete(job)
        if stage == "quarantine":
            return await self._quarantine_source(job)
        if stage == "pre_scan":
            return await self._pre_scan(job)
        if stage == "parse":
            return await self._parse_one(job)
        if stage == "content_scan":
            return await self._content_scan(job)
        if stage == "chunk":
            return await self._chunk_one(job)
        if stage == "embed":
            return await self._embed_one(job)
        if stage == "verify":
            return await self._verify(job)
        raise PermanentIngestionFailure("UNSUPPORTED_INGESTION_STAGE")

    async def _delete(
        self, job: KnowledgeIngestionJob
    ) -> tuple[KnowledgeIngestionJob, StageCheckpoint, tuple[ArtifactDescriptor, ...], str]:
        quarantine_hash = await self._quarantine.delete_job_artifacts(
            job.job_id, deletion_generation=job.deletion_generation
        )
        candidate_hash = await self._artifacts.delete_job_artifacts(
            job.job_id, deletion_generation=job.deletion_generation
        )
        evidence_hash = _digest(f"{quarantine_hash}:{candidate_hash}")
        completed = job.deletion_completed(
            evidence_hash=evidence_hash,
            fencing_token=job.fencing_token,
            at=self._clock(),
        )
        checkpoint = _checkpoint(
            job,
            cursor=1,
            count=1,
            input_hash=evidence_hash,
            output_hash=_digest("deleted"),
            artifact=None,
            completed=True,
        )
        return completed, checkpoint, (), "knowledge.ingestion.tombstoned"

    async def _quarantine_source(
        self, job: KnowledgeIngestionJob
    ) -> tuple[KnowledgeIngestionJob, StageCheckpoint, tuple[ArtifactDescriptor, ...], str]:
        source = await self._quarantine.write_stream(
            job_id=job.job_id,
            deletion_generation=job.deletion_generation,
            fencing_token=job.fencing_token,
            expected_checksum=job.expected_checksum_sha256,
            max_bytes=job.limits.max_source_bytes,
            chunks=self._sources.open_stream(
                source_id=job.source_id,
                source_revision=job.source_revision,
            ),
        )
        artifact = _source_artifact(source, job.current_stage)
        checkpoint = _checkpoint(
            job,
            cursor=1,
            count=1,
            input_hash=job.expected_checksum_sha256,
            output_hash=source.checksum_sha256,
            artifact=artifact,
            completed=True,
        )
        return self._finish(job, checkpoint, (artifact,))

    async def _pre_scan(
        self, job: KnowledgeIngestionJob
    ) -> tuple[KnowledgeIngestionJob, StageCheckpoint, tuple[ArtifactDescriptor, ...], str]:
        artifact = await self._single_artifact(job, stage="quarantine")
        source = await self._quarantine.read_object(artifact)
        evidence = await self._scanner.scan_object(source)
        _assert_scan_identity(evidence, job, "pre_parse")
        checkpoint = _checkpoint(
            job,
            cursor=1,
            count=1,
            input_hash=artifact.checksum_sha256,
            output_hash=evidence.evidence_hash,
            artifact=None,
            completed=True,
        )
        return self._finish(job, checkpoint, (), evidence=evidence)

    async def _parse_one(
        self, job: KnowledgeIngestionJob
    ) -> tuple[KnowledgeIngestionJob, StageCheckpoint, tuple[ArtifactDescriptor, ...], str]:
        source_artifact = await self._single_artifact(job, stage="quarantine")
        source = await self._quarantine.read_object(source_artifact)
        prior = _stage_checkpoint(job, "parse")
        cursor = prior.continuation_cursor if prior else 0
        unit_index = (prior.record_count if prior else 0) + 1
        next_unit = None
        async for unit in self._parser.parse_units(
            source,
            after_cursor=cursor or 0,
            next_unit_index=unit_index,
            max_units=job.limits.max_units,
        ):
            next_unit = unit
            break
        if next_unit is None:
            raise PermanentIngestionFailure("PARSED_UNIT_MISSING")
        artifact = await self._artifacts.persist_parsed_unit(
            job.job_id,
            next_unit,
            parent_checksum=source_artifact.checksum_sha256,
            deletion_generation=job.deletion_generation,
            fencing_token=job.fencing_token,
        )
        checkpoint = _checkpoint(
            job,
            cursor=next_unit.unit_index,
            continuation_cursor=next_unit.continuation_cursor,
            count=next_unit.unit_index if next_unit.is_last else None,
            input_hash=(prior.output_hash if prior else source_artifact.checksum_sha256),
            output_hash=_chain(prior, artifact),
            artifact=artifact,
            completed=next_unit.is_last,
        )
        return self._finish_or_pause(job, checkpoint, (artifact,))

    async def _content_scan(
        self, job: KnowledgeIngestionJob
    ) -> tuple[KnowledgeIngestionJob, StageCheckpoint, tuple[ArtifactDescriptor, ...], str]:
        artifacts = await self._repository.list_artifacts(
            job.job_id,
            deletion_generation=job.deletion_generation,
            stage="parse",
            kind="parsed-unit",
        )
        if not artifacts:
            raise PermanentIngestionFailure("PARSED_ARTIFACT_MISSING")
        prior = _stage_checkpoint(job, "content_scan")
        cursor = prior.unit_cursor if prior else 0
        if cursor >= len(artifacts):
            raise PermanentIngestionFailure("PARSED_ARTIFACT_MISSING")
        values = [unit async for unit in self._artifacts.read_parsed_units((artifacts[cursor],))]
        if len(values) != 1:
            raise PermanentIngestionFailure("PARSED_ARTIFACT_INVALID")
        evidence = await self._scanner.scan_text(values[0])
        _assert_scan_identity(evidence, job, "post_parse")
        output_hash = _digest(f"{prior.output_hash if prior else ''}:{evidence.evidence_hash}")
        completed = cursor + 1 == len(artifacts)
        aggregate = ScanEvidence(
            phase="post_parse",
            scanner_revision=job.scanner_revision,
            policy_revision=job.policy_revision,
            result="passed",
            finding_count=0,
            evidence_hash=output_hash,
        )
        checkpoint = _checkpoint(
            job,
            cursor=cursor + 1,
            count=len(artifacts),
            input_hash=prior.output_hash if prior else _artifacts_digest(artifacts),
            output_hash=aggregate.evidence_hash,
            artifact=None,
            completed=completed,
        )
        if completed:
            return self._finish(job, checkpoint, (), evidence=aggregate)
        return self._finish_or_pause(job, checkpoint, ())

    async def _chunk_one(
        self, job: KnowledgeIngestionJob
    ) -> tuple[KnowledgeIngestionJob, StageCheckpoint, tuple[ArtifactDescriptor, ...], str]:
        parsed = await self._repository.list_artifacts(
            job.job_id,
            deletion_generation=job.deletion_generation,
            stage="parse",
            kind="parsed-unit",
        )
        prior = _stage_checkpoint(job, "chunk")
        cursor = prior.unit_cursor if prior else 0
        if cursor >= len(parsed):
            raise PermanentIngestionFailure("PARSED_ARTIFACT_MISSING")
        source_artifact = parsed[cursor]
        units = [unit async for unit in self._artifacts.read_parsed_units((source_artifact,))]
        if len(units) != 1:
            raise PermanentIngestionFailure("PARSED_ARTIFACT_INVALID")
        chunks = await self._chunker.chunk(units[0])
        if not chunks:
            raise PermanentIngestionFailure("CHUNK_OUTPUT_EMPTY")
        existing = await self._repository.list_artifacts(
            job.job_id,
            deletion_generation=job.deletion_generation,
            stage="chunk",
            kind="knowledge-chunk",
        )
        accepted: list[ChunkUnit] = []
        decisions: list[DuplicateDecision] = []
        for chunk in chunks:
            decision = await self._find_duplicate(chunk, existing, tuple(accepted))
            if decision is None:
                accepted.append(chunk)
            else:
                decisions.append(decision)
        chunk_artifacts = await self._artifacts.persist_chunks(
            job.job_id,
            tuple(accepted),
            parent_checksum=source_artifact.checksum_sha256,
            deletion_generation=job.deletion_generation,
            fencing_token=job.fencing_token,
        )
        decision_artifacts = await self._artifacts.persist_duplicate_decisions(
            job.job_id,
            tuple(decisions),
            parent_checksum=source_artifact.checksum_sha256,
            deletion_generation=job.deletion_generation,
            fencing_token=job.fencing_token,
        )
        artifacts = chunk_artifacts + decision_artifacts
        if not artifacts:
            raise PermanentIngestionFailure("CHUNK_OUTPUT_EMPTY")
        checkpoint = _checkpoint(
            job,
            cursor=cursor + 1,
            count=len(parsed),
            input_hash=(prior.output_hash if prior else source_artifact.checksum_sha256),
            output_hash=_chain_many(prior, artifacts),
            artifact=artifacts[0],
            completed=cursor + 1 == len(parsed),
        )
        return self._finish_or_pause(job, checkpoint, artifacts)

    async def _embed_one(
        self, job: KnowledgeIngestionJob
    ) -> tuple[KnowledgeIngestionJob, StageCheckpoint, tuple[ArtifactDescriptor, ...], str]:
        if self._embedder.dimension != job.embedding_dimension:
            raise PermanentIngestionFailure("EMBEDDING_DIMENSION_MISMATCH")
        chunks = await self._repository.list_artifacts(
            job.job_id,
            deletion_generation=job.deletion_generation,
            stage="chunk",
            kind="knowledge-chunk",
        )
        prior = _stage_checkpoint(job, "embed")
        cursor = prior.unit_cursor if prior else 0
        if cursor >= len(chunks):
            raise PermanentIngestionFailure("CHUNK_ARTIFACT_MISSING")
        chunk_artifact = chunks[cursor]
        values = [chunk async for chunk in self._artifacts.read_chunks((chunk_artifact,))]
        if len(values) != 1:
            raise PermanentIngestionFailure("CHUNK_ARTIFACT_INVALID")
        embedded = await self._embedder.embed((values[0],))
        artifacts = await self._artifacts.persist_embeddings(
            job.job_id,
            embedded,
            parent_checksum=chunk_artifact.checksum_sha256,
            deletion_generation=job.deletion_generation,
            fencing_token=job.fencing_token,
        )
        checkpoint = _checkpoint(
            job,
            cursor=cursor + 1,
            count=len(chunks),
            input_hash=(prior.output_hash if prior else chunk_artifact.checksum_sha256),
            output_hash=_chain_many(prior, artifacts),
            artifact=artifacts[0],
            completed=cursor + 1 == len(chunks),
        )
        return self._finish_or_pause(job, checkpoint, artifacts)

    async def _verify(
        self, job: KnowledgeIngestionJob
    ) -> tuple[KnowledgeIngestionJob, StageCheckpoint, tuple[ArtifactDescriptor, ...], str]:
        committed = await self._repository.list_artifacts(
            job.job_id, deletion_generation=job.deletion_generation
        )
        if not any(item.kind == "embedding" for item in committed):
            raise PermanentIngestionFailure("CANDIDATE_ARTIFACT_MISSING")
        final_ref, final_hash, artifact = await self._artifacts.build_manifest(job, committed)
        checkpoint = _checkpoint(
            job,
            cursor=1,
            count=1,
            input_hash=_artifacts_digest(committed),
            output_hash=final_hash,
            artifact=artifact,
            completed=True,
        )
        return self._finish(
            job,
            checkpoint,
            (artifact,),
            final_ref=final_ref,
            final_hash=final_hash,
        )

    async def _find_duplicate(
        self,
        chunk: ChunkUnit,
        existing: tuple[ArtifactDescriptor, ...],
        accepted: tuple[ChunkUnit, ...],
    ) -> DuplicateDecision | None:
        async for candidate in self._artifacts.read_chunks(existing):
            decision = await self._duplicate_detector.compare(chunk, candidate)
            if decision is not None:
                return decision
        for candidate in accepted:
            decision = await self._duplicate_detector.compare(chunk, candidate)
            if decision is not None:
                return decision
        return None

    async def _single_artifact(
        self, job: KnowledgeIngestionJob, *, stage: str
    ) -> ArtifactDescriptor:
        artifacts = await self._repository.list_artifacts(
            job.job_id, deletion_generation=job.deletion_generation, stage=stage
        )
        if len(artifacts) != 1:
            raise PermanentIngestionFailure("INGESTION_ARTIFACT_CARDINALITY")
        return artifacts[0]

    def _finish_or_pause(
        self,
        job: KnowledgeIngestionJob,
        checkpoint: StageCheckpoint,
        artifacts: tuple[ArtifactDescriptor, ...],
    ) -> tuple[KnowledgeIngestionJob, StageCheckpoint, tuple[ArtifactDescriptor, ...], str]:
        if checkpoint.completed:
            return self._finish(job, checkpoint, artifacts)
        checkpointed = job.checkpoint(checkpoint, fencing_token=job.fencing_token, at=self._clock())
        paused = checkpointed.pause_stage(fencing_token=job.fencing_token, at=self._clock())
        return paused, checkpoint, artifacts, "knowledge.ingestion.unit-checkpointed"

    def _finish(
        self,
        job: KnowledgeIngestionJob,
        checkpoint: StageCheckpoint,
        artifacts: tuple[ArtifactDescriptor, ...],
        *,
        evidence: ScanEvidence | None = None,
        final_ref: str | None = None,
        final_hash: str | None = None,
    ) -> tuple[KnowledgeIngestionJob, StageCheckpoint, tuple[ArtifactDescriptor, ...], str]:
        checkpointed = job.checkpoint(checkpoint, fencing_token=job.fencing_token, at=self._clock())
        completed = checkpointed.complete_stage(
            fencing_token=job.fencing_token,
            at=self._clock(),
            scan_evidence=evidence,
            final_manifest_ref=final_ref,
            final_manifest_hash=final_hash,
        )
        event = (
            "knowledge.ingestion.candidate-ready"
            if completed.status == "candidate_ready"
            else "knowledge.ingestion.stage-completed"
        )
        return completed, checkpoint, artifacts, event


def _checkpoint(
    job: KnowledgeIngestionJob,
    *,
    cursor: int,
    continuation_cursor: int | None = None,
    count: int | None,
    input_hash: str,
    output_hash: str,
    artifact: ArtifactDescriptor | None,
    completed: bool,
) -> StageCheckpoint:
    return StageCheckpoint(
        stage=job.current_stage,
        unit_cursor=cursor,
        continuation_cursor=continuation_cursor,
        unit_count=count,
        input_hash=input_hash,
        output_hash=output_hash,
        artifact_ref=artifact.artifact_ref if artifact else None,
        byte_count=artifact.byte_count if artifact else 0,
        record_count=count if count is not None else cursor,
        completed=completed,
    )


def _source_artifact(source: SourceObject, stage: str) -> ArtifactDescriptor:
    return ArtifactDescriptor(
        artifact_ref=source.object_ref,
        kind="quarantined-source",
        stage=stage,
        unit_key="source",
        checksum_sha256=source.checksum_sha256,
        byte_count=source.byte_count,
        record_count=1,
        deletion_generation=source.deletion_generation,
        fencing_token=source.fencing_token,
    )


def _assert_scan_identity(evidence: ScanEvidence, job: KnowledgeIngestionJob, phase: str) -> None:
    if evidence.result != "passed":
        raise PermanentIngestionFailure(
            "PRE_PARSE_SCAN_REJECTED" if phase == "pre_parse" else "POST_PARSE_SCAN_REJECTED"
        )
    if (
        evidence.phase != phase
        or evidence.scanner_revision != job.scanner_revision
        or evidence.policy_revision != job.policy_revision
    ):
        raise PermanentIngestionFailure("SCAN_EVIDENCE_REJECTED")


def _stage_checkpoint(job: KnowledgeIngestionJob, stage: str) -> StageCheckpoint | None:
    return next((item for item in job.checkpoints if item.stage == stage), None)


def _chain(prior: StageCheckpoint | None, artifact: ArtifactDescriptor) -> str:
    return _digest(f"{prior.output_hash if prior else ''}:{artifact.checksum_sha256}")


def _chain_many(prior: StageCheckpoint | None, artifacts: tuple[ArtifactDescriptor, ...]) -> str:
    return _digest(
        f"{prior.output_hash if prior else ''}:"
        + ":".join(item.checksum_sha256 for item in artifacts)
    )


def _artifacts_digest(artifacts: tuple[ArtifactDescriptor, ...]) -> str:
    return _digest(":".join(item.checksum_sha256 for item in artifacts))


def _failure_event(job: KnowledgeIngestionJob) -> str:
    return (
        "knowledge.ingestion.dead-lettered"
        if job.status == "dead_lettered"
        else "knowledge.ingestion.retry-scheduled"
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
