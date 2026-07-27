import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.governance.domain.release_authority import canonical_sha256

AUTHORITY_TABLES = (
    "ai_assistant_release_commit_lease",
    "ai_assistant_release_outbox_delivery",
    "ai_assistant_release_outbox_event",
    "ai_assistant_release_pointer",
    "ai_assistant_release_history",
    "ai_assistant_release_activation",
    "ai_assistant_static_safe_release",
    "ai_assistant_release_candidate",
)


@dataclass(frozen=True, slots=True)
class SeededAuthority:
    profile: str
    environment: str
    safe_id: UUID
    activation_ids: tuple[UUID, ...]


def target_values(
    kind: str,
    identifier: UUID,
) -> Mapping[str, UUID | None | str]:
    return {
        "kind": kind,
        "activation_id": identifier if kind == "activation" else None,
        "safe_id": identifier if kind == "static_safe_release" else None,
    }


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


async def _target_document(
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
    if not isinstance(document, dict):
        raise AssertionError("release target projection is missing")
    return cast(Mapping[str, object], document)


async def _canonical_json_digest(
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
    if not isinstance(value, str):
        raise AssertionError("canonical release digest is missing")
    return value


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
) -> str:
    async with sessions() as session, session.begin():
        from_document = await _target_document(
            session,
            authority=authority,
            target=from_target,
        )
        to_document = await _target_document(
            session,
            authority=authority,
            target=to_target,
        )
        envelope_source = from_document if event_type == "revoked" else to_document
        activation_envelope = envelope_source.get("activation_envelope_sha256")
        if not isinstance(activation_envelope, str):
            raise AssertionError("activation envelope is missing")
        history_id = uuid4()
        history_event_ref = f"history://integration/{history_id.hex}"
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
        event_sha256 = await _canonical_json_digest(session, unsigned_document)
        event_document = {**unsigned_document, "event_sha256": event_sha256}
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
                "idempotency_sha256": _digest(idempotency),
                "occurred_at": occurred_at,
                "transaction_context": json.dumps(transaction_context),
                "document": json.dumps(event_document),
            },
        )
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
                RETURNING revision
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
        if pointer_update.scalar_one_or_none() is None:
            raise RuntimeError("stale assistant release pointer")
        outbox_id = uuid4()
        payload_sha256 = await _canonical_json_digest(session, event_document)
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
                "event_type": f"assistant.release.{event_type}",
                "event_sha256": event_sha256,
                "payload_sha256": payload_sha256,
                "idempotency_sha256": _digest(f"outbox:{idempotency}"),
                "payload": json.dumps(event_document),
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
    return event_sha256


def _artifact(reference: str, character: str = "a") -> dict[str, str]:
    return {"ref": reference, "sha256": character * 64}


def rehash_release_document(source: dict[str, Any]) -> None:
    gate = cast(Mapping[str, Any], source["automated_gate"])
    candidate = cast(Mapping[str, Any], source["candidate"])
    safe = cast(Mapping[str, Any], source["static_safe_release"])
    core = {
        "approval_set_sha256": source["approval_set_sha256"],
        "automated_gate_evidence_sha256": gate["evidence_sha256"],
        "candidate_sha256": candidate["content_sha256"],
        "effective_at": source["effective_at"],
        "expires_at": source["expires_at"],
        "kill_switch_registry_ref": source["kill_switch_registry_ref"],
        "kill_switch_registry_sha256": source["kill_switch_registry_sha256"],
        "rollback_drill_evidence_ref": source["rollback_drill_evidence_ref"],
        "rollback_drill_evidence_sha256": source["rollback_drill_evidence_sha256"],
        "rollback_target": source["rollback_target"],
        "static_safe_release_envelope_sha256": safe["safe_release_envelope_sha256"],
    }
    source["activation_core_sha256"] = canonical_sha256(core)
    source["promotion_evidence_target_sha256"] = source["activation_core_sha256"]
    source["activation_envelope_sha256"] = canonical_sha256(
        {
            "activation_core_sha256": source["activation_core_sha256"],
            "promotion_evidence_ref": source["promotion_evidence_ref"],
            "promotion_evidence_sha256": source["promotion_evidence_sha256"],
            "promotion_evidence_target_sha256": source["promotion_evidence_target_sha256"],
        }
    )
    activation_target = {
        "kind": "activation",
        "activation_id": source["activation_id"],
        "activation_envelope_sha256": source["activation_envelope_sha256"],
        "candidate_id": candidate["candidate_id"],
        "candidate_sha256": candidate["content_sha256"],
        "assistant_profile": candidate["assistant_profile"],
        "environment": candidate["environment"],
    }
    pointer = cast(dict[str, Any], source["pointer_transition"])
    if pointer["operation"] == "activate":
        pointer["to_target"] = activation_target
    else:
        pointer["from_target"] = activation_target
    event = cast(dict[str, Any], source["activation_event"])
    event["from_target"] = pointer["from_target"]
    event["to_target"] = pointer["to_target"]
    event["pointer_revision"] = pointer["result_pointer_revision"]
    event["transaction_context"] = source["transaction_context"]
    event["activation_envelope_sha256"] = source["activation_envelope_sha256"]
    event["event_sha256"] = canonical_sha256(
        {key: value for key, value in event.items() if key != "event_sha256"}
    )
    outbox = cast(dict[str, Any], source["outbox_event"])
    transaction = cast(Mapping[str, Any], source["transaction_context"])
    outbox["correlation_id"] = transaction["correlation_id"]
    outbox["idempotency_key"] = transaction["idempotency_key"]
    outbox["event_type"] = event["event_type"]
    outbox["pointer_revision"] = event["pointer_revision"]
    outbox["history_event_sha256"] = event["event_sha256"]
    outbox["occurred_at"] = event["occurred_at"]
    outbox["payload_sha256"] = canonical_sha256(
        {key: value for key, value in outbox.items() if key != "payload_sha256"}
    )


