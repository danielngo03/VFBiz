import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast

from app.modules.governance.domain.release_authority import (
    ReleaseAuthorityContractError,
    canonical_sha256,
)

_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "binding_id",
        "target_activation",
        "classifier_artifact",
        "output_schema",
        "routing_policy",
        "classification_stack_sha256",
        "evaluation_evidence",
        "effective_at",
        "expires_at",
        "binding_core_sha256",
        "approval_evidence",
        "binding_envelope_sha256",
    }
)


class SemanticClassifierBindingSchemaValidator(Protocol):
    def validate(self, document: Mapping[str, Any]) -> None: ...


def _object(document: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = document.get(field)
    if not isinstance(value, Mapping):
        raise ReleaseAuthorityContractError(f"{field} must be an object")
    return cast(Mapping[str, Any], value)


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ReleaseAuthorityContractError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReleaseAuthorityContractError(f"{field} must be a timestamp") from error
    if parsed.tzinfo is None:
        raise ReleaseAuthorityContractError(f"{field} must include timezone")
    return parsed


def _require_digest(actual: object, projection: object, field: str) -> None:
    if actual != canonical_sha256(projection):
        raise ReleaseAuthorityContractError(f"{field} mismatch")


@dataclass(frozen=True, slots=True, init=False)
class SemanticClassifierReleaseBinding:
    """Canonical authority required in addition to Assistant Release v3."""

    _canonical_document: bytes

    def __init__(
        self,
        document: Mapping[str, Any],
        *,
        schema_validator: SemanticClassifierBindingSchemaValidator,
    ) -> None:
        payload = deepcopy(dict(document))
        if frozenset(payload) != _TOP_LEVEL_FIELDS:
            raise ReleaseAuthorityContractError(
                "semantic classifier binding fields do not match the canonical contract"
            )
        try:
            schema_validator.validate(payload)
        except Exception as error:
            raise ReleaseAuthorityContractError(
                f"semantic classifier binding schema validation failed: {error}"
            ) from error
        self._verify(payload)
        object.__setattr__(
            self,
            "_canonical_document",
            json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode(),
        )

    @staticmethod
    def _verify(payload: Mapping[str, Any]) -> None:
        classifier = _object(payload, "classifier_artifact")
        output_schema = _object(payload, "output_schema")
        routing_policy = _object(payload, "routing_policy")
        target = _object(payload, "target_activation")
        evaluation = _object(payload, "evaluation_evidence")
        approval = _object(payload, "approval_evidence")
        stack_projection = {
            "classifier_artifact": classifier,
            "output_schema": output_schema,
            "routing_policy": routing_policy,
        }
        _require_digest(
            payload["classification_stack_sha256"],
            stack_projection,
            "classification stack digest",
        )
        stack_sha256 = payload["classification_stack_sha256"]
        if evaluation.get("target_classification_stack_sha256") != stack_sha256:
            raise ReleaseAuthorityContractError("evaluation target mismatch")
        effective_at = _timestamp(payload["effective_at"], "effective_at")
        expires_at = _timestamp(payload["expires_at"], "expires_at")
        evaluation_valid_until = _timestamp(
            evaluation.get("valid_until"),
            "evaluation valid_until",
        )
        if expires_at <= effective_at or evaluation_valid_until < expires_at:
            raise ReleaseAuthorityContractError(
                "semantic classifier binding effective window is invalid"
            )
        core_projection = {
            "schema_version": payload["schema_version"],
            "binding_id": payload["binding_id"],
            "target_activation": target,
            "classification_stack_sha256": stack_sha256,
            "evaluation_evidence": evaluation,
            "effective_at": payload["effective_at"],
            "expires_at": payload["expires_at"],
        }
        _require_digest(
            payload["binding_core_sha256"],
            core_projection,
            "binding core digest",
        )
        core_sha256 = payload["binding_core_sha256"]
        if approval.get("target_binding_core_sha256") != core_sha256:
            raise ReleaseAuthorityContractError("approval target mismatch")
        _require_digest(
            payload["binding_envelope_sha256"],
            {
                "approval_evidence": approval,
                "binding_core_sha256": core_sha256,
            },
            "binding envelope digest",
        )

    def to_document(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._canonical_document))

    @property
    def target_activation_id(self) -> str:
        return str(self.to_document()["target_activation"]["activation_id"])

    @property
    def target_activation_envelope_sha256(self) -> str:
        return str(self.to_document()["target_activation"]["activation_envelope_sha256"])

    @property
    def assistant_profile(self) -> str:
        return str(self.to_document()["target_activation"]["assistant_profile"])

    @property
    def environment(self) -> str:
        return str(self.to_document()["target_activation"]["environment"])

    @property
    def effective_at(self) -> datetime:
        return _timestamp(self.to_document()["effective_at"], "effective_at")

    @property
    def expires_at(self) -> datetime:
        return _timestamp(self.to_document()["expires_at"], "expires_at")

    @property
    def evaluation_valid_until(self) -> datetime:
        return _timestamp(
            self.to_document()["evaluation_evidence"]["valid_until"],
            "evaluation valid_until",
        )

    @property
    def routing_policy_revision(self) -> str:
        return str(self.to_document()["routing_policy"]["revision"])

    @property
    def classifier_artifact_ref(self) -> str:
        return str(self.to_document()["classifier_artifact"]["ref"])

    @property
    def classifier_artifact_sha256(self) -> str:
        return str(self.to_document()["classifier_artifact"]["sha256"])

    @property
    def classifier_revision(self) -> str:
        return str(self.to_document()["classifier_artifact"]["revision"])

    @property
    def output_schema_ref(self) -> str:
        return str(self.to_document()["output_schema"]["ref"])

    @property
    def output_schema_sha256(self) -> str:
        return str(self.to_document()["output_schema"]["sha256"])

    @property
    def output_schema_revision(self) -> str:
        return str(self.to_document()["output_schema"]["revision"])

    @property
    def routing_policy_ref(self) -> str:
        return str(self.to_document()["routing_policy"]["ref"])

    @property
    def routing_policy_sha256(self) -> str:
        return str(self.to_document()["routing_policy"]["sha256"])

    @property
    def evaluation_evidence_ref(self) -> str:
        return str(self.to_document()["evaluation_evidence"]["ref"])

    @property
    def evaluation_evidence_sha256(self) -> str:
        return str(self.to_document()["evaluation_evidence"]["sha256"])

    @property
    def evaluation_suite_revision(self) -> str:
        return str(self.to_document()["evaluation_evidence"]["suite_revision"])

    @property
    def approval_evidence_ref(self) -> str:
        return str(self.to_document()["approval_evidence"]["ref"])

    @property
    def approval_evidence_sha256(self) -> str:
        return str(self.to_document()["approval_evidence"]["sha256"])

    @property
    def binding_envelope_sha256(self) -> str:
        return str(self.to_document()["binding_envelope_sha256"])

    def artifact_digests(self) -> tuple[tuple[str, str], ...]:
        document = self.to_document()
        return tuple(
            (
                str(document[field]["ref"]),
                str(document[field]["sha256"]),
            )
            for field in ("classifier_artifact", "output_schema", "routing_policy")
        )
