from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.infrastructure.observability.authenticated_staging_lab import (
    AuthenticatedStagingLabPacket,
    LabActivationFailure,
    LabActivationFailureCode,
    RuntimeIdentity,
    SyntheticLabReleaseBinding,
)
from app.infrastructure.observability.authenticated_staging_lab_runtime import (
    AuthenticatedStagingLabAdapterError,
    AuthenticatedStagingLabRuntimeConfig,
    LabActivationControlSeed,
    LabControlDisableStatus,
    PinnedJsonPacketRegistry,
    PinnedJsonSyntheticEvidenceAuthority,
    SqliteLabActivationControl,
    build_authenticated_staging_lab_verifier,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _release() -> SyntheticLabReleaseBinding:
    return SyntheticLabReleaseBinding(
        candidate_sha256=_sha("candidate"),
        runtime_composition_sha256=_sha("runtime"),
        generation_deployment_sha256=_sha("generation"),
        embedding_deployment_sha256=_sha("embedding"),
        prompt_sha256=_sha("prompt"),
        policy_sha256=_sha("policy"),
        retriever_sha256=_sha("retriever"),
        synthetic_knowledge_sha256=_sha("synthetic-knowledge"),
        evaluation_evidence_sha256=_sha("evaluation"),
    )


def _packet(release: SyntheticLabReleaseBinding) -> AuthenticatedStagingLabPacket:
    now = datetime.now(UTC)
    return AuthenticatedStagingLabPacket.issue(
        packet_id="vfbiz-authenticated-lab-runtime-001",
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        portal_origin="http://localhost:3000",
        api_origin="http://127.0.0.1:3001",
        release=release,
        runtime_project_id="vinfast-503003",
        contract_parity_sha256=_sha("contract-parity"),
        authorization_negative_tests_sha256=_sha("auth-negative"),
        activation_nonce_sha256=_sha("activation-nonce"),
        kill_switch_registry_id="vfbiz-lab-kill-switch",
        kill_switch_generation=7,
        kill_switch_control_sha256=_sha("kill-switch-control"),
    )


def _write_json(path: Path, document: dict[str, object]) -> str:
    payload = json.dumps(
        document, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode()
    path.write_bytes(payload)
    path.chmod(0o600)
    return hashlib.sha256(payload).hexdigest()


def _runtime(tmp_path: Path) -> tuple[
    AuthenticatedStagingLabPacket,
    AuthenticatedStagingLabRuntimeConfig,
    LabActivationControlSeed,
]:
    tmp_path.chmod(0o700)
    release = _release()
    packet = _packet(release)
    packet_registry = tmp_path / "packet-registry.json"
    packet_registry_digest = _write_json(
        packet_registry,
        {
            "packet_sha256": packet.packet_sha256,
            "release_eligible": False,
            "schema_revision": "authenticated-staging-packet-registry-v1",
            "status": "pinned",
        },
    )
    evidence_registry = tmp_path / "evidence-registry.json"
    evidence_registry_digest = _write_json(
        evidence_registry,
        {
            "authority_class": "synthetic-browser-lab-qualification",
            "evidence_sha256": release.evaluation_evidence_sha256,
            "human_approved": False,
            "independent_review_sha256": _sha("independent-review"),
            "release_eligible": False,
            "schema_revision": "authenticated-staging-evidence-registry-v1",
            "target_release_binding_sha256": release.content_sha256,
        },
    )
    seed = LabActivationControlSeed(
        registry_id=packet.kill_switch_registry_id,
        generation=packet.kill_switch_generation,
        control_sha256=packet.kill_switch_control_sha256,
    )
    database = tmp_path / "activation.sqlite3"
    SqliteLabActivationControl.provision(database, seed)
    return (
        packet,
        AuthenticatedStagingLabRuntimeConfig(
            packet_registry_path=packet_registry,
            packet_registry_sha256=packet_registry_digest,
            evidence_registry_path=evidence_registry,
            evidence_registry_sha256=evidence_registry_digest,
            activation_database_path=database,
            runtime_identity=RuntimeIdentity(
                environment=packet.environment,
                project_id=packet.runtime_project_id,
                runtime_composition_sha256=release.runtime_composition_sha256,
            ),
        ),
        seed,
    )


def test_composed_runtime_activates_once_and_exposes_no_dispatch_authority(
    tmp_path: Path,
) -> None:
    packet, config, _ = _runtime(tmp_path)
    verifier = build_authenticated_staging_lab_verifier(config)

    receipt = verifier.authorize_activation(packet)

    assert receipt.packet_sha256 == packet.packet_sha256
    assert not hasattr(verifier, "authorize_message_dispatch")
    with pytest.raises(LabActivationFailure) as replay:
        verifier.authorize_activation(packet)
    assert replay.value.code is LabActivationFailureCode.KILL_SWITCH_OR_REPLAY_REJECTED


def test_atomic_control_allows_exactly_one_concurrent_consumer(tmp_path: Path) -> None:
    packet, config, _ = _runtime(tmp_path)
    control = SqliteLabActivationControl(config.activation_database_path)

    def consume(_: int) -> bool:
        return control.consume_if_enabled(
            packet_sha256=packet.packet_sha256,
            nonce_sha256=packet.activation_nonce_sha256,
            registry_id=packet.kill_switch_registry_id,
            generation=packet.kill_switch_generation,
            control_sha256=packet.kill_switch_control_sha256,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(consume, range(16)))

    assert results.count(True) == 1
    assert results.count(False) == 15


def test_kill_switch_disables_without_deleting_history(tmp_path: Path) -> None:
    packet, config, seed = _runtime(tmp_path)
    control = SqliteLabActivationControl(config.activation_database_path)

    assert control.disable(seed) is LabControlDisableStatus.DISABLED
    assert control.disable(seed) is LabControlDisableStatus.ALREADY_DISABLED
    assert (
        control.consume_if_enabled(
            packet_sha256=packet.packet_sha256,
            nonce_sha256=packet.activation_nonce_sha256,
            registry_id=packet.kill_switch_registry_id,
            generation=packet.kill_switch_generation,
            control_sha256=packet.kill_switch_control_sha256,
        )
        is False
    )


def test_registry_tamper_and_extra_content_fail_closed(tmp_path: Path) -> None:
    packet, config, _ = _runtime(tmp_path)
    config.packet_registry_path.write_text("{}", encoding="utf-8")

    with pytest.raises(LabActivationFailure) as rejected:
        build_authenticated_staging_lab_verifier(config).authorize_activation(packet)
    assert rejected.value.code is LabActivationFailureCode.PACKET_NOT_PINNED

    evidence = json.loads(config.evidence_registry_path.read_text(encoding="utf-8"))
    evidence["raw_prompt"] = "forbidden"
    digest = _write_json(config.evidence_registry_path, evidence)
    authority = PinnedJsonSyntheticEvidenceAuthority(
        config.evidence_registry_path, digest
    )
    assert authority.resolve(packet.release.evaluation_evidence_sha256) is None


def test_registry_and_database_symlinks_fail_closed(tmp_path: Path) -> None:
    packet, config, _ = _runtime(tmp_path)
    external_registry = tmp_path / "external.json"
    external_registry.write_bytes(config.packet_registry_path.read_bytes())
    external_registry.chmod(0o600)
    config.packet_registry_path.unlink()
    config.packet_registry_path.symlink_to(external_registry)
    registry = PinnedJsonPacketRegistry(
        config.packet_registry_path, config.packet_registry_sha256
    )
    assert registry.is_pinned(packet.packet_sha256) is False

    external_db = tmp_path / "external.sqlite3"
    config.activation_database_path.rename(external_db)
    config.activation_database_path.symlink_to(external_db)
    control = SqliteLabActivationControl(config.activation_database_path)
    assert (
        control.consume_if_enabled(
            packet_sha256=packet.packet_sha256,
            nonce_sha256=packet.activation_nonce_sha256,
            registry_id=packet.kill_switch_registry_id,
            generation=packet.kill_switch_generation,
            control_sha256=packet.kill_switch_control_sha256,
        )
        is False
    )


def test_provision_requires_new_file_inside_private_directory(tmp_path: Path) -> None:
    tmp_path.chmod(0o755)
    seed = LabActivationControlSeed(
        registry_id="vfbiz-lab-kill-switch",
        generation=1,
        control_sha256=_sha("control"),
    )

    with pytest.raises(AuthenticatedStagingLabAdapterError, match="not private"):
        SqliteLabActivationControl.provision(tmp_path / "activation.sqlite3", seed)


def test_sqlite_question_mark_path_cannot_redirect_to_another_database(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    seed = LabActivationControlSeed(
        registry_id="vfbiz-lab-kill-switch",
        generation=3,
        control_sha256=_sha("question-path-control"),
    )
    enabled_path = tmp_path / "activation.sqlite3"
    SqliteLabActivationControl.provision(enabled_path, seed)
    disabled_path = tmp_path / "activation.sqlite3?decoy=1"
    SqliteLabActivationControl.provision(
        disabled_path,
        LabActivationControlSeed(
            registry_id=seed.registry_id,
            generation=seed.generation,
            control_sha256=seed.control_sha256,
            enabled=False,
        ),
    )
    control = SqliteLabActivationControl(disabled_path)

    assert (
        control.consume_if_enabled(
            packet_sha256=_sha("question-packet"),
            nonce_sha256=_sha("question-nonce"),
            registry_id=seed.registry_id,
            generation=seed.generation,
            control_sha256=seed.control_sha256,
        )
        is False
    )


def test_disable_reports_unknown_state_instead_of_claiming_safe(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    seed = LabActivationControlSeed(
        registry_id="vfbiz-lab-kill-switch",
        generation=1,
        control_sha256=_sha("unknown-state-control"),
    )
    missing = SqliteLabActivationControl(tmp_path / "missing.sqlite3")

    with pytest.raises(AuthenticatedStagingLabAdapterError, match="unsafe"):
        missing.disable(seed)
