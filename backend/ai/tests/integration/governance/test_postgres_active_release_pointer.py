import json
import os
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.governance.infrastructure import PostgresActiveReleasePointerAdapter
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory
from tests.integration.governance.release_authority_fixtures import (
    AUTHORITY_TABLES,
    SeededAuthority,
    release_authority_document,
    target_values,
    transition,
)

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _clear(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session, session.begin():
        await session.execute(text(f"TRUNCATE TABLE {', '.join(AUTHORITY_TABLES)} CASCADE"))


async def _insert_static_safe(session: AsyncSession, document: dict) -> UUID:
    safe = document["static_safe_release"]
    identifier = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO ai_assistant_static_safe_release (
              id, assistant_profile, environment, safe_release_id,
              safe_release_ref, safe_release_core_sha256, approval_set_sha256,
              safe_release_envelope_sha256, effective_at, expires_at,
              canonical_document
            ) VALUES (
              :id, :profile, :environment, :safe_id, :safe_ref, :core_sha256,
              :approval_sha256, :envelope_sha256, :effective_at, :expires_at,
              CAST(:document AS jsonb)
            )
            """
        ),
        {
            "id": identifier,
            "profile": safe["assistant_profile"],
            "environment": safe["environment"],
            "safe_id": safe["safe_release_id"],
            "safe_ref": safe["safe_release_ref"],
            "core_sha256": safe["safe_release_core_sha256"],
            "approval_sha256": safe["approval_set_sha256"],
            "envelope_sha256": safe["safe_release_envelope_sha256"],
            "effective_at": _timestamp(safe["effective_at"]),
            "expires_at": _timestamp(safe["expires_at"]),
            "document": json.dumps(safe),
        },
    )
    return identifier


async def _insert_candidate(session: AsyncSession, document: dict) -> UUID:
    candidate = document["candidate"]
    identifier = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO ai_assistant_release_candidate (
              id, assistant_profile, environment, candidate_id, content_sha256,
              requested_by_subject, gate_policy_revision, gate_policy_sha256,
              canonical_document
            ) VALUES (
              :id, :profile, :environment, :candidate_id, :content_sha256,
              :requested_by, :gate_revision, :gate_sha256,
              CAST(:document AS jsonb)
            )
            """
        ),
        {
            "id": identifier,
            "profile": candidate["assistant_profile"],
            "environment": candidate["environment"],
            "candidate_id": candidate["candidate_id"],
            "content_sha256": candidate["content_sha256"],
            "requested_by": candidate["requested_by_subject"],
            "gate_revision": candidate["gate_policy_revision"],
            "gate_sha256": candidate["gate_policy_sha256"],
            "document": json.dumps(candidate),
        },
    )
    return identifier


async def _insert_activation(
    session: AsyncSession,
    document: dict,
    *,
    candidate_record_id: UUID,
    static_safe_record_id: UUID,
) -> UUID:
    identifier = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO ai_assistant_release_activation (
              id, assistant_profile, environment, activation_id,
              candidate_record_id, static_safe_release_record_id,
              candidate_sha256, approval_set_sha256,
              automated_gate_evidence_sha256, activation_core_sha256,
              activation_envelope_sha256, effective_at, expires_at,
              rollback_target_kind, rollback_activation_record_id,
              rollback_static_safe_record_id, kill_switch_registry_ref,
              kill_switch_registry_sha256, rollback_drill_evidence_ref,
              rollback_drill_evidence_sha256, promotion_evidence_ref,
              promotion_evidence_sha256, canonical_document
            ) VALUES (
              :id, :profile, :environment, :activation_id,
              :candidate_id, :safe_id, :candidate_sha256, :approval_sha256,
              :gate_sha256, :core_sha256, :envelope_sha256,
              :effective_at, :expires_at, 'static_safe_release',
              NULL, :safe_id, :kill_switch_ref, :kill_switch_sha256,
              :drill_ref, :drill_sha256, :promotion_ref, :promotion_sha256,
              CAST(:document AS jsonb)
            )
            """
        ),
        {
            "id": identifier,
            "profile": document["candidate"]["assistant_profile"],
            "environment": document["candidate"]["environment"],
            "activation_id": document["activation_id"],
            "candidate_id": candidate_record_id,
            "safe_id": static_safe_record_id,
            "candidate_sha256": document["candidate"]["content_sha256"],
            "approval_sha256": document["approval_set_sha256"],
            "gate_sha256": document["automated_gate"]["evidence_sha256"],
            "core_sha256": document["activation_core_sha256"],
            "envelope_sha256": document["activation_envelope_sha256"],
            "effective_at": _timestamp(document["effective_at"]),
            "expires_at": _timestamp(document["expires_at"]),
            "kill_switch_ref": document["kill_switch_registry_ref"],
            "kill_switch_sha256": document["kill_switch_registry_sha256"],
            "drill_ref": document["rollback_drill_evidence_ref"],
            "drill_sha256": document["rollback_drill_evidence_sha256"],
            "promotion_ref": document["promotion_evidence_ref"],
            "promotion_sha256": document["promotion_evidence_sha256"],
            "document": json.dumps(document),
        },
    )
    return identifier


async def _point_at(
    session: AsyncSession,
    *,
    profile: str,
    environment: str,
    target_kind: str,
    activation_record_id: UUID | None,
    static_safe_release_record_id: UUID | None,
    revision: int,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ai_assistant_release_pointer (
              assistant_profile, environment, target_kind,
              activation_record_id, static_safe_release_record_id, revision
            ) VALUES (
              :profile, :environment, :target_kind,
              :activation_id, :safe_id, :revision
            )
            """
        ),
        {
            "profile": profile,
            "environment": environment,
            "target_kind": target_kind,
            "activation_id": activation_record_id,
            "safe_id": static_safe_release_record_id,
            "revision": revision,
        },
    )


