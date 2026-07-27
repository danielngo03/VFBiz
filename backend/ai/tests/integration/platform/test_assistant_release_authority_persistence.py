import asyncio
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)

AI_ROOT = Path(__file__).resolve().parents[3]
AUTHORITY_TABLES = (
    "ai_assistant_release_outbox_delivery",
    "ai_assistant_release_outbox_event",
    "ai_assistant_release_pointer",
    "ai_assistant_release_history",
    "ai_assistant_release_activation",
    "ai_assistant_static_safe_release",
    "ai_assistant_release_candidate",
)


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SeededAuthority:
    profile: str
    environment: str
    safe_id: UUID
    activation_ids: tuple[UUID, ...]


def db() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    return engine, create_session_factory(engine)


async def clear_authority_tables(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session, session.begin():
        await session.execute(text(f"TRUNCATE TABLE {', '.join(AUTHORITY_TABLES)} CASCADE"))


async def insert_candidate(
    session: AsyncSession,
    *,
    profile: str,
    environment: str,
    candidate_number: int,
    record_id: UUID | None = None,
) -> UUID:
    identifier = record_id or uuid4()
    candidate_id = f"candidate-{candidate_number}"
    content_digest = digest(f"{profile}:{environment}:{candidate_id}")
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
            "profile": profile,
            "environment": environment,
            "candidate_id": candidate_id,
            "content_sha256": content_digest,
            "requested_by": "integration-maker",
            "gate_revision": "gate-policy-v1",
            "gate_sha256": digest("gate-policy-v1"),
            "document": json.dumps(
                {
                    "candidate_id": candidate_id,
                    "content_sha256": content_digest,
                }
            ),
        },
    )
    return identifier


async def insert_static_safe(
    session: AsyncSession,
    *,
    profile: str,
    environment: str,
) -> UUID:
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
              :approval_sha256, :envelope_sha256,
              clock_timestamp() - interval '1 hour',
              clock_timestamp() + interval '30 days',
              CAST(:document AS jsonb)
            )
            """
        ),
        {
            "id": identifier,
            "profile": profile,
            "environment": environment,
            "safe_id": f"safe-{identifier.hex}",
            "safe_ref": f"safe-release://integration/{identifier.hex}",
            "core_sha256": digest(f"safe-core:{identifier}"),
            "approval_sha256": digest(f"safe-approval:{identifier}"),
            "envelope_sha256": digest(f"safe-envelope:{identifier}"),
            "document": json.dumps({"safe_release_id": f"safe-{identifier.hex}"}),
        },
    )
    return identifier


async def insert_activation(
    session: AsyncSession,
    *,
    profile: str,
    environment: str,
    candidate_id: UUID,
    static_safe_id: UUID,
    activation_number: int,
    rollback_activation_id: UUID | None,
    candidate_sha256_override: str | None = None,
) -> UUID:
    identifier = uuid4()
    candidate_digest = await session.scalar(
        text(
            """
            SELECT content_sha256
            FROM ai_assistant_release_candidate
            WHERE id = :candidate_id
            """
        ),
        {"candidate_id": candidate_id},
    )
    assert isinstance(candidate_digest, str)
    rollback_kind = (
        "prior_activation" if rollback_activation_id is not None else "static_safe_release"
    )
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
              clock_timestamp() - interval '1 minute',
              clock_timestamp() + interval '7 days',
              :rollback_kind, :rollback_activation_id, :rollback_safe_id,
              :kill_switch_ref, :kill_switch_sha256, :drill_ref, :drill_sha256,
              :promotion_ref, :promotion_sha256, CAST(:document AS jsonb)
            )
            """
        ),
        {
            "id": identifier,
            "profile": profile,
            "environment": environment,
            "activation_id": f"activation-{activation_number}",
            "candidate_id": candidate_id,
            "safe_id": static_safe_id,
            "candidate_sha256": candidate_sha256_override or candidate_digest,
            "approval_sha256": digest(f"approval:{activation_number}"),
            "gate_sha256": digest(f"gate:{activation_number}"),
            "core_sha256": digest(f"core:{activation_number}"),
            "envelope_sha256": digest(f"envelope:{activation_number}"),
            "rollback_kind": rollback_kind,
            "rollback_activation_id": rollback_activation_id,
            "rollback_safe_id": (None if rollback_activation_id is not None else static_safe_id),
            "kill_switch_ref": "tools://integration/kill-switch",
            "kill_switch_sha256": digest("kill-switch"),
            "drill_ref": "drill://integration/rollback",
            "drill_sha256": digest("rollback-drill"),
            "promotion_ref": "approval://integration/promotion",
            "promotion_sha256": digest("promotion"),
            "document": json.dumps(
                {
                    "activation_id": f"activation-{activation_number}",
                    "candidate_sha256": candidate_digest,
                }
            ),
        },
    )
    return identifier


