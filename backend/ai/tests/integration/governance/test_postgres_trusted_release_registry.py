import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.governance.infrastructure.postgres_trusted_release_registry import (
    PostgresTrustedReleaseRegistry,
)
from app.modules.governance.infrastructure.trusted_release_artifacts import (
    EvidenceAuthenticityRequest,
    EvidenceKind,
    ReleaseArtifactInfrastructureError,
)
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)

NOW = datetime.now(UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64


def _database_url() -> str:
    value = Settings().database_url
    assert value is not None
    return value


async def _clear_registry(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session, session.begin():
        await session.execute(
            text(
                "TRUNCATE TABLE ai_trusted_release_registry_outbox, "
                "ai_trusted_release_registry_history, "
                "ai_trusted_release_evidence, ai_trusted_release_artifact CASCADE"
            )
        )


@pytest.mark.asyncio
async def test_artifact_registry_fails_closed_after_revocation() -> None:
    engine = create_engine(_database_url())
    sessions = create_session_factory(engine)
    registry = PostgresTrustedReleaseRegistry(sessions)
    try:
        await _clear_registry(sessions)
        async with sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO ai_trusted_release_artifact (
                      artifact_ref, artifact_sha256, state, effective_at, revision
                    ) VALUES (
                      'model://customer/release-1', :digest, 'active', :effective_at, 1
                    )
                    """
                ),
                {"digest": SHA_A, "effective_at": NOW - timedelta(minutes=1)},
            )
        assert await registry.read_sha256("model://customer/release-1") == SHA_A
        await registry.revoke(
            registry_kind="artifact",
            reference="model://customer/release-1",
            expected_revision=1,
            actor_subject="subject-release-owner",
            reason="security withdrawal",
            idempotency_key="revoke-artifact-1",
        )
        assert await registry.read_sha256("model://customer/release-1") is None
        async with sessions() as session:
            with pytest.raises(SQLAlchemyError):
                async with session.begin():
                    await session.execute(
                        text(
                            """
                            UPDATE ai_trusted_release_artifact
                            SET state = 'active', revision = revision + 1
                            WHERE artifact_ref = 'model://customer/release-1'
                            """
                        )
                    )
        async with sessions() as session:
            with pytest.raises(SQLAlchemyError):
                async with session.begin():
                    await session.execute(
                        text(
                            "DELETE FROM ai_trusted_release_artifact "
                            "WHERE artifact_ref = 'model://customer/release-1'"
                        )
                    )
        async with sessions() as session:
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM ai_trusted_release_registry_history "
                        "WHERE registry_ref = 'model://customer/release-1'"
                    )
                )
                == 1
            )
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM ai_trusted_release_registry_outbox")
                )
                == 1
            )
        async with sessions() as session:
            with pytest.raises(SQLAlchemyError):
                async with session.begin():
                    await session.execute(
                        text(
                            """
                            UPDATE ai_trusted_release_registry_outbox
                            SET payload = jsonb_build_object('tampered', true)
                            """
                        )
                    )
        with pytest.raises(ReleaseArtifactInfrastructureError):
            await registry.revoke(
                registry_kind="artifact",
                reference="model://customer/release-1",
                expected_revision=1,
                actor_subject="different-subject",
                reason="different reason",
                idempotency_key="revoke-artifact-1",
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_freshness_scope_rejects_revocation_after_lookup() -> None:
    engine = create_engine(_database_url())
    sessions = create_session_factory(engine)
    registry = PostgresTrustedReleaseRegistry(sessions)
    token = registry.begin_freshness_scope()
    try:
        await _clear_registry(sessions)
        async with sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO ai_trusted_release_artifact (
                      artifact_ref, artifact_sha256, state, effective_at, revision
                    ) VALUES (
                      'model://customer/concurrent-revoke', :digest,
                      'active', :effective_at, 1
                    )
                    """
                ),
                {"digest": SHA_A, "effective_at": NOW - timedelta(minutes=1)},
            )
        assert await registry.read_sha256("model://customer/concurrent-revoke") == SHA_A
        await registry.revoke(
            registry_kind="artifact",
            reference="model://customer/concurrent-revoke",
            expected_revision=1,
            actor_subject="subject-security-owner",
            reason="concurrent kill switch",
            idempotency_key="concurrent-revoke-1",
        )
        with pytest.raises(ReleaseArtifactInfrastructureError):
            await registry.assert_fresh()
    finally:
        registry.end_freshness_scope(token)
        await engine.dispose()


