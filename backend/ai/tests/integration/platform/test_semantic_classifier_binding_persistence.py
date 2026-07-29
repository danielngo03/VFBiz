import asyncio
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast
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


def digest(value: object) -> str:
    serialized = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )
    return sha256(serialized.encode()).hexdigest()


def db() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    return engine, create_session_factory(engine)


async def clear_authority(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session, session.begin():
        await session.execute(
            text(
                """
                TRUNCATE TABLE
                  ai_semantic_classifier_binding,
                  ai_trusted_release_evidence,
                  ai_trusted_release_artifact,
                  ai_assistant_release_activation,
                  ai_assistant_static_safe_release,
                  ai_assistant_release_candidate
                CASCADE
                """
            )
        )


async def seed_activation(
    session: AsyncSession,
    *,
    profile: str,
    environment: str,
    activation_name: str,
) -> tuple[UUID, str]:
    candidate_id = uuid4()
    safe_id = uuid4()
    activation_id = uuid4()
    candidate_digest = digest(f"candidate:{activation_name}")
    activation_envelope = digest(f"activation-envelope:{activation_name}")
    await session.execute(
        text(
            """
            INSERT INTO ai_assistant_release_candidate (
              id, assistant_profile, environment, candidate_id, content_sha256,
              requested_by_subject, gate_policy_revision, gate_policy_sha256,
              canonical_document
            ) VALUES (
              :id, :profile, :environment, :candidate_name, :candidate_sha,
              'integration-maker', 'gate-v1', :gate_sha, '{}'::jsonb
            )
            """
        ),
        {
            "id": candidate_id,
            "profile": profile,
            "environment": environment,
            "candidate_name": f"candidate-{activation_name}",
            "candidate_sha": candidate_digest,
            "gate_sha": digest("gate-v1"),
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO ai_assistant_static_safe_release (
              id, assistant_profile, environment, safe_release_id,
              safe_release_ref, safe_release_core_sha256, approval_set_sha256,
              safe_release_envelope_sha256, effective_at, expires_at,
              canonical_document
            ) VALUES (
              :id, :profile, :environment, :safe_name, :safe_ref,
              :core_sha, :approval_sha, :envelope_sha,
              clock_timestamp() - interval '1 day',
              clock_timestamp() + interval '60 days', '{}'::jsonb
            )
            """
        ),
        {
            "id": safe_id,
            "profile": profile,
            "environment": environment,
            "safe_name": f"safe-{activation_name}",
            "safe_ref": f"safe-release://integration/{activation_name}",
            "core_sha": digest(f"safe-core:{activation_name}"),
            "approval_sha": digest(f"safe-approval:{activation_name}"),
            "envelope_sha": digest(f"safe-envelope:{activation_name}"),
        },
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
              :id, :profile, :environment, :activation_name,
              :candidate_id, :safe_id, :candidate_sha, :approval_sha,
              :gate_sha, :core_sha, :envelope_sha,
              clock_timestamp() - interval '1 hour',
              clock_timestamp() + interval '30 days',
              'static_safe_release', NULL, :safe_id,
              'tools://integration/kill-switch', :kill_sha,
              'drill://integration/rollback', :drill_sha,
              'approval://integration/promotion', :promotion_sha,
              '{}'::jsonb
            )
            """
        ),
        {
            "id": activation_id,
            "profile": profile,
            "environment": environment,
            "activation_name": activation_name,
            "candidate_id": candidate_id,
            "safe_id": safe_id,
            "candidate_sha": candidate_digest,
            "approval_sha": digest(f"approval:{activation_name}"),
            "gate_sha": digest(f"gate:{activation_name}"),
            "core_sha": digest(f"core:{activation_name}"),
            "envelope_sha": activation_envelope,
            "kill_sha": digest("kill-switch"),
            "drill_sha": digest("rollback-drill"),
            "promotion_sha": digest("promotion"),
        },
    )
    return activation_id, activation_envelope


def binding_document(
    *,
    binding_id: str,
    activation_name: str,
    activation_envelope: str,
    profile: str,
    environment: str,
) -> dict[str, object]:
    effective_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    expires_at = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    artifacts = {
        "classifier_artifact": {
            "ref": "classifier://integration/router",
            "sha256": digest("classifier"),
            "revision": "router-v1",
        },
        "output_schema": {
            "ref": "schema://integration/router-output",
            "sha256": digest("output-schema"),
            "revision": "output-v1",
        },
        "routing_policy": {
            "ref": "policy://integration/router-thresholds",
            "sha256": digest("routing-policy"),
            "revision": "policy-v1",
            "threshold_authority": "code-owned",
        },
    }
    stack_sha = digest(artifacts)
    evaluation = {
        "ref": f"evaluation://integration/{binding_id}",
        "sha256": digest(f"evaluation:{binding_id}"),
        "suite_revision": "router-suite-v1",
        "target_classification_stack_sha256": stack_sha,
        "valid_until": (datetime.now(UTC) + timedelta(days=8)).isoformat(),
    }
    core = {
        "schema_version": 1,
        "binding_id": binding_id,
        "target_activation": {
            "activation_id": activation_name,
            "activation_envelope_sha256": activation_envelope,
            "assistant_profile": profile,
            "environment": environment,
        },
        "classification_stack_sha256": stack_sha,
        "evaluation_evidence": evaluation,
        "effective_at": effective_at,
        "expires_at": expires_at,
    }
    core_sha = digest(core)
    approval = {
        "ref": f"approval://integration/{binding_id}",
        "sha256": digest(f"approval:{binding_id}"),
        "target_binding_core_sha256": core_sha,
    }
    return {
        **core,
        **artifacts,
        "binding_core_sha256": core_sha,
        "approval_evidence": approval,
        "binding_envelope_sha256": digest(
            {
                "approval_evidence": approval,
                "binding_core_sha256": core_sha,
            }
        ),
    }


def replace_binding_window(
    document: dict[str, object],
    *,
    effective_at: datetime,
    expires_at: datetime,
) -> dict[str, object]:
    updated = json.loads(json.dumps(document))
    updated["effective_at"] = effective_at.isoformat()
    updated["expires_at"] = expires_at.isoformat()
    evaluation = updated["evaluation_evidence"]
    assert isinstance(evaluation, dict)
    evaluation["valid_until"] = (expires_at + timedelta(days=1)).isoformat()
    core = {
        field: updated[field]
        for field in (
            "schema_version",
            "binding_id",
            "target_activation",
            "classification_stack_sha256",
            "evaluation_evidence",
            "effective_at",
            "expires_at",
        )
    }
    updated["binding_core_sha256"] = digest(core)
    approval_value = updated["approval_evidence"]
    assert isinstance(approval_value, dict)
    approval = dict(cast(Mapping[str, object], approval_value))
    updated["approval_evidence"] = approval
    approval["target_binding_core_sha256"] = updated["binding_core_sha256"]
    envelope: dict[str, object] = {
        "approval_evidence": approval,
        "binding_core_sha256": updated["binding_core_sha256"],
    }
    updated["binding_envelope_sha256"] = digest(envelope)
    return updated


async def seed_trust(
    session: AsyncSession,
    *,
    document: dict[str, object],
    profile: str,
    environment: str,
) -> None:
    for field in ("classifier_artifact", "output_schema", "routing_policy"):
        artifact = document[field]
        assert isinstance(artifact, dict)
        await session.execute(
            text(
                """
                INSERT INTO ai_trusted_release_artifact (
                  artifact_ref, artifact_sha256, state, effective_at,
                  expires_at, revision
                ) VALUES (
                  :ref, :sha, 'active',
                  clock_timestamp() - interval '30 days',
                  clock_timestamp() + interval '30 days', 1
                )
                ON CONFLICT (artifact_ref) DO NOTHING
                """
            ),
            {"ref": artifact["ref"], "sha": artifact["sha256"]},
        )
    for field, kind, target in (
        ("evaluation_evidence", "classifier_evaluation", "classification_stack_sha256"),
        ("approval_evidence", "classifier_approval", "binding_core_sha256"),
    ):
        evidence = document[field]
        assert isinstance(evidence, dict)
        await session.execute(
            text(
                """
                INSERT INTO ai_trusted_release_evidence (
                  evidence_ref, evidence_kind, evidence_sha256, target_sha256,
                  assistant_profile, environment, authority_role,
                  approver_subject, state, effective_at, expires_at, revision
                ) VALUES (
                  :ref, :kind, :sha, :target, :profile, :environment,
                  'integration-reviewer', 'human:integration-owner', 'active',
                  clock_timestamp() - interval '30 days',
                  clock_timestamp() + interval '30 days', 1
                )
                """
            ),
            {
                "ref": evidence["ref"],
                "kind": kind,
                "sha": evidence["sha256"],
                "target": document[target],
                "profile": profile,
                "environment": environment,
            },
        )


async def seed_decision_evidence(
    session: AsyncSession,
    *,
    document: dict[str, object],
    profile: str,
    environment: str,
    suffix: str,
) -> tuple[str, str]:
    evidence_ref = f"control://integration/{suffix}"
    evidence_sha = digest(f"control:{suffix}")
    await session.execute(
        text(
            """
            INSERT INTO ai_trusted_release_evidence (
              evidence_ref, evidence_kind, evidence_sha256, target_sha256,
              assistant_profile, environment, authority_role,
              approver_subject, state, effective_at, expires_at, revision
            ) VALUES (
              :ref, 'live_control', :sha, :target, :profile, :environment,
              'release-owner', 'human:release-owner', 'active',
              clock_timestamp() - interval '1 day',
              clock_timestamp() + interval '30 days', 1
            )
            """
        ),
        {
            "ref": evidence_ref,
            "sha": evidence_sha,
            "target": document["binding_envelope_sha256"],
            "profile": profile,
            "environment": environment,
        },
    )
    return evidence_ref, evidence_sha


async def transition_binding(
    session: AsyncSession,
    *,
    binding_id: str,
    expected_revision: int,
    target_state: str,
    event_ref: str,
    evidence_ref: str,
    evidence_sha: str,
) -> None:
    await session.execute(
        text(
            """
            SELECT semantic_classifier_binding_transition(
              :binding_id, :expected_revision, :target_state,
              'human:release-owner', 'integration-decision',
              :event_ref, :evidence_ref, :evidence_sha
            )
            """
        ),
        {
            "binding_id": binding_id,
            "expected_revision": expected_revision,
            "target_state": target_state,
            "event_ref": event_ref,
            "evidence_ref": evidence_ref,
            "evidence_sha": evidence_sha,
        },
    )


async def set_transition_context(
    session: AsyncSession,
    *,
    event_ref: str,
    evidence_ref: str,
    evidence_sha: str,
    allow_supersede: bool = False,
) -> None:
    for key, value in (
        ("vfbiz.semantic_classifier_actor", "human:release-owner"),
        ("vfbiz.semantic_classifier_reason", "integration-decision"),
        ("vfbiz.semantic_classifier_event_ref", event_ref),
        ("vfbiz.semantic_classifier_decision_evidence_ref", evidence_ref),
        ("vfbiz.semantic_classifier_decision_evidence_sha256", evidence_sha),
        (
            "vfbiz.semantic_classifier_allow_supersede",
            "true" if allow_supersede else "false",
        ),
    ):
        await session.execute(
            text("SELECT set_config(:key, :value, true)"),
            {"key": key, "value": value},
        )


async def insert_binding(
    session: AsyncSession,
    *,
    activation_id: UUID,
    document: dict[str, object],
    state: str = "active",
) -> None:
    target = document["target_activation"]
    assert isinstance(target, dict)
    await session.execute(
        text(
            """
            INSERT INTO ai_semantic_classifier_binding (
              binding_id, activation_record_id, activation_envelope_sha256,
              assistant_profile, environment, classification_stack_sha256,
              binding_core_sha256, binding_envelope_sha256, canonical_document,
              state, effective_at, expires_at, revision
            ) VALUES (
              :binding_id, :activation_id, :activation_envelope,
              :profile, :environment, :stack_sha, :core_sha, :envelope_sha,
              CAST(:document AS jsonb), :state,
              CAST(:effective_at AS timestamptz),
              CAST(:expires_at AS timestamptz), 1
            )
            """
        ),
        {
            "binding_id": document["binding_id"],
            "activation_id": activation_id,
            "activation_envelope": target["activation_envelope_sha256"],
            "profile": target["assistant_profile"],
            "environment": target["environment"],
            "stack_sha": document["classification_stack_sha256"],
            "core_sha": document["binding_core_sha256"],
            "envelope_sha": document["binding_envelope_sha256"],
            "document": json.dumps(document),
            "state": state,
            "effective_at": datetime.fromisoformat(str(document["effective_at"])),
            "expires_at": datetime.fromisoformat(str(document["expires_at"])),
        },
    )


@pytest.mark.asyncio
async def test_active_binding_is_unique_and_can_be_superseded() -> None:
    engine, sessions = db()
    profile = "customer-assistant"
    environment = "test"
    try:
        await clear_authority(sessions)
        async with sessions() as session, session.begin():
            activation_id, envelope = await seed_activation(
                session,
                profile=profile,
                environment=environment,
                activation_name="activation-router-v1",
            )
            first = binding_document(
                binding_id="binding-router-v1",
                activation_name="activation-router-v1",
                activation_envelope=envelope,
                profile=profile,
                environment=environment,
            )
            await seed_trust(
                session,
                document=first,
                profile=profile,
                environment=environment,
            )
            await insert_binding(
                session,
                activation_id=activation_id,
                document=first,
            )

        second = binding_document(
            binding_id="binding-router-v2",
            activation_name="activation-router-v1",
            activation_envelope=envelope,
            profile=profile,
            environment=environment,
        )
        future_replacement = replace_binding_window(
            binding_document(
                binding_id="binding-router-future",
                activation_name="activation-router-v1",
                activation_envelope=envelope,
                profile=profile,
                environment=environment,
            ),
            effective_at=datetime.now(UTC) + timedelta(days=1),
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        expired_replacement = replace_binding_window(
            binding_document(
                binding_id="binding-router-expired",
                activation_name="activation-router-v1",
                activation_envelope=envelope,
                profile=profile,
                environment=environment,
            ),
            effective_at=datetime.now(UTC) - timedelta(minutes=50),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        async with sessions() as session, session.begin():
            for candidate in (second, future_replacement, expired_replacement):
                await seed_trust(
                    session,
                    document=candidate,
                    profile=profile,
                    environment=environment,
                )
            decision_ref, decision_sha = await seed_decision_evidence(
                session,
                document=first,
                profile=profile,
                environment=environment,
                suffix="supersede-router-v1",
            )
        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                await insert_binding(
                    session,
                    activation_id=activation_id,
                    document=second,
                )

        for index, replacement in enumerate((future_replacement, expired_replacement)):
            with pytest.raises(DBAPIError, match="requires active replacement"):
                async with sessions() as session, session.begin():
                    await session.execute(
                        text(
                            """
                            SELECT semantic_classifier_binding_supersede(
                              'binding-router-v1', 1, :activation_id,
                              CAST(:replacement AS jsonb),
                              'human:release-owner', 'invalid-cutover',
                              :event_ref, :decision_ref, :decision_sha
                            )
                            """
                        ),
                        {
                            "activation_id": activation_id,
                            "replacement": json.dumps(replacement),
                            "event_ref": (f"event://integration/invalid-cutover-{index}"),
                            "decision_ref": decision_ref,
                            "decision_sha": decision_sha,
                        },
                    )

        async with sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    SELECT semantic_classifier_binding_supersede(
                      'binding-router-v1', 1, :activation_id,
                      CAST(:replacement AS jsonb),
                      'human:release-owner', 'classifier-upgrade',
                      'event://integration/supersede-router-v1',
                      :decision_ref, :decision_sha
                    )
                    """
                ),
                {
                    "activation_id": activation_id,
                    "replacement": json.dumps(second),
                    "decision_ref": decision_ref,
                    "decision_sha": decision_sha,
                },
            )
            history_count = await session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM ai_semantic_classifier_binding_history
                    WHERE binding_id = 'binding-router-v1'
                    """
                )
            )
            outbox_count = await session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM ai_semantic_classifier_binding_outbox_event
                    WHERE event_ref =
                      'event://integration/supersede-router-v1'
                    """
                )
            )
            assert history_count == 1
            assert outbox_count == 1

        async with sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    SELECT semantic_classifier_binding_supersede(
                      'binding-router-v1', 1, :activation_id,
                      CAST(:replacement AS jsonb),
                      'human:release-owner', 'classifier-upgrade',
                      'event://integration/supersede-router-v1',
                      :decision_ref, :decision_sha
                    )
                    """
                ),
                {
                    "activation_id": activation_id,
                    "replacement": json.dumps(second),
                    "decision_ref": decision_ref,
                    "decision_sha": decision_sha,
                },
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_binding_rejects_cross_activation_mutation_delete_and_revision_gap() -> None:
    engine, sessions = db()
    profile = "customer-assistant"
    environment = "test"
    try:
        await clear_authority(sessions)
        async with sessions() as session, session.begin():
            activation_id, envelope = await seed_activation(
                session,
                profile=profile,
                environment=environment,
                activation_name="activation-router-v1",
            )
            other_activation_id, _ = await seed_activation(
                session,
                profile=profile,
                environment=environment,
                activation_name="activation-router-other",
            )
            document = binding_document(
                binding_id="binding-router-v1",
                activation_name="activation-router-v1",
                activation_envelope=envelope,
                profile=profile,
                environment=environment,
            )
            await seed_trust(
                session,
                document=document,
                profile=profile,
                environment=environment,
            )
            noncanonical_document = {**document, "caller_extension": True}
            with pytest.raises(DBAPIError, match="canonical contract mismatch"):
                async with session.begin_nested():
                    await insert_binding(
                        session,
                        activation_id=activation_id,
                        document=noncanonical_document,
                    )
            with pytest.raises(DBAPIError, match="target activation mismatch"):
                async with session.begin_nested():
                    await insert_binding(
                        session,
                        activation_id=other_activation_id,
                        document=document,
                    )
            await insert_binding(
                session,
                activation_id=activation_id,
                document=document,
            )
            decision_ref, decision_sha = await seed_decision_evidence(
                session,
                document=document,
                profile=profile,
                environment=environment,
                suffix="revoke-router-v1",
            )

        for index, (statement, message) in enumerate(
            (
                (
                    """
                UPDATE ai_semantic_classifier_binding
                SET binding_core_sha256 = :digest,
                    state = 'revoked', revision = revision + 1
                WHERE binding_id = 'binding-router-v1'
                """,
                    "identity is immutable",
                ),
                (
                    """
                UPDATE ai_semantic_classifier_binding
                SET state = 'revoked', revision = revision + 2
                WHERE binding_id = 'binding-router-v1'
                """,
                    "revision must advance exactly once",
                ),
                (
                    """
                DELETE FROM ai_semantic_classifier_binding
                WHERE binding_id = 'binding-router-v1'
                """,
                    "delete is forbidden",
                ),
            )
        ):
            with pytest.raises(DBAPIError, match=message):
                async with sessions() as session, session.begin():
                    await set_transition_context(
                        session,
                        event_ref=f"event://integration/invalid-{index}",
                        evidence_ref=decision_ref,
                        evidence_sha=decision_sha,
                    )
                    await session.execute(text(statement), {"digest": "0" * 64})

        with pytest.raises(DBAPIError, match="requires active replacement"):
            async with sessions() as session, session.begin():
                await set_transition_context(
                    session,
                    event_ref="event://integration/orphan-supersede",
                    evidence_ref=decision_ref,
                    evidence_sha=decision_sha,
                    allow_supersede=True,
                )
                await session.execute(
                    text(
                        """
                        UPDATE ai_semantic_classifier_binding
                        SET state = 'superseded', revision = revision + 1
                        WHERE binding_id = 'binding-router-v1'
                        """
                    )
                )

        async with sessions() as session, session.begin():
            await transition_binding(
                session,
                binding_id="binding-router-v1",
                expected_revision=1,
                target_state="revoked",
                event_ref="event://integration/revoke-router-v1",
                evidence_ref=decision_ref,
                evidence_sha=decision_sha,
            )
        async with sessions() as session, session.begin():
            await transition_binding(
                session,
                binding_id="binding-router-v1",
                expected_revision=1,
                target_state="revoked",
                event_ref="event://integration/revoke-router-v1",
                evidence_ref=decision_ref,
                evidence_sha=decision_sha,
            )
        with pytest.raises(DBAPIError, match="transition fence mismatch"):
            async with sessions() as session, session.begin():
                await transition_binding(
                    session,
                    binding_id="binding-router-v1",
                    expected_revision=2,
                    target_state="revoked",
                    event_ref="event://integration/revoke-router-v1-again",
                    evidence_ref=decision_ref,
                    evidence_sha=decision_sha,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_binding_window_must_be_contained_by_activation() -> None:
    engine, sessions = db()
    profile = "customer-assistant"
    environment = "test"
    try:
        await clear_authority(sessions)
        async with sessions() as session, session.begin():
            activation_id, envelope = await seed_activation(
                session,
                profile=profile,
                environment=environment,
                activation_name="activation-window",
            )
            before = replace_binding_window(
                binding_document(
                    binding_id="binding-before-activation",
                    activation_name="activation-window",
                    activation_envelope=envelope,
                    profile=profile,
                    environment=environment,
                ),
                effective_at=datetime.now(UTC) - timedelta(days=2),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
            after = replace_binding_window(
                binding_document(
                    binding_id="binding-after-activation",
                    activation_name="activation-window",
                    activation_envelope=envelope,
                    profile=profile,
                    environment=environment,
                ),
                effective_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=31),
            )
            for document in (before, after):
                await seed_trust(
                    session,
                    document=document,
                    profile=profile,
                    environment=environment,
                )
                with pytest.raises(
                    DBAPIError,
                    match="target activation mismatch",
                ):
                    async with session.begin_nested():
                        await insert_binding(
                            session,
                            activation_id=activation_id,
                            document=document,
                        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_lifecycle_transition_has_one_audited_winner() -> None:
    engine, sessions = db()
    profile = "customer-assistant"
    environment = "test"
    try:
        await clear_authority(sessions)
        async with sessions() as session, session.begin():
            activation_id, envelope = await seed_activation(
                session,
                profile=profile,
                environment=environment,
                activation_name="activation-concurrent",
            )
            document = binding_document(
                binding_id="binding-concurrent",
                activation_name="activation-concurrent",
                activation_envelope=envelope,
                profile=profile,
                environment=environment,
            )
            await seed_trust(
                session,
                document=document,
                profile=profile,
                environment=environment,
            )
            await insert_binding(
                session,
                activation_id=activation_id,
                document=document,
            )
            decision_ref, decision_sha = await seed_decision_evidence(
                session,
                document=document,
                profile=profile,
                environment=environment,
                suffix="concurrent",
            )

        async def attempt(event_ref: str) -> str:
            try:
                async with sessions() as session, session.begin():
                    await transition_binding(
                        session,
                        binding_id="binding-concurrent",
                        expected_revision=1,
                        target_state="revoked",
                        event_ref=event_ref,
                        evidence_ref=decision_ref,
                        evidence_sha=decision_sha,
                    )
                return "committed"
            except DBAPIError:
                return "rejected"

        outcomes = await asyncio.gather(
            attempt("event://integration/concurrent-a"),
            attempt("event://integration/concurrent-b"),
        )
        assert sorted(outcomes) == ["committed", "rejected"]
        async with sessions() as session:
            state = (
                await session.execute(
                    text(
                        """
                        SELECT state, revision
                        FROM ai_semantic_classifier_binding
                        WHERE binding_id = 'binding-concurrent'
                        """
                    )
                )
            ).one()
            history_count = await session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM ai_semantic_classifier_binding_history
                    WHERE binding_id = 'binding-concurrent'
                    """
                )
            )
            outbox_count = await session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM ai_semantic_classifier_binding_outbox_event
                    """
                )
            )
            assert state == ("revoked", 2)
            assert history_count == 1
            assert outbox_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_downgrade_refuses_persisted_classifier_authority() -> None:
    engine, sessions = db()
    try:
        await clear_authority(sessions)
        async with sessions() as session, session.begin():
            activation_id, envelope = await seed_activation(
                session,
                profile="customer-assistant",
                environment="test",
                activation_name="activation-downgrade",
            )
            document = binding_document(
                binding_id="binding-downgrade",
                activation_name="activation-downgrade",
                activation_envelope=envelope,
                profile="customer-assistant",
                environment="test",
            )
            await seed_trust(
                session,
                document=document,
                profile="customer-assistant",
                environment="test",
            )
            await insert_binding(
                session,
                activation_id=activation_id,
                document=document,
            )
        configuration = Config(str(AI_ROOT / "alembic.ini"))
        with pytest.raises(Exception, match="downgrade refused"):
            await asyncio.to_thread(
                command.downgrade,
                configuration,
                "20260729_0018",
            )
        async with sessions() as session:
            version = await session.scalar(text("SELECT version_num FROM alembic_version"))
            binding_count = await session.scalar(
                text("SELECT count(*) FROM ai_semantic_classifier_binding")
            )
            evidence_count = await session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM ai_trusted_release_evidence
                    WHERE evidence_kind IN (
                      'classifier_evaluation',
                      'classifier_approval'
                    )
                    """
                )
            )
            history_table = await session.scalar(
                text("SELECT to_regclass('ai_semantic_classifier_binding_history')")
            )
            outbox_table = await session.scalar(
                text("SELECT to_regclass('ai_semantic_classifier_binding_outbox_event')")
            )
            assert version == "20260729_0019"
            assert binding_count == 1
            assert evidence_count == 2
            assert history_table == "ai_semantic_classifier_binding_history"
            assert outbox_table == "ai_semantic_classifier_binding_outbox_event"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_empty_downgrade_restores_legacy_constraint_and_reupgrades() -> None:
    engine, sessions = db()
    configuration = Config(str(AI_ROOT / "alembic.ini"))
    try:
        await clear_authority(sessions)
        await engine.dispose()
        await asyncio.to_thread(
            command.downgrade,
            configuration,
            "20260729_0018",
        )

        downgraded_engine, downgraded_sessions = db()
        try:
            async with downgraded_sessions() as session:
                table = await session.scalar(
                    text("SELECT to_regclass('ai_semantic_classifier_binding')")
                )
                assert table is None
            with pytest.raises(IntegrityError):
                async with downgraded_sessions() as session, session.begin():
                    await session.execute(
                        text(
                            """
                            INSERT INTO ai_trusted_release_evidence (
                              evidence_ref, evidence_kind, evidence_sha256,
                              target_sha256, assistant_profile, environment,
                              state, effective_at, revision
                            ) VALUES (
                              'evaluation://integration/legacy-reject',
                              'classifier_evaluation', :sha, :sha,
                              'customer-assistant', 'test', 'active',
                              clock_timestamp(), 1
                            )
                            """
                        ),
                        {"sha": "a" * 64},
                    )
        finally:
            await downgraded_engine.dispose()
    finally:
        await asyncio.to_thread(command.upgrade, configuration, "head")
