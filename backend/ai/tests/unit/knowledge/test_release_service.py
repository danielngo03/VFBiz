from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.modules.knowledge.application import (
    CreateKnowledgeCandidate,
    KnowledgeReleaseService,
)
from app.modules.knowledge.domain import (
    ApprovedKnowledgeSource,
    InvalidKnowledgeTransition,
    KnowledgeActor,
    KnowledgeAuthorizationRejected,
    KnowledgeRelease,
    KnowledgeScope,
    RevisionBarrier,
    SourceApprovalRejected,
)

NOW = datetime(2026, 7, 25, tzinfo=UTC)
INDEX_GENERATION_ID = UUID("00000000-0000-4000-8000-000000000411")


def approved_source(*, registry_hash: str = "b" * 64) -> ApprovedKnowledgeSource:
    return ApprovedKnowledgeSource(
        source_id="warranty-policy",
        source_type="internal-content",
        locator_ref="gs://approved-knowledge/warranty-policy/v1.pdf",
        owner_role="content-owner",
        custodian_role="knowledge-steward",
        version="v1",
        source_revision="revision-1",
        checksum_sha256="a" * 64,
        registry_document_hash=registry_hash,
        approved_purposes=("knowledge",),
        acl_namespaces=("public_customer:warranty:vi-VN",),
        classification="public",
        rights_approved=True,
        rights_license_id="LicenseRef-Internal-1",
        rights_commercial_use="permitted",
        rights_derivatives="permitted",
        rights_redistribution="prohibited",
        rights_access_conditions="Approved customer-support retrieval only",
        rights_evidence_urls=("urn:vfbiz:evidence:rights-1",),
        rights_legal_review="approved",
        retention_policy_id="policy-365d",
        retention_duration_days=365,
        deletion_method="crypto-erase",
        approval_evidence_hashes=("c" * 64,),
        review_date=NOW + timedelta(days=30),
    )


class MemorySourceReader:
    def __init__(self, current: ApprovedKnowledgeSource) -> None:
        self.current = current

    async def read_approved(
        self, source_ids: tuple[str, ...]
    ) -> tuple[ApprovedKnowledgeSource, ...]:
        if source_ids != (self.current.source_id,):
            return ()
        return (self.current,)


class MemoryReleaseRepository:
    def __init__(self) -> None:
        self.releases: dict[UUID, KnowledgeRelease] = {}
        self.pointer_version = 0
        self.barrier_generation = 0
        self.activated_source_hashes: dict[str, str] | None = None
        self.active_release_id: UUID | None = None

    async def get_idempotent_release_result(self, *_: object, **__: object) -> None:
        return None

    async def get_idempotent_barrier_result(self, *_: object, **__: object) -> None:
        return None

    async def add(self, release: KnowledgeRelease, **_: object) -> None:
        self.releases[release.release_id] = release

    async def get(self, release_id: UUID) -> KnowledgeRelease | None:
        return self.releases.get(release_id)

    async def save_transition(
        self,
        release: KnowledgeRelease,
        *,
        expected_version: int,
        **_: object,
    ) -> None:
        assert self.releases[release.release_id].version == expected_version
        self.releases[release.release_id] = release

    async def open_barrier(
        self,
        *,
        scope: KnowledgeScope,
        candidate_release_id: UUID,
        critical: bool,
        deadline_at: datetime,
        **_: object,
    ) -> RevisionBarrier:
        self.pointer_version += 1
        self.barrier_generation += 1
        release = self.releases[candidate_release_id]
        self.releases[candidate_release_id] = release.model_copy(
            update={
                "barrier_generation": self.barrier_generation,
                "version": release.version + 1,
            }
        )
        return RevisionBarrier(
            scope=scope,
            state="syncing" if critical else "clear",
            generation=self.barrier_generation,
            candidate_release_id=candidate_release_id,
            deadline_at=deadline_at if critical else None,
            pointer_version=self.pointer_version,
        )

    async def activate_atomic(
        self,
        *,
        release_id: UUID,
        expected_release_version: int,
        expected_pointer_version: int,
        expected_barrier_generation: int,
        current_source_hashes: dict[str, str],
        **_: object,
    ) -> KnowledgeRelease:
        release = self.releases[release_id]
        assert release.version == expected_release_version
        assert expected_pointer_version == self.pointer_version
        assert expected_barrier_generation == self.barrier_generation
        self.activated_source_hashes = current_source_hashes
        active = release.model_copy(update={"status": "active", "version": release.version + 1})
        self.releases[release_id] = active
        self.active_release_id = release_id
        return active

    async def rollback_atomic(
        self,
        *,
        target_release_id: UUID,
        expected_pointer_version: int,
        current_source_hashes: dict[str, str],
        **_: object,
    ) -> KnowledgeRelease:
        assert expected_pointer_version == self.pointer_version
        assert self.active_release_id is not None
        current = self.releases[self.active_release_id]
        self.releases[current.release_id] = current.model_copy(
            update={"status": "superseded", "version": current.version + 1}
        )
        target = self.releases[target_release_id]
        restored = target.model_copy(
            update={
                "status": "active",
                "rollback_of_release_id": current.release_id,
                "version": target.version + 1,
            }
        )
        self.releases[target_release_id] = restored
        self.active_release_id = target_release_id
        self.pointer_version += 1
        self.activated_source_hashes = current_source_hashes
        return restored

    async def tombstone_atomic(
        self,
        *,
        release_id: UUID,
        expected_release_version: int,
        expected_pointer_version: int | None,
        **_: object,
    ) -> KnowledgeRelease:
        release = self.releases[release_id]
        assert release.version == expected_release_version
        if release.status == "active":
            assert expected_pointer_version == self.pointer_version
            self.active_release_id = None
            self.pointer_version += 1
        tombstoned = release.model_copy(
            update={"status": "tombstoned", "version": release.version + 1}
        )
        self.releases[release_id] = tombstoned
        return tombstoned