async def seed_authority(
    sessions: async_sessionmaker[AsyncSession],
    *,
    profile: str,
    activation_count: int,
    environment: str = "test",
) -> SeededAuthority:
    async with sessions() as session, session.begin():
        safe_id = await insert_static_safe(
            session,
            profile=profile,
            environment=environment,
        )
        activation_ids: list[UUID] = []
        for number in range(1, activation_count + 1):
            candidate_id = await insert_candidate(
                session,
                profile=profile,
                environment=environment,
                candidate_number=number,
            )
            activation_ids.append(
                await insert_activation(
                    session,
                    profile=profile,
                    environment=environment,
                    candidate_id=candidate_id,
                    static_safe_id=safe_id,
                    activation_number=number,
                    rollback_activation_id=(activation_ids[0] if activation_ids else None),
                )
            )
        await session.execute(
            text(
                """
                INSERT INTO ai_assistant_release_pointer (
                  assistant_profile, environment, target_kind,
                  activation_record_id, static_safe_release_record_id,
                  revision, last_history_event_sha256
                ) VALUES (
                  :profile, :environment, 'static_safe_release',
                  NULL, :safe_id, 0, NULL
                )
                """
            ),
            {
                "profile": profile,
                "environment": environment,
                "safe_id": safe_id,
            },
        )
    return SeededAuthority(
        profile=profile,
        environment=environment,
        safe_id=safe_id,
        activation_ids=tuple(activation_ids),
    )


def target_values(
    kind: str,
    identifier: UUID,
) -> Mapping[str, UUID | None | str]:
    return {
        "kind": kind,
        "activation_id": identifier if kind == "activation" else None,
        "safe_id": identifier if kind == "static_safe_release" else None,
    }


async def target_document(
    session: AsyncSession,
    *,
    authority: SeededAuthority,
    target: Mapping[str, UUID | None | str],
) -> Mapping[str, object]:
    document = await session.scalar(
        text(
            """
            SELECT assistant_release_target_document(
              :kind, :activation_id, :safe_id, :profile, :environment
            )
            """
        ),
        {
            "kind": target["kind"],
            "activation_id": target["activation_id"],
            "safe_id": target["safe_id"],
            "profile": authority.profile,
            "environment": authority.environment,
        },
    )
    assert isinstance(document, dict)
    return document


async def build_event_document(
    session: AsyncSession,
    *,
    authority: SeededAuthority,
    history_event_ref: str,
    sequence: int,
    event_type: str,
    from_target: Mapping[str, UUID | None | str],
    to_target: Mapping[str, UUID | None | str],
    previous_event_sha256: str | None,
) -> tuple[str, str, datetime, Mapping[str, object], Mapping[str, object]]:
    from_document = await target_document(
        session,
        authority=authority,
        target=from_target,
    )
    to_document = await target_document(
        session,
        authority=authority,
        target=to_target,
    )
    envelope_source = from_document if event_type == "revoked" else to_document
    activation_envelope = envelope_source.get("activation_envelope_sha256")
    assert isinstance(activation_envelope, str)
    occurred_at = datetime.now(UTC)
    transaction_context = {"actor": "integration-owner"}
    unsigned_document: dict[str, object] = {
        "event_ref": history_event_ref,
        "sequence": sequence,
        "previous_event_sha256": previous_event_sha256,
        "event_type": event_type,
        "from_target": from_document,
        "to_target": to_document,
        "activation_envelope_sha256": activation_envelope,
        "pointer_revision": sequence,
        "transaction_context": transaction_context,
        "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
    }
    event_sha256 = await canonical_json_digest(session, unsigned_document)
    return (
        event_sha256,
        activation_envelope,
        occurred_at,
        transaction_context,
        {**unsigned_document, "event_sha256": event_sha256},
    )


async def canonical_json_digest(
    session: AsyncSession,
    document: Mapping[str, object],
) -> str:
    value = await session.scalar(
        text(
            """
            SELECT encode(
              digest(
                convert_to(
                  assistant_release_canonical_jsonb(CAST(:document AS jsonb)),
                  'UTF8'
                ),
                'sha256'
              ),
              'hex'
            )
            """
        ),
        {"document": json.dumps(document)},
    )
    assert isinstance(value, str)
    return value


async def insert_history_record(
    session: AsyncSession,
    *,
    authority: SeededAuthority,
    sequence: int,
    event_type: str,
    from_target: Mapping[str, UUID | None | str],
    to_target: Mapping[str, UUID | None | str],
    previous_event_sha256: str | None,
    idempotency: str,
    canonical_document: Mapping[str, object] | None = None,
) -> tuple[UUID, str, Mapping[str, object]]:
    history_id = uuid4()
    history_event_ref = f"history://integration/{history_id.hex}"
    (
        event_sha256,
        activation_envelope,
        occurred_at,
        transaction_context,
        event_document,
    ) = await build_event_document(
        session,
        authority=authority,
        history_event_ref=history_event_ref,
        sequence=sequence,
        event_type=event_type,
        from_target=from_target,
        to_target=to_target,
        previous_event_sha256=previous_event_sha256,
    )
    await session.execute(
        text(
            """
            INSERT INTO ai_assistant_release_history (
              id, assistant_profile, environment, sequence, event_type,
              pointer_revision, from_target_kind,
              from_activation_record_id, from_static_safe_record_id,
              to_target_kind, to_activation_record_id,
              to_static_safe_record_id, history_event_ref,
              previous_event_sha256, event_sha256,
              activation_envelope_sha256, correlation_id,
              idempotency_key_sha256, occurred_at,
              transaction_context, canonical_document
            ) VALUES (
              :id, :profile, :environment, :sequence, :event_type,
              :sequence, :from_kind, :from_activation_id, :from_safe_id,
              :to_kind, :to_activation_id, :to_safe_id, :event_ref,
              :previous_sha256, :event_sha256, :activation_envelope,
              :correlation_id, :idempotency_sha256, :occurred_at,
              CAST(:transaction_context AS jsonb), CAST(:document AS jsonb)
            )
            """
        ),
        {
            "id": history_id,
            "profile": authority.profile,
            "environment": authority.environment,
            "sequence": sequence,
            "event_type": event_type,
            "from_kind": from_target["kind"],
            "from_activation_id": from_target["activation_id"],
            "from_safe_id": from_target["safe_id"],
            "to_kind": to_target["kind"],
            "to_activation_id": to_target["activation_id"],
            "to_safe_id": to_target["safe_id"],
            "event_ref": history_event_ref,
            "previous_sha256": previous_event_sha256,
            "event_sha256": event_sha256,
            "activation_envelope": activation_envelope,
            "correlation_id": f"corr-{idempotency}",
            "idempotency_sha256": digest(idempotency),
            "occurred_at": occurred_at,
            "transaction_context": json.dumps(transaction_context),
            "document": json.dumps(canonical_document or event_document),
        },
    )
    return history_id, event_sha256, event_document