def release_authority_document() -> dict[str, Any]:
    profile = "customer-assistant"
    environment = "staging"
    artifacts: dict[str, Any] = {
        "model_deployment": _artifact("model://customer/1"),
        "prompt": _artifact("prompt://customer/1", "b"),
        "output_schema": _artifact("schema://grounded-answer/3", "c"),
        "graph": _artifact("graph://customer/3", "d"),
        "policy": _artifact("policy://customer/3", "e"),
        "validator": _artifact("validator://grounding/3", "f"),
        "knowledge_profile": _artifact("knowledge://customer/1", "1"),
        "retriever": _artifact("retriever://hybrid/1", "2"),
        "embedding_generation_sha256": "3" * 64,
        "dataset_releases": [_artifact("dataset://assistant-gold/1", "4")],
        "tool_registry": _artifact("tools://customer-read-only/1", "5"),
        "evaluator": _artifact("evaluator://assistant-release/3", "6"),
    }
    candidate_projection = {
        "artifacts": {
            "embeddingGenerationDigest": artifacts["embedding_generation_sha256"],
            "modelDeployment": artifacts["model_deployment"],
            "prompt": artifacts["prompt"],
            "outputSchema": artifacts["output_schema"],
            "graph": artifacts["graph"],
            "policy": artifacts["policy"],
            "validator": artifacts["validator"],
            "knowledgeProfile": artifacts["knowledge_profile"],
            "retriever": artifacts["retriever"],
            "datasets": artifacts["dataset_releases"],
            "toolRegistry": artifacts["tool_registry"],
            "evaluator": artifacts["evaluator"],
        },
        "assistantProfile": profile,
        "candidateId": "candidate-1",
        "environment": environment,
        "gatePolicyRevision": "release-gate-v3",
        "gatePolicySha256": "4" * 64,
        "requestedBySubject": "subject-proposer",
    }
    candidate_sha256 = canonical_sha256(candidate_projection)
    approvals: list[dict[str, Any]] = [
        {
            "approval_id": identifier,
            "authority_role": role,
            "approver_subject": f"subject-{identifier}",
            "approved_at": "2026-07-26T05:00:00Z",
            "evidence_ref": f"approval://{identifier}/1",
            "evidence_sha256": character * 64,
            "target_candidate_sha256": candidate_sha256,
            "assistant_profile": profile,
            "environment": environment,
        }
        for identifier, role, character in (
            ("release", "release-owner", "7"),
            ("security", "security-owner", "8"),
        )
    ]
    approvals.sort(key=lambda item: str(item["approval_id"]))
    safe_core: dict[str, Any] = {
        "safe_release_id": "safe-1",
        "safe_release_ref": "safe-release://customer/1",
        "template_ref": "prompt://static-safe/1",
        "template_sha256": "9" * 64,
        "response_policy_ref": "policy://static-safe/1",
        "response_policy_sha256": "a" * 64,
        "assistant_profile": profile,
        "environment": environment,
        "effective_at": "2026-07-26T04:00:00Z",
        "expires_at": "2027-07-26T04:00:00Z",
    }
    safe_core_sha256 = canonical_sha256(safe_core)
    safe_approvals: list[dict[str, Any]] = [
        {
            "approval_id": identifier,
            "authority_role": role,
            "approver_subject": f"subject-{identifier}",
            "approved_at": "2026-07-26T04:00:00Z",
            "evidence_ref": f"approval://{identifier}/1",
            "evidence_sha256": character * 64,
            "target_safe_release_core_sha256": safe_core_sha256,
        }
        for identifier, role, character in (
            ("safe-release", "release-owner", "b"),
            ("safe-security", "security-owner", "c"),
        )
    ]
    safe_approvals.sort(key=lambda item: str(item["approval_id"]))
    safe_approval_set_sha256 = canonical_sha256(safe_approvals)
    safe_envelope_sha256 = canonical_sha256(
        {
            "approval_set_sha256": safe_approval_set_sha256,
            "safe_release_core_sha256": safe_core_sha256,
        }
    )
    static_safe_release = {
        **safe_core,
        "safe_release_core_sha256": safe_core_sha256,
        "approval_set_sha256": safe_approval_set_sha256,
        "safe_release_envelope_sha256": safe_envelope_sha256,
        "approvals": safe_approvals,
    }
    safe_target = {
        "kind": "static_safe_release",
        "safe_release_id": "safe-1",
        "safe_release_ref": "safe-release://customer/1",
        "safe_release_core_sha256": safe_core_sha256,
        "approval_set_sha256": safe_approval_set_sha256,
        "safe_release_envelope_sha256": safe_envelope_sha256,
        "assistant_profile": profile,
        "environment": environment,
    }
    document: dict[str, Any] = {
        "schema_version": 3,
        "activation_id": "activation-1",
        "candidate": {
            "candidate_id": "candidate-1",
            "content_sha256": candidate_sha256,
            "assistant_profile": profile,
            "environment": environment,
            "requested_by_subject": "subject-proposer",
            "gate_policy_revision": "release-gate-v3",
            "gate_policy_sha256": "4" * 64,
            "artifacts": artifacts,
        },
        "automated_gate": {
            "evidence_ref": "evaluation://assistant-release/1",
            "evidence_sha256": "d" * 64,
            "target_candidate_sha256": candidate_sha256,
            "assistant_profile": profile,
            "environment": environment,
            "gate_policy_revision": "release-gate-v3",
            "gate_policy_sha256": "4" * 64,
        },
        "approvals": approvals,
        "approval_set_sha256": canonical_sha256(approvals),
        "effective_at": "2026-07-26T05:00:00Z",
        "expires_at": "2026-08-02T05:00:00Z",
        "rollback_target": safe_target,
        "kill_switch_registry_ref": "tools://kill-switch/1",
        "kill_switch_registry_sha256": "e" * 64,
        "rollback_drill_evidence_ref": "drill://customer/1",
        "rollback_drill_evidence_sha256": "f" * 64,
        "promotion_evidence_ref": "approval://promotion/1",
        "promotion_evidence_sha256": "1" * 64,
        "promotion_evidence_target_sha256": "0" * 64,
        "activation_core_sha256": "0" * 64,
        "activation_envelope_sha256": "0" * 64,
        "digest_projection_version": 1,
        "static_safe_release": static_safe_release,
        "transaction_context": {
            "idempotency_key": "activate-1",
            "correlation_id": "correlation-1",
            "actor_subject": "subject-release",
            "reason": "Promote evaluated customer assistant release.",
        },
        "pointer_transition": {
            "operation": "activate",
            "assistant_profile": profile,
            "environment": environment,
            "from_target": safe_target,
            "to_target": {},
            "expected_pointer_revision": 0,
            "result_pointer_revision": 1,
        },
        "activation_event": {
            "event_ref": "history://customer/1",
            "sequence": 1,
            "previous_event_sha256": None,
            "event_type": "activated",
            "from_target": safe_target,
            "to_target": {},
            "activation_envelope_sha256": "0" * 64,
            "pointer_revision": 1,
            "transaction_context": {},
            "occurred_at": "2026-07-26T05:00:01Z",
            "event_sha256": "0" * 64,
        },
        "outbox_event": {
            "event_ref": "outbox://customer/1",
            "schema_version": 1,
            "aggregate_id": f"{profile}:{environment}",
            "assistant_profile": profile,
            "environment": environment,
            "correlation_id": "correlation-1",
            "idempotency_key": "activate-1",
            "event_type": "activated",
            "pointer_revision": 1,
            "history_event_sha256": "0" * 64,
            "occurred_at": "2026-07-26T05:00:01Z",
            "payload_sha256": "0" * 64,
        },
    }
    rehash_release_document(document)
    return deepcopy(document)
