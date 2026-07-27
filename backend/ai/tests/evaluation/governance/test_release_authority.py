import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app.modules.governance.domain.release_authority import (
    AssistantReleaseAuthorityTransaction,
    ReleaseAuthorityContractError,
    canonical_sha256,
)

ROOT = Path(__file__).resolve().parents[5]
SCHEMA = json.loads(
    (ROOT / "contracts/ai/ai-release-manifest.schema.json").read_text(encoding="utf-8")
)


class CanonicalSchemaValidator:
    def __init__(self) -> None:
        self.validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())

    def validate(self, document: Mapping[str, Any]) -> None:
        self.validator.validate(dict(document))  # pyright: ignore[reportUnknownMemberType]


def _artifact(reference: str) -> dict[str, str]:
    return {"ref": reference, "sha256": "a" * 64}


def _approval(identifier: str, target: str, character: str) -> dict[str, object]:
    return {
        "approval_id": identifier,
        "authority_role": f"{identifier}-owner",
        "approver_subject": f"subject-{identifier}",
        "approved_at": "2026-07-26T05:00:00Z",
        "evidence_ref": f"approval://{identifier}/1",
        "evidence_sha256": character * 64,
        "target_candidate_sha256": target,
        "assistant_profile": "customer-assistant",
        "environment": "staging",
    }