async def update_pointer(
    session: AsyncSession,
    *,
    authority: SeededAuthority,
    sequence: int,
    to_target: Mapping[str, UUID | None | str],
    event_sha256: str,
) -> None:
    pointer_update = await session.execute(
        text(
            """
            UPDATE ai_assistant_release_pointer
            SET target_kind = :to_kind,
                activation_record_id = :to_activation_id,
                static_safe_release_record_id = :to_safe_id,
                revision = :sequence,
                last_history_event_sha256 = :event_sha256,
                updated_at = clock_timestamp()
            WHERE assistant_profile = :profile
              AND environment = :environment
              AND revision = :expected_revision
            """
        ),
        {
            "to_kind": to_target["kind"],
            "to_activation_id": to_target["activation_id"],
            "to_safe_id": to_target["safe_id"],
            "sequence": sequence,
            "event_sha256": event_sha256,
            "profile": authority.profile,
            "environment": authority.environment,
            "expected_revision": sequence - 1,
        },
    )
    if pointer_update.rowcount != 1:
        raise RuntimeError("stale assistant release pointer")


async def insert_outbox_event(
    session: AsyncSession,
    *,
    authority: SeededAuthority,
    history_id: UUID,
    event_type: str,
    event_sha256: str,
    event_document: Mapping[str, object],
    idempotency: str,
    event_type_override: str | None = None,
    event_sha256_override: str | None = None,
    payload_override: Mapping[str, object] | None = None,
) -> UUID:
    outbox_id = uuid4()
    payload = payload_override or event_document
    payload_sha256 = await canonical_json_digest(session, payload)
    await session.execute(
        text(
            """
            INSERT INTO ai_assistant_release_outbox_event (
              id, assistant_profile, environment, history_record_id,
              event_ref, event_type, event_sha256, payload_sha256,
              idempotency_key_sha256, payload
            ) VALUES (
              :id, :profile, :environment, :history_id, :event_ref,
              :event_type, :event_sha256, :payload_sha256,
              :idempotency_sha256, CAST(:payload AS jsonb)
            )
            """
        ),
        {
            "id": outbox_id,
            "profile": authority.profile,
            "environment": authority.environment,
            "history_id": history_id,
            "event_ref": f"outbox://integration/{outbox_id.hex}",
            "event_type": event_type_override or f"assistant.release.{event_type}",
            "event_sha256": event_sha256_override or event_sha256,
            "payload_sha256": payload_sha256,
            "idempotency_sha256": digest(f"outbox:{idempotency}"),
            "payload": json.dumps(payload),
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO ai_assistant_release_outbox_delivery (
              event_record_id, destination
            ) VALUES (:event_id, 'release-control')
            """
        ),
        {"event_id": outbox_id},
    )
    return outbox_id


async def transition(
    sessions: async_sessionmaker[AsyncSession],
    *,
    authority: SeededAuthority,
    sequence: int,
    event_type: str,
    from_target: Mapping[str, UUID | None | str],
    to_target: Mapping[str, UUID | None | str],
    previous_event_sha256: str | None,
    idempotency: str,
    canonical_document: Mapping[str, object] | None = None,
) -> str:
    async with sessions() as session, session.begin():
        history_id, event_sha256, event_document = await insert_history_record(
            session,
            authority=authority,
            sequence=sequence,
            event_type=event_type,
            from_target=from_target,
            to_target=to_target,
            previous_event_sha256=previous_event_sha256,
            idempotency=idempotency,
            canonical_document=canonical_document,
        )
        await update_pointer(
            session,
            authority=authority,
            sequence=sequence,
            to_target=to_target,
            event_sha256=event_sha256,
        )
        await insert_outbox_event(
            session,
            authority=authority,
            history_id=history_id,
            event_type=event_type,
            event_sha256=event_sha256,
            event_document=event_document,
            idempotency=idempotency,
        )
    return event_sha256


@pytest.mark.asyncio
async def test_canonical_json_is_stable_for_utf8_event_fields() -> None:
    engine, sessions = db()
    try:
        payload = {
            "z": "VF 8",
            "a": {"A": 1, "β": "pin"},
            "á": "Đà Nẵng",
        }
        expected = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        async with sessions() as session:
            canonical, event_digest = (
                await session.execute(
                    text(
                        """
                        SELECT
                          assistant_release_canonical_jsonb(
                            CAST(:document AS jsonb)
                          ),
                          encode(
                            digest(
                              convert_to(
                                assistant_release_canonical_jsonb(
                                  CAST(:document AS jsonb)
                                ),
                                'UTF8'
                              ),
                              'sha256'
                            ),
                            'hex'
                          )
                        """
                    ),
                    {"document": json.dumps(payload, ensure_ascii=False)},
                )
            ).one()
        assert canonical == expected
        assert event_digest == sha256(expected.encode("utf-8")).hexdigest()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_round_trip_immutability_and_business_idempotency_collision() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-roundtrip",
            activation_count=1,
        )
        async with sessions() as session:
            candidate = (
                await session.execute(
                    text(
                        """
                        SELECT candidate_id, content_sha256, canonical_document
                        FROM ai_assistant_release_candidate
                        WHERE assistant_profile = :profile
                        """
                    ),
                    {"profile": authority.profile},
                )
            ).one()
            assert candidate.candidate_id == "candidate-1"
            assert candidate.canonical_document["candidate_id"] == "candidate-1"
            assert len(candidate.content_sha256) == 64

        for mutation in (
            """
            UPDATE ai_assistant_release_candidate
            SET requested_by_subject = 'tampered'
            WHERE assistant_profile = :profile
            """,
            """
            DELETE FROM ai_assistant_release_candidate
            WHERE assistant_profile = :profile
            """,
        ):
            with pytest.raises(DBAPIError, match="immutable"):
                async with sessions() as session, session.begin():
                    await session.execute(text(mutation), {"profile": authority.profile})

        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO ai_assistant_release_candidate (
                          assistant_profile, environment, candidate_id,
                          content_sha256, requested_by_subject,
                          gate_policy_revision, gate_policy_sha256,
                          canonical_document
                        )
                        SELECT assistant_profile, environment, candidate_id,
                          :different_digest, requested_by_subject,
                          gate_policy_revision, gate_policy_sha256,
                          canonical_document
                        FROM ai_assistant_release_candidate
                        WHERE assistant_profile = :profile
                        """
                    ),
                    {
                        "profile": authority.profile,
                        "different_digest": digest("different"),
                    },
                )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_activation_rejects_candidate_digest_not_owned_by_candidate() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-candidate-digest-binding",
            activation_count=0,
        )
        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                candidate_id = await insert_candidate(
                    session,
                    profile=authority.profile,
                    environment=authority.environment,
                    candidate_number=1,
                )
                await insert_activation(
                    session,
                    profile=authority.profile,
                    environment=authority.environment,
                    candidate_id=candidate_id,
                    static_safe_id=authority.safe_id,
                    activation_number=1,
                    rollback_activation_id=None,
                    candidate_sha256_override=digest("not-the-candidate-digest"),
                )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_activation_must_start_from_its_pinned_static_safe_target() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        profile = "integration-pinned-activation"
        environment = "test"
        async with sessions() as session, session.begin():
            pinned_safe_id = await insert_static_safe(
                session,
                profile=profile,
                environment=environment,
            )
            candidate_id = await insert_candidate(
                session,
                profile=profile,
                environment=environment,
                candidate_number=1,
            )
            activation_id = await insert_activation(
                session,
                profile=profile,
                environment=environment,
                candidate_id=candidate_id,
                static_safe_id=pinned_safe_id,
                activation_number=1,
                rollback_activation_id=None,
            )
            wrong_safe_id = await insert_static_safe(
                session,
                profile=profile,
                environment=environment,
            )
            await session.execute(
                text(
                    """
                    INSERT INTO ai_assistant_release_pointer (
                      assistant_profile, environment, target_kind,
                      activation_record_id, static_safe_release_record_id,
                      revision, last_history_event_sha256
                    ) VALUES (
                      :profile, :environment, 'static_safe_release',
                      NULL, :safe_id, 0, NULL
                    )
                    """
                ),
                {
                    "profile": profile,
                    "environment": environment,
                    "safe_id": wrong_safe_id,
                },
            )
        authority = SeededAuthority(
            profile=profile,
            environment=environment,
            safe_id=wrong_safe_id,
            activation_ids=(activation_id,),
        )
        with pytest.raises(
            DBAPIError,
            match="activation source does not match activation-pinned authority",
        ):
            await transition(
                sessions,
                authority=authority,
                sequence=1,
                event_type="activated",
                from_target=target_values("static_safe_release", wrong_safe_id),
                to_target=target_values("activation", activation_id),
                previous_event_sha256=None,
                idempotency="pinned-activation-wrong-source",
            )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.parametrize(
    ("include_pointer", "include_outbox"),
    ((False, False), (True, False), (False, True)),
)
@pytest.mark.asyncio
async def test_history_cannot_commit_without_matching_pointer_and_outbox(
    include_pointer: bool,
    include_outbox: bool,
) -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile=(
                f"integration-history-commit-coupling-{int(include_pointer)}-{int(include_outbox)}"
            ),
            activation_count=1,
        )
        with pytest.raises(DBAPIError, match="commit requires matching pointer and outbox"):
            async with sessions() as session, session.begin():
                history_id, event_sha256, event_document = await insert_history_record(
                    session,
                    authority=authority,
                    sequence=1,
                    event_type="activated",
                    from_target=target_values(
                        "static_safe_release",
                        authority.safe_id,
                    ),
                    to_target=target_values(
                        "activation",
                        authority.activation_ids[0],
                    ),
                    previous_event_sha256=None,
                    idempotency="history-without-pointer-outbox",
                )
                if include_pointer:
                    await update_pointer(
                        session,
                        authority=authority,
                        sequence=1,
                        to_target=target_values(
                            "activation",
                            authority.activation_ids[0],
                        ),
                        event_sha256=event_sha256,
                    )
                if include_outbox:
                    await insert_outbox_event(
                        session,
                        authority=authority,
                        history_id=history_id,
                        event_type="activated",
                        event_sha256=event_sha256,
                        event_document=event_document,
                        idempotency="history-without-pointer-outbox",
                    )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.parametrize(
    ("tamper_kind", "expected_message"),
    (
        ("event_type", "outbox event is not bound to release history"),
        ("event_sha256", "outbox event is not bound to release history"),
        ("payload", "outbox payload is not bound to release history"),
    ),
)
@pytest.mark.asyncio
async def test_outbox_rejects_tampered_history_projection(
    tamper_kind: str,
    expected_message: str,
) -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile=f"integration-outbox-binding-{tamper_kind}",
            activation_count=1,
        )
        with pytest.raises(DBAPIError, match=expected_message):
            async with sessions() as session, session.begin():
                history_id, event_sha256, event_document = await insert_history_record(
                    session,
                    authority=authority,
                    sequence=1,
                    event_type="activated",
                    from_target=target_values(
                        "static_safe_release",
                        authority.safe_id,
                    ),
                    to_target=target_values(
                        "activation",
                        authority.activation_ids[0],
                    ),
                    previous_event_sha256=None,
                    idempotency=f"outbox-binding-{tamper_kind}",
                )
                await update_pointer(
                    session,
                    authority=authority,
                    sequence=1,
                    to_target=target_values(
                        "activation",
                        authority.activation_ids[0],
                    ),
                    event_sha256=event_sha256,
                )
                await insert_outbox_event(
                    session,
                    authority=authority,
                    history_id=history_id,
                    event_type="activated",
                    event_sha256=event_sha256,
                    event_document=event_document,
                    idempotency=f"outbox-binding-{tamper_kind}",
                    event_type_override=(
                        "assistant.release.revoked" if tamper_kind == "event_type" else None
                    ),
                    event_sha256_override=(
                        digest("wrong-event") if tamper_kind == "event_sha256" else None
                    ),
                    payload_override=(
                        {"event_sha256": event_sha256, "tampered": True}
                        if tamper_kind == "payload"
                        else None
                    ),
                )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_initial_supersede_rollback_revoke_and_hash_chain_guards() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-lifecycle",
            activation_count=2,
        )
        first, second = authority.activation_ids
        event_1 = await transition(
            sessions,
            authority=authority,
            sequence=1,
            event_type="activated",
            from_target=target_values("static_safe_release", authority.safe_id),
            to_target=target_values("activation", first),
            previous_event_sha256=None,
            idempotency="activate-first",
        )
        event_2 = await transition(
            sessions,
            authority=authority,
            sequence=2,
            event_type="superseded",
            from_target=target_values("activation", first),
            to_target=target_values("activation", second),
            previous_event_sha256=event_1,
            idempotency="activate-second",
        )
        event_3 = await transition(
            sessions,
            authority=authority,
            sequence=3,
            event_type="rolled_back",
            from_target=target_values("activation", second),
            to_target=target_values("activation", first),
            previous_event_sha256=event_2,
            idempotency="rollback-first",
        )
        await transition(
            sessions,
            authority=authority,
            sequence=4,
            event_type="revoked",
            from_target=target_values("activation", first),
            to_target=target_values("static_safe_release", authority.safe_id),
            previous_event_sha256=event_3,
            idempotency="revoke-to-safe",
        )

        async with sessions() as session:
            pointer = (
                await session.execute(
                    text(
                        """
                        SELECT target_kind, revision, static_safe_release_record_id
                        FROM ai_assistant_release_pointer
                        WHERE assistant_profile = :profile
                        """
                    ),
                    {"profile": authority.profile},
                )
            ).one()
            assert tuple(pointer) == ("static_safe_release", 4, authority.safe_id)
            assert (
                await session.scalar(
                    text(
                        """
                    SELECT count(*)
                    FROM ai_assistant_release_history
                    WHERE assistant_profile = :profile
                    """
                    ),
                    {"profile": authority.profile},
                )
                == 4
            )
            assert (
                await session.scalar(
                    text(
                        """
                    SELECT count(*)
                    FROM ai_assistant_release_outbox_event
                    WHERE assistant_profile = :profile
                    """
                    ),
                    {"profile": authority.profile},
                )
                == 4
            )

        with pytest.raises(DBAPIError, match="hash chain is not contiguous"):
            await transition(
                sessions,
                authority=authority,
                sequence=6,
                event_type="activated",
                from_target=target_values("static_safe_release", authority.safe_id),
                to_target=target_values("activation", second),
                previous_event_sha256=digest("wrong"),
                idempotency="bad-chain",
            )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_rollback_must_use_target_pinned_by_current_activation() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-pinned-rollback",
            activation_count=3,
        )
        first, second, third = authority.activation_ids
        event_1 = await transition(
            sessions,
            authority=authority,
            sequence=1,
            event_type="activated",
            from_target=target_values("static_safe_release", authority.safe_id),
            to_target=target_values("activation", first),
            previous_event_sha256=None,
            idempotency="pinned-rollback-first",
        )
        event_2 = await transition(
            sessions,
            authority=authority,
            sequence=2,
            event_type="superseded",
            from_target=target_values("activation", first),
            to_target=target_values("activation", second),
            previous_event_sha256=event_1,
            idempotency="pinned-rollback-second",
        )
        event_3 = await transition(
            sessions,
            authority=authority,
            sequence=3,
            event_type="superseded",
            from_target=target_values("activation", second),
            to_target=target_values("activation", third),
            previous_event_sha256=event_2,
            idempotency="pinned-rollback-third",
        )
        with pytest.raises(
            DBAPIError,
            match="rollback target does not match activation-pinned authority",
        ):
            await transition(
                sessions,
                authority=authority,
                sequence=4,
                event_type="rolled_back",
                from_target=target_values("activation", third),
                to_target=target_values("activation", second),
                previous_event_sha256=event_3,
                idempotency="pinned-rollback-wrong-target",
            )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_revoke_must_use_static_safe_target_pinned_by_activation() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-pinned-revoke",
            activation_count=1,
        )
        event_1 = await transition(
            sessions,
            authority=authority,
            sequence=1,
            event_type="activated",
            from_target=target_values("static_safe_release", authority.safe_id),
            to_target=target_values("activation", authority.activation_ids[0]),
            previous_event_sha256=None,
            idempotency="pinned-revoke-first",
        )
        async with sessions() as session, session.begin():
            wrong_safe_id = await insert_static_safe(
                session,
                profile=authority.profile,
                environment=authority.environment,
            )
        with pytest.raises(
            DBAPIError,
            match="revoke target does not match activation-pinned authority",
        ):
            await transition(
                sessions,
                authority=authority,
                sequence=2,
                event_type="revoked",
                from_target=target_values(
                    "activation",
                    authority.activation_ids[0],
                ),
                to_target=target_values("static_safe_release", wrong_safe_id),
                previous_event_sha256=event_1,
                idempotency="pinned-revoke-wrong-target",
            )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_cas_has_one_winner_and_loser_leaves_no_outbox() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-cas",
            activation_count=3,
        )
        first, second, third = authority.activation_ids
        event_1 = await transition(
            sessions,
            authority=authority,
            sequence=1,
            event_type="activated",
            from_target=target_values("static_safe_release", authority.safe_id),
            to_target=target_values("activation", first),
            previous_event_sha256=None,
            idempotency="cas-first",
        )
        results = await asyncio.gather(
            transition(
                sessions,
                authority=authority,
                sequence=2,
                event_type="superseded",
                from_target=target_values("activation", first),
                to_target=target_values("activation", second),
                previous_event_sha256=event_1,
                idempotency="cas-second",
            ),
            transition(
                sessions,
                authority=authority,
                sequence=2,
                event_type="superseded",
                from_target=target_values("activation", first),
                to_target=target_values("activation", third),
                previous_event_sha256=event_1,
                idempotency="cas-third",
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(result, str) for result in results) == 1
        assert sum(isinstance(result, DBAPIError) for result in results) == 1
        async with sessions() as session:
            assert (
                await session.scalar(
                    text(
                        """
                    SELECT count(*) FROM ai_assistant_release_history
                    WHERE assistant_profile = :profile
                    """
                    ),
                    {"profile": authority.profile},
                )
                == 2
            )
            assert (
                await session.scalar(
                    text(
                        """
                    SELECT count(*) FROM ai_assistant_release_outbox_event
                    WHERE assistant_profile = :profile
                    """
                    ),
                    {"profile": authority.profile},
                )
                == 2
            )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_pointer_update_requires_history_inserted_in_same_transaction() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-pointer-coupling",
            activation_count=1,
        )
        with pytest.raises(
            DBAPIError,
            match="matching history transition",
        ):
            async with sessions() as session, session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE ai_assistant_release_pointer
                        SET target_kind = 'activation',
                            activation_record_id = :activation_id,
                            static_safe_release_record_id = NULL,
                            revision = 1,
                            last_history_event_sha256 = :event_sha256,
                            updated_at = clock_timestamp()
                        WHERE assistant_profile = :profile
                          AND environment = :environment
                          AND revision = 0
                        """
                    ),
                    {
                        "activation_id": authority.activation_ids[0],
                        "event_sha256": digest("missing-history"),
                        "profile": authority.profile,
                        "environment": authority.environment,
                    },
                )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_pointer_update_rejects_history_with_wrong_from_target() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-pointer-from-target",
            activation_count=3,
        )
        first, second, wrong_from = authority.activation_ids
        event_1 = await transition(
            sessions,
            authority=authority,
            sequence=1,
            event_type="activated",
            from_target=target_values("static_safe_release", authority.safe_id),
            to_target=target_values("activation", first),
            previous_event_sha256=None,
            idempotency="pointer-from-first",
        )
        with pytest.raises(
            DBAPIError,
            match="history transition does not match pointer targets",
        ):
            await transition(
                sessions,
                authority=authority,
                sequence=2,
                event_type="superseded",
                from_target=target_values("activation", wrong_from),
                to_target=target_values("activation", second),
                previous_event_sha256=event_1,
                idempotency="pointer-from-wrong",
            )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_history_event_digest_rejects_canonical_payload_tampering() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-history-digest",
            activation_count=1,
        )
        with pytest.raises(
            DBAPIError,
            match="canonical event digest mismatch",
        ):
            await transition(
                sessions,
                authority=authority,
                sequence=1,
                event_type="activated",
                from_target=target_values(
                    "static_safe_release",
                    authority.safe_id,
                ),
                to_target=target_values(
                    "activation",
                    authority.activation_ids[0],
                ),
                previous_event_sha256=None,
                idempotency="tampered-history",
                canonical_document={
                    "event_type": "revoked",
                    "sequence": 999,
                    "tampered": True,
                },
            )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_rollback_target_must_have_prior_authoritative_history() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-rollback-eligibility",
            activation_count=2,
        )
        initial, never_active = authority.activation_ids
        async with sessions() as session, session.begin():
            current_candidate = await insert_candidate(
                session,
                profile=authority.profile,
                environment=authority.environment,
                candidate_number=3,
            )
            current = await insert_activation(
                session,
                profile=authority.profile,
                environment=authority.environment,
                candidate_id=current_candidate,
                static_safe_id=authority.safe_id,
                activation_number=3,
                rollback_activation_id=never_active,
            )
        event_1 = await transition(
            sessions,
            authority=authority,
            sequence=1,
            event_type="activated",
            from_target=target_values("static_safe_release", authority.safe_id),
            to_target=target_values("activation", initial),
            previous_event_sha256=None,
            idempotency="eligibility-first",
        )
        event_2 = await transition(
            sessions,
            authority=authority,
            sequence=2,
            event_type="superseded",
            from_target=target_values("activation", initial),
            to_target=target_values("activation", current),
            previous_event_sha256=event_1,
            idempotency="eligibility-current",
        )
        with pytest.raises(
            DBAPIError,
            match="eligible rollback activation has never been authoritative",
        ):
            await transition(
                sessions,
                authority=authority,
                sequence=3,
                event_type="rolled_back",
                from_target=target_values("activation", current),
                to_target=target_values("activation", never_active),
                previous_event_sha256=event_2,
                idempotency="unsafe-rollback",
            )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_pointer_scope_rejects_stale_or_cross_profile_target() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-owned",
            activation_count=1,
        )
        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO ai_assistant_release_pointer (
                          assistant_profile, environment, target_kind,
                          activation_record_id, static_safe_release_record_id,
                          revision
                        ) VALUES (
                          'integration-other', 'test', 'activation',
                          :activation_id, NULL, 0
                        )
                        """
                    ),
                    {"activation_id": authority.activation_ids[0]},
                )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_candidate_activation_history_pointer_and_outbox_commit_atomically() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-atomic",
            activation_count=0,
        )
        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                candidate_id = await insert_candidate(
                    session,
                    profile=authority.profile,
                    environment=authority.environment,
                    candidate_number=1,
                )
                activation_id = await insert_activation(
                    session,
                    profile=authority.profile,
                    environment=authority.environment,
                    candidate_id=candidate_id,
                    static_safe_id=authority.safe_id,
                    activation_number=1,
                    rollback_activation_id=None,
                )
                history_id, event_sha256, event_document = await insert_history_record(
                    session,
                    authority=authority,
                    sequence=1,
                    event_type="activated",
                    from_target=target_values(
                        "static_safe_release",
                        authority.safe_id,
                    ),
                    to_target=target_values("activation", activation_id),
                    previous_event_sha256=None,
                    idempotency="atomic-history",
                )
                await update_pointer(
                    session,
                    authority=authority,
                    sequence=1,
                    to_target=target_values("activation", activation_id),
                    event_sha256=event_sha256,
                )
                outbox_id = await insert_outbox_event(
                    session,
                    authority=authority,
                    history_id=history_id,
                    event_type="activated",
                    event_sha256=event_sha256,
                    event_document=event_document,
                    idempotency="atomic-outbox",
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO ai_assistant_release_outbox_event (
                          id, assistant_profile, environment,
                          history_record_id, event_ref, event_type,
                          event_sha256, payload_sha256,
                          idempotency_key_sha256, payload
                        )
                        SELECT gen_random_uuid(), assistant_profile,
                          environment, history_record_id,
                          'outbox://integration/collision',
                          event_type, event_sha256, payload_sha256,
                          idempotency_key_sha256, payload
                        FROM ai_assistant_release_outbox_event
                        WHERE id = :outbox_id
                        """
                    ),
                    {"outbox_id": outbox_id},
                )

        async with sessions() as session:
            for table in (
                "ai_assistant_release_candidate",
                "ai_assistant_release_activation",
                "ai_assistant_release_history",
                "ai_assistant_release_outbox_event",
            ):
                assert (
                    await session.scalar(
                        text(f"SELECT count(*) FROM {table}")  # noqa: S608
                    )
                    == 0
                )
            assert (
                await session.scalar(
                    text(
                        """
                    SELECT revision FROM ai_assistant_release_pointer
                    WHERE assistant_profile = :profile
                    """
                    ),
                    {"profile": authority.profile},
                )
                == 0
            )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_restart_recovers_pending_delivery_and_reclaims_expired_lease() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-outbox-recovery",
            activation_count=1,
        )
        await transition(
            sessions,
            authority=authority,
            sequence=1,
            event_type="activated",
            from_target=target_values("static_safe_release", authority.safe_id),
            to_target=target_values("activation", authority.activation_ids[0]),
            previous_event_sha256=None,
            idempotency="recovery-first",
        )
        database_url = Settings().database_url
        assert database_url is not None
        await engine.dispose()

        restarted = create_engine(database_url)
        restarted_sessions = create_session_factory(restarted)
        async with restarted_sessions() as session, session.begin():
            first_claim = (
                await session.execute(
                    text(
                        """
                        SELECT id, lease_owner, attempt_count
                        FROM assistant_release_claim_outbox_delivery(
                          'release-control', 'worker-a', 30, 10
                        )
                        """
                    )
                )
            ).one()
            assert first_claim.lease_owner == "worker-a"
            assert first_claim.attempt_count == 1
            await session.execute(
                text(
                    """
                    UPDATE ai_assistant_release_outbox_delivery
                    SET lease_expires_at = clock_timestamp() - interval '1 second',
                        updated_at = clock_timestamp()
                    WHERE id = :delivery_id
                    """
                ),
                {"delivery_id": first_claim.id},
            )
        await restarted.dispose()

        recovered = create_engine(database_url)
        recovered_sessions = create_session_factory(recovered)
        async with recovered_sessions() as session, session.begin():
            reclaimed = (
                await session.execute(
                    text(
                        """
                        SELECT lease_owner, attempt_count
                        FROM assistant_release_claim_outbox_delivery(
                          'release-control', 'worker-b', 30, 10
                        )
                        """
                    )
                )
            ).one()
            assert tuple(reclaimed) == ("worker-b", 2)
        await clear_authority_tables(recovered_sessions)
        await recovered.dispose()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_final_attempt_crash_is_recovered_to_dead_letter() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority = await seed_authority(
            sessions,
            profile="integration-final-attempt",
            activation_count=1,
        )
        await transition(
            sessions,
            authority=authority,
            sequence=1,
            event_type="activated",
            from_target=target_values("static_safe_release", authority.safe_id),
            to_target=target_values("activation", authority.activation_ids[0]),
            previous_event_sha256=None,
            idempotency="final-attempt",
        )
        async with sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    UPDATE ai_assistant_release_outbox_delivery
                    SET max_attempts = 1
                    """
                )
            )
            claimed = (
                await session.execute(
                    text(
                        """
                        SELECT id, attempt_count
                        FROM assistant_release_claim_outbox_delivery(
                          'release-control', 'crashing-worker', 30, 10
                        )
                        """
                    )
                )
            ).one()
            assert claimed.attempt_count == 1
            await session.execute(
                text(
                    """
                    UPDATE ai_assistant_release_outbox_delivery
                    SET lease_expires_at = clock_timestamp() - interval '1 second',
                        updated_at = clock_timestamp()
                    WHERE id = :delivery_id
                    """
                ),
                {"delivery_id": claimed.id},
            )

        async with sessions() as session, session.begin():
            reclaimed = (
                await session.execute(
                    text(
                        """
                        SELECT id
                        FROM assistant_release_claim_outbox_delivery(
                          'release-control', 'recovery-worker', 30, 10
                        )
                        """
                    )
                )
            ).all()
            assert reclaimed == []
            status = (
                await session.execute(
                    text(
                        """
                        SELECT status, lease_owner, lease_expires_at,
                               attempt_count, max_attempts
                        FROM ai_assistant_release_outbox_delivery
                        WHERE id = :delivery_id
                        """
                    ),
                    {"delivery_id": claimed.id},
                )
            ).one()
            assert tuple(status) == ("dead_letter", None, None, 1, 1)
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


