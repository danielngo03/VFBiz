from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import Literal, Protocol, Self
from urllib.parse import urlsplit

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9._-]{2,127}$")
_SYNTHETIC_AUTHORITY = "synthetic-browser-lab-qualification"
_SYNTHETIC_DISPOSITION = "candidate-for-loopback-browser-lab"
_ALLOWED_USE = "authenticated-staging-browser-lab-only"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_sha256(*values: str) -> None:
    if any(not _is_sha256(value) for value in values):
        raise ValueError("lab evidence identities must use SHA-256 hex")


def _require_identifier(*values: str) -> None:
    if any(not _IDENTIFIER.fullmatch(value) for value in values):
        raise ValueError("lab identity must be a bounded opaque identifier")


def _validate_loopback_origin(value: str) -> None:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("lab origin must use an explicit valid port") from error
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("authenticated staging lab origins must be HTTP loopback")


@dataclass(frozen=True, slots=True)
class SyntheticLabReleaseBinding:
    """Digest-only release binding that can never become a product release."""

    candidate_sha256: str
    runtime_composition_sha256: str
    generation_deployment_sha256: str
    embedding_deployment_sha256: str
    prompt_sha256: str
    policy_sha256: str
    retriever_sha256: str
    synthetic_knowledge_sha256: str
    evaluation_evidence_sha256: str
    generation_provider: Literal["vertex"] = "vertex"
    embedding_provider: Literal["vertex"] = "vertex"
    knowledge_kind: Literal["synthetic-fact-free"] = "synthetic-fact-free"
    required_evaluation_authority_class: str = _SYNTHETIC_AUTHORITY
    technical_disposition: str = _SYNTHETIC_DISPOSITION
    allowed_use: str = _ALLOWED_USE
    human_approved: bool = False
    training_eligible: bool = False
    release_eligible: bool = False
    production_retriever_eligible: bool = False

    def __post_init__(self) -> None:
        _require_sha256(
            self.candidate_sha256,
            self.runtime_composition_sha256,
            self.generation_deployment_sha256,
            self.embedding_deployment_sha256,
            self.prompt_sha256,
            self.policy_sha256,
            self.retriever_sha256,
            self.synthetic_knowledge_sha256,
            self.evaluation_evidence_sha256,
        )
        if (
            self.generation_provider != "vertex"
            or self.embedding_provider != "vertex"
            or self.knowledge_kind != "synthetic-fact-free"
            or self.required_evaluation_authority_class != _SYNTHETIC_AUTHORITY
            or self.technical_disposition != _SYNTHETIC_DISPOSITION
            or self.allowed_use != _ALLOWED_USE
            or self.human_approved
            or self.training_eligible
            or self.release_eligible
            or self.production_retriever_eligible
        ):
            raise ValueError("browser lab release binding must remain synthetic-only")

    def as_dict(self) -> dict[str, object]:
        return {
            "allowedUse": self.allowed_use,
            "candidateSha256": self.candidate_sha256,
            "embeddingDeploymentSha256": self.embedding_deployment_sha256,
            "embeddingProvider": self.embedding_provider,
            "evaluationEvidenceSha256": self.evaluation_evidence_sha256,
            "generationDeploymentSha256": self.generation_deployment_sha256,
            "generationProvider": self.generation_provider,
            "humanApproved": self.human_approved,
            "policySha256": self.policy_sha256,
            "productionRetrieverEligible": self.production_retriever_eligible,
            "promptSha256": self.prompt_sha256,
            "releaseEligible": self.release_eligible,
            "retrieverSha256": self.retriever_sha256,
            "runtimeCompositionSha256": self.runtime_composition_sha256,
            "syntheticKnowledgeSha256": self.synthetic_knowledge_sha256,
            "knowledgeKind": self.knowledge_kind,
            "requiredEvaluationAuthorityClass": (self.required_evaluation_authority_class),
            "technicalDisposition": self.technical_disposition,
            "trainingEligible": self.training_eligible,
        }

    @property
    def content_sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    environment: Literal["development", "test"]
    project_id: str
    runtime_composition_sha256: str

    def __post_init__(self) -> None:
        _require_identifier(self.project_id)
        _require_sha256(self.runtime_composition_sha256)


