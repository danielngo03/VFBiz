import asyncio
import json
import os
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.bootstrap.release_runtime import (
    ReleaseBoundRuntimeResolver,
    ResolvedReleaseRuntime,
)
from app.modules.governance.application.release_resolver import (
    ReleaseManifestResolutionError,
)
from app.modules.governance.domain.release_authority import canonical_sha256
from app.modules.governance.infrastructure.postgres_release_authority import (
    PostgresReleaseAuthorityResolver,
    ReleasePersistenceError,
    ReleasePersistenceErrorCode,
    TrustFreshnessFence,
)
from app.modules.governance.infrastructure.postgres_trusted_release_registry import (
    PostgresTrustedReleaseRegistry,
)
from app.modules.governance.infrastructure.release_authority_schema import (
    JsonSchemaReleaseAuthorityValidator,
)
from app.modules.governance.infrastructure.trusted_release_artifacts import (
    BoundedOpaqueArtifactDigestReader,
    BoundedReleaseEvidenceVerifier,
    EvidenceAuthenticityRequest,
    EvidenceKind,
    ReleaseArtifactInfrastructureError,
    TrustedEvidenceRegistry,
)
from app.platform.config import Settings
from app.platform.database.session import create_engine, create_session_factory
from tests.integration.governance.release_authority_fixtures import (
    AUTHORITY_TABLES,
    SeededAuthority,
    rehash_release_document,
    release_authority_document,
    target_values,
    transition,
)

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)

NOW = datetime(2026, 7, 26, 6, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[5]
RELEASE_AUTHORITY_SCHEMA = json.loads(
    (ROOT / "contracts/ai/ai-release-manifest.schema.json").read_text(encoding="utf-8")
)


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class MemoryArtifactRegistry:
    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)

    async def read_sha256(self, artifact_ref: str) -> str | None:
        await asyncio.sleep(0)
        return self._values.get(artifact_ref)


class AcceptingEvidenceRegistry:
    def __init__(self) -> None:
        self.requests: list[EvidenceAuthenticityRequest] = []

    async def verify(self, request: EvidenceAuthenticityRequest) -> bool:
        await asyncio.sleep(0)
        self.requests.append(request)
        return True


class RejectingPromotionEvidenceRegistry(AcceptingEvidenceRegistry):
    async def verify(self, request: EvidenceAuthenticityRequest) -> bool:
        await super().verify(request)
        return request.kind is not EvidenceKind.PROMOTION


class RejectingPriorLiveControlEvidenceRegistry(AcceptingEvidenceRegistry):
    def __init__(self, prior_candidate_sha256: str) -> None:
        super().__init__()
        self._prior_candidate_sha256 = prior_candidate_sha256

    async def verify(self, request: EvidenceAuthenticityRequest) -> bool:
        await super().verify(request)
        return not (
            request.kind is EvidenceKind.LIVE_CONTROL
            and request.target_sha256 == self._prior_candidate_sha256
        )


class RejectingStaticSafeApprovalEvidenceRegistry(AcceptingEvidenceRegistry):
    async def verify(self, request: EvidenceAuthenticityRequest) -> bool:
        await super().verify(request)
        return request.kind is not EvidenceKind.STATIC_SAFE_APPROVAL


class RevokedDuringResolutionFence:
    def __init__(self) -> None:
        self.scope_ended = False

    def begin_freshness_scope(self) -> object:
        return object()

    async def assert_fresh(self) -> None:
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.AUTHORITY_CHANGED,
            retryable=True,
        )

    def end_freshness_scope(self, token: object) -> None:
        del token
        self.scope_ended = True


class AcceptingTrustFence:
    def begin_freshness_scope(self) -> object:
        return object()

    async def assert_fresh(self) -> None:
        return None

    def end_freshness_scope(self, token: object) -> None:
        del token


class RevokingTrustedRegistry(PostgresTrustedReleaseRegistry):
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        reference: str,
    ) -> None:
        super().__init__(sessions)
        self._reference = reference
        self._revoked = False

    async def assert_fresh(self) -> None:
        if not self._revoked:
            self._revoked = True
            await self.revoke(
                registry_kind="artifact",
                reference=self._reference,
                expected_revision=1,
                actor_subject="subject-security-owner",
                reason="concurrent kill switch",
                idempotency_key="resolver-concurrent-revoke",
            )
        await super().assert_fresh()


class BlockingArtifactRegistry:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def read_sha256(self, artifact_ref: str) -> str | None:
        self.started.set()
        await asyncio.Event().wait()
        return None


class GatedArtifactRegistry:
    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def read_sha256(self, artifact_ref: str) -> str | None:
        self.started.set()
        await self.release.wait()
        return self._values.get(artifact_ref)


def db() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    return engine, create_session_factory(engine)


async def clear_authority_tables(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session, session.begin():
        await session.execute(text(f"TRUNCATE TABLE {', '.join(AUTHORITY_TABLES)} CASCADE"))


async def insert_candidate(
    session: AsyncSession,
    document: Mapping[str, Any],
) -> UUID:
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
            "profile": document["assistant_profile"],
            "environment": document["environment"],
            "candidate_id": document["candidate_id"],
            "content_sha256": document["content_sha256"],
            "requested_by": document["requested_by_subject"],
            "gate_revision": document["gate_policy_revision"],
            "gate_sha256": document["gate_policy_sha256"],
            "document": json.dumps(document),
        },
    )
    return identifier


