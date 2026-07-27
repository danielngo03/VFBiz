import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Protocol, cast

_EVENT_BY_TRANSITION = {
    ("activate", "static_safe_release", "activation"): "activated",
    ("activate", "activation", "activation"): "superseded",
    ("revoke", "activation", "static_safe_release"): "revoked",
    ("rollback", "activation", "activation"): "rolled_back",
}
_TARGET_KINDS_BY_OPERATION = {
    "activate": frozenset(
        {
            ("static_safe_release", "activation"),
            ("activation", "activation"),
        }
    ),
    "revoke": frozenset({("activation", "static_safe_release")}),
    "rollback": frozenset({("activation", "activation")}),
}
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


class ReleaseAuthorityContractError(ValueError):
    """Raised when a release-authority transaction is not authoritative."""


class ReleaseAuthoritySchemaValidator(Protocol):
    """Port implemented by a Draft 2020-12 validator compiled from canonical schema."""

    def validate(self, document: Mapping[str, Any]) -> None: ...


def _assert_canonical_types(value: object) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_INTEGER:
            raise ReleaseAuthorityContractError("canonical integer exceeds safe range")
        return
    if isinstance(value, list):
        for item in cast(list[object], value):
            _assert_canonical_types(item)
        return
    if isinstance(value, Mapping):
        for key, item in cast(Mapping[object, object], value).items():
            if not isinstance(key, str):
                raise ReleaseAuthorityContractError("canonical keys must be strings")
            _assert_canonical_types(item)
        return
    raise ReleaseAuthorityContractError("canonical projection contains unsupported type")


def canonical_sha256(value: object) -> str:
    """Hash the contract's string/integer-only RFC-8785-compatible projection."""
    _assert_canonical_types(value)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(encoded).hexdigest()


def _without(source: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in source.items() if key not in keys}


def _require_digest(actual: object, projection: object, field: str) -> None:
    if actual != canonical_sha256(projection):
        raise ReleaseAuthorityContractError(f"{field} does not match canonical projection")