def run_alembic(operation: str, revision: str) -> None:
    configuration = Config(str(AI_ROOT / "alembic.ini"))
    if operation == "upgrade":
        command.upgrade(configuration, revision)
    elif operation == "downgrade":
        command.downgrade(configuration, revision)
    else:  # pragma: no cover - fixed test helper contract
        raise ValueError(f"unsupported Alembic operation: {operation}")


@pytest.mark.asyncio
async def test_populated_downgrade_refuses_and_empty_downgrade_round_trips() -> None:
    engine, sessions = db()
    database_url = Settings().database_url
    assert database_url is not None
    try:
        await clear_authority_tables(sessions)
        async with sessions() as session, session.begin():
            await insert_candidate(
                session,
                profile="integration-downgrade",
                environment="test",
                candidate_number=1,
            )
        await engine.dispose()

        with pytest.raises(
            DBAPIError,
            match="assistant release authority downgrade refused",
        ):
            await asyncio.to_thread(run_alembic, "downgrade", "20260725_0010")

        cleanup_engine = create_engine(database_url)
        cleanup_sessions = create_session_factory(cleanup_engine)
        await clear_authority_tables(cleanup_sessions)
        await cleanup_engine.dispose()

        await asyncio.to_thread(run_alembic, "downgrade", "20260725_0010")
        await asyncio.to_thread(run_alembic, "upgrade", "head")
    finally:
        await engine.dispose()