def _document() -> dict[str, Any]:
    artifacts = {
        "model_deployment": _artifact("model://customer/1"),
        "prompt": _artifact("prompt://customer/1"),
        "output_schema": _artifact("schema://grounded-answer/3"),
        "graph": _artifact("graph://customer/3"),
        "policy": _artifact("policy://customer/3"),
        "validator": _artifact("validator://grounding/3"),
        "knowledge_profile": _artifact("knowledge://customer/1"),
        "retriever": _artifact("retriever://hybrid/1"),
        "embedding_generation_sha256": "a" * 64,
        "dataset_releases": [_artifact("dataset://assistant-gold/1")],
        "tool_registry": _artifact("tools://customer-read-only/1"),
        "evaluator": _artifact("evaluator://assistant-release/3"),
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
        "assistantProfile": "customer-assistant",
        "candidateId": "candidate-1",
        "environment": "staging",
        "gatePolicyRevision": "release-gate-v3",
        "gatePolicySha256": "4" * 64,
        "requestedBySubject": "subject-proposer",
    }
    candidate_sha = canonical_sha256(candidate_projection)
    approvals = [
        _approval("release", candidate_sha, "a"),
        _approval("security", candidate_sha, "b"),
    ]
    approvals.sort(key=lambda item: str(item["approval_id"]))
    approval_set_sha = canonical_sha256(approvals)

    safe_core = {
        "safe_release_id": "safe-1",
        "safe_release_ref": "safe-release://customer/1",
        "template_ref": "prompt://static-safe/1",
        "template_sha256": "b" * 64,
        "response_policy_ref": "policy://static-safe/1",
        "response_policy_sha256": "c" * 64,
        "assistant_profile": "customer-assistant",
        "environment": "staging",
        "effective_at": "2026-07-26T04:00:00Z",
        "expires_at": "2027-07-26T04:00:00Z",
    }
    safe_core_sha = canonical_sha256(safe_core)
    safe_approvals = [
        {
            "approval_id": identifier,
            "authority_role": role,
            "approver_subject": f"subject-{identifier}",
            "approved_at": "2026-07-26T04:00:00Z",
            "evidence_ref": f"approval://{identifier}/1",
            "evidence_sha256": character * 64,
            "target_safe_release_core_sha256": safe_core_sha,
        }
        for identifier, role, character in (
            ("safe-release", "release-owner", "d"),
            ("safe-security", "security-owner", "e"),
        )
    ]
    safe_approvals.sort(key=lambda item: str(item["approval_id"]))
    safe_approval_sha = canonical_sha256(safe_approvals)
    safe_envelope_sha = canonical_sha256(
        {
            "approval_set_sha256": safe_approval_sha,
            "safe_release_core_sha256": safe_core_sha,
        }
    )
    static_safe = {
        **safe_core,
        "safe_release_core_sha256": safe_core_sha,
        "approval_set_sha256": safe_approval_sha,
        "safe_release_envelope_sha256": safe_envelope_sha,
        "approvals": safe_approvals,
    }
    safe_target = {
        "kind": "static_safe_release",
        "safe_release_id": "safe-1",
        "safe_release_ref": "safe-release://customer/1",
        "safe_release_core_sha256": safe_core_sha,
        "approval_set_sha256": safe_approval_sha,
        "safe_release_envelope_sha256": safe_envelope_sha,
        "assistant_profile": "customer-assistant",
        "environment": "staging",
    }
    transaction = {
        "idempotency_key": "activate-1",
        "correlation_id": "correlation-1",
        "actor_subject": "subject-release",
        "reason": "Promote evaluated customer assistant release.",
    }
    activation_core = {
        "approval_set_sha256": approval_set_sha,
        "automated_gate_evidence_sha256": "f" * 64,
        "candidate_sha256": candidate_sha,
        "effective_at": "2026-07-26T05:00:00Z",
        "expires_at": "2026-08-02T05:00:00Z",
        "kill_switch_registry_ref": "tools://kill-switch/1",
        "kill_switch_registry_sha256": "1" * 64,
        "rollback_drill_evidence_ref": "drill://customer/1",
        "rollback_drill_evidence_sha256": "2" * 64,
        "rollback_target": safe_target,
        "static_safe_release_envelope_sha256": safe_envelope_sha,
    }
    activation_core_sha = canonical_sha256(activation_core)
    activation_envelope_sha = canonical_sha256(
        {
            "activation_core_sha256": activation_core_sha,
            "promotion_evidence_ref": "approval://promotion/1",
            "promotion_evidence_sha256": "3" * 64,
            "promotion_evidence_target_sha256": activation_core_sha,
        }
    )
    activation_target = {
        "kind": "activation",
        "activation_id": "activation-1",
        "activation_envelope_sha256": activation_envelope_sha,
        "candidate_id": "candidate-1",
        "candidate_sha256": candidate_sha,
        "assistant_profile": "customer-assistant",
        "environment": "staging",
    }
    history = {
        "event_ref": "history://customer/1",
        "sequence": 1,
        "previous_event_sha256": None,
        "event_type": "activated",
        "from_target": safe_target,
        "to_target": activation_target,
        "activation_envelope_sha256": activation_envelope_sha,
        "pointer_revision": 2,
        "transaction_context": transaction,
        "occurred_at": "2026-07-26T05:00:01Z",
    }
    history["event_sha256"] = canonical_sha256(history)
    outbox = {
        "event_ref": "outbox://customer/1",
        "schema_version": 1,
        "aggregate_id": "customer-assistant:staging",
        "assistant_profile": "customer-assistant",
        "environment": "staging",
        "correlation_id": "correlation-1",
        "idempotency_key": "activate-1",
        "event_type": "activated",
        "pointer_revision": 2,
        "history_event_sha256": history["event_sha256"],
        "occurred_at": history["occurred_at"],
    }
    outbox["payload_sha256"] = canonical_sha256(outbox)
    return {
        "schema_version": 3,
        "activation_id": "activation-1",
        "candidate": {
            "candidate_id": "candidate-1",
            "content_sha256": candidate_sha,
            "assistant_profile": "customer-assistant",
            "environment": "staging",
            "requested_by_subject": "subject-proposer",
            "gate_policy_revision": "release-gate-v3",
            "gate_policy_sha256": "4" * 64,
            "artifacts": artifacts,
        },
        "automated_gate": {
            "evidence_ref": "evaluation://assistant-release/1",
            "evidence_sha256": "f" * 64,
            "target_candidate_sha256": candidate_sha,
            "assistant_profile": "customer-assistant",
            "environment": "staging",
            "gate_policy_revision": "release-gate-v3",
            "gate_policy_sha256": "4" * 64,
        },
        "approvals": approvals,
        "effective_at": activation_core["effective_at"],
        "expires_at": activation_core["expires_at"],
        "rollback_target": safe_target,
        "kill_switch_registry_ref": activation_core["kill_switch_registry_ref"],
        "kill_switch_registry_sha256": activation_core["kill_switch_registry_sha256"],
        "rollback_drill_evidence_ref": activation_core["rollback_drill_evidence_ref"],
        "rollback_drill_evidence_sha256": activation_core[
            "rollback_drill_evidence_sha256"
        ],
        "promotion_evidence_ref": "approval://promotion/1",
        "promotion_evidence_sha256": "3" * 64,
        "promotion_evidence_target_sha256": activation_core_sha,
        "approval_set_sha256": approval_set_sha,
        "activation_core_sha256": activation_core_sha,
        "activation_envelope_sha256": activation_envelope_sha,
        "digest_projection_version": 1,
        "static_safe_release": static_safe,
        "transaction_context": transaction,
        "pointer_transition": {
            "operation": "activate",
            "assistant_profile": "customer-assistant",
            "environment": "staging",
            "from_target": safe_target,
            "to_target": activation_target,
            "expected_pointer_revision": 1,
            "result_pointer_revision": 2,
        },
        "activation_event": history,
        "outbox_event": outbox,
    }


