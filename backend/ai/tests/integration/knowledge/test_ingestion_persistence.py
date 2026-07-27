import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.modules.knowledge.application.ingestion_ports import ArtifactDescriptor
from app.modules.knowledge.domain import (
    IngestionLimits,
    KnowledgeConcurrencyConflict,
    KnowledgeIngestionJob,
    KnowledgeScope,
    StageCheckpoint,
)
from app.modules.knowledge.infrastructure.ingestion_models import (
    KnowledgeIngestionArtifact,
    KnowledgeIngestionJobRecord,
)
from app.modules.knowledge.infrastructure.postgres_ingestion import (
    PostgresIngestionRepository,
)
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


def job(*, parser_revision: str = "parser-v1") -> KnowledgeIngestionJob:
    now = datetime.now(UTC)
    return KnowledgeIngestionJob(
        job_id=uuid4(),
        source_id="synthetic-ingestion-integration",
        source_revision="revision-1",
        source_snapshot_hash="a" * 64,
        expected_checksum_sha256="b" * 64,
        scope=KnowledgeScope(
            domain="integration",
            locale="vi-VN",
            assistant_profile="public_customer",
            acl_namespace="public_customer:integration:vi-VN",
        ),
        parser_revision=parser_revision,
        chunker_revision="chunk-v1",
        scanner_revision="scan-v1",
        embedding_revision="embed-v1",
        embedding_dimension=8,
        policy_revision="policy-v1",
        code_revision="1" * 40,
        candidate_namespace="candidate/public_customer/integration/vi-vn/test",
        limits=IngestionLimits(
            max_source_bytes=1_000,
            max_units=2,
            max_decoded_pixels_per_unit=1,
            max_expansion_ratio=1,
            max_archive_depth=0,
            max_extracted_files=1,
            max_stage_seconds=10,
            max_attempts_per_stage=2,
        ),
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_idempotent_submit_claim_and_stale_fence() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    repository = PostgresIngestionRepository(sessions)
    command = job()
    idempotency_key = f"integration-{command.job_id}"
    try:
        submissions = await asyncio.gather(
            *(
                repository.add_idempotent(
                    command,
                    idempotency_key=idempotency_key,
                    actor_ref="integration-controller",
                )
                for _ in range(2)
            )
        )
        assert submissions[0] == submissions[1]
        with pytest.raises(KnowledgeConcurrencyConflict, match="different ingestion inputs"):
            await repository.add_idempotent(
                job(parser_revision="parser-v2"),
                idempotency_key=idempotency_key,
                actor_ref="integration-controller",
            )

        now = datetime.now(UTC)
        claims = await asyncio.gather(
            *(
                repository.claim_next(
                    now=now,
                    lease_expires_at=now + timedelta(seconds=30),
                )
                for _ in range(2)
            )
        )
        assert sum(value is not None for value in claims) == 1
        first = next(value for value in claims if value is not None)
        assert first is not None
        assert first.fencing_token == 1

        takeover_at = now + timedelta(minutes=1)
        second = await repository.claim_next(
            now=takeover_at,
            lease_expires_at=takeover_at + timedelta(seconds=30),
        )
        assert second is not None
        assert second.fencing_token == 2

        old_checkpoint = StageCheckpoint(
            stage="quarantine",
            unit_cursor=1,
            unit_count=1,
            input_hash="c" * 64,
            output_hash="d" * 64,
            artifact_ref=f"jobs/{first.job_id}/quarantine/checkpoint.json",
            byte_count=10,
            record_count=1,
            completed=True,
        )
        stale = first.checkpoint(
            old_checkpoint,
            fencing_token=first.fencing_token,
            at=now + timedelta(seconds=1),
        ).complete_stage(
            fencing_token=first.fencing_token,
            at=now + timedelta(seconds=1),
        )
        with pytest.raises(KnowledgeConcurrencyConflict, match="stale"):
            await repository.commit_stage(
                stale,
                expected_version=first.version,
                fencing_token=first.fencing_token,
                attempt_number=first.stage_attempt,
                checkpoint=old_checkpoint,
                artifacts=(),
                event_type="knowledge.ingestion.stage-completed",
            )

        checkpoint = old_checkpoint.model_copy(
            update={"artifact_ref": f"jobs/{second.job_id}/quarantine/checkpoint.json"}
        )
        completed = second.checkpoint(
            checkpoint,
            fencing_token=second.fencing_token,
            at=takeover_at,
        ).complete_stage(fencing_token=second.fencing_token, at=takeover_at)
        persisted = await repository.commit_stage(
            completed,
            expected_version=second.version,
            fencing_token=second.fencing_token,
            attempt_number=second.stage_attempt,
            checkpoint=checkpoint,
            artifacts=(
                ArtifactDescriptor(
                    artifact_ref=f"quarantine/{second.job_id}/source.bin",
                    kind="quarantined-source",
                    stage="quarantine",
                    unit_key="source",
                    checksum_sha256="d" * 64,
                    byte_count=10,
                    record_count=1,
                    deletion_generation=second.deletion_generation,
                    fencing_token=second.fencing_token,
                ),
            ),
            event_type="knowledge.ingestion.stage-completed",
        )
        assert persisted.status == "queued"
        restored = await repository.get(command.job_id)
        assert restored == persisted

        deletion_pending = persisted.request_deletion(
            generation=1, at=takeover_at + timedelta(seconds=1)
        )
        deletion_results = await asyncio.gather(
            *(
                repository.save_control_transition(
                    deletion_pending,
                    expected_version=persisted.version,
                    operation="request-deletion",
                    idempotency_key=f"delete-{command.job_id}",
                    actor_ref="integration-deletion-controller",
                )
                for _ in range(2)
            )
        )
        assert deletion_results[0] == deletion_results[1]
        replay = await repository.get_idempotent_control_result(
            command.job_id,
            operation="request-deletion",
            idempotency_key=f"delete-{command.job_id}",
        )
        assert replay == deletion_pending

        deletion_claimed = await repository.claim_next(
            now=takeover_at + timedelta(seconds=2),
            lease_expires_at=takeover_at + timedelta(minutes=1),
        )
        assert deletion_claimed is not None
        tombstoned = deletion_claimed.deletion_completed(
            evidence_hash="e" * 64,
            fencing_token=deletion_claimed.fencing_token,
            at=takeover_at + timedelta(seconds=3),
        )
        await repository.commit_stage(
            tombstoned,
            expected_version=deletion_claimed.version,
            fencing_token=deletion_claimed.fencing_token,
            attempt_number=1,
            checkpoint=None,
            artifacts=(),
            event_type="knowledge.ingestion.tombstoned",
        )
        async with sessions() as session:
            artifact_count = await session.scalar(
                select(func.count())
                .select_from(KnowledgeIngestionArtifact)
                .where(KnowledgeIngestionArtifact.job_id == command.job_id)
            )
        assert artifact_count == 0
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                delete(KnowledgeIngestionJobRecord).where(
                    KnowledgeIngestionJobRecord.source_id == "synthetic-ingestion-integration"
                )
            )
        await engine.dispose()
