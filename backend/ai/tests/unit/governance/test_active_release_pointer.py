import pytest

from app.modules.governance.application.active_release_pointer import (
    ActiveReleasePointer,
)

_VALID_SHA256 = "a" * 64


def test_activation_pointer_requires_activation_and_candidate_identity() -> None:
    pointer = ActiveReleasePointer(
        assistant_profile="public_customer",
        environment="test",
        target_kind="activation",
        activation_id="activation-1",
        candidate_sha256=_VALID_SHA256,
        safe_release_id=None,
        envelope_sha256=_VALID_SHA256,
        pointer_revision=1,
    )
    assert pointer.activation_id == "activation-1"
    assert pointer.safe_release_id is None


def test_static_safe_pointer_requires_safe_release_id_only() -> None:
    pointer = ActiveReleasePointer(
        assistant_profile="public_customer",
        environment="test",
        target_kind="static_safe_release",
        activation_id=None,
        candidate_sha256=None,
        safe_release_id="safe-release-1",
        envelope_sha256=_VALID_SHA256,
        pointer_revision=1,
    )
    assert pointer.safe_release_id == "safe-release-1"
    assert pointer.activation_id is None


def test_activation_pointer_rejects_missing_activation_id() -> None:
    with pytest.raises(ValueError, match="activation_id"):
        ActiveReleasePointer(
            assistant_profile="public_customer",
            environment="test",
            target_kind="activation",
            activation_id=None,
            candidate_sha256=_VALID_SHA256,
            safe_release_id=None,
            envelope_sha256=_VALID_SHA256,
            pointer_revision=1,
        )


def test_activation_pointer_rejects_stray_safe_release_id() -> None:
    with pytest.raises(ValueError, match="activation_id"):
        ActiveReleasePointer(
            assistant_profile="public_customer",
            environment="test",
            target_kind="activation",
            activation_id="activation-1",
            candidate_sha256=_VALID_SHA256,
            safe_release_id="safe-release-1",
            envelope_sha256=_VALID_SHA256,
            pointer_revision=1,
        )


def test_static_safe_pointer_rejects_missing_safe_release_id() -> None:
    with pytest.raises(ValueError, match="safe_release_id"):
        ActiveReleasePointer(
            assistant_profile="public_customer",
            environment="test",
            target_kind="static_safe_release",
            activation_id=None,
            candidate_sha256=None,
            safe_release_id=None,
            envelope_sha256=_VALID_SHA256,
            pointer_revision=1,
        )


def test_static_safe_pointer_rejects_stray_activation_id() -> None:
    with pytest.raises(ValueError, match="safe_release_id"):
        ActiveReleasePointer(
            assistant_profile="public_customer",
            environment="test",
            target_kind="static_safe_release",
            activation_id="activation-1",
            candidate_sha256=None,
            safe_release_id="safe-release-1",
            envelope_sha256=_VALID_SHA256,
            pointer_revision=1,
        )


@pytest.mark.parametrize(
    "envelope_sha256",
    ["", "not-hex" * 8, "a" * 63, "a" * 65, "A" * 64],
)
def test_rejects_malformed_envelope_digest(envelope_sha256: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        ActiveReleasePointer(
            assistant_profile="public_customer",
            environment="test",
            target_kind="activation",
            activation_id="activation-1",
            candidate_sha256=_VALID_SHA256,
            safe_release_id=None,
            envelope_sha256=envelope_sha256,
            pointer_revision=1,
        )


def test_rejects_negative_pointer_revision() -> None:
    with pytest.raises(ValueError, match="pointer_revision"):
        ActiveReleasePointer(
            assistant_profile="public_customer",
            environment="test",
            target_kind="activation",
            activation_id="activation-1",
            candidate_sha256=_VALID_SHA256,
            safe_release_id=None,
            envelope_sha256=_VALID_SHA256,
            pointer_revision=-1,
        )


def test_activation_pointer_rejects_malformed_candidate_digest() -> None:
    with pytest.raises(ValueError, match="candidate_sha256"):
        ActiveReleasePointer(
            assistant_profile="public_customer",
            environment="test",
            target_kind="activation",
            activation_id="activation-1",
            candidate_sha256="A" * 64,
            safe_release_id=None,
            envelope_sha256=_VALID_SHA256,
            pointer_revision=1,
        )
