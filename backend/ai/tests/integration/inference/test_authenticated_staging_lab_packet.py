from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from app.infrastructure.observability.authenticated_staging_lab import (
    AcceptedSyntheticEvidence,
    AuthenticatedStagingLabPacket,
    AuthenticatedStagingLabVerifier,
    LabActivationFailure,
    LabActivationFailureCode,
    RuntimeIdentity,
    SyntheticLabReleaseBinding,
)


def _sha(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _release(**overrides: object) -> SyntheticLabReleaseBinding:
    values: dict[str, object] = {
        "candidate_sha256": _sha("candidate"),
        "runtime_composition_sha256": _sha("runtime"),
        "generation_deployment_sha256": _sha("generation"),
        "embedding_deployment_sha256": _sha("embedding"),
        "prompt_sha256": _sha("prompt"),
        "policy_sha256": _sha("policy"),
        "retriever_sha256": _sha("retriever"),
        "synthetic_knowledge_sha256": _sha("synthetic-knowledge"),
        "evaluation_evidence_sha256": _sha("evaluation"),
    }
    values.update(overrides)
    return SyntheticLabReleaseBinding(**values)  # type: ignore[arg-type]


def _packet(**overrides: object) -> AuthenticatedStagingLabPacket:
    issued_at = datetime(2026, 8, 1, 1, tzinfo=UTC)
    values: dict[str, object] = {
        "packet_id": "vfbiz-authenticated-lab-001",
        "issued_at": issued_at,
        "expires_at": issued_at + timedelta(hours=2),
        "portal_origin": "http://localhost:3000",
        "api_origin": "http://127.0.0.1:3001",
        "release": _release(),
        "runtime_project_id": "vinfast-503003",
        "contract_parity_sha256": _sha("contract-parity"),
        "authorization_negative_tests_sha256": _sha("auth-negative"),
        "activation_nonce_sha256": _sha("activation-nonce"),
        "kill_switch_registry_id": "vfbiz-lab-kill-switch",
        "kill_switch_generation": 7,
        "kill_switch_control_sha256": _sha("kill-switch-control"),
    }
    values.update(overrides)
    return AuthenticatedStagingLabPacket.issue(**values)  # type: ignore[arg-type]


class _PacketRegistry:
    def __init__(self, packet_sha256: str) -> None:
        self.packet_sha256 = packet_sha256

    def is_pinned(self, packet_sha256: str) -> bool:
        return packet_sha256 == self.packet_sha256


class _RuntimeIdentityProvider:
    def __init__(
        self,
        packet: AuthenticatedStagingLabPacket,
        **overrides: object,
    ) -> None:
        values: dict[str, object] = {
            "environment": packet.environment,
            "project_id": packet.runtime_project_id,
            "runtime_composition_sha256": (packet.release.runtime_composition_sha256),
        }
        values.update(overrides)
        self.identity = RuntimeIdentity(**values)  # type: ignore[arg-type]

    def current(self) -> RuntimeIdentity:
        return self.identity


class _Clock:
    def __init__(self, observed_at: datetime) -> None:
        self.observed_at = observed_at

    def now(self) -> datetime:
        return self.observed_at


class _SyntheticEvidenceAuthority:
    def __init__(
        self,
        packet: AuthenticatedStagingLabPacket,
        *,
        target_sha256: str | None = None,
    ) -> None:
        self.receipt = AcceptedSyntheticEvidence(
            evidence_sha256=packet.release.evaluation_evidence_sha256,
            target_release_binding_sha256=(target_sha256 or packet.release.content_sha256),
            authority_class="synthetic-browser-lab-qualification",
            independent_review_sha256=_sha("independent-review"),
        )

    def resolve(self, evidence_sha256: str) -> AcceptedSyntheticEvidence | None:
        if evidence_sha256 != self.receipt.evidence_sha256:
            return None
        return self.receipt


class _ActivationControl:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.consumed: set[tuple[str, str]] = set()

    def consume_if_enabled(
        self,
        *,
        packet_sha256: str,
        nonce_sha256: str,
        registry_id: str,
        generation: int,
        control_sha256: str,
    ) -> bool:
        assert registry_id == "vfbiz-lab-kill-switch"
        assert generation == 7
        assert control_sha256 == _sha("kill-switch-control")
        key = (packet_sha256, nonce_sha256)
        if not self.enabled or key in self.consumed:
            return False
        self.consumed.add(key)
        return True


def _verifier(
    packet: AuthenticatedStagingLabPacket,
    *,
    registry: _PacketRegistry | None = None,
    runtime: _RuntimeIdentityProvider | None = None,
    clock: _Clock | None = None,
    evidence: _SyntheticEvidenceAuthority | None = None,
    control: _ActivationControl | None = None,
) -> AuthenticatedStagingLabVerifier:
    return AuthenticatedStagingLabVerifier(
        packet_registry=registry or _PacketRegistry(packet.packet_sha256),
        runtime_identity=runtime or _RuntimeIdentityProvider(packet),
        clock=clock or _Clock(packet.issued_at),
        synthetic_evidence=evidence or _SyntheticEvidenceAuthority(packet),
        activation_control=control or _ActivationControl(),
    )


def test_external_authorities_accept_one_synthetic_authenticated_activation() -> None:
    packet = _packet()

    activation = _verifier(packet).authorize_activation(packet)

    assert activation.packet_sha256 == packet.packet_sha256
    assert activation.release_binding_sha256 == packet.release.content_sha256
    assert activation.runtime_composition_sha256 == packet.release.runtime_composition_sha256
    assert packet.release.release_eligible is False
    assert packet.release.production_retriever_eligible is False
    assert packet.release.human_approved is False
    assert packet.anonymous_allowed is False
    assert packet.workforce_allowed is False
    assert packet.public_capability_allowed is False
    assert packet.public_release_eligible is False


def test_live_kill_switch_and_replay_control_fail_closed_atomically() -> None:
    packet = _packet()
    control = _ActivationControl()
    verifier = _verifier(packet, control=control)

    verifier.authorize_activation(packet)
    with pytest.raises(LabActivationFailure) as replay:
        verifier.authorize_activation(packet)
    assert replay.value.code is LabActivationFailureCode.KILL_SWITCH_OR_REPLAY_REJECTED

    fresh_packet = _packet(activation_nonce_sha256=_sha("fresh-nonce"))
    fresh_registry = _PacketRegistry(fresh_packet.packet_sha256)
    control.enabled = False
    with pytest.raises(LabActivationFailure) as disabled:
        _verifier(
            fresh_packet,
            registry=fresh_registry,
            control=control,
        ).authorize_activation(fresh_packet)
    assert disabled.value.code is LabActivationFailureCode.KILL_SWITCH_OR_REPLAY_REJECTED


def test_expiry_is_exclusive_and_packet_cannot_authorize_itself() -> None:
    packet = _packet()
    verifier = _verifier(packet, clock=_Clock(packet.expires_at))

    with pytest.raises(LabActivationFailure) as expired:
        verifier.authorize_activation(packet)
    assert expired.value.code is LabActivationFailureCode.PACKET_EXPIRED


def test_historical_packet_cannot_replay_with_its_caller_selected_issue_time() -> None:
    historical = _packet(
        issued_at=datetime(2020, 1, 1, tzinfo=UTC),
        expires_at=datetime(2020, 1, 1, 1, tzinfo=UTC),
    )
    verifier = _verifier(
        historical,
        clock=_Clock(datetime(2026, 8, 1, tzinfo=UTC)),
    )

    with pytest.raises(LabActivationFailure) as expired:
        verifier.authorize_activation(historical)
    assert expired.value.code is LabActivationFailureCode.PACKET_EXPIRED


def test_trusted_clock_must_be_timezone_aware() -> None:
    packet = _packet()
    verifier = _verifier(packet, clock=_Clock(datetime(2026, 8, 1, 1)))

    with pytest.raises(ValueError, match="timezone"):
        verifier.authorize_activation(packet)


def test_resealed_tampering_is_rejected_by_external_packet_registry() -> None:
    original = _packet()
    tampered = _packet(contract_parity_sha256=_sha("tampered-and-resealed"))
    verifier = _verifier(
        tampered,
        registry=_PacketRegistry(original.packet_sha256),
    )

    with pytest.raises(LabActivationFailure) as rejected:
        verifier.authorize_activation(tampered)
    assert rejected.value.code is LabActivationFailureCode.PACKET_NOT_PINNED


def test_runtime_project_environment_and_composition_are_external_facts() -> None:
    packet = _packet()
    runtime = _RuntimeIdentityProvider(packet, project_id="different-project")

    with pytest.raises(LabActivationFailure) as rejected:
        _verifier(packet, runtime=runtime).authorize_activation(packet)
    assert rejected.value.code is LabActivationFailureCode.RUNTIME_MISMATCH


def test_synthetic_candidate_cannot_self_qualify_without_resolved_evidence() -> None:
    packet = _packet()
    evidence = _SyntheticEvidenceAuthority(
        packet,
        target_sha256=_sha("different-release-binding"),
    )

    with pytest.raises(LabActivationFailure) as rejected:
        _verifier(packet, evidence=evidence).authorize_activation(packet)
    assert rejected.value.code is LabActivationFailureCode.EVIDENCE_INVALID


@pytest.mark.parametrize(
    "origin",
    [
        "https://localhost:3000",
        "http://example.com:3000",
        "http://localhost",
        "http://user:password@localhost:3000",
        "http://localhost:3000/chat",
        "http://localhost:3000/?token=secret",
    ],
)
def test_packet_rejects_non_loopback_or_credential_bearing_origin(origin: str) -> None:
    with pytest.raises(ValueError, match="HTTP loopback"):
        _packet(portal_origin=origin)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_packet_is_impossible_outside_development_or_test(environment: str) -> None:
    with pytest.raises(ValueError, match="public or workforce"):
        _packet(environment=environment)


def test_local_golden_rehearsal_cannot_be_used_as_lab_evaluation_authority() -> None:
    with pytest.raises(ValueError, match="synthetic-only"):
        _release(required_evaluation_authority_class="local-golden-rehearsal")


@pytest.mark.parametrize(
    "override",
    [
        {"human_approved": True},
        {"training_eligible": True},
        {"release_eligible": True},
        {"production_retriever_eligible": True},
        {"allowed_use": "public-release"},
        {"technical_disposition": "accepted-for-public-release"},
    ],
)
def test_release_binding_cannot_self_grant_external_authority(
    override: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="synthetic-only"):
        _release(**override)


def test_packet_detects_post_seal_tampering() -> None:
    packet = _packet()

    with pytest.raises(ValueError, match="digest mismatch"):
        replace(packet, contract_parity_sha256=_sha("tampered"))


def test_packet_exposes_no_parallel_identity_or_message_dispatch_authority() -> None:
    packet = _packet()
    document = _packet().as_dict()
    flattened = " ".join(_walk_scalars(document)).lower().replace("_", "")

    for forbidden in (
        "oidc",
        "jwks",
        "issuer",
        "audience",
        "authorizedparty",
        "promptcontent",
        "completion",
        "customerid",
        "subject",
        "claims",
        "bearer",
        "password",
        "secretkey",
        "scope",
        "principal",
        "token",
        "documenttext",
        "retrievedtext",
    ):
        assert forbidden not in flattened
    assert not hasattr(packet, "authorize_message_dispatch")


def _walk_scalars(value: object) -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for key, child in value.items():
            result.append(str(key))
            result.extend(_walk_scalars(child))
        return result
    if isinstance(value, list):
        result = []
        for child in value:
            result.extend(_walk_scalars(child))
        return result
    return [str(value)]
