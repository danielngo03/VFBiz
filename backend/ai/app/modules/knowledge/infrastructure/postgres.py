import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.knowledge.domain import (
    ApprovedKnowledgeSource,
    KnowledgeActor,
    KnowledgeConcurrencyConflict,
    KnowledgeRelease,
    KnowledgeScope,
    RevisionBarrier,
    SourceApprovalRejected,
)
from app.modules.knowledge.infrastructure.models import (
    KnowledgeChunk,
    KnowledgeReleaseDecision,
    KnowledgeReleaseOutbox,
    KnowledgeReleaseRecord,
    KnowledgeReleaseSource,
    KnowledgeReleaseTransition,
    KnowledgeRevisionPointer,
    KnowledgeSource,
)
from app.modules.knowledge.infrastructure.postgres_materialization import (
    membership_checksum,
)
from app.platform.audit.models import AuditEvent

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "candidate": {"evaluated", "rejected", "tombstoned"},
    "evaluated": {"ready", "rejected", "tombstoned"},
    "ready": {"active", "rejected", "tombstoned"},
    "active": {"superseded"},
    "superseded": {"active", "tombstoned"},
    "rejected": set(),
    "tombstoned": set(),
}


class PostgresSourceRegisterReader:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def read_approved(
        self, source_ids: tuple[str, ...]
    ) -> tuple[ApprovedKnowledgeSource, ...]:
        if not source_ids or len(set(source_ids)) != len(source_ids):
            raise SourceApprovalRejected("source IDs must be non-empty and unique")
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(KnowledgeSource).where(
                        KnowledgeSource.canonical_source_id.in_(source_ids)
                    )
                )
            ).all()
        by_id = {row.canonical_source_id: row for row in rows}
        if set(by_id) != set(source_ids):
            raise SourceApprovalRejected("approved source projection is incomplete")
        return tuple(_source_snapshot(by_id[source_id]) for source_id in source_ids)


class PostgresKnowledgeReleaseRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get_idempotent_release_result(
        self, release_id: UUID, *, operation: str, idempotency_key: str
    ) -> KnowledgeRelease | None:
        async with self._sessions() as session:
            return await _release_replay_in_transaction(
                session, release_id, operation, idempotency_key
            )

    async def get_idempotent_barrier_result(
        self, release_id: UUID, *, idempotency_key: str
    ) -> RevisionBarrier | None:
        event_hash = _event_idempotency_hash(release_id, "barrier-opened", idempotency_key)
        async with self._sessions() as session:
            return await _barrier_replay_by_hash(session, release_id, event_hash)

    async def add(
        self,
        release: KnowledgeRelease,
        *,
        actor: KnowledgeActor,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await _lock_command(session, release.release_id, "candidate-created", idempotency_key)
            existing = await session.get(KnowledgeReleaseRecord, release.release_id)
            if existing is not None:
                if existing.manifest_hash != release.manifest_hash:
                    raise KnowledgeConcurrencyConflict(
                        "idempotency key was reused with different candidate inputs"
                    )
                return
            session.add(_release_record(release))
            source_rows = await _source_rows(session, release.sources)
            for source in release.sources:
                session.add(
                    KnowledgeReleaseSource(
                        release_id=release.release_id,
                        source_id=source_rows[source.source_id].id,
                        source_revision=source.source_revision,
                        checksum_sha256=source.checksum_sha256,
                        registry_document_hash=source.registry_document_hash,
                        source_snapshot_hash=source.digest(),
                        snapshot=source.model_dump(mode="json"),
                    )
                )
            _append_event(
                session,
                release=release,
                previous_state=None,
                actor=actor,
                reason="candidate-created",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )

    async def get(self, release_id: UUID) -> KnowledgeRelease | None:
        async with self._sessions() as session:
            record = await session.get(KnowledgeReleaseRecord, release_id)
            if record is None:
                return None
            sources = await _release_sources(session, release_id)
            return _to_domain(record, sources)

    async def save_transition(
        self,
        release: KnowledgeRelease,
        *,
        expected_version: int,
        actor: KnowledgeActor,
        reason: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await _lock_command(session, release.release_id, reason, idempotency_key)
            replay = await _release_replay_in_transaction(
                session, release.release_id, reason, idempotency_key
            )
            if replay is not None:
                if replay != release:
                    raise KnowledgeConcurrencyConflict(
                        "idempotency key was reused with different transition inputs"
                    )
                return
            record = await _locked_release(session, release.release_id)
            if record.version != expected_version:
                raise KnowledgeConcurrencyConflict("knowledge release version changed")
            if release.status not in _ALLOWED_TRANSITIONS.get(record.status, set()):
                raise KnowledgeConcurrencyConflict("illegal persisted release transition")
            previous = record.status
            if release.status == "ready":
                await _assert_pinned_sources_current(session, release.release_id)
            _apply_release(record, release)
            if release.status == "ready":
                if not release.approver_ref or not release.approval_evidence_hash:
                    raise KnowledgeConcurrencyConflict("approval record is incomplete")
                session.add(
                    KnowledgeReleaseDecision(
                        release_id=release.release_id,
                        decision="approved",
                        actor_ref=release.approver_ref,
                        entitlement_revision=actor.entitlement_revision,
                        evidence_hash=release.approval_evidence_hash,
                        decided_at=datetime.now(UTC),
                    )
                )
            _append_event(
                session,
                release=release,
                previous_state=previous,
                actor=actor,
                reason=reason,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )

    async def open_barrier(
        self,
        *,
        scope: KnowledgeScope,
        candidate_release_id: UUID,
        expected_release_version: int,
        current_source_hashes: dict[str, str],
        critical: bool,
        deadline_at: datetime,
        actor: KnowledgeActor,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> RevisionBarrier:
        async with self._sessions() as session, session.begin():
            await _lock_command(session, candidate_release_id, "barrier-opened", idempotency_key)
            replay = await _barrier_replay_in_transaction(
                session, candidate_release_id, idempotency_key
            )
            if replay is not None:
                return replay
            release = await _locked_release(session, candidate_release_id)
            if release.status != "ready" or release.version != expected_release_version:
                raise KnowledgeConcurrencyConflict("release is no longer barrier-ready")
            now = datetime.now(UTC)
            if deadline_at <= now or deadline_at > now + timedelta(minutes=15):
                raise KnowledgeConcurrencyConflict("knowledge barrier deadline is invalid")
            pointer = await _ensure_locked_pointer(session, scope)
            if (
                pointer.candidate_release_id not in {None, candidate_release_id}
                and pointer.barrier_state != "clear"
            ):
                raise KnowledgeConcurrencyConflict(
                    "another knowledge candidate already owns the barrier"
                )
            database_current = await _assert_pinned_sources_current(session, candidate_release_id)
            if database_current != current_source_hashes:
                raise SourceApprovalRejected("source registry changed before barrier")
            pointer.candidate_release_id = candidate_release_id
            pointer.barrier_state = "syncing" if critical else "clear"
            pointer.barrier_generation += 1
            pointer.barrier_deadline_at = deadline_at if critical else None
            pointer.version += 1
            release.barrier_generation = pointer.barrier_generation
            release.version += 1
            event_key = _event_idempotency_hash(
                candidate_release_id, "barrier-opened", idempotency_key
            )
            barrier = RevisionBarrier(
                scope=scope,
                state=pointer.barrier_state,  # type: ignore[arg-type]
                generation=pointer.barrier_generation,
                candidate_release_id=candidate_release_id,
                deadline_at=pointer.barrier_deadline_at,
                pointer_version=pointer.version,
            )
            session.add(
                KnowledgeReleaseTransition(
                    release_id=candidate_release_id,
                    previous_state=release.status,
                    next_state=release.status,
                    actor_ref=actor.actor_ref,
                    reason="barrier-opened",
                    correlation_id=correlation_id,
                    idempotency_key_hash=event_key,
                    evidence_hash=None,
                    barrier_generation=pointer.barrier_generation,
                    result_snapshot=barrier.model_dump(mode="json"),
                )
            )
            session.add(
                KnowledgeReleaseOutbox(
                    aggregate_id=candidate_release_id,
                    event_type="knowledge.barrier.opened",
                    payload={
                        "releaseId": str(candidate_release_id),
                        "barrierGeneration": pointer.barrier_generation,
                        "critical": critical,
                        "correlationId": str(correlation_id),
                    },
                    idempotency_key_hash=event_key,
                )
            )
            _append_audit(
                session,
                release=_to_domain(
                    release,
                    await _release_sources(session, candidate_release_id),
                ),
                actor=actor,
                action="knowledge.barrier.opened",
                outcome="accepted",
                reason="barrier-opened",
                correlation_id=correlation_id,
            )
            await session.flush()
            return barrier

    async def activate_atomic(
        self,
        *,
        release_id: UUID,
        expected_release_version: int,
        expected_pointer_version: int,
        expected_barrier_generation: int,
        current_source_hashes: dict[str, str],
        actor: KnowledgeActor,
        reason: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeRelease:
        async with self._sessions() as session, session.begin():
            await _lock_command(session, release_id, "activate", idempotency_key)
            replay = await _release_replay_in_transaction(
                session, release_id, "activate", idempotency_key
            )
            if replay is not None:
                return replay
            initial = await _read_release(session, release_id)
            scope = _scope_from_record(initial)
            pointer_hint = await _read_pointer(session, scope)
            release_ids = [release_id]
            hinted_active = pointer_hint.active_release_id if pointer_hint else None
            if hinted_active is not None:
                release_ids.append(hinted_active)
            records = await _locked_release_set(session, release_ids)
            record = records[release_id]
            pointer = await _locked_pointer(session, scope)
            if pointer is None:
                raise KnowledgeConcurrencyConflict("knowledge pointer is missing")
            if pointer.active_release_id != hinted_active:
                raise KnowledgeConcurrencyConflict("active knowledge pointer changed")
            if record.status != "ready" or record.version != expected_release_version:
                raise KnowledgeConcurrencyConflict("release is no longer activation-ready")
            if (
                record.materialization_checksum is None
                or record.materialized_chunk_count is None
                or record.materialized_chunk_count <= 0
            ):
                raise KnowledgeConcurrencyConflict("release retrieval index is not materialized")
            if (
                pointer.version != expected_pointer_version
                or pointer.barrier_generation != expected_barrier_generation
                or pointer.candidate_release_id != release_id
            ):
                raise KnowledgeConcurrencyConflict("knowledge barrier changed")
            expected_barrier_state = "syncing" if record.criticality == "critical" else "clear"
            if pointer.barrier_state != expected_barrier_state:
                raise KnowledgeConcurrencyConflict("knowledge barrier state changed")
            now = datetime.now(UTC)
            if record.criticality == "critical" and (
                pointer.barrier_deadline_at is None or pointer.barrier_deadline_at <= now
            ):
                raise KnowledgeConcurrencyConflict("critical knowledge barrier expired")
            if record.effective_at > now or record.freshness_expires_at <= now:
                raise SourceApprovalRejected("release effective/freshness window is invalid")
            links = await _release_source_links(session, release_id)
            await _assert_materialization_complete(session, record, len(links))
            pinned = {link.snapshot["source_id"]: link.source_snapshot_hash for link in links}
            database_current = await _assert_pinned_sources_current(session, release_id)
            if pinned != current_source_hashes or database_current != current_source_hashes:
                raise SourceApprovalRejected("source registry changed before commit")
            previous_active = pointer.active_release_id
            if previous_active is not None:
                previous = records[previous_active]
                if previous.status != "active":
                    raise KnowledgeConcurrencyConflict("active pointer is inconsistent")
                previous.status = "superseded"
                previous.version += 1
                previous_domain = _to_domain(
                    previous,
                    await _release_sources(session, previous_active),
                )
                _append_event(
                    session,
                    release=previous_domain,
                    previous_state="active",
                    actor=actor,
                    reason="superseded-by-activation",
                    correlation_id=correlation_id,
                    idempotency_key=f"{idempotency_key}:previous",
                )
                await session.flush()
            previous_state = record.status
            record.status = "active"
            record.version += 1
            record.supersedes_release_id = previous_active
            pointer.previous_release_id = previous_active
            pointer.active_release_id = release_id
            pointer.candidate_release_id = None
            pointer.barrier_state = "clear"
            pointer.barrier_deadline_at = None
            pointer.version += 1
            sources = tuple(ApprovedKnowledgeSource.model_validate(link.snapshot) for link in links)
            activated = _to_domain(record, sources)
            _append_event(
                session,
                release=activated,
                previous_state=previous_state,
                actor=actor,
                reason=reason,
                operation="activate",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
            return activated

    async def rollback_atomic(
        self,
        *,
        target_release_id: UUID,
        expected_pointer_version: int,
        expected_barrier_generation: int,
        current_source_hashes: dict[str, str],
        actor: KnowledgeActor,
        reason: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeRelease:
        async with self._sessions() as session, session.begin():
            await _lock_command(session, target_release_id, "rollback", idempotency_key)
            replay = await _release_replay_in_transaction(
                session, target_release_id, "rollback", idempotency_key
            )
            if replay is not None:
                return replay
            target_hint = await _read_release(session, target_release_id)
            scope = _scope_from_record(target_hint)
            pointer_hint = await _read_pointer(session, scope)
            hinted_active = pointer_hint.active_release_id if pointer_hint else None
            release_ids = [target_release_id]
            if hinted_active is not None:
                release_ids.append(hinted_active)
            records = await _locked_release_set(session, release_ids)
            target = records[target_release_id]
            pointer = await _locked_pointer(session, scope)
            if pointer is None or pointer.version != expected_pointer_version:
                raise KnowledgeConcurrencyConflict("knowledge pointer changed")
            if pointer.active_release_id != hinted_active:
                raise KnowledgeConcurrencyConflict("active knowledge pointer changed")
            if (
                pointer.barrier_state != "clear"
                or pointer.candidate_release_id is not None
                or pointer.barrier_generation != expected_barrier_generation
            ):
                raise KnowledgeConcurrencyConflict(
                    "rollback cannot bypass an active knowledge barrier"
                )
            if target.status != "superseded":
                raise KnowledgeConcurrencyConflict("rollback target is not superseded")
            if (
                target.materialization_checksum is None
                or target.materialized_chunk_count is None
                or target.materialized_chunk_count <= 0
            ):
                raise KnowledgeConcurrencyConflict("rollback retrieval index is not materialized")
            current_active_id = pointer.active_release_id
            if current_active_id is None or current_active_id == target_release_id:
                raise KnowledgeConcurrencyConflict("rollback requires a different active release")
            now = datetime.now(UTC)
            if target.effective_at > now or target.freshness_expires_at <= now:
                raise SourceApprovalRejected("rollback target is outside freshness window")
            database_current = await _assert_pinned_sources_current(session, target_release_id)
            if database_current != current_source_hashes:
                raise SourceApprovalRejected("rollback source registry changed")
            target_links = await _release_source_links(session, target_release_id)
            await _assert_materialization_complete(session, target, len(target_links))
            current = records[current_active_id]
            if current.status != "active":
                raise KnowledgeConcurrencyConflict("active pointer is inconsistent")
            if (
                target.embedding_dimension != current.embedding_dimension
                or target.embedding_revision != current.embedding_revision
                or target.retriever_revision != current.retriever_revision
            ):
                raise KnowledgeConcurrencyConflict(
                    "rollback target is incompatible with the active retrieval runtime"
                )
            current.status = "superseded"
            current.version += 1
            _append_event(
                session,
                release=_to_domain(current, await _release_sources(session, current.id)),
                previous_state="active",
                actor=actor,
                reason="superseded-by-rollback",
                correlation_id=correlation_id,
                idempotency_key=f"{idempotency_key}:current",
            )
            await session.flush()
            target.status = "active"
            target.version += 1
            target.rollback_of_release_id = current_active_id
            pointer.previous_release_id = current_active_id
            pointer.active_release_id = target_release_id
            pointer.candidate_release_id = None
            pointer.barrier_state = "clear"
            pointer.barrier_deadline_at = None
            pointer.version += 1
            restored = _to_domain(
                target,
                tuple(
                    ApprovedKnowledgeSource.model_validate(link.snapshot) for link in target_links
                ),
            )
            _append_event(
                session,
                release=restored,
                previous_state="superseded",
                actor=actor,
                reason=reason,
                operation="rollback",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
            return restored

    async def tombstone_atomic(
        self,
        *,
        release_id: UUID,
        expected_release_version: int,
        expected_pointer_version: int | None,
        actor: KnowledgeActor,
        reason: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> KnowledgeRelease:
        async with self._sessions() as session, session.begin():
            await _lock_command(session, release_id, "tombstone", idempotency_key)
            replay = await _release_replay_in_transaction(
                session, release_id, "tombstone", idempotency_key
            )
            if replay is not None:
                return replay
            record = await _locked_release(session, release_id)
            if record.version != expected_release_version:
                raise KnowledgeConcurrencyConflict("knowledge release version changed")
            if record.status == "tombstoned":
                return _to_domain(record, await _release_sources(session, release_id))
            previous_state = record.status
            pointer = await _locked_pointer(session, _scope_from_record(record))
            if pointer is not None and (
                pointer.active_release_id == release_id
                or pointer.candidate_release_id == release_id
            ):
                if expected_pointer_version is None or pointer.version != expected_pointer_version:
                    raise KnowledgeConcurrencyConflict("knowledge pointer changed")
                if pointer.active_release_id == release_id:
                    pointer.previous_release_id = release_id
                    pointer.active_release_id = None
                pointer.candidate_release_id = None
                pointer.barrier_state = "blocked"
                pointer.barrier_generation += 1
                pointer.barrier_deadline_at = None
                pointer.version += 1
                record.barrier_generation = pointer.barrier_generation
            elif expected_pointer_version is not None:
                raise KnowledgeConcurrencyConflict(
                    "pointer version is only valid for a referenced release"
                )
            if previous_state in {"rejected"}:
                raise KnowledgeConcurrencyConflict("terminal rejected release cannot tombstone")
            record.status = "tombstoned"
            record.version += 1
            tombstoned = _to_domain(record, await _release_sources(session, release_id))
            _append_event(
                session,
                release=tombstoned,
                previous_state=previous_state,
                actor=actor,
                reason=reason,
                operation="tombstone",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
            return tombstoned


async def _source_rows(
    session: AsyncSession, sources: tuple[ApprovedKnowledgeSource, ...]
) -> dict[str, KnowledgeSource]:
    rows = (
        await session.scalars(
            select(KnowledgeSource)
            .where(
                KnowledgeSource.canonical_source_id.in_(
                    tuple(source.source_id for source in sources)
                )
            )
            .with_for_update()
        )
    ).all()
    result = {row.canonical_source_id: row for row in rows}
    if set(result) != {source.source_id for source in sources}:
        raise SourceApprovalRejected("source projection changed before candidate commit")
    expected = {source.source_id: source.digest() for source in sources}
    current = {source_id: _source_snapshot(row).digest() for source_id, row in result.items()}
    if current != expected:
        raise SourceApprovalRejected("source projection changed before candidate commit")
    return result  # type: ignore[return-value]


async def _assert_pinned_sources_current(session: AsyncSession, release_id: UUID) -> dict[str, str]:
    links = await _release_source_links(session, release_id)
    source_ids = tuple(link.source_id for link in links)
    rows = (
        await session.scalars(
            select(KnowledgeSource).where(KnowledgeSource.id.in_(source_ids)).with_for_update()
        )
    ).all()
    current = {
        source.source_id: source.digest() for source in (_source_snapshot(row) for row in rows)
    }
    pinned = {str(link.snapshot["source_id"]): link.source_snapshot_hash for link in links}
    if current != pinned:
        raise SourceApprovalRejected("source registry changed after evaluation")
    return current


async def _release_sources(
    session: AsyncSession, release_id: UUID
) -> tuple[ApprovedKnowledgeSource, ...]:
    links = await _release_source_links(session, release_id)
    return tuple(ApprovedKnowledgeSource.model_validate(link.snapshot) for link in links)


async def _release_source_links(
    session: AsyncSession, release_id: UUID
) -> list[KnowledgeReleaseSource]:
    return list(
        (
            await session.scalars(
                select(KnowledgeReleaseSource)
                .where(KnowledgeReleaseSource.release_id == release_id)
                .order_by(KnowledgeReleaseSource.source_id)
            )
        ).all()
    )


async def _locked_release(session: AsyncSession, release_id: UUID) -> KnowledgeReleaseRecord:
    record = await session.scalar(
        select(KnowledgeReleaseRecord)
        .where(KnowledgeReleaseRecord.id == release_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if record is None:
        raise LookupError("knowledge release does not exist")
    return record


async def _read_release(session: AsyncSession, release_id: UUID) -> KnowledgeReleaseRecord:
    record = await session.get(KnowledgeReleaseRecord, release_id)
    if record is None:
        raise LookupError("knowledge release does not exist")
    return record


async def _locked_release_set(
    session: AsyncSession, release_ids: list[UUID]
) -> dict[UUID, KnowledgeReleaseRecord]:
    unique_ids = sorted(set(release_ids), key=str)
    rows = (
        await session.scalars(
            select(KnowledgeReleaseRecord)
            .where(KnowledgeReleaseRecord.id.in_(unique_ids))
            .order_by(KnowledgeReleaseRecord.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    result = {row.id: row for row in rows}
    if set(result) != set(unique_ids):
        raise KnowledgeConcurrencyConflict("knowledge release set changed")
    return result


async def _locked_pointer(
    session: AsyncSession, scope: KnowledgeScope
) -> KnowledgeRevisionPointer | None:
    return await session.scalar(
        select(KnowledgeRevisionPointer)
        .where(
            KnowledgeRevisionPointer.domain == scope.domain,
            KnowledgeRevisionPointer.locale == scope.locale,
            KnowledgeRevisionPointer.assistant_profile == scope.assistant_profile,
            KnowledgeRevisionPointer.acl_namespace == scope.acl_namespace,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _read_pointer(
    session: AsyncSession, scope: KnowledgeScope
) -> KnowledgeRevisionPointer | None:
    return await session.scalar(
        select(KnowledgeRevisionPointer).where(
            KnowledgeRevisionPointer.domain == scope.domain,
            KnowledgeRevisionPointer.locale == scope.locale,
            KnowledgeRevisionPointer.assistant_profile == scope.assistant_profile,
            KnowledgeRevisionPointer.acl_namespace == scope.acl_namespace,
        )
    )


async def _lock_command(
    session: AsyncSession,
    release_id: UUID,
    operation: str,
    idempotency_key: str,
) -> None:
    digest = hashlib.sha256(f"{release_id}:{operation}:{idempotency_key}".encode()).digest()
    signed_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await session.execute(select(func.pg_advisory_xact_lock(signed_key)))


async def _release_replay_in_transaction(
    session: AsyncSession,
    release_id: UUID,
    operation: str,
    idempotency_key: str,
) -> KnowledgeRelease | None:
    transition = await session.scalar(
        select(KnowledgeReleaseTransition).where(
            KnowledgeReleaseTransition.release_id == release_id,
            KnowledgeReleaseTransition.idempotency_key_hash
            == _event_idempotency_hash(release_id, operation, idempotency_key),
        )
    )
    if transition is None or transition.result_snapshot is None:
        return None
    snapshot = transition.result_snapshot
    if snapshot.get("kind") == "knowledge-release-result":
        release_payload = snapshot.get("release")
        if not isinstance(release_payload, dict):
            raise KnowledgeConcurrencyConflict("idempotent result is malformed")
        sources = await _release_sources(session, release_id)
        return KnowledgeRelease.model_validate(
            release_payload | {"sources": [source.model_dump(mode="json") for source in sources]}
        )
    return KnowledgeRelease.model_validate(snapshot)


async def _barrier_replay_in_transaction(
    session: AsyncSession, release_id: UUID, idempotency_key: str
) -> RevisionBarrier | None:
    return await _barrier_replay_by_hash(
        session,
        release_id,
        _event_idempotency_hash(release_id, "barrier-opened", idempotency_key),
    )


async def _barrier_replay_by_hash(
    session: AsyncSession, release_id: UUID, event_hash: str
) -> RevisionBarrier | None:
    transition = await session.scalar(
        select(KnowledgeReleaseTransition).where(
            KnowledgeReleaseTransition.release_id == release_id,
            KnowledgeReleaseTransition.idempotency_key_hash == event_hash,
        )
    )
    if transition is None or transition.result_snapshot is None:
        return None
    return RevisionBarrier.model_validate(transition.result_snapshot)


async def _ensure_locked_pointer(
    session: AsyncSession, scope: KnowledgeScope
) -> KnowledgeRevisionPointer:
    await session.execute(
        insert(KnowledgeRevisionPointer)
        .values(
            domain=scope.domain,
            locale=scope.locale,
            assistant_profile=scope.assistant_profile,
            acl_namespace=scope.acl_namespace,
            active_release_id=None,
            previous_release_id=None,
            candidate_release_id=None,
            barrier_state="clear",
            barrier_generation=0,
            barrier_deadline_at=None,
            version=0,
        )
        .on_conflict_do_nothing(constraint="uq_ai_knowledge_revision_pointer_scope")
    )
    pointer = await _locked_pointer(session, scope)
    if pointer is None:
        raise KnowledgeConcurrencyConflict("knowledge pointer could not be initialized")
    return pointer


def _source_snapshot(row: KnowledgeSource) -> ApprovedKnowledgeSource:
    rights = row.rights or {}
    retention = row.retention or {}
    if row.status != "approved" or not all(
        (
            row.canonical_source_id,
            row.source_type,
            row.locator_ref,
            row.owner_role,
            row.custodian_role,
            row.version,
            row.source_revision,
            row.checksum,
            row.registry_document_hash,
            row.approved_purposes,
            row.acl_namespaces,
            row.deletion_method,
            row.approval_evidence,
            row.review_date,
            retention.get("policy_id"),
            retention.get("duration_days"),
            "license_id" in rights,
            rights.get("commercial_use"),
            rights.get("derivatives"),
            rights.get("redistribution"),
            "access_conditions" in rights,
            "evidence_urls" in rights,
            rights.get("legal_review"),
        )
    ):
        raise SourceApprovalRejected("Source Register v2 projection is incomplete")
    rights_approved = (
        rights.get("commercial_use") == "permitted"
        and rights.get("derivatives") == "permitted"
        and rights.get("legal_review") == "approved"
    )
    return ApprovedKnowledgeSource.model_validate(
        {
            "source_id": row.canonical_source_id,
            "source_type": row.source_type,
            "locator_ref": row.locator_ref,
            "owner_role": row.owner_role,
            "custodian_role": row.custodian_role,
            "version": row.version,
            "source_revision": row.source_revision,
            "checksum_sha256": row.checksum,
            "registry_document_hash": row.registry_document_hash,
            "approved_purposes": row.approved_purposes,
            "acl_namespaces": row.acl_namespaces,
            "classification": row.classification,
            "rights_approved": rights_approved,
            "rights_license_id": rights["license_id"],
            "rights_commercial_use": rights["commercial_use"],
            "rights_derivatives": rights["derivatives"],
            "rights_redistribution": rights["redistribution"],
            "rights_access_conditions": rights["access_conditions"],
            "rights_evidence_urls": rights["evidence_urls"],
            "rights_legal_review": rights["legal_review"],
            "retention_policy_id": retention["policy_id"],
            "retention_duration_days": retention["duration_days"],
            "deletion_method": row.deletion_method,
            "approval_evidence_hashes": row.approval_evidence,
            "review_date": row.review_date,
            "deletion_fenced": row.deletion_fenced,
        }
    )


def _release_record(release: KnowledgeRelease) -> KnowledgeReleaseRecord:
    return KnowledgeReleaseRecord(
        id=release.release_id,
        **_release_values(release),
    )


def _apply_release(record: KnowledgeReleaseRecord, release: KnowledgeRelease) -> None:
    for name, value in _release_values(release).items():
        setattr(record, name, value)


def _release_values(release: KnowledgeRelease) -> dict[str, Any]:
    return {
        "domain": release.scope.domain,
        "locale": release.scope.locale,
        "assistant_profile": release.scope.assistant_profile,
        "acl_namespace": release.scope.acl_namespace,
        "status": release.status,
        "criticality": release.criticality,
        "source_set_hash": release.source_set_hash,
        "manifest_hash": cast(str, release.manifest_hash),
        "transform_revision": release.transform_revision,
        "chunking_revision": release.chunking_revision,
        "index_generation_id": release.index_generation_id,
        "embedding_revision": release.embedding_revision,
        "embedding_dimension": release.embedding_dimension,
        "retriever_revision": release.retriever_revision,
        "policy_revision": release.policy_revision,
        "index_checksum": release.index_checksum,
        "evaluation_run_ref": release.evaluation_run_ref,
        "evaluation_suite_revision": release.evaluation_suite_revision,
        "evaluation_evidence_hashes": list(release.evaluation_evidence_hashes),
        "proposer_ref": release.proposer_ref,
        "approver_ref": release.approver_ref,
        "approval_source_set_hash": release.approval_source_set_hash,
        "approval_evidence_hash": release.approval_evidence_hash,
        "effective_at": release.effective_at,
        "freshness_expires_at": release.freshness_expires_at,
        "supersedes_release_id": release.supersedes_release_id,
        "rollback_of_release_id": release.rollback_of_release_id,
        "barrier_generation": release.barrier_generation,
        "version": release.version,
    }


def _to_domain(
    record: KnowledgeReleaseRecord,
    sources: tuple[ApprovedKnowledgeSource, ...],
) -> KnowledgeRelease:
    if record.index_generation_id is None:
        raise ValueError("knowledge release has no embedding index generation")
    return KnowledgeRelease(
        release_id=record.id,
        scope=_scope_from_record(record),
        status=record.status,  # type: ignore[arg-type]
        criticality=record.criticality,  # type: ignore[arg-type]
        sources=sources,
        source_set_hash=record.source_set_hash,
        manifest_hash=record.manifest_hash,
        transform_revision=record.transform_revision,
        chunking_revision=record.chunking_revision,
        index_generation_id=record.index_generation_id,
        embedding_revision=record.embedding_revision,
        embedding_dimension=record.embedding_dimension,
        retriever_revision=record.retriever_revision,
        policy_revision=record.policy_revision,
        index_checksum=record.index_checksum,
        evaluation_run_ref=record.evaluation_run_ref,
        evaluation_suite_revision=record.evaluation_suite_revision,
        evaluation_evidence_hashes=tuple(record.evaluation_evidence_hashes),
        proposer_ref=record.proposer_ref,
        approver_ref=record.approver_ref,
        approval_source_set_hash=record.approval_source_set_hash,
        approval_evidence_hash=record.approval_evidence_hash,
        effective_at=record.effective_at,
        freshness_expires_at=record.freshness_expires_at,
        supersedes_release_id=record.supersedes_release_id,
        rollback_of_release_id=record.rollback_of_release_id,
        barrier_generation=record.barrier_generation,
        version=record.version,
    )


def _scope_from_record(record: KnowledgeReleaseRecord) -> KnowledgeScope:
    return KnowledgeScope(
        domain=record.domain,
        locale=record.locale,  # type: ignore[arg-type]
        assistant_profile=record.assistant_profile,  # type: ignore[arg-type]
        acl_namespace=record.acl_namespace,
    )


async def _assert_materialization_complete(
    session: AsyncSession,
    release: KnowledgeReleaseRecord,
    expected_source_count: int,
) -> None:
    rows = (
        await session.execute(
            select(
                KnowledgeChunk.id,
                KnowledgeChunk.content_checksum,
                KnowledgeChunk.source_id,
            ).where(KnowledgeChunk.release_id == release.id)
        )
    ).all()
    persisted_checksum = membership_checksum(
        tuple((chunk_id, content_checksum) for chunk_id, content_checksum, _ in rows)
    )
    if (
        release.materialization_checksum is None
        or release.materialized_chunk_count is None
        or len(rows) != release.materialized_chunk_count
        or len({source_id for _, _, source_id in rows}) != expected_source_count
        or persisted_checksum != release.materialization_checksum
    ):
        raise KnowledgeConcurrencyConflict("release retrieval materialization is incomplete")


def _append_event(
    session: AsyncSession,
    *,
    release: KnowledgeRelease,
    previous_state: str | None,
    actor: KnowledgeActor,
    reason: str,
    operation: str | None = None,
    correlation_id: UUID,
    idempotency_key: str,
) -> None:
    idempotency_hash = _event_idempotency_hash(
        release.release_id, operation or reason, idempotency_key
    )
    session.add(
        KnowledgeReleaseTransition(
            release_id=release.release_id,
            previous_state=previous_state,
            next_state=release.status,
            actor_ref=actor.actor_ref,
            reason=reason,
            correlation_id=correlation_id,
            idempotency_key_hash=idempotency_hash,
            evidence_hash=release.approval_evidence_hash,
            barrier_generation=release.barrier_generation,
            result_snapshot={
                "kind": "knowledge-release-result",
                "release": release.model_dump(mode="json", exclude={"sources"}),
            },
        )
    )
    session.add(
        KnowledgeReleaseOutbox(
            aggregate_id=release.release_id,
            event_type=f"knowledge.release.{release.status}",
            payload={
                "releaseId": str(release.release_id),
                "domain": release.scope.domain,
                "locale": release.scope.locale,
                "assistantProfile": release.scope.assistant_profile,
                "barrierGeneration": release.barrier_generation,
                "releaseVersion": release.version,
                "correlationId": str(correlation_id),
            },
            idempotency_key_hash=idempotency_hash,
        )
    )
    _append_audit(
        session,
        release=release,
        actor=actor,
        action=f"knowledge.release.{release.status}",
        outcome="accepted",
        reason=reason,
        correlation_id=correlation_id,
    )


def _append_audit(
    session: AsyncSession,
    *,
    release: KnowledgeRelease,
    actor: KnowledgeActor,
    action: str,
    outcome: str,
    reason: str,
    correlation_id: UUID,
) -> None:
    session.add(
        AuditEvent(
            actor_ref=actor.actor_ref,
            action=action,
            resource_type="knowledge-release",
            resource_ref=str(release.release_id),
            outcome=outcome,
            evidence={
                "reason": reason,
                "releaseVersion": release.version,
                "barrierGeneration": release.barrier_generation,
                "sourceSetHash": release.source_set_hash,
            },
            correlation_id=str(correlation_id),
        )
    )


def _idempotency_hash(value: str) -> str:
    if not value or len(value) > 256:
        raise ValueError("idempotency key must be bounded")
    return hashlib.sha256(value.encode()).hexdigest()


def _event_idempotency_hash(release_id: UUID, operation: str, value: str) -> str:
    return _idempotency_hash(f"{release_id}:{operation}:{value}")