@pytest.mark.asyncio
async def test_current_returns_none_for_an_unpointed_scope() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    await _clear(sessions)
    adapter = PostgresActiveReleasePointerAdapter(sessions)
    try:
        pointer = await adapter.current(
            assistant_profile="never-pointed", environment="test"
        )
        assert pointer is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_current_reads_a_static_safe_release_pointer() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    await _clear(sessions)
    document = release_authority_document()
    profile = document["candidate"]["assistant_profile"]
    environment = document["candidate"]["environment"]
    try:
        async with sessions() as session, session.begin():
            safe_id = await _insert_static_safe(session, document)
            await _point_at(
                session,
                profile=profile,
                environment=environment,
                target_kind="static_safe_release",
                activation_record_id=None,
                static_safe_release_record_id=safe_id,
                revision=0,
            )

        adapter = PostgresActiveReleasePointerAdapter(sessions)
        pointer = await adapter.current(
            assistant_profile=profile, environment=environment
        )

        assert pointer is not None
        assert pointer.target_kind == "static_safe_release"
        assert pointer.activation_id is None
        assert pointer.safe_release_id == document["static_safe_release"]["safe_release_id"]
        assert (
            pointer.envelope_sha256
            == document["static_safe_release"]["safe_release_envelope_sha256"]
        )
        assert pointer.pointer_revision == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_current_reads_an_activation_pointer() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    await _clear(sessions)
    document = release_authority_document()
    profile = document["candidate"]["assistant_profile"]
    environment = document["candidate"]["environment"]
    try:
        async with sessions() as session, session.begin():
            candidate_id = await _insert_candidate(session, document)
            safe_id = await _insert_static_safe(session, document)
            activation_id = await _insert_activation(
                session,
                document,
                candidate_record_id=candidate_id,
                static_safe_record_id=safe_id,
            )
            # The pointer table's guard trigger requires every scope's first
            # row to be a static-safe pointer at revision 0, and every later
            # transition to have a matching row in ai_assistant_release_history
            # inserted in the same transaction — a raw second INSERT/UPDATE
            # cannot satisfy that, so this reuses the shared transition()
            # fixture instead of hand-rolling the pointer mutation.
            await _point_at(
                session,
                profile=profile,
                environment=environment,
                target_kind="static_safe_release",
                activation_record_id=None,
                static_safe_release_record_id=safe_id,
                revision=0,
            )
        await transition(
            sessions,
            authority=SeededAuthority(
                profile=profile,
                environment=environment,
                safe_id=safe_id,
                activation_ids=(activation_id,),
            ),
            sequence=1,
            event_type="activated",
            from_target=target_values("static_safe_release", safe_id),
            to_target=target_values("activation", activation_id),
            previous_event_sha256=None,
            idempotency="active-release-pointer-test-activate",
        )

        adapter = PostgresActiveReleasePointerAdapter(sessions)
        pointer = await adapter.current(
            assistant_profile=profile, environment=environment
        )

        assert pointer is not None
        assert pointer.target_kind == "activation"
        assert pointer.safe_release_id is None
        assert pointer.activation_id == document["activation_id"]
        assert pointer.envelope_sha256 == document["activation_envelope_sha256"]
        assert pointer.pointer_revision == 1
    finally:
        await engine.dispose()
