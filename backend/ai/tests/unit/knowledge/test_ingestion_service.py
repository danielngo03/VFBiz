from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.knowledge.application import (
    KnowledgeIngestionService,
    KnowledgeSourceApprovalGate,
    SubmitKnowledgeIngestion,
)
from app.modules.knowledge.domain import (
    ApprovedKnowledgeSource,
    IngestionLimits,
    KnowledgeActor,
    KnowledgeAuthorizationRejected,
    KnowledgeIngestionJob,
    KnowledgeScope,
    SourceApprovalRejected,
)

NOW = datetime(2026, 7, 25, tzinfo=UTC)


def source(*, deletion_fenced: bool = False) -> ApprovedKnowledgeSource:
    return ApprovedKnowledgeSource(
        source_id="synthetic-warranty",
        source_type="synthetic",
        locator_ref="fixtures/synthetic-warranty-v1.md",
        owner_role="data-owner",
        custodian_role="knowledge-steward",
        version="v1",
        source_revision="revision-1",
        checksum_sha256="a" * 64,
        registry_document_hash="b" * 64,
        approved_purposes=("knowledge",),
        acl_namespaces=("public_customer:warranty:vi-VN",),
        classification="public",
        rights_approved=True,
        rights_license_id="LicenseRef-Synthetic-1",
        rights_commercial_use="permitted",
        rights_derivatives="permitted",
        rights_redistribution="prohibited",
        rights_access_conditions="Synthetic tests only",
        rights_evidence_urls=("urn:vfbiz:evidence:synthetic-rights",),
        rights_legal_review="approved",
        retention_policy_id="synthetic-30d",
        retention_duration_days=30,
        deletion_method="test-delete",
        approval_evidence_hashes=("c" * 64,),
        review_date=NOW + timedelta(days=1),
        deletion_fenced=deletion_fenced,
    )


class SourceReader:
    def __init__(self, value: ApprovedKnowledgeSource | None) -> None:
        self.value = value
        self.calls = 0

    async def read_approved(
        self, source_ids: tuple[str, ...]
    ) -> tuple[ApprovedKnowledgeSource, ...]:
        self.calls += 1
        if self.value is None or source_ids != (self.value.source_id,):
            return ()
        return (self.value,)


class JobRepository:
    def __init__(self) -> None:
        self.jobs: dict[object, KnowledgeIngestionJob] = {}
        self.write_calls = 0

    async def add_idempotent(
        self, job: KnowledgeIngestionJob, **_: object
    ) -> KnowledgeIngestionJob:
        self.write_calls += 1
        prior = self.jobs.get(job.job_id)
        if prior is not None and prior.command_fingerprint != job.command_fingerprint:
            raise RuntimeError("idempotency conflict")
        self.jobs[job.job_id] = prior or job
        return self.jobs[job.job_id]

    async def get(self, job_id: object) -> KnowledgeIngestionJob | None:
        return self.jobs.get(job_id)

    async def get_idempotent_control_result(
        self, job_id: object, *, operation: str, idempotency_key: str
    ) -> KnowledgeIngestionJob | None:
        return self.jobs.get((job_id, operation, idempotency_key))

    async def save_control_transition(
        self,
        job: KnowledgeIngestionJob,
        *,
        expected_version: int,
        operation: str,
        idempotency_key: str,
        actor_ref: str,
    ) -> KnowledgeIngestionJob:
        del actor_ref
        current = self.jobs[job.job_id]
        assert current.version == expected_version
        self.jobs[job.job_id] = job
        self.jobs[(job.job_id, operation, idempotency_key)] = job
        return job


def actor(capability: str = "knowledge.ingestion.submit") -> KnowledgeActor:
    return KnowledgeActor(
        actor_ref="ingestion-controller",
        kind="system",
        capability=capability,
        entitlement_revision="entitlement-v1",
        mfa_verified=False,
    )


def command() -> SubmitKnowledgeIngestion:
    return SubmitKnowledgeIngestion(
        source_id="synthetic-warranty",
        expected_source_revision="revision-1",
        expected_checksum_sha256="a" * 64,
        scope=KnowledgeScope(
            domain="warranty",
            locale="vi-VN",
            assistant_profile="public_customer",
            acl_namespace="public_customer:warranty:vi-VN",
        ),
        parser_revision="utf8-lines-v1",
        chunker_revision="semantic-v1",
        scanner_revision="deterministic-v1",
        embedding_revision="fake-embedding-v1",
        embedding_dimension=8,
        policy_revision="policy-v1",
        code_revision="1" * 40,
        limits=IngestionLimits(
            max_source_bytes=10_000,
            max_units=10,
            max_decoded_pixels_per_unit=1_000_000,
            max_expansion_ratio=1,
            max_archive_depth=0,
            max_extracted_files=1,
            max_stage_seconds=30,
            max_attempts_per_stage=3,
        ),
    )


