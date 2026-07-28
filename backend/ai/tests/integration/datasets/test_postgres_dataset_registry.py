import os
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.modules.datasets.domain import (
    AllowedUse,
    DatasetFetch,
    DatasetScanEvidence,
    DatasetSource,
    DlpDecision,
    FetchState,
    RegistryInvariantError,
    SourceStatus,
)
from app.modules.datasets.infrastructure.models import DatasetFetchRecord, DatasetSourceRecord
from app.modules.datasets.infrastructure.postgres_registry import PostgresDatasetRegistry
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


@pytest.mark.asyncio
async def test_source_transition_uses_optimistic_concurrency() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    registry = PostgresDatasetRegistry(sessions)
    candidate = DatasetSource(
        source_id=uuid4(),
        source_key=f"integration-{uuid4()}",
        source_revision="exact-revision",
        origin_uri="urn:vfbiz:dataset:integration",
        status=SourceStatus.CANDIDATE,
        owner_ref="integration-data-owner",
        classification="internal",
        proposed_uses=(AllowedUse.EVALUATION,),
    )
    try:
        await registry.add_source(candidate)
        await registry.add_source(candidate)
        approved = candidate.transition(
            SourceStatus.FETCH_APPROVED,
            rights_evidence_ref="approval:integration",
            rights_evidence_sha256="a" * 64,
            terms_sha256="b" * 64,
        )
        await registry.save_source(approved, expected_version=1)
        persisted = await registry.get_source(candidate.source_id)
        assert persisted == approved
        with pytest.raises(RegistryInvariantError, match="optimistic concurrency"):
            await registry.save_source(approved, expected_version=1)
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                delete(DatasetSourceRecord).where(DatasetSourceRecord.id == candidate.source_id)
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_fetch_scan_evidence_round_trips_and_is_content_bound() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    registry = PostgresDatasetRegistry(sessions)
    candidate = DatasetSource(
        source_id=uuid4(),
        source_key=f"integration-fetch-{uuid4()}",
        source_revision="exact-revision",
        origin_uri="urn:vfbiz:dataset:integration-fetch",
        status=SourceStatus.CANDIDATE,
        owner_ref="integration-data-owner",
        classification="internal",
        proposed_uses=(AllowedUse.EVALUATION,),
    )
    fetch_id = uuid4()
    digest = "d" * 64
    requested = DatasetFetch(
        fetch_id=fetch_id,
        source_id=candidate.source_id,
        state=FetchState.REQUESTED,
        requested_by="dataset-source-researcher",
        approval_evidence_ref="approval:integration-fetch",
        approval_evidence_sha256="a" * 64,
    )
    try:
        await registry.add_source(candidate)
        await registry.add_fetch(requested)
        await registry.add_fetch(requested)
        with pytest.raises(RegistryInvariantError, match="fetch id conflicts"):
            await registry.add_fetch(
                DatasetFetch(
                    fetch_id=fetch_id,
                    source_id=candidate.source_id,
                    state=FetchState.REQUESTED,
                    requested_by="different-requester",
                    approval_evidence_ref="approval:integration-fetch",
                    approval_evidence_sha256="a" * 64,
                )
            )
        downloading = requested.transition(FetchState.DOWNLOADING)
        await registry.save_fetch(downloading, expected_version=1)
        quarantined = downloading.transition(
            FetchState.QUARANTINED,
            observed_sha256=digest,
            byte_size=42,
            quarantine_uri=f"file:///quarantine/{digest}",
        )
        await registry.save_fetch(quarantined, expected_version=2)
        verified = quarantined.transition(FetchState.VERIFIED)
        await registry.save_fetch(verified, expected_version=3)
        evidence = DatasetScanEvidence(
            evidence_ref="scan://integration/1",
            evidence_sha256="b" * 64,
            artifact_sha256=digest,
            scanner_revision="vivi-dataset-inspection-v1",
            signature_revision="clamav-daily-28075",
            structural_valid=True,
            malware_passed=True,
            dlp_decision=DlpDecision.PASSED,
        )
        passed = verified.transition(FetchState.SCAN_PASSED, scan_evidence=evidence)
        await registry.save_fetch(passed, expected_version=4)

        assert await registry.get_fetch(fetch_id) == passed
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                delete(DatasetFetchRecord).where(DatasetFetchRecord.id == fetch_id)
            )
            await session.execute(
                delete(DatasetSourceRecord).where(DatasetSourceRecord.id == candidate.source_id)
            )
        await engine.dispose()