@pytest.mark.asyncio
async def test_child_task_receipts_are_included_in_atomic_final_fence() -> None:
    engine = create_engine(_database_url())
    sessions = create_session_factory(engine)
    registry = PostgresTrustedReleaseRegistry(sessions)
    token = registry.begin_freshness_scope()
    try:
        await _clear_registry(sessions)
        async with sessions() as session, session.begin():
            for index in (1, 2):
                await session.execute(
                    text(
                        """
                        INSERT INTO ai_trusted_release_artifact (
                          artifact_ref, artifact_sha256, state, effective_at, revision
                        ) VALUES (
                          :reference, :digest, 'active', :effective_at, 1
                        )
                        """
                    ),
                    {
                        "reference": f"model://customer/gather-{index}",
                        "digest": SHA_A if index == 1 else SHA_B,
                        "effective_at": NOW - timedelta(minutes=1),
                    },
                )
        await asyncio.gather(
            registry.read_sha256("model://customer/gather-1"),
            registry.read_sha256("model://customer/gather-2"),
        )
        await registry.revoke(
            registry_kind="artifact",
            reference="model://customer/gather-2",
            expected_revision=1,
            actor_subject="subject-security-owner",
            reason="kill switch",
            idempotency_key="gather-revoke-2",
        )
        with pytest.raises(ReleaseArtifactInfrastructureError):
            await registry.assert_fresh()
    finally:
        registry.end_freshness_scope(token)
        await engine.dispose()


@pytest.mark.asyncio
async def test_evidence_registry_requires_exact_identity_and_active_state() -> None:
    engine = create_engine(_database_url())
    sessions = create_session_factory(engine)
    registry = PostgresTrustedReleaseRegistry(sessions)
    request = EvidenceAuthenticityRequest(
        kind=EvidenceKind.APPROVAL,
        evidence_ref="approval://security/release-1",
        evidence_sha256=SHA_A,
        target_sha256=SHA_B,
        assistant_profile="customer-assistant",
        environment="staging",
        authority_role="security-owner",
        approver_subject="subject-security",
    )
    try:
        await _clear_registry(sessions)
        async with sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO ai_trusted_release_evidence (
                      evidence_ref, evidence_kind, evidence_sha256, target_sha256,
                      assistant_profile, environment, authority_role,
                      approver_subject, state, effective_at, revision
                    ) VALUES (
                      :ref, :kind, :digest, :target, :profile, :environment,
                      :role, :subject, 'active', :effective_at, 1
                    )
                    """
                ),
                {
                    "ref": request.evidence_ref,
                    "kind": request.kind.value,
                    "digest": request.evidence_sha256,
                    "target": request.target_sha256,
                    "profile": request.assistant_profile,
                    "environment": request.environment,
                    "role": request.authority_role,
                    "subject": request.approver_subject,
                    "effective_at": NOW - timedelta(minutes=1),
                },
            )
        assert await registry.verify(request)
        assert not await registry.verify(
            EvidenceAuthenticityRequest(
                kind=request.kind,
                evidence_ref=request.evidence_ref,
                evidence_sha256=request.evidence_sha256,
                target_sha256=request.target_sha256,
                assistant_profile=request.assistant_profile,
                environment=request.environment,
                authority_role=request.authority_role,
                approver_subject="different-subject",
            )
        )
        await registry.revoke(
            registry_kind="evidence",
            reference=request.evidence_ref,
            expected_revision=1,
            actor_subject="subject-release-owner",
            reason="approval withdrawn",
            idempotency_key="revoke-evidence-1",
        )
        assert not await registry.verify(request)
    finally:
        await engine.dispose()