@pytest.mark.asyncio
async def test_submit_revalidates_source_before_creating_job() -> None:
    sources = SourceReader(source())
    jobs = JobRepository()
    service = KnowledgeIngestionService(sources, jobs, clock=lambda: NOW)

    first = await service.submit(command(), actor=actor(), idempotency_key="submit-1")
    replay = await service.submit(command(), actor=actor(), idempotency_key="submit-1")

    assert first == replay
    assert first.status == "queued"
    assert sources.calls == 2
    assert jobs.write_calls == 2


@pytest.mark.asyncio
async def test_missing_or_deletion_fenced_source_stops_before_job_write() -> None:
    for value in (None, source(deletion_fenced=True)):
        sources = SourceReader(value)
        jobs = JobRepository()
        service = KnowledgeIngestionService(sources, jobs, clock=lambda: NOW)
        with pytest.raises(SourceApprovalRejected):
            await service.submit(command(), actor=actor(), idempotency_key="submit-denied")
        assert jobs.write_calls == 0


@pytest.mark.asyncio
async def test_submit_requires_capability_and_exact_source_revision() -> None:
    sources = SourceReader(source())
    jobs = JobRepository()
    service = KnowledgeIngestionService(sources, jobs, clock=lambda: NOW)
    with pytest.raises(KnowledgeAuthorizationRejected):
        await service.submit(
            command(), actor=actor("knowledge.release.submit"), idempotency_key="denied"
        )
    assert sources.calls == 0

    stale = replace(command(), expected_source_revision="revision-old")
    with pytest.raises(SourceApprovalRejected, match="revision"):
        await service.submit(stale, actor=actor(), idempotency_key="stale")
    assert jobs.write_calls == 0


@pytest.mark.asyncio
async def test_deletion_and_dead_letter_replay_are_authorized_and_idempotent() -> None:
    sources = SourceReader(source())
    jobs = JobRepository()
    service = KnowledgeIngestionService(sources, jobs, clock=lambda: NOW)
    created = await service.submit(command(), actor=actor(), idempotency_key="create")

    deletion_actor = actor("knowledge.ingestion.delete")
    pending = await service.request_deletion(
        created.job_id,
        generation=1,
        actor=deletion_actor,
        idempotency_key="delete-1",
    )
    replayed_delete = await service.request_deletion(
        created.job_id,
        generation=1,
        actor=deletion_actor,
        idempotency_key="delete-1",
    )
    assert pending == replayed_delete
    assert pending.status == "deletion_pending"

    dead_lettered = created.model_copy(
        update={
            "status": "dead_lettered",
            "failure_code": "PARSER_TIMEOUT",
            "failure_stage": "parse",
            "version": created.version + 1,
        }
    )
    jobs.jobs[created.job_id] = dead_lettered
    replay_actor = actor("knowledge.ingestion.replay")
    queued = await service.replay_dead_letter(
        created.job_id,
        generation=1,
        actor=replay_actor,
        idempotency_key="replay-1",
    )
    replayed = await service.replay_dead_letter(
        created.job_id,
        generation=1,
        actor=replay_actor,
        idempotency_key="replay-1",
    )
    assert queued == replayed
    assert queued.status == "queued"
    assert queued.replay_generation == 1


@pytest.mark.asyncio
async def test_execution_gate_revalidates_exact_source_snapshot() -> None:
    sources = SourceReader(source())
    jobs = JobRepository()
    service = KnowledgeIngestionService(sources, jobs, clock=lambda: NOW)
    created = await service.submit(command(), actor=actor(), idempotency_key="gate")
    gate = KnowledgeSourceApprovalGate(sources, clock=lambda: NOW)

    await gate.assert_current(created)
    sources.value = source(deletion_fenced=True)
    with pytest.raises(RuntimeError, match="SOURCE_APPROVAL_REVOKED"):
        await gate.assert_current(created)


@pytest.mark.asyncio
async def test_candidate_namespace_changes_with_pipeline_revision() -> None:
    sources = SourceReader(source())
    jobs = JobRepository()
    service = KnowledgeIngestionService(sources, jobs, clock=lambda: NOW)

    first = await service.submit(command(), actor=actor(), idempotency_key="pipeline-1")
    second = await service.submit(
        replace(command(), parser_revision="utf8-lines-v2"),
        actor=actor(),
        idempotency_key="pipeline-2",
    )

    assert first.candidate_namespace != second.candidate_namespace
    assert first.command_fingerprint != second.command_fingerprint