def actor(
    capability: str,
    *,
    actor_ref: str,
    kind: str = "human",
    mfa: bool = True,
) -> KnowledgeActor:
    return KnowledgeActor(
        actor_ref=actor_ref,
        kind=kind,
        capability=capability,
        entitlement_revision="entitlement-v1",
        mfa_verified=mfa,
    )  # type: ignore[arg-type]


def command() -> CreateKnowledgeCandidate:
    return CreateKnowledgeCandidate(
        scope=KnowledgeScope(
            domain="warranty",
            locale="vi-VN",
            assistant_profile="public_customer",
            acl_namespace="public_customer:warranty:vi-VN",
        ),
        criticality="critical",
        source_ids=("warranty-policy",),
        transform_revision="transform-v1",
        chunking_revision="chunk-v1",
        index_generation_id=INDEX_GENERATION_ID,
        embedding_revision="embed-v1",
        embedding_dimension=1536,
        retriever_revision="retriever-v1",
        policy_revision="policy-v1",
        index_checksum="d" * 64,
        effective_at=NOW,
        freshness_expires_at=NOW + timedelta(days=30),
        barrier_generation=0,
    )


async def prepared_release(
    sources: MemorySourceReader, repository: MemoryReleaseRepository
) -> tuple[KnowledgeReleaseService, KnowledgeRelease]:
    service = KnowledgeReleaseService(sources, repository, clock=lambda: NOW)
    release = await service.create_candidate(
        command(),
        actor=actor(
            "knowledge.release.submit",
            actor_ref="ingestion-worker",
            kind="ingestion_service",
            mfa=False,
        ),
        correlation_id=uuid4(),
        idempotency_key="candidate-1",
    )
    release = await service.record_evaluation(
        release.release_id,
        run_ref="evaluation-1",
        suite_revision="golden-v1",
        evidence_hashes=("e" * 64,),
        actor=actor("knowledge.release.evaluate", actor_ref="evaluator"),
        correlation_id=uuid4(),
        idempotency_key="evaluation-1",
    )
    return service, release


@pytest.mark.asyncio
async def test_candidate_to_activation_revalidates_sources_and_maker_checker() -> None:
    sources = MemorySourceReader(approved_source())
    repository = MemoryReleaseRepository()
    service, release = await prepared_release(sources, repository)
    release = await service.approve(
        release.release_id,
        actor=actor("knowledge.release.approve", actor_ref="checker-01"),
        evidence_hash="f" * 64,
        correlation_id=uuid4(),
        idempotency_key="approval-1",
    )
    barrier = await service.open_barrier(
        release.release_id,
        deadline_at=NOW + timedelta(minutes=5),
        actor=actor("knowledge.release.submit", actor_ref="sync-controller"),
        correlation_id=uuid4(),
        idempotency_key="barrier-1",
    )
    active = await service.activate(
        release.release_id,
        expected_pointer_version=barrier.pointer_version,
        expected_barrier_generation=barrier.generation,
        actor=actor("knowledge.release.activate", actor_ref="release-owner"),
        reason="approved-staging-release",
        correlation_id=uuid4(),
        idempotency_key="activate-1",
    )

    assert active.status == "active"
    assert repository.activated_source_hashes == {"warranty-policy": approved_source().digest()}


@pytest.mark.asyncio
async def test_source_change_after_evaluation_invalidates_approval() -> None:
    sources = MemorySourceReader(approved_source())
    repository = MemoryReleaseRepository()
    service, release = await prepared_release(sources, repository)
    sources.current = approved_source(registry_hash="9" * 64)

    with pytest.raises(SourceApprovalRejected, match="changed"):
        await service.approve(
            release.release_id,
            actor=actor("knowledge.release.approve", actor_ref="checker-01"),
            evidence_hash="f" * 64,
            correlation_id=uuid4(),
            idempotency_key="approval-1",
        )