def _authority(
    document: dict[str, Any] | None = None,
) -> AssistantReleaseAuthorityTransaction:
    return AssistantReleaseAuthorityTransaction(
        document or _document(),
        schema_validator=CanonicalSchemaValidator(),
    )


def _rehash(source: dict[str, Any]) -> None:
    core = {
        "approval_set_sha256": source["approval_set_sha256"],
        "automated_gate_evidence_sha256": source["automated_gate"][
            "evidence_sha256"
        ],
        "candidate_sha256": source["candidate"]["content_sha256"],
        "effective_at": source["effective_at"],
        "expires_at": source["expires_at"],
        "kill_switch_registry_ref": source["kill_switch_registry_ref"],
        "kill_switch_registry_sha256": source["kill_switch_registry_sha256"],
        "rollback_drill_evidence_ref": source["rollback_drill_evidence_ref"],
        "rollback_drill_evidence_sha256": source[
            "rollback_drill_evidence_sha256"
        ],
        "rollback_target": source["rollback_target"],
        "static_safe_release_envelope_sha256": source["static_safe_release"][
            "safe_release_envelope_sha256"
        ],
    }
    source["activation_core_sha256"] = canonical_sha256(core)
    source["promotion_evidence_target_sha256"] = source["activation_core_sha256"]
    source["activation_envelope_sha256"] = canonical_sha256(
        {
            "activation_core_sha256": source["activation_core_sha256"],
            "promotion_evidence_ref": source["promotion_evidence_ref"],
            "promotion_evidence_sha256": source["promotion_evidence_sha256"],
            "promotion_evidence_target_sha256": source[
                "promotion_evidence_target_sha256"
            ],
        }
    )
    target = (
        source["pointer_transition"]["to_target"]
        if source["pointer_transition"]["operation"] == "activate"
        else source["pointer_transition"]["from_target"]
    )
    if target["kind"] == "activation":
        target["activation_envelope_sha256"] = source["activation_envelope_sha256"]
    source["activation_event"]["activation_envelope_sha256"] = source[
        "activation_envelope_sha256"
    ]
    source["activation_event"]["event_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in source["activation_event"].items()
            if key != "event_sha256"
        }
    )
    source["outbox_event"]["history_event_sha256"] = source["activation_event"][
        "event_sha256"
    ]
    source["outbox_event"]["event_type"] = source["activation_event"]["event_type"]
    source["outbox_event"]["pointer_revision"] = source["activation_event"][
        "pointer_revision"
    ]
    source["outbox_event"]["occurred_at"] = source["activation_event"]["occurred_at"]
    source["outbox_event"]["payload_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in source["outbox_event"].items()
            if key != "payload_sha256"
        }
    )