def _object(source: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = source.get(field)
    if not isinstance(value, Mapping):
        raise ReleaseAuthorityContractError(f"{field} must be an object")
    return cast(Mapping[str, Any], value)


def _approval_set(approvals: object) -> list[dict[str, Any]]:
    if not isinstance(approvals, list) or not approvals:
        raise ReleaseAuthorityContractError("approval set must be non-empty")
    typed = cast(list[object], approvals)
    records = [dict(cast(Mapping[str, Any], item)) for item in typed if isinstance(item, Mapping)]
    if len(records) != len(typed):
        raise ReleaseAuthorityContractError("approval records must be objects")
    records.sort(key=lambda record: str(record["approval_id"]))
    if len({record["approval_id"] for record in records}) != len(records):
        raise ReleaseAuthorityContractError("approval IDs must be unique")
    return records


def _target_scope(target: object) -> tuple[object, object]:
    if not isinstance(target, Mapping):
        raise ReleaseAuthorityContractError("authority target must be an object")
    typed = cast(Mapping[str, Any], target)
    return typed.get("assistant_profile"), typed.get("environment")


def _target_kind(target: object) -> object:
    if not isinstance(target, Mapping):
        return None
    return cast(Mapping[str, Any], target).get("kind")


def _parse_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ReleaseAuthorityContractError(f"{field} must be a timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ReleaseAuthorityContractError(f"{field} must include timezone")
    return parsed


def _candidate_content_sha256(candidate: Mapping[str, Any]) -> str:
    artifacts = _object(candidate, "artifacts")
    datasets = cast(list[Mapping[str, Any]], artifacts["dataset_releases"])
    projection = {
        "artifacts": {
            "embeddingGenerationDigest": artifacts["embedding_generation_sha256"],
            "modelDeployment": deepcopy(artifacts["model_deployment"]),
            "prompt": deepcopy(artifacts["prompt"]),
            "outputSchema": deepcopy(artifacts["output_schema"]),
            "graph": deepcopy(artifacts["graph"]),
            "policy": deepcopy(artifacts["policy"]),
            "validator": deepcopy(artifacts["validator"]),
            "knowledgeProfile": deepcopy(artifacts["knowledge_profile"]),
            "retriever": deepcopy(artifacts["retriever"]),
            "datasets": [deepcopy(item) for item in datasets],
            "toolRegistry": deepcopy(artifacts["tool_registry"]),
            "evaluator": deepcopy(artifacts["evaluator"]),
        },
        "assistantProfile": candidate["assistant_profile"],
        "candidateId": candidate["candidate_id"],
        "environment": candidate["environment"],
        "gatePolicyRevision": candidate["gate_policy_revision"],
        "gatePolicySha256": candidate["gate_policy_sha256"],
        "requestedBySubject": candidate["requested_by_subject"],
    }
    return canonical_sha256(projection)


def _rollback_matches_target(rollback: Mapping[str, Any], target: Mapping[str, Any]) -> bool:
    if rollback["kind"] == "prior_activation" and target["kind"] == "activation":
        fields = (
            ("activation_id", "activation_id"),
            ("activation_envelope_sha256", "activation_envelope_sha256"),
            ("candidate_id", "candidate_id"),
            ("candidate_sha256", "candidate_sha256"),
            ("assistant_profile", "assistant_profile"),
            ("environment", "environment"),
        )
        return all(rollback[left] == target[right] for left, right in fields)
    if rollback["kind"] == target["kind"] == "static_safe_release":
        fields = (
            "safe_release_id",
            "safe_release_ref",
            "safe_release_core_sha256",
            "approval_set_sha256",
            "safe_release_envelope_sha256",
            "assistant_profile",
            "environment",
        )
        return all(rollback[field] == target[field] for field in fields)
    return False


def _activation_matches_target(
    payload: Mapping[str, Any],
    candidate: Mapping[str, Any],
    target: Mapping[str, Any],
) -> bool:
    return target["kind"] == "activation" and all(
        (
            target["activation_id"] == payload["activation_id"],
            target["activation_envelope_sha256"] == payload["activation_envelope_sha256"],
            target["candidate_id"] == candidate["candidate_id"],
            target["candidate_sha256"] == candidate["content_sha256"],
        )
    )


def _static_safe_matches_target(static_safe: Mapping[str, Any], target: Mapping[str, Any]) -> bool:
    if target["kind"] != "static_safe_release":
        return False
    fields = (
        "safe_release_id",
        "safe_release_ref",
        "safe_release_core_sha256",
        "approval_set_sha256",
        "safe_release_envelope_sha256",
        "assistant_profile",
        "environment",
    )
    return all(static_safe[field] == target[field] for field in fields)


@dataclass(frozen=True, slots=True, init=False)
class AssistantReleaseAuthorityTransaction:
    """Immutable canonical-v3 transaction after structural and semantic validation."""

    _canonical_document: bytes

    def __init__(
        self,
        document: Mapping[str, Any],
        *,
        schema_validator: ReleaseAuthoritySchemaValidator,
    ) -> None:
        payload = deepcopy(dict(document))
        _assert_canonical_types(payload)
        try:
            schema_validator.validate(payload)
        except Exception as error:
            raise ReleaseAuthorityContractError(
                f"release authority schema validation failed: {error}"
            ) from error
        self._verify(payload)
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        object.__setattr__(self, "_canonical_document", canonical)

    def to_document(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._canonical_document))

    @staticmethod
    def _verify(payload: Mapping[str, Any]) -> None:
        candidate = _object(payload, "candidate")
        gate = _object(payload, "automated_gate")
        static_safe = _object(payload, "static_safe_release")
        transaction = _object(payload, "transaction_context")
        pointer = _object(payload, "pointer_transition")
        history = _object(payload, "activation_event")
        outbox = _object(payload, "outbox_event")
        profile = candidate["assistant_profile"]
        environment = candidate["environment"]
        candidate_sha = candidate["content_sha256"]
        if candidate_sha != _candidate_content_sha256(candidate):
            raise ReleaseAuthorityContractError("candidate content digest mismatch")

        safe_core = _without(
            static_safe,
            "safe_release_core_sha256",
            "approval_set_sha256",
            "safe_release_envelope_sha256",
            "approvals",
        )
        _require_digest(
            static_safe["safe_release_core_sha256"],
            safe_core,
            "safe_release_core_sha256",
        )
        safe_approvals = _approval_set(static_safe["approvals"])
        if any(
            approval["target_safe_release_core_sha256"] != static_safe["safe_release_core_sha256"]
            for approval in safe_approvals
        ):
            raise ReleaseAuthorityContractError("safe-release approval target mismatch")
        if len({approval["approver_subject"] for approval in safe_approvals}) != len(
            safe_approvals
        ):
            raise ReleaseAuthorityContractError("safe-release approvers must be distinct")
        safe_effective = _parse_timestamp(static_safe["effective_at"], "safe effective_at")
        safe_expires = _parse_timestamp(static_safe["expires_at"], "safe expires_at")
        if safe_expires <= safe_effective:
            raise ReleaseAuthorityContractError("safe-release window is invalid")
        if any(
            _parse_timestamp(approval["approved_at"], "safe approval") > safe_effective
            for approval in safe_approvals
        ):
            raise ReleaseAuthorityContractError("safe approval occurs after activation")
        _require_digest(
            static_safe["approval_set_sha256"],
            safe_approvals,
            "safe-release approval_set_sha256",
        )
        _require_digest(
            static_safe["safe_release_envelope_sha256"],
            {
                "approval_set_sha256": static_safe["approval_set_sha256"],
                "safe_release_core_sha256": static_safe["safe_release_core_sha256"],
            },
            "safe_release_envelope_sha256",
        )

        approvals = _approval_set(payload["approvals"])
        if any(
            approval["target_candidate_sha256"] != candidate_sha
            or (approval["assistant_profile"], approval["environment"]) != (profile, environment)
            for approval in approvals
        ):
            raise ReleaseAuthorityContractError("activation approval binding mismatch")
        if candidate["requested_by_subject"] in {
            approval["approver_subject"] for approval in approvals
        }:
            raise ReleaseAuthorityContractError("release proposer cannot self-approve")
        if len({approval["approver_subject"] for approval in approvals}) != len(approvals):
            raise ReleaseAuthorityContractError("activation approvers must be distinct")
        effective_at = _parse_timestamp(payload["effective_at"], "effective_at")
        expires_at = _parse_timestamp(payload["expires_at"], "expires_at")
        if expires_at <= effective_at:
            raise ReleaseAuthorityContractError("activation window is invalid")
        if safe_effective > effective_at or safe_expires < expires_at:
            raise ReleaseAuthorityContractError(
                "static-safe release must cover the activation window"
            )
        if any(
            _parse_timestamp(approval["approved_at"], "approval") > effective_at
            for approval in approvals
        ):
            raise ReleaseAuthorityContractError("approval occurs after activation")
        _require_digest(
            payload["approval_set_sha256"],
            approvals,
            "activation approval_set_sha256",
        )
        if (
            gate["target_candidate_sha256"] != candidate_sha
            or (gate["assistant_profile"], gate["environment"]) != (profile, environment)
            or gate["gate_policy_revision"] != candidate["gate_policy_revision"]
            or gate["gate_policy_sha256"] != candidate["gate_policy_sha256"]
        ):
            raise ReleaseAuthorityContractError("automated gate binding mismatch")

        activation_core = {
            "approval_set_sha256": payload["approval_set_sha256"],
            "automated_gate_evidence_sha256": gate["evidence_sha256"],
            "candidate_sha256": candidate_sha,
            "effective_at": payload["effective_at"],
            "expires_at": payload["expires_at"],
            "kill_switch_registry_ref": payload["kill_switch_registry_ref"],
            "kill_switch_registry_sha256": payload["kill_switch_registry_sha256"],
            "rollback_drill_evidence_ref": payload["rollback_drill_evidence_ref"],
            "rollback_drill_evidence_sha256": payload["rollback_drill_evidence_sha256"],
            "rollback_target": deepcopy(payload["rollback_target"]),
            "static_safe_release_envelope_sha256": static_safe["safe_release_envelope_sha256"],
        }
        _require_digest(
            payload["activation_core_sha256"],
            activation_core,
            "activation_core_sha256",
        )
        if payload["promotion_evidence_target_sha256"] != payload["activation_core_sha256"]:
            raise ReleaseAuthorityContractError("promotion evidence target mismatch")
        _require_digest(
            payload["activation_envelope_sha256"],
            {
                "activation_core_sha256": payload["activation_core_sha256"],
                "promotion_evidence_ref": payload["promotion_evidence_ref"],
                "promotion_evidence_sha256": payload["promotion_evidence_sha256"],
                "promotion_evidence_target_sha256": payload["promotion_evidence_target_sha256"],
            },
            "activation_envelope_sha256",
        )

        expected_revision = pointer["expected_pointer_revision"]
        if pointer["result_pointer_revision"] != expected_revision + 1:
            raise ReleaseAuthorityContractError("pointer revision must increment once")
        operation = pointer["operation"]
        from_kind = _target_kind(pointer["from_target"])
        to_kind = _target_kind(pointer["to_target"])
        if not all(isinstance(value, str) for value in (operation, from_kind, to_kind)):
            raise ReleaseAuthorityContractError("pointer transition identity is invalid")
        transition = cast(tuple[str, str, str], (operation, from_kind, to_kind))
        if (transition[1], transition[2]) not in _TARGET_KINDS_BY_OPERATION[operation]:
            raise ReleaseAuthorityContractError("pointer target transition mismatch")
        if history["event_type"] != _EVENT_BY_TRANSITION[transition]:
            raise ReleaseAuthorityContractError("pointer operation/event mismatch")
        if pointer["from_target"] == pointer["to_target"]:
            raise ReleaseAuthorityContractError("authority transition cannot target itself")

        scopes = (
            (profile, environment),
            (pointer["assistant_profile"], pointer["environment"]),
            _target_scope(pointer["from_target"]),
            _target_scope(pointer["to_target"]),
            _target_scope(static_safe),
            _target_scope(history["from_target"]),
            _target_scope(history["to_target"]),
            (outbox["assistant_profile"], outbox["environment"]),
        )
        if len(set(scopes)) != 1:
            raise ReleaseAuthorityContractError("profile/environment binding mismatch")
        if (
            history["from_target"] != pointer["from_target"]
            or history["to_target"] != pointer["to_target"]
            or history["pointer_revision"] != pointer["result_pointer_revision"]
            or history["transaction_context"] != transaction
            or history["activation_envelope_sha256"] != payload["activation_envelope_sha256"]
        ):
            raise ReleaseAuthorityContractError("history/pointer binding mismatch")
        occurred_at = _parse_timestamp(history["occurred_at"], "activation event")
        all_approval_times = [
            *(
                _parse_timestamp(approval["approved_at"], "safe approval")
                for approval in safe_approvals
            ),
            *(_parse_timestamp(approval["approved_at"], "approval") for approval in approvals),
        ]
        if occurred_at < max(all_approval_times):
            raise ReleaseAuthorityContractError("authority transition occurs before its approvals")
        if operation == "activate" and occurred_at < effective_at:
            raise ReleaseAuthorityContractError("activation transition occurs before effective_at")

        from_target = _object(pointer, "from_target")
        to_target = _object(pointer, "to_target")
        authoritative_activation = to_target if operation == "activate" else from_target
        if not _activation_matches_target(payload, candidate, authoritative_activation):
            raise ReleaseAuthorityContractError("activation target identity mismatch")

        rollback = _object(payload, "rollback_target")
        if operation == "activate" and not _rollback_matches_target(rollback, from_target):
            raise ReleaseAuthorityContractError("rollback target identity mismatch")
        if operation == "revoke" and not _static_safe_matches_target(static_safe, to_target):
            raise ReleaseAuthorityContractError(
                "revoke target must be the approved static-safe release"
            )
        if operation == "rollback" and not _rollback_matches_target(rollback, to_target):
            raise ReleaseAuthorityContractError("rollback target identity mismatch")

        sequence = history["sequence"]
        previous = history["previous_event_sha256"]
        if (sequence == 1) != (previous is None):
            raise ReleaseAuthorityContractError("history hash-chain position is invalid")
        _require_digest(
            history["event_sha256"],
            _without(history, "event_sha256"),
            "history event_sha256",
        )
        if (
            outbox["aggregate_id"] != f"{profile}:{environment}"
            or outbox["correlation_id"] != transaction["correlation_id"]
            or outbox["idempotency_key"] != transaction["idempotency_key"]
            or outbox["event_type"] != history["event_type"]
            or outbox["pointer_revision"] != history["pointer_revision"]
            or outbox["history_event_sha256"] != history["event_sha256"]
            or outbox["occurred_at"] != history["occurred_at"]
        ):
            raise ReleaseAuthorityContractError("outbox/history binding mismatch")
        _require_digest(
            outbox["payload_sha256"],
            _without(outbox, "payload_sha256"),
            "outbox payload_sha256",
        )