@dataclass(frozen=True, slots=True)
class AcceptedSyntheticEvidence:
    evidence_sha256: str
    target_release_binding_sha256: str
    authority_class: Literal["synthetic-browser-lab-qualification"]
    independent_review_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(
            self.evidence_sha256,
            self.target_release_binding_sha256,
            self.independent_review_sha256,
        )


class PacketAuthorityRegistry(Protocol):
    def is_pinned(self, packet_sha256: str) -> bool: ...


class RuntimeIdentityProvider(Protocol):
    def current(self) -> RuntimeIdentity: ...


class TrustedClock(Protocol):
    def now(self) -> datetime: ...


class SyntheticEvidenceAuthority(Protocol):
    def resolve(self, evidence_sha256: str) -> AcceptedSyntheticEvidence | None: ...


class LabActivationControl(Protocol):
    """Atomically enforce live kill-switch state and one-time activation."""

    def consume_if_enabled(
        self,
        *,
        packet_sha256: str,
        nonce_sha256: str,
        registry_id: str,
        generation: int,
        control_sha256: str,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class VerifiedLabActivation:
    packet_sha256: str
    release_binding_sha256: str
    runtime_composition_sha256: str
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_sha256(
            self.packet_sha256,
            self.release_binding_sha256,
            self.runtime_composition_sha256,
        )
        if self.expires_at.tzinfo is None:
            raise ValueError("verified lab activation expiry must include a timezone")


class LabActivationFailureCode(StrEnum):
    PACKET_NOT_PINNED = "packet_not_pinned"
    PACKET_EXPIRED = "packet_expired"
    RUNTIME_MISMATCH = "runtime_mismatch"
    EVIDENCE_INVALID = "evidence_invalid"
    KILL_SWITCH_OR_REPLAY_REJECTED = "kill_switch_or_replay_rejected"


class LabActivationFailure(RuntimeError):
    def __init__(self, code: LabActivationFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True, slots=True)
class AuthenticatedStagingLabPacket:
    """Content-free activation request; external authorities decide acceptance."""

    packet_id: str
    issued_at: datetime
    expires_at: datetime
    portal_origin: str
    api_origin: str
    release: SyntheticLabReleaseBinding
    runtime_project_id: str
    contract_parity_sha256: str
    authorization_negative_tests_sha256: str
    activation_nonce_sha256: str
    kill_switch_registry_id: str
    kill_switch_generation: int
    kill_switch_control_sha256: str
    packet_sha256: str
    environment: Literal["development", "test"] = "development"
    chat_mode: Literal["authenticated-staging"] = "authenticated-staging"
    assistant_profile: Literal["authenticated_customer"] = "authenticated_customer"
    transport: Literal["typed-sse-v1"] = "typed-sse-v1"
    anonymous_allowed: bool = False
    workforce_allowed: bool = False
    public_capability_allowed: bool = False
    public_release_eligible: bool = False

    def __post_init__(self) -> None:
        _require_identifier(
            self.packet_id,
            self.runtime_project_id,
            self.kill_switch_registry_id,
        )
        _validate_loopback_origin(self.portal_origin)
        _validate_loopback_origin(self.api_origin)
        _require_sha256(
            self.contract_parity_sha256,
            self.authorization_negative_tests_sha256,
            self.activation_nonce_sha256,
            self.kill_switch_control_sha256,
            self.packet_sha256,
        )
        if self.kill_switch_generation < 1:
            raise ValueError("kill-switch generation must be positive")
        if self.portal_origin == self.api_origin:
            raise ValueError("portal and API lab origins must be distinct")
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("lab packet timestamps must include a timezone")
        lifetime = self.expires_at - self.issued_at
        if lifetime <= timedelta(0) or lifetime > timedelta(hours=4):
            raise ValueError("lab packet lifetime must be positive and at most four hours")
        if (
            self.environment not in {"development", "test"}
            or self.chat_mode != "authenticated-staging"
            or self.assistant_profile != "authenticated_customer"
            or self.transport != "typed-sse-v1"
            or self.anonymous_allowed
            or self.workforce_allowed
            or self.public_capability_allowed
            or self.public_release_eligible
        ):
            raise ValueError("lab packet cannot grant public or workforce Chat authority")
        if self.packet_sha256 != _digest(self.unsigned_document()):
            raise ValueError("authenticated staging lab packet digest mismatch")

    @classmethod
    def issue(
        cls,
        *,
        packet_id: str,
        issued_at: datetime,
        expires_at: datetime,
        portal_origin: str,
        api_origin: str,
        release: SyntheticLabReleaseBinding,
        runtime_project_id: str,
        contract_parity_sha256: str,
        authorization_negative_tests_sha256: str,
        activation_nonce_sha256: str,
        kill_switch_registry_id: str,
        kill_switch_generation: int,
        kill_switch_control_sha256: str,
        environment: Literal["development", "test"] = "development",
    ) -> Self:
        unsigned = cls._unsigned_document(
            packet_id=packet_id,
            issued_at=issued_at,
            expires_at=expires_at,
            portal_origin=portal_origin,
            api_origin=api_origin,
            release=release,
            runtime_project_id=runtime_project_id,
            contract_parity_sha256=contract_parity_sha256,
            authorization_negative_tests_sha256=(authorization_negative_tests_sha256),
            activation_nonce_sha256=activation_nonce_sha256,
            kill_switch_registry_id=kill_switch_registry_id,
            kill_switch_generation=kill_switch_generation,
            kill_switch_control_sha256=kill_switch_control_sha256,
            environment=environment,
        )
        return cls(
            packet_id=packet_id,
            issued_at=issued_at,
            expires_at=expires_at,
            portal_origin=portal_origin,
            api_origin=api_origin,
            release=release,
            runtime_project_id=runtime_project_id,
            contract_parity_sha256=contract_parity_sha256,
            authorization_negative_tests_sha256=authorization_negative_tests_sha256,
            activation_nonce_sha256=activation_nonce_sha256,
            kill_switch_registry_id=kill_switch_registry_id,
            kill_switch_generation=kill_switch_generation,
            kill_switch_control_sha256=kill_switch_control_sha256,
            packet_sha256=_digest(unsigned),
            environment=environment,
        )

    def unsigned_document(self) -> dict[str, object]:
        return self._unsigned_document(
            packet_id=self.packet_id,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
            portal_origin=self.portal_origin,
            api_origin=self.api_origin,
            release=self.release,
            runtime_project_id=self.runtime_project_id,
            contract_parity_sha256=self.contract_parity_sha256,
            authorization_negative_tests_sha256=(self.authorization_negative_tests_sha256),
            activation_nonce_sha256=self.activation_nonce_sha256,
            kill_switch_registry_id=self.kill_switch_registry_id,
            kill_switch_generation=self.kill_switch_generation,
            kill_switch_control_sha256=self.kill_switch_control_sha256,
            environment=self.environment,
        )

    def as_dict(self) -> dict[str, object]:
        return {**self.unsigned_document(), "packetSha256": self.packet_sha256}

    @staticmethod
    def _unsigned_document(
        *,
        packet_id: str,
        issued_at: datetime,
        expires_at: datetime,
        portal_origin: str,
        api_origin: str,
        release: SyntheticLabReleaseBinding,
        runtime_project_id: str,
        contract_parity_sha256: str,
        authorization_negative_tests_sha256: str,
        activation_nonce_sha256: str,
        kill_switch_registry_id: str,
        kill_switch_generation: int,
        kill_switch_control_sha256: str,
        environment: str,
    ) -> dict[str, object]:
        return {
            "anonymousAllowed": False,
            "apiOrigin": api_origin,
            "assistantProfile": "authenticated_customer",
            "activationNonceSha256": activation_nonce_sha256,
            "authorizationNegativeTestsSha256": (authorization_negative_tests_sha256),
            "chatMode": "authenticated-staging",
            "contractParitySha256": contract_parity_sha256,
            "environment": environment,
            "expiresAt": expires_at.astimezone(UTC).isoformat(),
            "issuedAt": issued_at.astimezone(UTC).isoformat(),
            "killSwitchControlSha256": kill_switch_control_sha256,
            "killSwitchGeneration": kill_switch_generation,
            "killSwitchRegistryId": kill_switch_registry_id,
            "packetId": packet_id,
            "portalOrigin": portal_origin,
            "publicCapabilityAllowed": False,
            "publicReleaseEligible": False,
            "release": release.as_dict(),
            "runtimeProjectId": runtime_project_id,
            "schemaVersion": 1,
            "transport": "typed-sse-v1",
            "workforceAllowed": False,
        }


class AuthenticatedStagingLabVerifier:
    """Resolve external trust before allowing one browser-lab activation.

    The returned receipt is not message-dispatch authority. Every Chat request
    must still pass the API's verified customer guard and live kill switch.
    """

    def __init__(
        self,
        *,
        packet_registry: PacketAuthorityRegistry,
        runtime_identity: RuntimeIdentityProvider,
        clock: TrustedClock,
        synthetic_evidence: SyntheticEvidenceAuthority,
        activation_control: LabActivationControl,
    ) -> None:
        self._packet_registry = packet_registry
        self._runtime_identity = runtime_identity
        self._clock = clock
        self._synthetic_evidence = synthetic_evidence
        self._activation_control = activation_control

    def authorize_activation(
        self,
        packet: AuthenticatedStagingLabPacket,
    ) -> VerifiedLabActivation:
        observed_at = self._clock.now()
        if observed_at.tzinfo is None:
            raise ValueError("trusted clock must return a timezone-aware timestamp")
        if not self._packet_registry.is_pinned(packet.packet_sha256):
            raise LabActivationFailure(LabActivationFailureCode.PACKET_NOT_PINNED)
        if not packet.issued_at <= observed_at < packet.expires_at:
            raise LabActivationFailure(LabActivationFailureCode.PACKET_EXPIRED)

        runtime = self._runtime_identity.current()
        if (
            runtime.environment != packet.environment
            or runtime.project_id != packet.runtime_project_id
            or runtime.runtime_composition_sha256 != packet.release.runtime_composition_sha256
        ):
            raise LabActivationFailure(LabActivationFailureCode.RUNTIME_MISMATCH)

        evidence = self._synthetic_evidence.resolve(packet.release.evaluation_evidence_sha256)
        if (
            evidence is None
            or evidence.evidence_sha256 != packet.release.evaluation_evidence_sha256
            or evidence.target_release_binding_sha256 != packet.release.content_sha256
            or evidence.authority_class != _SYNTHETIC_AUTHORITY
        ):
            raise LabActivationFailure(LabActivationFailureCode.EVIDENCE_INVALID)

        if not self._activation_control.consume_if_enabled(
            packet_sha256=packet.packet_sha256,
            nonce_sha256=packet.activation_nonce_sha256,
            registry_id=packet.kill_switch_registry_id,
            generation=packet.kill_switch_generation,
            control_sha256=packet.kill_switch_control_sha256,
        ):
            raise LabActivationFailure(LabActivationFailureCode.KILL_SWITCH_OR_REPLAY_REJECTED)

        return VerifiedLabActivation(
            packet_sha256=packet.packet_sha256,
            release_binding_sha256=packet.release.content_sha256,
            runtime_composition_sha256=runtime.runtime_composition_sha256,
            expires_at=packet.expires_at,
        )
