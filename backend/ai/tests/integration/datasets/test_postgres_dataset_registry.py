from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
from app.modules.datasets.infrastructure import postgres_registry
from app.modules.datasets.infrastructure.models import DatasetFetchRecord, DatasetSourceRecord
from app.modules.datasets.infrastructure.postgres_registry import PostgresDatasetRegistry
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory

requires_postgres = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


@requires_postgres
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
                text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            )
            await session.execute(
                delete(DatasetSourceRecord).where(DatasetSourceRecord.id == candidate.source_id)
            )
        await engine.dispose()


@requires_postgres
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
                text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            )
            await session.execute(
                delete(DatasetFetchRecord).where(DatasetFetchRecord.id == fetch_id)
            )
            await session.execute(
                delete(DatasetSourceRecord).where(DatasetSourceRecord.id == candidate.source_id)
            )
        await engine.dispose()


@requires_postgres
@pytest.mark.asyncio
async def test_release_provenance_resolves_exact_revision_purpose_and_scanned_digest() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    registry = PostgresDatasetRegistry(sessions)
    candidate = DatasetSource(
        source_id=uuid4(),
        source_key=f"integration-provenance-{uuid4()}",
        source_revision="exact-revision",
        origin_uri="urn:vfbiz:dataset:integration-provenance",
        status=SourceStatus.CANDIDATE,
        owner_ref="integration-data-owner",
        classification="internal",
        proposed_uses=(AllowedUse.CLASSIFIER_TRAINING,),
    )
    fetch_id = uuid4()
    digest = "9" * 64
    requested = DatasetFetch(
        fetch_id=fetch_id,
        source_id=candidate.source_id,
        state=FetchState.REQUESTED,
        requested_by="dataset-source-researcher",
        approval_evidence_ref="approval:integration-provenance",
        approval_evidence_sha256="a" * 64,
    )
    try:
        await registry.add_source(candidate)
        fetch_approved = candidate.transition(
            SourceStatus.FETCH_APPROVED,
            rights_evidence_ref="approval:rights:integration-provenance",
            rights_evidence_sha256="b" * 64,
            terms_sha256="c" * 64,
        )
        await registry.save_source(fetch_approved, expected_version=1)
        purpose_approved = fetch_approved.transition(
            SourceStatus.PURPOSE_APPROVED,
            approved_uses=(AllowedUse.CLASSIFIER_TRAINING,),
        )
        await registry.save_source(purpose_approved, expected_version=2)

        await registry.add_fetch(requested)
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
            evidence_ref="scan://integration/provenance",
            evidence_sha256="d" * 64,
            artifact_sha256=digest,
            scanner_revision="vivi-dataset-inspection-v1",
            signature_revision="clamav-daily-28075",
            structural_valid=True,
            malware_passed=True,
            dlp_decision=DlpDecision.PASSED,
        )
        scan_passed = verified.transition(FetchState.SCAN_PASSED, scan_evidence=evidence)
        await registry.save_fetch(scan_passed, expected_version=4)

        resolution = await registry.resolve_source_provenance(
            source_key=candidate.source_key,
            source_revision="exact-revision",
            artifact_sha256=digest,
        )

        assert resolution is not None
        assert resolution.source == purpose_approved
        assert resolution.scan_passed_fetch == scan_passed
        assert (
            await registry.resolve_source_provenance(
                source_key=candidate.source_key,
                source_revision="wrong-revision",
                artifact_sha256=digest,
            )
            is None
        )
        wrong_digest = await registry.resolve_source_provenance(
            source_key=candidate.source_key,
            source_revision="exact-revision",
            artifact_sha256="8" * 64,
        )
        assert wrong_digest is not None
        assert wrong_digest.source == purpose_approved
        assert wrong_digest.scan_passed_fetch is None
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            )
            await session.execute(
                delete(DatasetFetchRecord).where(DatasetFetchRecord.id == fetch_id)
            )
            await session.execute(
                delete(DatasetSourceRecord).where(
                    DatasetSourceRecord.id == candidate.source_id
                )
            )
        await engine.dispose()


class FakeDatabaseFailure(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        return None


class FakeSession:
    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        return None

    def begin(self) -> FakeTransaction:
        return FakeTransaction()

    async def execute(self, _statement: object) -> None:
        return None


class FakeSessionFactory:
    def __init__(self) -> None:
        self.attempts = 0

    def __call__(self) -> FakeSession:
        self.attempts += 1
        return FakeSession()


def database_error(sqlstate: str) -> DBAPIError:
    return DBAPIError(
        "dataset registry transaction",
        {},
        FakeDatabaseFailure(sqlstate),
        False,
    )


async def run_with_fake_sessions[T](
    factory: FakeSessionFactory,
    operation: Callable[[AsyncSession], Awaitable[T]],
) -> T:
    return await postgres_registry._run_serializable(  # pyright: ignore[reportPrivateUsage]
        cast(async_sessionmaker[AsyncSession], factory),
        operation,
    )


@pytest.mark.asyncio
async def test_serializable_retry_succeeds_on_third_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeSessionFactory()
    operation_attempts = 0

    async def no_sleep(_delay: float) -> None:
        return None

    async def operation(_session: AsyncSession) -> str:
        nonlocal operation_attempts
        operation_attempts += 1
        if operation_attempts < 3:
            raise database_error("40001")
        return "committed"

    monkeypatch.setattr(postgres_registry.asyncio, "sleep", no_sleep)

    assert await run_with_fake_sessions(factory, operation) == "committed"
    assert factory.attempts == 3


@pytest.mark.asyncio
async def test_serializable_retry_stops_after_third_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeSessionFactory()

    async def no_sleep(_delay: float) -> None:
        return None

    async def operation(_session: AsyncSession) -> None:
        raise database_error("40001")

    monkeypatch.setattr(postgres_registry.asyncio, "sleep", no_sleep)

    with pytest.raises(DBAPIError) as error:
        await run_with_fake_sessions(factory, operation)
    assert getattr(error.value.orig, "sqlstate", None) == "40001"
    assert factory.attempts == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        database_error("23514"),
        RegistryInvariantError("optimistic concurrency"),
    ],
)
async def test_serializable_retry_does_not_retry_non_serialization_failures(
    failure: Exception,
) -> None:
    factory = FakeSessionFactory()

    async def operation(_session: AsyncSession) -> None:
        raise failure

    with pytest.raises(type(failure)):
        await run_with_fake_sessions(factory, operation)
    assert factory.attempts == 1


@pytest.mark.asyncio
async def test_serializable_retry_propagates_cancellation() -> None:
    factory = FakeSessionFactory()

    async def operation(_session: AsyncSession) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_with_fake_sessions(factory, operation)
    assert factory.attempts == 1