def test_release_authority_accepts_schema_valid_golden_transaction() -> None:
    source = _document()

    assert _authority(source).to_document() == source
    assert {
        "candidate": source["candidate"]["content_sha256"],
        "approval_set": source["approval_set_sha256"],
        "safe_core": source["static_safe_release"]["safe_release_core_sha256"],
        "safe_approval_set": source["static_safe_release"]["approval_set_sha256"],
        "safe_envelope": source["static_safe_release"][
            "safe_release_envelope_sha256"
        ],
        "activation_core": source["activation_core_sha256"],
        "activation_envelope": source["activation_envelope_sha256"],
        "history": source["activation_event"]["event_sha256"],
        "outbox": source["outbox_event"]["payload_sha256"],
    } == {
        "candidate": (
            "906bc2f2dbaa35ec21bfe0cab598594050cde650306f92a324216644f729d762"
        ),
        "approval_set": (
            "eb384edfed7ddbc2b68e101a505d7c68eac1f9b17ff0c7654809cb8614618508"
        ),
        "safe_core": (
            "68d6cf3294fb1d5ab18cd2a24678a764db3c41b9009ef589179fa48bdd9454e3"
        ),
        "safe_approval_set": (
            "d957c1bf23813954080e5092588ddb150dd2c50667c74b2db3ccc40720aa2616"
        ),
        "safe_envelope": (
            "63751535a96a85cc4192a0c8b93e75e508f39e00d6139c19cf30eaafd1eb749e"
        ),
        "activation_core": (
            "8ba12c84f8748d29dad5d70e3140968d6814c746eac5acd091b8a0a02f592e75"
        ),
        "activation_envelope": (
            "26cd98f82b771088a42e8431fe01e1cca5c0b0abf51d99d8e6e73c4bc3518a06"
        ),
        "history": (
            "879547e33c85b56d981bfeac83c0a1317ef2bd351fca32c15d8ac47fa688f1bf"
        ),
        "outbox": (
            "c628e7e35e481229ed6a59d7f7c29f779a31d6fcd72167ab688187a9fe8badcf"
        ),
    }


def test_release_authority_is_immutable_after_validation() -> None:
    source = _document()
    authority = _authority(source)

    source["schema_version"] = 2
    returned = authority.to_document()
    returned["schema_version"] = 1

    assert authority.to_document()["schema_version"] == 3


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("activation_id",), "activation-tampered"),
        (("candidate", "artifacts", "prompt", "sha256"), "0" * 64),
        (("automated_gate", "assistant_profile"), "other-assistant"),
        (("pointer_transition", "result_pointer_revision"), 4),
        (("activation_event", "event_type"), "revoked"),
        (("outbox_event", "history_event_sha256"), "0" * 64),
        (("static_safe_release", "template_sha256"), "0" * 64),
        (("promotion_evidence_target_sha256",), "0" * 64),
    ],
)
def test_release_authority_rejects_tampered_bindings(
    path: tuple[str, ...], value: object
) -> None:
    source = _document()
    target: dict[str, Any] = source
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = value

    with pytest.raises(ReleaseAuthorityContractError):
        _authority(source)


def test_release_authority_requires_structural_schema_validation() -> None:
    source = _document()
    del source["candidate"]["artifacts"]

    with pytest.raises(ReleaseAuthorityContractError, match="schema validation failed"):
        _authority(source)


def test_release_authority_accepts_supersede_and_exact_prior_rollback() -> None:
    source = _document()
    prior = {
        "kind": "activation",
        "activation_id": "activation-prior",
        "activation_envelope_sha256": "5" * 64,
        "candidate_id": "candidate-prior",
        "candidate_sha256": "6" * 64,
        "assistant_profile": "customer-assistant",
        "environment": "staging",
    }
    source["rollback_target"] = {
        "kind": "prior_activation",
        **{key: value for key, value in prior.items() if key != "kind"},
        "eligible_history_event_ref": "history://customer/prior",
        "eligible_history_event_sha256": "7" * 64,
    }
    source["pointer_transition"].update(
        {
            "operation": "activate",
            "from_target": prior,
        }
    )
    source["activation_event"].update(
        {
            "event_type": "superseded",
            "from_target": prior,
        }
    )
    _rehash(source)

    assert _authority(source).to_document() == source

    current = deepcopy(source["pointer_transition"]["to_target"])
    rollback = source["rollback_target"]
    target = {
        "kind": "activation",
        "activation_id": rollback["activation_id"],
        "activation_envelope_sha256": rollback["activation_envelope_sha256"],
        "candidate_id": rollback["candidate_id"],
        "candidate_sha256": rollback["candidate_sha256"],
        "assistant_profile": rollback["assistant_profile"],
        "environment": rollback["environment"],
    }
    source["pointer_transition"].update(
        {
            "operation": "rollback",
            "from_target": current,
            "to_target": target,
        }
    )
    source["activation_event"].update(
        {
            "event_type": "rolled_back",
            "from_target": current,
            "to_target": source["pointer_transition"]["to_target"],
            "sequence": 2,
            "previous_event_sha256": "a" * 64,
        }
    )
    source["outbox_event"]["event_type"] = "rolled_back"
    _rehash(source)

    assert _authority(source).to_document() == source