@pytest.mark.asyncio
async def test_source_change_after_approval_blocks_activation() -> None:
    sources = MemorySourceReader(approved_source())
    repository = MemoryReleaseRepository()
    service, release = await prepared_release(sources, repository)
    release = await service.approve(
        release.release_id,
        actor=actor("knowledge.release.approve", actor_ref="checker-01"),
        evidence_hash="f" * 64,
        correlation_id=uuid4(),
        idempotency_key="approval-1",
    )
    barrier = await service.open_barrier(
        release.release_id,
        deadline_at=NOW + timedelta(minutes=5),
        actor=actor("knowledge.release.submit", actor_ref="sync-controller"),
        correlation_id=uuid4(),
        idempotency_key="barrier-1",
    )
    sources.current = approved_source(registry_hash="9" * 64)

    with pytest.raises(SourceApprovalRejected, match="changed"):
        await service.activate(
            release.release_id,
            expected_pointer_version=barrier.pointer_version,
            expected_barrier_generation=barrier.generation,
            actor=actor("knowledge.release.activate", actor_ref="release-owner"),
            reason="must-not-activate",
            correlation_id=uuid4(),
            idempotency_key="activate-1",
        )


@pytest.mark.asyncio
async def test_evaluation_requires_independent_evaluation_authority() -> None:
    sources = MemorySourceReader(approved_source())
    repository = MemoryReleaseRepository()
    service = KnowledgeReleaseService(sources, repository, clock=lambda: NOW)
    release = await service.create_candidate(
        command(),
        actor=actor("knowledge.release.submit", actor_ref="maker"),
        correlation_id=uuid4(),
        idempotency_key="candidate-authz",
    )

    with pytest.raises(KnowledgeAuthorizationRejected, match="evaluation capability"):
        await service.record_evaluation(
            release.release_id,
            run_ref="evaluation-1",
            suite_revision="golden-v1",
            evidence_hashes=("e" * 64,),
            actor=actor("knowledge.release.submit", actor_ref="maker"),
            correlation_id=uuid4(),
            idempotency_key="evaluation-denied",
        )
    with pytest.raises(KnowledgeAuthorizationRejected, match="ingestion worker"):
        await service.record_evaluation(
            release.release_id,
            run_ref="evaluation-1",
            suite_revision="golden-v1",
            evidence_hashes=("e" * 64,),
            actor=actor(
                "knowledge.release.evaluate",
                actor_ref="ingestion-worker",
                kind="ingestion_service",
                mfa=False,
            ),
            correlation_id=uuid4(),
            idempotency_key="evaluation-ingestion-denied",
        )


@pytest.mark.asyncio
async def test_barrier_requires_ready_release_and_bounded_future_deadline() -> None:
    sources = MemorySourceReader(approved_source())
    repository = MemoryReleaseRepository()
    service, evaluated = await prepared_release(sources, repository)

    with pytest.raises(InvalidKnowledgeTransition, match="ready"):
        await service.open_barrier(
            evaluated.release_id,
            deadline_at=NOW + timedelta(minutes=5),
            actor=actor("knowledge.release.submit", actor_ref="sync-controller"),
            correlation_id=uuid4(),
            idempotency_key="barrier-not-ready",
        )

    ready = await service.approve(
        evaluated.release_id,
        actor=actor("knowledge.release.approve", actor_ref="checker-01"),
        evidence_hash="f" * 64,
        correlation_id=uuid4(),
        idempotency_key="approval-deadline",
    )
    with pytest.raises(InvalidKnowledgeTransition, match="15 minutes"):
        await service.open_barrier(
            ready.release_id,
            deadline_at=NOW + timedelta(hours=1),
            actor=actor("knowledge.release.submit", actor_ref="sync-controller"),
            correlation_id=uuid4(),
            idempotency_key="barrier-too-long",
        )


@pytest.mark.asyncio
async def test_active_release_can_be_tombstoned_only_with_pointer_fence() -> None:
    sources = MemorySourceReader(approved_source())
    repository = MemoryReleaseRepository()
    service, release = await prepared_release(sources, repository)
    release = await service.approve(
        release.release_id,
        actor=actor("knowledge.release.approve", actor_ref="checker-01"),
        evidence_hash="f" * 64,
        correlation_id=uuid4(),
        idempotency_key="approval-tombstone",
    )
    barrier = await service.open_barrier(
        release.release_id,
        deadline_at=NOW + timedelta(minutes=5),
        actor=actor("knowledge.release.submit", actor_ref="sync-controller"),
        correlation_id=uuid4(),
        idempotency_key="barrier-tombstone",
    )
    active = await service.activate(
        release.release_id,
        expected_pointer_version=barrier.pointer_version,
        expected_barrier_generation=barrier.generation,
        actor=actor("knowledge.release.activate", actor_ref="release-owner"),
        reason="activate-before-withdrawal",
        correlation_id=uuid4(),
        idempotency_key="activate-tombstone",
    )
    tombstoned = await service.tombstone(
        active.release_id,
        expected_pointer_version=repository.pointer_version,
        actor=actor("knowledge.release.tombstone", actor_ref="release-owner"),
        reason="emergency-withdrawal",
        correlation_id=uuid4(),
        idempotency_key="tombstone-active",
    )

    assert tombstoned.status == "tombstoned"
    assert repository.active_release_id is None
