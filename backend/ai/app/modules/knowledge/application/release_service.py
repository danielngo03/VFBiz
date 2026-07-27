import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from app.modules.knowledge.application.ports import (
    KnowledgeReleaseRepository,
    SourceRegisterReader,
)
from app.modules.knowledge.domain import (
    ApprovedKnowledgeSource,
    InvalidKnowledgeTransition,
    KnowledgeActor,
    KnowledgeAuthorizationRejected,
    KnowledgeCriticality,
    KnowledgeRelease,
    KnowledgeScope,
    RevisionBarrier,
    SourceApprovalRejected,
    source_set_digest,
)


@dataclass(frozen=True, slots=True)
class CreateKnowledgeCandidate:
    scope: KnowledgeScope
    criticality: KnowledgeCriticality
    source_ids: tuple[str, ...]
    transform_revision: str
    chunking_revision: str
    index_generation_id: UUID
    embedding_revision: str
    embedding_dimension: int
    retriever_revision: str
    policy_revision: str
    index_checksum: str
    effective_at: datetime
    freshness_expires_at: datetime
    barrier_generation: int


class KnowledgeReleaseService:
    def __init__(
        self,
        sources: SourceRegisterReader,
        releases: KnowledgeReleaseRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sources = sources
        self._releases = releases
        self._clock = clock or (lambda: datetime.now(UTC))

    async def create_candidate(
        self,
        command: CreateKnowledgeCandidate,
        *,
        actor: KnowledgeActor,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeRelease:
        if actor.capability != "knowledge.release.submit":
            raise KnowledgeAuthorizationRejected("submit capability is required")
        sources = await self._sources.read_approved(command.source_ids)
        if len(sources) != len(set(command.source_ids)):
            raise SourceApprovalRejected("all approved sources must be resolved")
        now = self._clock()
        for source in sources:
            source.assert_eligible(command.scope, at=now)
        release = KnowledgeRelease(
            release_id=uuid5(
                NAMESPACE_URL,
                "vfbiz:knowledge:"
                f"{actor.actor_ref}:{command.scope.model_dump_json()}:{idempotency_key}",
            ),
            scope=command.scope,
            criticality=command.criticality,
            sources=sources,
            source_set_hash=source_set_digest(sources),
            transform_revision=command.transform_revision,
            chunking_revision=command.chunking_revision,
            index_generation_id=command.index_generation_id,
            embedding_revision=command.embedding_revision,
            embedding_dimension=command.embedding_dimension,
            retriever_revision=command.retriever_revision,
            policy_revision=command.policy_revision,
            index_checksum=command.index_checksum,
            proposer_ref=actor.actor_ref,
            effective_at=command.effective_at,
            freshness_expires_at=command.freshness_expires_at,
            barrier_generation=command.barrier_generation,
            version=1,
        )
        await self._releases.add(
            release,
            actor=actor,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
        return release

    async def record_evaluation(
        self,
        release_id: UUID,
        *,
        run_ref: str,
        suite_revision: str,
        evidence_hashes: tuple[str, ...],
        actor: KnowledgeActor,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeRelease:
        actor.assert_evaluation_authority()
        replay = await self._releases.get_idempotent_release_result(
            release_id, operation="evaluation-recorded", idempotency_key=idempotency_key
        )
        if replay is not None:
            return replay
        release = await self._require_release(release_id)
        evaluated = release.record_evaluation(
            run_ref=run_ref,
            suite_revision=suite_revision,
            evidence_hashes=evidence_hashes,
        )
        await self._releases.save_transition(
            evaluated,
            expected_version=release.version,
            actor=actor,
            reason="evaluation-recorded",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
        return evaluated

    async def approve(
        self,
        release_id: UUID,
        *,
        actor: KnowledgeActor,
        evidence_hash: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeRelease:
        actor.assert_human_authority("knowledge.release.approve")
        replay = await self._releases.get_idempotent_release_result(
            release_id,
            operation="maker-checker-approved",
            idempotency_key=idempotency_key,
        )
        if replay is not None:
            return replay
        release = await self._require_release(release_id)
        current_sources = await self._revalidate_sources(release)
        approved = release.approve(
            actor=actor,
            source_set_hash=source_set_digest(current_sources),
            evidence_hash=evidence_hash,
        )
        await self._releases.save_transition(
            approved,
            expected_version=release.version,
            actor=actor,
            reason="maker-checker-approved",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
        return approved

    async def open_barrier(
        self,
        release_id: UUID,
        *,
        deadline_at: datetime,
        actor: KnowledgeActor,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> RevisionBarrier:
        if actor.capability != "knowledge.release.submit":
            raise KnowledgeAuthorizationRejected("submit capability is required")
        replay = await self._releases.get_idempotent_barrier_result(
            release_id, idempotency_key=idempotency_key
        )
        if replay is not None:
            return replay
        release = await self._require_release(release_id)
        if release.status != "ready":
            raise InvalidKnowledgeTransition("only a ready release can open a barrier")
        now = self._clock()
        if deadline_at <= now or deadline_at > now + timedelta(minutes=15):
            raise InvalidKnowledgeTransition("barrier deadline must be within the next 15 minutes")
        current_sources = await self._revalidate_sources(release)
        return await self._releases.open_barrier(
            scope=release.scope,
            candidate_release_id=release.release_id,
            expected_release_version=release.version,
            current_source_hashes={source.source_id: source.digest() for source in current_sources},
            critical=release.criticality == "critical",
            deadline_at=deadline_at,
            actor=actor,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    async def activate(
        self,
        release_id: UUID,
        *,
        expected_pointer_version: int,
        expected_barrier_generation: int,
        actor: KnowledgeActor,
        reason: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeRelease:
        actor.assert_human_authority("knowledge.release.activate")
        reason = _validate_reason_code(reason)
        replay = await self._releases.get_idempotent_release_result(
            release_id, operation="activate", idempotency_key=idempotency_key
        )
        if replay is not None:
            return replay
        release = await self._require_release(release_id)
        current_sources = await self._revalidate_sources(release)
        current_hash = source_set_digest(current_sources)
        if current_hash != release.source_set_hash:
            raise SourceApprovalRejected("source snapshot changed before activation")
        return await self._releases.activate_atomic(
            release_id=release.release_id,
            expected_release_version=release.version,
            expected_pointer_version=expected_pointer_version,
            expected_barrier_generation=expected_barrier_generation,
            current_source_hashes={source.source_id: source.digest() for source in current_sources},
            actor=actor,
            reason=reason,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    async def rollback(
        self,
        release_id: UUID,
        *,
        expected_pointer_version: int,
        expected_barrier_generation: int,
        actor: KnowledgeActor,
        reason: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeRelease:
        actor.assert_human_authority("knowledge.release.rollback")
        reason = _validate_reason_code(reason)
        replay = await self._releases.get_idempotent_release_result(
            release_id, operation="rollback", idempotency_key=idempotency_key
        )
        if replay is not None:
            return replay
        release = await self._require_release(release_id)
        if release.status != "superseded":
            raise InvalidKnowledgeTransition("only a superseded release can be restored")
        current_sources = await self._revalidate_sources(release)
        return await self._releases.rollback_atomic(
            target_release_id=release.release_id,
            expected_pointer_version=expected_pointer_version,
            expected_barrier_generation=expected_barrier_generation,
            current_source_hashes={source.source_id: source.digest() for source in current_sources},
            actor=actor,
            reason=reason,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    async def tombstone(
        self,
        release_id: UUID,
        *,
        expected_pointer_version: int | None,
        actor: KnowledgeActor,
        reason: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeRelease:
        actor.assert_human_authority("knowledge.release.tombstone")
        reason = _validate_reason_code(reason)
        replay = await self._releases.get_idempotent_release_result(
            release_id, operation="tombstone", idempotency_key=idempotency_key
        )
        if replay is not None:
            return replay
        release = await self._require_release(release_id)
        return await self._releases.tombstone_atomic(
            release_id=release.release_id,
            expected_release_version=release.version,
            expected_pointer_version=expected_pointer_version,
            actor=actor,
            reason=reason,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    async def _revalidate_sources(
        self, release: KnowledgeRelease
    ) -> tuple[ApprovedKnowledgeSource, ...]:
        current = await self._sources.read_approved(
            tuple(source.source_id for source in release.sources)
        )
        if len(current) != len(release.sources):
            raise SourceApprovalRejected("approved source disappeared")
        now = self._clock()
        for source in current:
            source.assert_eligible(release.scope, at=now)
        return current

    async def _require_release(self, release_id: UUID) -> KnowledgeRelease:
        release = await self._releases.get(release_id)
        if release is None:
            raise LookupError("knowledge release does not exist")
        return release


def _validate_reason_code(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9.-]{2,79}", value):
        raise ValueError("reason must be a bounded non-sensitive reason code")
    return value