def test_release_authority_accepts_revoke_to_embedded_static_safe() -> None:
    source = _document()
    current = deepcopy(source["pointer_transition"]["to_target"])
    safe_target = deepcopy(source["pointer_transition"]["from_target"])
    source["pointer_transition"].update(
        {
            "operation": "revoke",
            "from_target": current,
            "to_target": safe_target,
        }
    )
    source["activation_event"].update(
        {
            "event_type": "revoked",
            "from_target": current,
            "to_target": safe_target,
            "sequence": 2,
            "previous_event_sha256": "a" * 64,
        }
    )
    _rehash(source)

    assert _authority(source).to_document() == source


def test_release_authority_rejects_invalid_windows() -> None:
    source = _document()
    source["expires_at"] = source["effective_at"]
    _rehash(source)

    with pytest.raises(ReleaseAuthorityContractError, match="window"):
        _authority(source)


def test_release_authority_requires_static_safe_window_to_cover_activation() -> None:
    source = _document()
    source["static_safe_release"]["expires_at"] = "2026-07-27T05:00:00Z"
    safe = source["static_safe_release"]
    safe_core = {
        key: value
        for key, value in safe.items()
        if key
        not in {
            "safe_release_core_sha256",
            "approval_set_sha256",
            "safe_release_envelope_sha256",
            "approvals",
        }
    }
    safe["safe_release_core_sha256"] = canonical_sha256(safe_core)
    for approval in safe["approvals"]:
        approval["target_safe_release_core_sha256"] = safe["safe_release_core_sha256"]
    safe["approval_set_sha256"] = canonical_sha256(safe["approvals"])
    safe["safe_release_envelope_sha256"] = canonical_sha256(
        {
            "approval_set_sha256": safe["approval_set_sha256"],
            "safe_release_core_sha256": safe["safe_release_core_sha256"],
        }
    )
    source["pointer_transition"]["from_target"].update(
        {
            key: safe[key]
            for key in (
                "safe_release_core_sha256",
                "approval_set_sha256",
                "safe_release_envelope_sha256",
            )
        }
    )
    source["activation_event"]["from_target"] = deepcopy(
        source["pointer_transition"]["from_target"]
    )
    _rehash(source)

    with pytest.raises(ReleaseAuthorityContractError, match="cover"):
        _authority(source)


def test_release_authority_rejects_transition_before_approval() -> None:
    source = _document()
    source["activation_event"]["occurred_at"] = "2026-07-26T03:00:00Z"
    source["outbox_event"]["occurred_at"] = source["activation_event"]["occurred_at"]
    source["activation_event"]["event_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in source["activation_event"].items()
            if key != "event_sha256"
        }
    )
    source["outbox_event"]["history_event_sha256"] = source["activation_event"][
        "event_sha256"
    ]
    source["outbox_event"]["payload_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in source["outbox_event"].items()
            if key != "payload_sha256"
        }
    )

    with pytest.raises(ReleaseAuthorityContractError, match="before its approvals"):
        _authority(source)


def test_canonical_hash_rejects_floats_and_unsafe_integers() -> None:
    with pytest.raises(ReleaseAuthorityContractError):
        canonical_sha256({"value": 1.0})
    with pytest.raises(ReleaseAuthorityContractError):
        canonical_sha256({"value": 9_007_199_254_740_992})
