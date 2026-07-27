import hashlib
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, delete, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.knowledge.application.ingestion_ports import (
    ArtifactDescriptor,
    IngestionRepository,
)
from app.modules.knowledge.domain import (
    KnowledgeConcurrencyConflict,
    KnowledgeIngestionJob,
    StageCheckpoint,
)
from app.modules.knowledge.infrastructure.ingestion_models import (
    KnowledgeIngestionArtifact,
    KnowledgeIngestionControlCommand,
    KnowledgeIngestionJobRecord,
    KnowledgeIngestionOutbox,
    KnowledgeIngestionStageAttempt,
)


class PostgresIngestionRepository(IngestionRepository):
    """Durable, fenced job queue; artifact contents remain in object storage."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add_idempotent(
        self, job: KnowledgeIngestionJob, *, idempotency_key: str, actor_ref: str
    ) -> KnowledgeIngestionJob:
        key_hash = _sha256(idempotency_key)
        async with self._sessions() as session, session.begin():
            await _advisory_lock(session, actor_ref, key_hash)
            existing = await session.scalar(
                select(KnowledgeIngestionJobRecord).where(
                    KnowledgeIngestionJobRecord.actor_ref == actor_ref,
                    KnowledgeIngestionJobRecord.idempotency_key_hash == key_hash,
                )
            )
            if existing is not None:
                if existing.command_fingerprint != job.command_fingerprint:
                    raise KnowledgeConcurrencyConflict(
                        "idempotency key was reused with different ingestion inputs"
                    )
                return _to_domain(existing)
            session.add(_job_record(job, actor_ref=actor_ref, key_hash=key_hash))
            session.add(
                KnowledgeIngestionOutbox(
                    job_id=job.job_id,
                    event_type="knowledge.ingestion.queued",
                    aggregate_version=job.version,
                    payload=_event_payload(job),
                )
            )
            await session.flush()
            return job

    async def get(self, job_id: UUID) -> KnowledgeIngestionJob | None:
        async with self._sessions() as session:
            record = await session.get(KnowledgeIngestionJobRecord, job_id)
            return _to_domain(record) if record is not None else None

    async def list_artifacts(
        self,
        job_id: UUID,
        *,
        deletion_generation: int,
        stage: str | None = None,
        kind: str | None = None,
    ) -> tuple[ArtifactDescriptor, ...]:
        async with self._sessions() as session:
            statement = select(KnowledgeIngestionArtifact).where(
                KnowledgeIngestionArtifact.job_id == job_id,
                KnowledgeIngestionArtifact.deletion_generation == deletion_generation,
            )
            if stage is not None:
                statement = statement.where(KnowledgeIngestionArtifact.stage == stage)
            if kind is not None:
                statement = statement.where(KnowledgeIngestionArtifact.kind == kind)
            rows = (
                await session.scalars(
                    statement.order_by(
                        KnowledgeIngestionArtifact.unit_key,
                        KnowledgeIngestionArtifact.created_at,
                    )
                )
            ).all()
            return tuple(_artifact_descriptor(row) for row in rows)

    async def get_idempotent_control_result(
        self,
        job_id: UUID,
        *,
        operation: Literal["request-deletion", "replay-dead-letter"],
        idempotency_key: str,
    ) -> KnowledgeIngestionJob | None:
        async with self._sessions() as session:
            command = await session.scalar(
                select(KnowledgeIngestionControlCommand).where(
                    KnowledgeIngestionControlCommand.job_id == job_id,
                    KnowledgeIngestionControlCommand.operation == operation,
                    KnowledgeIngestionControlCommand.idempotency_key_hash
                    == _sha256(idempotency_key),
                )
            )
            return (
                KnowledgeIngestionJob.model_validate(command.result_snapshot)
                if command is not None
                else None
            )

    async def save_control_transition(
        self,
        job: KnowledgeIngestionJob,
        *,
        expected_version: int,
        operation: Literal["request-deletion", "replay-dead-letter"],
        idempotency_key: str,
        actor_ref: str,
    ) -> KnowledgeIngestionJob:
        key_hash = _sha256(idempotency_key)
        async with self._sessions() as session, session.begin():
            await _advisory_lock(session, str(job.job_id), f"{operation}:{key_hash}")
            replay = await session.scalar(
                select(KnowledgeIngestionControlCommand).where(
                    KnowledgeIngestionControlCommand.job_id == job.job_id,
                    KnowledgeIngestionControlCommand.operation == operation,
                    KnowledgeIngestionControlCommand.idempotency_key_hash == key_hash,
                )
            )
            if replay is not None:
                return KnowledgeIngestionJob.model_validate(replay.result_snapshot)
            result = await session.execute(
                update(KnowledgeIngestionJobRecord)
                .where(
                    KnowledgeIngestionJobRecord.id == job.job_id,
                    KnowledgeIngestionJobRecord.version == expected_version,
                )
                .values(**_record_values(job))
                .returning(KnowledgeIngestionJobRecord.id)
            )
            if result.scalar_one_or_none() is None:
                raise KnowledgeConcurrencyConflict("ingestion control state changed")
            session.add(
                KnowledgeIngestionControlCommand(
                    job_id=job.job_id,
                    operation=operation,
                    idempotency_key_hash=key_hash,
                    actor_ref=actor_ref,
                    result_snapshot=job.model_dump(mode="json"),
                )
            )
            session.add(
                KnowledgeIngestionOutbox(
                    job_id=job.job_id,
                    event_type=f"knowledge.ingestion.{operation}",
                    aggregate_version=job.version,
                    payload=_event_payload(job),
                )
            )
            await session.flush()
            return job

    async def claim_next(
        self, *, now: datetime, lease_expires_at: datetime
    ) -> KnowledgeIngestionJob | None:
        async with self._sessions() as session, session.begin():
            record = await session.scalar(
                select(KnowledgeIngestionJobRecord)
                .where(
                    or_(
                        KnowledgeIngestionJobRecord.status == "queued",
                        and_(
                            KnowledgeIngestionJobRecord.status == "retry_wait",
                            KnowledgeIngestionJobRecord.next_attempt_at <= now,
                        ),
                        and_(
                            KnowledgeIngestionJobRecord.status == "running",
                            KnowledgeIngestionJobRecord.lease_expires_at <= now,
                        ),
                        KnowledgeIngestionJobRecord.status == "deletion_pending",
                        and_(
                            KnowledgeIngestionJobRecord.status == "deleting",
                            KnowledgeIngestionJobRecord.lease_expires_at <= now,
                        ),
                    )
                )
                .order_by(KnowledgeIngestionJobRecord.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if record is None:
                return None
            current = _to_domain(record)
            next_fence = current.fencing_token + 1
            if current.status in {"deletion_pending", "deleting"}:
                if current.status == "deletion_pending":
                    claimed = current.deletion_started(
                        fencing_token=next_fence,
                        lease_expires_at=lease_expires_at,
                        at=now,
                    )
                else:
                    claimed = current.model_copy(
                        update={
                            "fencing_token": next_fence,
                            "lease_expires_at": lease_expires_at,
                            "updated_at": now,
                            "version": current.version + 1,
                        }
                    )
            else:
                claimed = current.claim(
                    fencing_token=next_fence,
                    lease_expires_at=lease_expires_at,
                    at=now,
                )
            _apply_record(record, claimed)
            return claimed

    async def renew_lease(
        self,
        job_id: UUID,
        *,
        expected_version: int,
        fencing_token: int,
        lease_expires_at: datetime,
    ) -> bool:
        async with self._sessions() as session, session.begin():
            renewed = await session.scalar(
                update(KnowledgeIngestionJobRecord)
                .where(
                    KnowledgeIngestionJobRecord.id == job_id,
                    KnowledgeIngestionJobRecord.version == expected_version,
                    KnowledgeIngestionJobRecord.fencing_token == fencing_token,
                    KnowledgeIngestionJobRecord.status.in_(("running", "deleting")),
                )
                .values(lease_expires_at=lease_expires_at)
                .returning(KnowledgeIngestionJobRecord.id)
            )
            return renewed is not None

    async def commit_stage(
        self,
        job: KnowledgeIngestionJob,
        *,
        expected_version: int,
        fencing_token: int,
        attempt_number: int,
        checkpoint: StageCheckpoint | None,
        artifacts: tuple[ArtifactDescriptor, ...],
        event_type: str,
    ) -> KnowledgeIngestionJob:
        if job.version <= expected_version or job.fencing_token != fencing_token:
            raise KnowledgeConcurrencyConflict("invalid ingestion commit version or fence")
        if any(
            artifact.deletion_generation != job.deletion_generation
            or artifact.fencing_token != fencing_token
            for artifact in artifacts
        ):
            raise KnowledgeConcurrencyConflict("artifact generation or fence is invalid")
        expected_deletion_generation = (
            job.deletion_generation - 1
            if job.status == "deletion_pending"
            else job.deletion_generation
        )
        async with self._sessions() as session, session.begin():
            statement = (
                update(KnowledgeIngestionJobRecord)
                .where(
                    KnowledgeIngestionJobRecord.id == job.job_id,
                    KnowledgeIngestionJobRecord.version == expected_version,
                    KnowledgeIngestionJobRecord.fencing_token == fencing_token,
                    KnowledgeIngestionJobRecord.deletion_generation == expected_deletion_generation,
                )
                .values(**_record_values(job))
                .returning(KnowledgeIngestionJobRecord.id)
            )
            result = await session.execute(statement)
            if result.scalar_one_or_none() is None:
                raise KnowledgeConcurrencyConflict(
                    "ingestion job changed or worker fence became stale"
                )
            if job.status == "tombstoned":
                await session.execute(
                    delete(KnowledgeIngestionArtifact).where(
                        KnowledgeIngestionArtifact.job_id == job.job_id
                    )
                )
            for artifact in artifacts:
                inserted = await session.scalar(
                    insert(KnowledgeIngestionArtifact)
                    .values(
                        job_id=job.job_id,
                        deletion_generation=job.deletion_generation,
                        fencing_token=artifact.fencing_token,
                        stage=artifact.stage,
                        kind=artifact.kind,
                        unit_key=artifact.unit_key,
                        artifact_ref=artifact.artifact_ref,
                        checksum_sha256=artifact.checksum_sha256,
                        byte_count=artifact.byte_count,
                        record_count=artifact.record_count,
                        parent_checksum=artifact.parent_checksum,
                    )
                    .on_conflict_do_nothing(constraint="uq_ai_knowledge_ingestion_artifact")
                    .returning(KnowledgeIngestionArtifact.id)
                )
                if inserted is None:
                    existing = await session.scalar(
                        select(KnowledgeIngestionArtifact).where(
                            KnowledgeIngestionArtifact.job_id == job.job_id,
                            KnowledgeIngestionArtifact.deletion_generation
                            == job.deletion_generation,
                            KnowledgeIngestionArtifact.stage == artifact.stage,
                            KnowledgeIngestionArtifact.kind == artifact.kind,
                            KnowledgeIngestionArtifact.unit_key == artifact.unit_key,
                        )
                    )
                    if existing is None or (
                        existing.checksum_sha256 != artifact.checksum_sha256
                        or existing.artifact_ref != artifact.artifact_ref
                        or existing.byte_count != artifact.byte_count
                        or existing.record_count != artifact.record_count
                        or existing.parent_checksum != artifact.parent_checksum
                        or existing.fencing_token != artifact.fencing_token
                    ):
                        raise KnowledgeConcurrencyConflict(
                            "artifact identity was reused with different content"
                        )
            session.add(
                KnowledgeIngestionStageAttempt(
                    job_id=job.job_id,
                    stage=(checkpoint.stage if checkpoint else job.current_stage),
                    attempt_number=attempt_number,
                    fencing_token=fencing_token,
                    outcome=_attempt_outcome(event_type, job.status),
                    failure_code=job.failure_code,
                    checkpoint=(checkpoint.model_dump(mode="json") if checkpoint else None),
                    completed_at=job.updated_at,
                )
            )
            session.add(
                KnowledgeIngestionOutbox(
                    job_id=job.job_id,
                    event_type=event_type,
                    aggregate_version=job.version,
                    payload=_event_payload(job),
                )
            )
            await session.flush()
        return job


async def _advisory_lock(session: AsyncSession, actor_ref: str, key_hash: str) -> None:
    lock_key = int.from_bytes(
        hashlib.sha256(f"{actor_ref}:{key_hash}".encode()).digest()[:8],
        byteorder="big",
        signed=True,
    )
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})


def _job_record(
    job: KnowledgeIngestionJob, *, actor_ref: str, key_hash: str
) -> KnowledgeIngestionJobRecord:
    return KnowledgeIngestionJobRecord(
        id=job.job_id,
        actor_ref=actor_ref,
        idempotency_key_hash=key_hash,
        **_record_values(job),
    )


def _record_values(job: KnowledgeIngestionJob) -> dict[str, object]:
    return {
        "source_id": job.source_id,
        "source_revision": job.source_revision,
        "scope_key": job.scope.acl_namespace,
        "command_fingerprint": job.command_fingerprint,
        "status": job.status,
        "current_stage": job.current_stage,
        "next_attempt_at": job.next_attempt_at,
        "lease_expires_at": job.lease_expires_at,
        "fencing_token": job.fencing_token,
        "deletion_generation": job.deletion_generation,
        "version": job.version,
        "aggregate": job.model_dump(mode="json"),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _apply_record(record: KnowledgeIngestionJobRecord, job: KnowledgeIngestionJob) -> None:
    for name, value in _record_values(job).items():
        setattr(record, name, value)


def _to_domain(record: KnowledgeIngestionJobRecord) -> KnowledgeIngestionJob:
    return KnowledgeIngestionJob.model_validate(record.aggregate)


def _event_payload(job: KnowledgeIngestionJob) -> dict[str, object]:
    return {
        "jobId": str(job.job_id),
        "sourceId": job.source_id,
        "scopeKey": job.scope.acl_namespace,
        "status": job.status,
        "stage": job.current_stage,
        "version": job.version,
        "fencingToken": job.fencing_token,
        "deletionGeneration": job.deletion_generation,
    }


def _artifact_descriptor(record: KnowledgeIngestionArtifact) -> ArtifactDescriptor:
    return ArtifactDescriptor(
        artifact_ref=record.artifact_ref,
        kind=record.kind,
        stage=record.stage,
        unit_key=record.unit_key,
        checksum_sha256=record.checksum_sha256,
        byte_count=record.byte_count,
        record_count=record.record_count,
        parent_checksum=record.parent_checksum,
        deletion_generation=record.deletion_generation,
        fencing_token=record.fencing_token,
    )


def _attempt_outcome(event_type: str, status: str) -> str:
    mapping = {
        "knowledge.ingestion.stage-completed": "completed",
        "knowledge.ingestion.candidate-ready": "completed",
        "knowledge.ingestion.unit-checkpointed": "checkpointed",
        "knowledge.ingestion.retry-scheduled": "retry_scheduled",
        "knowledge.ingestion.dead-lettered": "dead_lettered",
        "knowledge.ingestion.failed-safely": "failed_safely",
        "knowledge.ingestion.deletion-scheduled": "deletion_scheduled",
        "knowledge.ingestion.tombstoned": "tombstoned",
    }
    try:
        return mapping[event_type]
    except KeyError as error:
        raise KnowledgeConcurrencyConflict(
            f"unsupported ingestion attempt event for status {status}"
        ) from error


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