async def insert_static_safe(
    session: AsyncSession,
    document: Mapping[str, Any],
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
              :approval_sha256, :envelope_sha256, :effective_at, :expires_at,
              CAST(:document AS jsonb)
            )
            """
        ),
        {
            "id": identifier,
            "profile": document["assistant_profile"],
            "environment": document["environment"],
            "safe_id": document["safe_release_id"],
            "safe_ref": document["safe_release_ref"],
            "core_sha256": document["safe_release_core_sha256"],
            "approval_sha256": document["approval_set_sha256"],
            "envelope_sha256": document["safe_release_envelope_sha256"],
            "effective_at": timestamp(str(document["effective_at"])),
            "expires_at": timestamp(str(document["expires_at"])),
            "document": json.dumps(document),
        },
    )
    return identifier


async def insert_activation(
    session: AsyncSession,
    *,
    document: Mapping[str, Any],
    candidate_record_id: UUID,
    static_safe_record_id: UUID,
    rollback_activation_record_id: UUID | None,
) -> UUID:
    identifier = uuid4()
    rollback = cast(Mapping[str, Any], document["rollback_target"])
    raw_rollback_kind = rollback["kind"]
    if raw_rollback_kind not in {"prior_activation", "static_safe_release"}:
        raise AssertionError("fixture rollback kind is invalid")
    rollback_kind = cast(
        Literal["prior_activation", "static_safe_release"],
        raw_rollback_kind,
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
              :effective_at, :expires_at, :rollback_kind,
              :rollback_activation_id, :rollback_safe_id,
              :kill_switch_ref, :kill_switch_sha256, :drill_ref, :drill_sha256,
              :promotion_ref, :promotion_sha256, CAST(:document AS jsonb)
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
            "effective_at": timestamp(str(document["effective_at"])),
            "expires_at": timestamp(str(document["expires_at"])),
            "rollback_kind": rollback_kind,
            "rollback_activation_id": rollback_activation_record_id,
            "rollback_safe_id": (
                static_safe_record_id if rollback_kind == "static_safe_release" else None
            ),
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


async def initialize_pointer(
    session: AsyncSession,
    *,
    profile: str,
    environment: str,
    safe_id: UUID,
) -> None:
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
        {"profile": profile, "environment": environment, "safe_id": safe_id},
    )


def second_document(
    first: Mapping[str, Any],
    *,
    eligible_history_ref: str,
    eligible_history_sha256: str,
) -> dict[str, Any]:
    document = deepcopy(dict(first))
    document["expires_at"] = "2026-08-02T05:00:00Z"
    document["kill_switch_registry_ref"] = "tools://kill-switch/2"
    document["kill_switch_registry_sha256"] = "7" * 64
    document["rollback_drill_evidence_ref"] = "drill://customer/2"
    document["rollback_drill_evidence_sha256"] = "8" * 64
    candidate = document["candidate"]
    candidate["candidate_id"] = "candidate-2"
    candidate["artifacts"]["model_deployment"] = {
        "ref": "model://customer/2",
        "sha256": "9" * 64,
    }
    candidate_projection = {
        "artifacts": {
            "embeddingGenerationDigest": candidate["artifacts"]["embedding_generation_sha256"],
            "modelDeployment": candidate["artifacts"]["model_deployment"],
            "prompt": candidate["artifacts"]["prompt"],
            "outputSchema": candidate["artifacts"]["output_schema"],
            "graph": candidate["artifacts"]["graph"],
            "policy": candidate["artifacts"]["policy"],
            "validator": candidate["artifacts"]["validator"],
            "knowledgeProfile": candidate["artifacts"]["knowledge_profile"],
            "retriever": candidate["artifacts"]["retriever"],
            "datasets": candidate["artifacts"]["dataset_releases"],
            "toolRegistry": candidate["artifacts"]["tool_registry"],
            "evaluator": candidate["artifacts"]["evaluator"],
        },
        "assistantProfile": candidate["assistant_profile"],
        "candidateId": candidate["candidate_id"],
        "environment": candidate["environment"],
        "gatePolicyRevision": candidate["gate_policy_revision"],
        "gatePolicySha256": candidate["gate_policy_sha256"],
        "requestedBySubject": candidate["requested_by_subject"],
    }
    candidate["content_sha256"] = canonical_sha256(candidate_projection)
    document["activation_id"] = "activation-2"
    document["automated_gate"]["target_candidate_sha256"] = candidate["content_sha256"]
    document["automated_gate"]["evidence_ref"] = "evaluation://assistant-release/2"
    document["automated_gate"]["evidence_sha256"] = "8" * 64
    for index, approval in enumerate(document["approvals"], start=1):
        approval["target_candidate_sha256"] = candidate["content_sha256"]
        approval["evidence_ref"] = f"approval://candidate-2/{index}"
        approval["evidence_sha256"] = str(index) * 64
    approvals = cast(list[dict[str, Any]], document["approvals"])

    def approval_id(value: Mapping[str, Any]) -> str:
        return str(value["approval_id"])

    approvals.sort(key=approval_id)
    document["approval_set_sha256"] = canonical_sha256(approvals)
    document["rollback_target"] = {
        "kind": "prior_activation",
        "activation_id": first["activation_id"],
        "activation_envelope_sha256": first["activation_envelope_sha256"],
        "candidate_id": first["candidate"]["candidate_id"],
        "candidate_sha256": first["candidate"]["content_sha256"],
        "assistant_profile": first["candidate"]["assistant_profile"],
        "environment": first["candidate"]["environment"],
        "eligible_history_event_ref": eligible_history_ref,
        "eligible_history_event_sha256": eligible_history_sha256,
    }
    first_activation_target = {
        "kind": "activation",
        "activation_id": first["activation_id"],
        "activation_envelope_sha256": first["activation_envelope_sha256"],
        "candidate_id": first["candidate"]["candidate_id"],
        "candidate_sha256": first["candidate"]["content_sha256"],
        "assistant_profile": first["candidate"]["assistant_profile"],
        "environment": first["candidate"]["environment"],
    }
    document["transaction_context"] = {
        "idempotency_key": "activate-2",
        "correlation_id": "correlation-2",
        "actor_subject": "subject-release",
        "reason": "Supersede with evaluated customer assistant release.",
    }
    document["pointer_transition"] = {
        "operation": "activate",
        "assistant_profile": candidate["assistant_profile"],
        "environment": candidate["environment"],
        "from_target": first_activation_target,
        "to_target": {},
        "expected_pointer_revision": 1,
        "result_pointer_revision": 2,
    }
    document["activation_event"] = {
        "event_ref": "history://customer/2",
        "sequence": 2,
        "previous_event_sha256": eligible_history_sha256,
        "event_type": "superseded",
        "from_target": first_activation_target,
        "to_target": {},
        "activation_envelope_sha256": "0" * 64,
        "pointer_revision": 2,
        "transaction_context": {},
        "occurred_at": "2026-07-26T05:00:02Z",
        "event_sha256": "0" * 64,
    }
    document["outbox_event"] = {
        "event_ref": "outbox://customer/2",
        "schema_version": 1,
        "aggregate_id": (f"{candidate['assistant_profile']}:{candidate['environment']}"),
        "assistant_profile": candidate["assistant_profile"],
        "environment": candidate["environment"],
        "correlation_id": "correlation-2",
        "idempotency_key": "activate-2",
        "event_type": "superseded",
        "pointer_revision": 2,
        "history_event_sha256": "0" * 64,
        "occurred_at": "2026-07-26T05:00:02Z",
        "payload_sha256": "0" * 64,
    }
    rehash_release_document(document)
    return document


def artifact_values(document: Mapping[str, Any]) -> dict[str, str]:
    artifacts = document["candidate"]["artifacts"]
    values = {
        value["ref"]: value["sha256"]
        for key, value in artifacts.items()
        if key
        not in {
            "embedding_generation_sha256",
            "dataset_releases",
        }
    }
    values.update({value["ref"]: value["sha256"] for value in artifacts["dataset_releases"]})
    values[document["automated_gate"]["evidence_ref"]] = document["automated_gate"][
        "evidence_sha256"
    ]
    values[document["kill_switch_registry_ref"]] = document["kill_switch_registry_sha256"]
    values[document["rollback_drill_evidence_ref"]] = document["rollback_drill_evidence_sha256"]
    values[document["promotion_evidence_ref"]] = document["promotion_evidence_sha256"]
    for approval in document["approvals"]:
        values[approval["evidence_ref"]] = approval["evidence_sha256"]
    safe = document["static_safe_release"]
    values[safe["safe_release_ref"]] = safe["safe_release_envelope_sha256"]
    values[safe["template_ref"]] = safe["template_sha256"]
    values[safe["response_policy_ref"]] = safe["response_policy_sha256"]
    for approval in safe["approvals"]:
        values[approval["evidence_ref"]] = approval["evidence_sha256"]
    return values


async def seed_trusted_registry(
    sessions: async_sessionmaker[AsyncSession],
    document: Mapping[str, Any],
) -> None:
    candidate = cast(Mapping[str, Any], document["candidate"])
    safe = cast(Mapping[str, Any], document["static_safe_release"])
    evidence: list[tuple[str, Mapping[str, Any], str]] = [
        (
            "automated_gate",
            cast(Mapping[str, Any], document["automated_gate"]),
            str(candidate["content_sha256"]),
        ),
        (
            "promotion",
            {
                "evidence_ref": document["promotion_evidence_ref"],
                "evidence_sha256": document["promotion_evidence_sha256"],
            },
            str(document["activation_core_sha256"]),
        ),
        (
            "live_control",
            {
                "evidence_ref": document["kill_switch_registry_ref"],
                "evidence_sha256": document["kill_switch_registry_sha256"],
            },
            str(candidate["content_sha256"]),
        ),
        (
            "live_control",
            {
                "evidence_ref": document["rollback_drill_evidence_ref"],
                "evidence_sha256": document["rollback_drill_evidence_sha256"],
            },
            str(candidate["content_sha256"]),
        ),
    ]
    evidence.extend(
        ("approval", cast(Mapping[str, Any], item), str(candidate["content_sha256"]))
        for item in cast(list[object], document["approvals"])
    )
    evidence.extend(
        (
            "static_safe_approval",
            cast(Mapping[str, Any], item),
            str(safe["safe_release_core_sha256"]),
        )
        for item in cast(list[object], safe["approvals"])
    )
    async with sessions() as session, session.begin():
        await session.execute(
            text(
                "TRUNCATE TABLE ai_trusted_release_registry_outbox, "
                "ai_trusted_release_registry_history, ai_trusted_release_evidence, "
                "ai_trusted_release_artifact CASCADE"
            )
        )
        for reference, digest in artifact_values(document).items():
            await session.execute(
                text(
                    """
                    INSERT INTO ai_trusted_release_artifact (
                      artifact_ref, artifact_sha256, state, effective_at, revision
                    ) VALUES (:reference, :digest, 'active', :effective_at, 1)
                    """
                ),
                {"reference": reference, "digest": digest, "effective_at": NOW - timedelta(days=1)},
            )
        for kind, item, target in evidence:
            await session.execute(
                text(
                    """
                    INSERT INTO ai_trusted_release_evidence (
                      evidence_ref, evidence_kind, evidence_sha256, target_sha256,
                      assistant_profile, environment, authority_role,
                      approver_subject, state, effective_at, revision
                    ) VALUES (
                      :reference, :kind, :digest, :target, :profile, :environment,
                      :role, :subject, 'active', :effective_at, 1
                    )
                    """
                ),
                {
                    "reference": item["evidence_ref"],
                    "kind": kind,
                    "digest": item["evidence_sha256"],
                    "target": target,
                    "profile": candidate["assistant_profile"],
                    "environment": candidate["environment"],
                    "role": item.get("authority_role"),
                    "subject": item.get("approver_subject"),
                    "effective_at": NOW - timedelta(days=1),
                },
            )


def resolver(
    sessions: async_sessionmaker[AsyncSession],
    document: Mapping[str, Any],
    *additional_documents: Mapping[str, Any],
    artifact_registry: MemoryArtifactRegistry | GatedArtifactRegistry | None = None,
    evidence_registry: TrustedEvidenceRegistry | None = None,
    trust_freshness_fence: TrustFreshnessFence | None = None,
    max_history_events: int = 4096,
) -> PostgresReleaseAuthorityResolver:
    evidence = evidence_registry or AcceptingEvidenceRegistry()
    artifacts: dict[str, str] = {}
    for release_document in (*additional_documents, document):
        artifacts.update(artifact_values(release_document))
    return PostgresReleaseAuthorityResolver(
        sessions=sessions,
        digest_reader=BoundedOpaqueArtifactDigestReader(
            registry=artifact_registry or MemoryArtifactRegistry(artifacts),
            timeout_seconds=1,
            max_concurrency=4,
        ),
        evidence_verifier=BoundedReleaseEvidenceVerifier(
            registry=evidence,
            timeout_seconds=1,
            max_concurrency=4,
        ),
        schema_validator=JsonSchemaReleaseAuthorityValidator(RELEASE_AUTHORITY_SCHEMA),
        required_approval_roles=("release-owner", "security-owner"),
        clock=lambda: NOW,
        timeout_seconds=5,
        max_concurrency=4,
        max_history_events=max_history_events,
        trust_freshness_fence=trust_freshness_fence or AcceptingTrustFence(),
    )


async def seed_initial(
    sessions: async_sessionmaker[AsyncSession],
    *,
    profile: str,
    document_override: Mapping[str, Any] | None = None,
) -> tuple[SeededAuthority, dict[str, Any]]:
    document = deepcopy(
        dict(document_override) if document_override is not None else release_authority_document()
    )
    assert document["candidate"]["assistant_profile"] == profile
    async with sessions() as session, session.begin():
        safe_id = await insert_static_safe(
            session,
            document["static_safe_release"],
        )
        candidate_id = await insert_candidate(session, document["candidate"])
        activation_id = await insert_activation(
            session,
            document=document,
            candidate_record_id=candidate_id,
            static_safe_record_id=safe_id,
            rollback_activation_record_id=None,
        )
        await initialize_pointer(
            session,
            profile=profile,
            environment="staging",
            safe_id=safe_id,
        )
    authority = SeededAuthority(
        profile=profile,
        environment="staging",
        safe_id=safe_id,
        activation_ids=(activation_id,),
    )
    await transition(
        sessions,
        authority=authority,
        sequence=1,
        event_type="activated",
        from_target=target_values("static_safe_release", safe_id),
        to_target=target_values("activation", activation_id),
        previous_event_sha256=None,
        idempotency=f"{profile}-activate-1",
    )
    return authority, document


async def seed_second(
    sessions: async_sessionmaker[AsyncSession],
    *,
    authority: SeededAuthority,
    first: Mapping[str, Any],
) -> tuple[SeededAuthority, dict[str, Any]]:
    async with sessions() as session:
        event = (
            (
                await session.execute(
                    text(
                        """
                    SELECT history_event_ref, event_sha256
                    FROM ai_assistant_release_history
                    WHERE assistant_profile = :profile
                      AND environment = :environment
                      AND sequence = 1
                    """
                    ),
                    {
                        "profile": authority.profile,
                        "environment": authority.environment,
                    },
                )
            )
            .mappings()
            .one()
        )
    document = second_document(
        first,
        eligible_history_ref=str(event["history_event_ref"]),
        eligible_history_sha256=str(event["event_sha256"]),
    )
    async with sessions() as session, session.begin():
        candidate_id = await insert_candidate(session, document["candidate"])
        activation_id = await insert_activation(
            session,
            document=document,
            candidate_record_id=candidate_id,
            static_safe_record_id=authority.safe_id,
            rollback_activation_record_id=authority.activation_ids[0],
        )
    event_2 = await transition(
        sessions,
        authority=authority,
        sequence=2,
        event_type="superseded",
        from_target=target_values("activation", authority.activation_ids[0]),
        to_target=target_values("activation", activation_id),
        previous_event_sha256=str(event["event_sha256"]),
        idempotency=f"{authority.profile}-activate-2",
    )
    return (
        SeededAuthority(
            profile=authority.profile,
            environment=authority.environment,
            safe_id=authority.safe_id,
            activation_ids=(*authority.activation_ids, activation_id),
        ),
        {**document, "_event_2_sha256": event_2},
    )


@pytest.mark.asyncio
async def test_resolves_first_activation_with_static_safe_rollback() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        _, document = await seed_initial(
            sessions,
            profile="customer-assistant",
        )

        result = await resolver(sessions, document).resolve(
            activation_id=document["activation_id"],
            expected_candidate_sha256=document["candidate"]["content_sha256"],
            assistant_profile="customer-assistant",
            environment="staging",
        )

        assert result.static_safe_release is not None
        assert result.rollback_target == result.static_safe_release.rollback_target()
        assert result.candidate.content_sha256 == document["candidate"]["content_sha256"]
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_active_commit_lease_fences_release_rollback() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, document = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        lease_id = uuid4()
        async with sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    WITH lease_clock AS (
                      SELECT clock_timestamp() AS issued_at
                    )
                    INSERT INTO ai_assistant_release_commit_lease (
                      id, assistant_profile, environment,
                      activation_record_id, candidate_sha256,
                      activation_envelope_sha256, pointer_revision,
                      session_id, turn_id, request_id,
                      conversation_version, fencing_token,
                      issued_at, expires_at
                    ) VALUES (
                      :id, :profile, :environment, :activation_id,
                      :candidate_sha256, :envelope_sha256, 1,
                      :session_id, :turn_id, :request_id, 2, 7,
                      (SELECT issued_at FROM lease_clock),
                      (SELECT issued_at FROM lease_clock) + interval '15 seconds'
                    )
                    """
                ),
                {
                    "id": lease_id,
                    "profile": authority.profile,
                    "environment": authority.environment,
                    "activation_id": authority.activation_ids[0],
                    "candidate_sha256": document["candidate"]["content_sha256"],
                    "envelope_sha256": document["activation_envelope_sha256"],
                    "session_id": uuid4(),
                    "turn_id": uuid4(),
                    "request_id": uuid4(),
                },
            )

        with pytest.raises(DBAPIError, match="active final-commit leases"):
            async with sessions() as session, session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE ai_assistant_release_pointer
                        SET target_kind = 'static_safe_release',
                            activation_record_id = NULL,
                            static_safe_release_record_id = :safe_id,
                            revision = 2
                        WHERE assistant_profile = :profile
                          AND environment = :environment
                        """
                    ),
                    {
                        "safe_id": authority.safe_id,
                        "profile": authority.profile,
                        "environment": authority.environment,
                    },
                )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_commit_lease_retry_returns_the_same_bound_lease() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, document = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        runtime = object.__new__(ReleaseBoundRuntimeResolver)
        runtime._sessions = sessions  # noqa: SLF001
        runtime._settings = SimpleNamespace(environment="staging")  # noqa: SLF001
        release = cast(
            ResolvedReleaseRuntime,
            type(
                "LeaseRelease",
                (),
                {
                    "activation_id": str(authority.activation_ids[0]),
                    "candidate_sha256": document["candidate"]["content_sha256"],
                    "activation_envelope_sha256": document[
                        "activation_envelope_sha256"
                    ],
                    "pointer_revision": 1,
                },
            )(),
        )
        binding = {
            "session_id": uuid4(),
            "turn_id": uuid4(),
            "request_id": uuid4(),
            "conversation_version": 2,
            "fencing_token": 7,
            "assistant_profile": authority.profile,
        }

        first = await runtime.issue_commit_lease(release, **binding)
        second = await runtime.issue_commit_lease(release, **binding)

        assert second == first
        async with sessions() as session:
            assert (
                await session.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM ai_assistant_release_commit_lease
                        WHERE session_id = :session_id
                          AND turn_id = :turn_id
                          AND fencing_token = :fencing_token
                        """
                    ),
                    binding,
                )
                == 1
            )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_final_trust_fence_rejects_revocation_during_resolution() -> None:
    engine, sessions = db()
    fence = RevokedDuringResolutionFence()
    try:
        await clear_authority_tables(sessions)
        _, document = await seed_initial(sessions, profile="customer-assistant")
        with pytest.raises(ReleasePersistenceError) as captured:
            await resolver(
                sessions,
                document,
                trust_freshness_fence=fence,
            ).resolve(
                activation_id=document["activation_id"],
                expected_candidate_sha256=document["candidate"]["content_sha256"],
                assistant_profile="customer-assistant",
                environment="staging",
            )
        assert captured.value.code is ReleasePersistenceErrorCode.AUTHORITY_CHANGED
        assert fence.scope_ended
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_registry_revocation_during_resolution_fails_closed() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        _, document = await seed_initial(sessions, profile="customer-assistant")
        await seed_trusted_registry(sessions, document)
        model_ref = str(document["candidate"]["artifacts"]["model_deployment"]["ref"])
        registry = RevokingTrustedRegistry(sessions, reference=model_ref)
        authority_resolver = PostgresReleaseAuthorityResolver(
            sessions=sessions,
            digest_reader=BoundedOpaqueArtifactDigestReader(
                registry=registry,
                timeout_seconds=1,
                max_concurrency=8,
            ),
            evidence_verifier=BoundedReleaseEvidenceVerifier(
                registry=registry,
                timeout_seconds=1,
                max_concurrency=8,
            ),
            schema_validator=JsonSchemaReleaseAuthorityValidator(RELEASE_AUTHORITY_SCHEMA),
            required_approval_roles=("release-owner", "security-owner"),
            clock=lambda: NOW,
            trust_freshness_fence=registry,
        )
        with pytest.raises(ReleaseArtifactInfrastructureError):
            await authority_resolver.resolve(
                activation_id=document["activation_id"],
                expected_candidate_sha256=document["candidate"]["content_sha256"],
                assistant_profile="customer-assistant",
                environment="staging",
            )
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper",
    (
        "activation_approval_set",
        "static_safe_envelope",
        "schema_version",
        "transaction_context",
    ),
)
async def test_recomputes_approval_and_static_safe_envelope_digests(
    tamper: str,
) -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, document = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        tampered = deepcopy(document)
        if tamper == "activation_approval_set":
            tampered["approval_set_sha256"] = "0" * 64
        elif tamper == "static_safe_envelope":
            tampered["static_safe_release"]["safe_release_envelope_sha256"] = "0" * 64
        elif tamper == "schema_version":
            tampered["schema_version"] = 2
        else:
            tampered["transaction_context"]["unexpected"] = True
        async with sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    ALTER TABLE ai_assistant_release_activation
                    DISABLE TRIGGER tr_ai_assistant_release_activation_immutable
                    """
                )
            )
            await session.execute(
                text(
                    """
                    UPDATE ai_assistant_release_activation
                    SET canonical_document = CAST(:document AS jsonb)
                    WHERE id = :record_id
                    """
                ),
                {
                    "document": json.dumps(tampered),
                    "record_id": authority.activation_ids[0],
                },
            )
            await session.execute(
                text(
                    """
                    ALTER TABLE ai_assistant_release_activation
                    ENABLE TRIGGER tr_ai_assistant_release_activation_immutable
                    """
                )
            )
        with pytest.raises(ReleasePersistenceError) as captured:
            await resolver(sessions, document).resolve(
                activation_id=document["activation_id"],
                expected_candidate_sha256=document["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert captured.value.code is ReleasePersistenceErrorCode.CANONICAL_DOCUMENT_INVALID
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_resolves_prior_activation_and_rejects_stale_pointer() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, first = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        authority, second = await seed_second(
            sessions,
            authority=authority,
            first=first,
        )
        authority_resolver = resolver(sessions, second, first)

        resolved = await authority_resolver.resolve(
            activation_id=second["activation_id"],
            expected_candidate_sha256=second["candidate"]["content_sha256"],
            assistant_profile=authority.profile,
            environment=authority.environment,
        )
        assert resolved.rollback_target is not None
        assert (
            getattr(resolved.rollback_target, "candidate_id", None)
            == first["candidate"]["candidate_id"]
        )

        with pytest.raises(ReleaseManifestResolutionError) as captured:
            await authority_resolver.resolve(
                activation_id=first["activation_id"],
                expected_candidate_sha256=first["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert captured.value.code == "RELEASE_NOT_ACTIVE"
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_revoke_is_observed_and_restart_recovers_authority() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, document = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        async with sessions() as session:
            prior = await session.scalar(
                text(
                    """
                    SELECT event_sha256 FROM ai_assistant_release_history
                    WHERE assistant_profile = :profile AND sequence = 1
                    """
                ),
                {"profile": authority.profile},
            )
        assert isinstance(prior, str)
        await transition(
            sessions,
            authority=authority,
            sequence=2,
            event_type="revoked",
            from_target=target_values("activation", authority.activation_ids[0]),
            to_target=target_values("static_safe_release", authority.safe_id),
            previous_event_sha256=prior,
            idempotency="resolver-revoke-2",
        )
        with pytest.raises(ReleaseManifestResolutionError) as captured:
            await resolver(sessions, document).resolve(
                activation_id=document["activation_id"],
                expected_candidate_sha256=document["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert captured.value.code == "RELEASE_REVOKED"

        await engine.dispose()
        restarted_engine, restarted_sessions = db()
        try:
            with pytest.raises(ReleaseManifestResolutionError) as restarted:
                await resolver(restarted_sessions, document).resolve(
                    activation_id=document["activation_id"],
                    expected_candidate_sha256=document["candidate"]["content_sha256"],
                    assistant_profile=authority.profile,
                    environment=authority.environment,
                )
            assert restarted.value.code == "RELEASE_REVOKED"
        finally:
            await clear_authority_tables(restarted_sessions)
            await restarted_engine.dispose()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_pointer_change_returns_only_consistent_snapshots() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, first = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        authority, second = await seed_second(
            sessions,
            authority=authority,
            first=first,
        )
        authority_resolver = resolver(sessions, second, first)

        async def resolve_once() -> str:
            try:
                await authority_resolver.resolve(
                    activation_id=second["activation_id"],
                    expected_candidate_sha256=second["candidate"]["content_sha256"],
                    assistant_profile=authority.profile,
                    environment=authority.environment,
                )
                return "active"
            except ReleaseManifestResolutionError as error:
                return error.code
            except ReleasePersistenceError as error:
                return error.code.value

        resolutions = [asyncio.create_task(resolve_once()) for _ in range(12)]
        rollback = asyncio.create_task(
            transition(
                sessions,
                authority=authority,
                sequence=3,
                event_type="rolled_back",
                from_target=target_values(
                    "activation",
                    authority.activation_ids[1],
                ),
                to_target=target_values(
                    "activation",
                    authority.activation_ids[0],
                ),
                previous_event_sha256=str(second["_event_2_sha256"]),
                idempotency="resolver-concurrent-rollback",
            )
        )
        outcomes = await asyncio.gather(*resolutions)
        await rollback

        assert set(outcomes).issubset(
            {
                "active",
                "RELEASE_NOT_ACTIVE",
                "RELEASE_AUTHORITY_CHANGED",
            }
        )
        with pytest.raises(ReleaseManifestResolutionError) as captured:
            await authority_resolver.resolve(
                activation_id=second["activation_id"],
                expected_candidate_sha256=second["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert captured.value.code == "RELEASE_NOT_ACTIVE"
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_revoke_during_external_verification_fails_freshness_compare() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, document = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        registry = GatedArtifactRegistry(artifact_values(document))
        authority_resolver = resolver(
            sessions,
            document,
            artifact_registry=registry,
        )
        resolution = asyncio.create_task(
            authority_resolver.resolve(
                activation_id=document["activation_id"],
                expected_candidate_sha256=document["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        )
        await asyncio.wait_for(registry.started.wait(), timeout=2)
        async with sessions() as session:
            prior = await session.scalar(
                text(
                    """
                    SELECT event_sha256
                    FROM ai_assistant_release_history
                    WHERE assistant_profile = :profile
                      AND environment = :environment
                      AND sequence = 1
                    """
                ),
                {
                    "profile": authority.profile,
                    "environment": authority.environment,
                },
            )
        assert isinstance(prior, str)
        await transition(
            sessions,
            authority=authority,
            sequence=2,
            event_type="revoked",
            from_target=target_values(
                "activation",
                authority.activation_ids[0],
            ),
            to_target=target_values(
                "static_safe_release",
                authority.safe_id,
            ),
            previous_event_sha256=prior,
            idempotency="resolver-toctou-revoke",
        )
        registry.release.set()

        with pytest.raises(ReleasePersistenceError) as captured:
            await resolution
        assert captured.value.code is ReleasePersistenceErrorCode.AUTHORITY_CHANGED
        assert captured.value.retryable is True
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", ("artifact", "gate"))
async def test_prior_rollback_requires_immutable_readiness(
    unavailable: str,
) -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, first = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        authority, second = await seed_second(
            sessions,
            authority=authority,
            first=first,
        )
        values = {
            **artifact_values(first),
            **artifact_values(second),
        }
        if unavailable == "artifact":
            values.pop(first["candidate"]["artifacts"]["model_deployment"]["ref"])
            expected = "ARTIFACT_DIGEST_MISMATCH"
        else:
            values.pop(first["automated_gate"]["evidence_ref"])
            expected = "AUTOMATED_GATE_INVALID"

        with pytest.raises(ReleaseManifestResolutionError) as captured:
            await resolver(
                sessions,
                second,
                first,
                artifact_registry=MemoryArtifactRegistry(values),
            ).resolve(
                activation_id=second["activation_id"],
                expected_candidate_sha256=second["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert captured.value.code == expected
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_prior_rollback_must_still_be_within_its_effective_window() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        expired = release_authority_document()
        expired["expires_at"] = "2026-07-26T05:30:00Z"
        rehash_release_document(expired)
        authority, first = await seed_initial(
            sessions,
            profile="customer-assistant",
            document_override=expired,
        )
        authority, second = await seed_second(
            sessions,
            authority=authority,
            first=first,
        )

        with pytest.raises(ReleaseManifestResolutionError) as captured:
            await resolver(sessions, second, first).resolve(
                activation_id=second["activation_id"],
                expected_candidate_sha256=second["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert captured.value.code == "ROLLBACK_NOT_READY"
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("missing_digest", "authenticity"))
async def test_prior_rollback_requires_live_control_readiness(
    failure: str,
) -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, first = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        authority, second = await seed_second(
            sessions,
            authority=authority,
            first=first,
        )
        values = {
            **artifact_values(first),
            **artifact_values(second),
        }
        evidence_registry: TrustedEvidenceRegistry | None = None
        if failure == "missing_digest":
            values.pop(first["kill_switch_registry_ref"])
        else:
            evidence_registry = RejectingPriorLiveControlEvidenceRegistry(
                first["candidate"]["content_sha256"]
            )

        with pytest.raises(ReleaseManifestResolutionError) as captured:
            await resolver(
                sessions,
                second,
                first,
                artifact_registry=MemoryArtifactRegistry(values),
                evidence_registry=evidence_registry,
            ).resolve(
                activation_id=second["activation_id"],
                expected_candidate_sha256=second["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert captured.value.code == "LIVE_CONTROL_INVALID"
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("missing_artifact", "approval_authenticity"))
async def test_prior_rollback_requires_pinned_static_safe_readiness(
    failure: str,
) -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, first = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        authority, second = await seed_second(
            sessions,
            authority=authority,
            first=first,
        )
        values = {
            **artifact_values(first),
            **artifact_values(second),
        }
        evidence_registry: TrustedEvidenceRegistry | None = None
        if failure == "missing_artifact":
            values.pop(first["static_safe_release"]["template_ref"])
            expected = "STATIC_SAFE_RELEASE_INVALID"
        else:
            evidence_registry = RejectingStaticSafeApprovalEvidenceRegistry()
            expected = "STATIC_SAFE_APPROVAL_INVALID"

        with pytest.raises(ReleaseManifestResolutionError) as captured:
            await resolver(
                sessions,
                second,
                first,
                artifact_registry=MemoryArtifactRegistry(values),
                evidence_registry=evidence_registry,
            ).resolve(
                activation_id=second["activation_id"],
                expected_candidate_sha256=second["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert captured.value.code == expected
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_history_fetch_fails_closed_above_configured_resource_cap() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, first = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        authority, second = await seed_second(
            sessions,
            authority=authority,
            first=first,
        )
        with pytest.raises(ReleasePersistenceError) as captured:
            await resolver(
                sessions,
                second,
                first,
                max_history_events=1,
            ).resolve(
                activation_id=second["activation_id"],
                expected_candidate_sha256=second["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert captured.value.code is ReleasePersistenceErrorCode.HISTORY_LIMIT_EXCEEDED
        assert captured.value.retryable is False
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("missing_digest", "authenticity"))
async def test_promotion_evidence_must_exist_in_trusted_registry(
    failure: str,
) -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, document = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        values = artifact_values(document)
        evidence_registry = None
        if failure == "missing_digest":
            values.pop(document["promotion_evidence_ref"])
        else:
            evidence_registry = RejectingPromotionEvidenceRegistry()
        with pytest.raises(ReleaseManifestResolutionError) as captured:
            await resolver(
                sessions,
                document,
                artifact_registry=MemoryArtifactRegistry(values),
                evidence_registry=evidence_registry,
            ).resolve(
                activation_id=document["activation_id"],
                expected_candidate_sha256=document["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert captured.value.code == "PROMOTION_EVIDENCE_INVALID"
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_resolution_cancellation_propagates_without_background_lookup() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, document = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        blocking = BlockingArtifactRegistry()
        authority_resolver = PostgresReleaseAuthorityResolver(
            sessions=sessions,
            digest_reader=BoundedOpaqueArtifactDigestReader(
                registry=blocking,
                timeout_seconds=30,
                max_concurrency=1,
            ),
            evidence_verifier=BoundedReleaseEvidenceVerifier(
                registry=AcceptingEvidenceRegistry(),
                timeout_seconds=1,
                max_concurrency=1,
            ),
            schema_validator=JsonSchemaReleaseAuthorityValidator(RELEASE_AUTHORITY_SCHEMA),
            required_approval_roles=("release-owner", "security-owner"),
            clock=lambda: NOW,
            trust_freshness_fence=AcceptingTrustFence(),
            timeout_seconds=30,
            max_concurrency=1,
        )
        task = asyncio.create_task(
            authority_resolver.resolve(
                activation_id=document["activation_id"],
                expected_candidate_sha256=document["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        )
        await asyncio.wait_for(blocking.started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()


@pytest.mark.asyncio
async def test_wrong_profile_digest_and_tampered_rollback_fail_closed() -> None:
    engine, sessions = db()
    try:
        await clear_authority_tables(sessions)
        authority, first = await seed_initial(
            sessions,
            profile="customer-assistant",
        )
        authority, second = await seed_second(
            sessions,
            authority=authority,
            first=first,
        )
        authority_resolver = resolver(sessions, second, first)

        with pytest.raises(ReleaseManifestResolutionError) as digest_error:
            await authority_resolver.resolve(
                activation_id=second["activation_id"],
                expected_candidate_sha256="0" * 64,
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert digest_error.value.code == "CANDIDATE_DIGEST_MISMATCH"

        with pytest.raises(ReleaseManifestResolutionError) as profile_error:
            await authority_resolver.resolve(
                activation_id=second["activation_id"],
                expected_candidate_sha256=second["candidate"]["content_sha256"],
                assistant_profile="another-profile",
                environment=authority.environment,
            )
        assert profile_error.value.code == "RELEASE_NOT_FOUND"

        with pytest.raises(ReleaseManifestResolutionError) as missing_error:
            await authority_resolver.resolve(
                activation_id="missing-activation",
                expected_candidate_sha256=second["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert missing_error.value.code == "RELEASE_NOT_FOUND"

        tampered = deepcopy(second)
        tampered.pop("_event_2_sha256", None)
        tampered["rollback_target"]["eligible_history_event_sha256"] = "0" * 64
        rehash_release_document(tampered)
        async with sessions() as session, session.begin():
            await session.execute(
                text(
                    """
                    ALTER TABLE ai_assistant_release_activation
                    DISABLE TRIGGER tr_ai_assistant_release_activation_immutable
                    """
                )
            )
            await session.execute(
                text(
                    """
                    UPDATE ai_assistant_release_activation
                    SET canonical_document = CAST(:document AS jsonb)
                    WHERE id = :record_id
                    """
                ),
                {
                    "document": json.dumps(tampered),
                    "record_id": authority.activation_ids[-1],
                },
            )
            await session.execute(
                text(
                    """
                    ALTER TABLE ai_assistant_release_activation
                    ENABLE TRIGGER tr_ai_assistant_release_activation_immutable
                    """
                )
            )
        with pytest.raises(ReleasePersistenceError) as rollback_error:
            await authority_resolver.resolve(
                activation_id=second["activation_id"],
                expected_candidate_sha256=second["candidate"]["content_sha256"],
                assistant_profile=authority.profile,
                environment=authority.environment,
            )
        assert rollback_error.value.code is ReleasePersistenceErrorCode.ROLLBACK_HISTORY_INVALID
    finally:
        await clear_authority_tables(sessions)
        await engine.dispose()
