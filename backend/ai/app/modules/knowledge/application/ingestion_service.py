import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from app.modules.knowledge.application.ingestion_ports import (
    IngestionRepository,
    PermanentIngestionFailure,
    SourceApprovalGate,
)
from app.modules.knowledge.application.ports import SourceRegisterReader
from app.modules.knowledge.domain import (
    IngestionLimits,
    KnowledgeActor,
    KnowledgeAuthorizationRejected,
    KnowledgeIngestionJob,
    KnowledgeScope,
    SourceApprovalRejected,
)


@dataclass(frozen=True, slots=True)
class SubmitKnowledgeIngestion:
    source_id: str
    expected_source_revision: str
    expected_checksum_sha256: str
    scope: KnowledgeScope
    parser_revision: str
    chunker_revision: str
    scanner_revision: str
    embedding_revision: str
    embedding_dimension: int
    policy_revision: str
    code_revision: str
    limits: IngestionLimits


class KnowledgeIngestionService:
    def __init__(
        self,
        sources: SourceRegisterReader,
        jobs: IngestionRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sources = sources
        self._jobs = jobs
        self._clock = clock or (lambda: datetime.now(UTC))

    async def submit(
        self,
        command: SubmitKnowledgeIngestion,
        *,
        actor: KnowledgeActor,
        idempotency_key: str,
    ) -> KnowledgeIngestionJob:
        if actor.capability != "knowledge.ingestion.submit":
            raise KnowledgeAuthorizationRejected("ingestion submit capability is required")
        resolved = await self._sources.read_approved((command.source_id,))
        if len(resolved) != 1:
            raise SourceApprovalRejected("approved source was not resolved")
        source = resolved[0]
        source.assert_eligible(command.scope, at=self._clock())
        if (
            source.source_revision != command.expected_source_revision
            or source.checksum_sha256 != command.expected_checksum_sha256
        ):
            raise SourceApprovalRejected("source revision or checksum changed before submit")
        scope_key = command.scope.acl_namespace
        pipeline_digest = _pipeline_digest(command, source.digest())
        job_id = uuid5(
            NAMESPACE_URL,
            f"vfbiz:ingestion:{actor.actor_ref}:{scope_key}:{idempotency_key}",
        )
        now = self._clock()
        job = KnowledgeIngestionJob(
            job_id=job_id,
            source_id=source.source_id,
            source_revision=source.source_revision,
            source_snapshot_hash=source.digest(),
            expected_checksum_sha256=source.checksum_sha256,
            scope=command.scope,
            parser_revision=command.parser_revision,
            chunker_revision=command.chunker_revision,
            scanner_revision=command.scanner_revision,
            embedding_revision=command.embedding_revision,
            embedding_dimension=command.embedding_dimension,
            policy_revision=command.policy_revision,
            code_revision=command.code_revision,
            candidate_namespace=(
                f"candidate/{command.scope.assistant_profile}/{command.scope.domain}/"
                f"{command.scope.locale.lower()}/{pipeline_digest[:24]}"
            ),
            limits=command.limits,
            created_at=now,
            updated_at=now,
        )
        return await self._jobs.add_idempotent(
            job, idempotency_key=idempotency_key, actor_ref=actor.actor_ref
        )

    async def get(self, job_id: UUID) -> KnowledgeIngestionJob:
        job = await self._jobs.get(job_id)
        if job is None:
            raise LookupError("knowledge ingestion job does not exist")
        return job

    async def request_deletion(
        self,
        job_id: UUID,
        *,
        generation: int,
        actor: KnowledgeActor,
        idempotency_key: str,
    ) -> KnowledgeIngestionJob:
        if actor.capability != "knowledge.ingestion.delete":
            raise KnowledgeAuthorizationRejected("ingestion delete capability is required")
        replay = await self._jobs.get_idempotent_control_result(
            job_id,
            operation="request-deletion",
            idempotency_key=idempotency_key,
        )
        if replay is not None:
            return replay
        current = await self.get(job_id)
        updated = current.request_deletion(generation=generation, at=self._clock())
        return await self._jobs.save_control_transition(
            updated,
            expected_version=current.version,
            operation="request-deletion",
            idempotency_key=idempotency_key,
            actor_ref=actor.actor_ref,
        )

    async def replay_dead_letter(
        self,
        job_id: UUID,
        *,
        generation: int,
        actor: KnowledgeActor,
        idempotency_key: str,
    ) -> KnowledgeIngestionJob:
        if actor.capability != "knowledge.ingestion.replay":
            raise KnowledgeAuthorizationRejected("ingestion replay capability is required")
        replay = await self._jobs.get_idempotent_control_result(
            job_id,
            operation="replay-dead-letter",
            idempotency_key=idempotency_key,
        )
        if replay is not None:
            return replay
        current = await self.get(job_id)
        resolved = await self._sources.read_approved((current.source_id,))
        if len(resolved) != 1:
            raise SourceApprovalRejected("approved source was not resolved for replay")
        source = resolved[0]
        source.assert_eligible(current.scope, at=self._clock())
        if (
            source.source_revision != current.source_revision
            or source.checksum_sha256 != current.expected_checksum_sha256
            or source.digest() != current.source_snapshot_hash
        ):
            raise SourceApprovalRejected("source snapshot changed before replay")
        updated = current.replay_dead_letter(generation=generation, at=self._clock())
        return await self._jobs.save_control_transition(
            updated,
            expected_version=current.version,
            operation="replay-dead-letter",
            idempotency_key=idempotency_key,
            actor_ref=actor.actor_ref,
        )


class KnowledgeSourceApprovalGate(SourceApprovalGate):
    def __init__(
        self,
        sources: SourceRegisterReader,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sources = sources
        self._clock = clock or (lambda: datetime.now(UTC))

    async def assert_current(self, job: KnowledgeIngestionJob) -> None:
        resolved = await self._sources.read_approved((job.source_id,))
        if len(resolved) != 1:
            raise PermanentIngestionFailure("SOURCE_APPROVAL_REVOKED")
        source = resolved[0]
        try:
            source.assert_eligible(job.scope, at=self._clock())
        except SourceApprovalRejected as error:
            raise PermanentIngestionFailure("SOURCE_APPROVAL_REVOKED") from error
        if (
            source.source_revision != job.source_revision
            or source.checksum_sha256 != job.expected_checksum_sha256
            or source.digest() != job.source_snapshot_hash
        ):
            raise PermanentIngestionFailure("SOURCE_SNAPSHOT_CHANGED")


def _pipeline_digest(command: SubmitKnowledgeIngestion, source_snapshot_hash: str) -> str:
    payload = {
        "source_snapshot_hash": source_snapshot_hash,
        "scope": command.scope.model_dump(mode="json"),
        "parser_revision": command.parser_revision,
        "chunker_revision": command.chunker_revision,
        "scanner_revision": command.scanner_revision,
        "embedding_revision": command.embedding_revision,
        "embedding_dimension": command.embedding_dimension,
        "policy_revision": command.policy_revision,
        "code_revision": command.code_revision,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
