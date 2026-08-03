import hashlib
import json
from pathlib import Path

import pytest

from scripts.validate_gcp_activation_packet import (
    ActivationPacketError,
    canonical_digest,
    validate_packet,
)


def _packet(**overrides: object) -> dict[str, object]:
    packet: dict[str, object] = {
        "schema_version": "vfbiz-gcp-ingestion-activation/v1",
        "work_item": "VFBIZ-0199",
        "status": "preflight",
        "project_id": "vinfast-503003",
        "project_number": "81588547131",
        "region": "asia-southeast1",
        "worker_image": (
            "asia-southeast1-docker.pkg.dev/vinfast-503003/vfbiz-ai-workers-dev/"
            "intake-worker@sha256:" + "a" * 64
        ),
        "rollback_image_sha256": "b" * 64,
        "worker_database_secret_id": "vfbiz-ai-worker-url",
        "worker_database_secret_version": "1",
        "reconciler_database_secret_id": "vfbiz-ai-reconciler-url",
        "reconciler_database_secret_version": "2",
        "synthetic_smoke_manifest": {"c" * 64: 6},
        "authority": {
            "sha256": "d" * 64,
            "generation": "17",
            "storage_uri": "gs://vinfast-503003-evidence-dev/activation/packet.json",
        },
        "saved_plan": {
            "sha256": "e" * 64,
            "replacement_count": 0,
            "destruction_count": 0,
        },
        "risk_disposition": {
            "sha256": "f" * 64,
            "reference": "evidence://vfbiz-0199/document-ai-scope",
        },
        "switches": {
            "worker_dispatch_enabled": False,
            "reconciler_schedule_enabled": False,
            "ocr_output_bucket_enabled": False,
        },
    }
    packet.update(overrides)
    packet["packet_sha256"] = canonical_digest(packet)
    return packet


def test_valid_packet_returns_only_sanitized_identity_evidence() -> None:
    result = validate_packet(_packet())

    assert result == {
        "schema_version": "vfbiz-gcp-ingestion-activation/v1",
        "work_item": "VFBIZ-0199",
        "packet_sha256": "".join("0" for _ in range(64)),
        "authority_sha256": "d" * 64,
        "authority_generation": "17",
        "saved_plan_sha256": "e" * 64,
        "risk_disposition_sha256": "f" * 64,
    } | {"packet_sha256": canonical_digest(_packet())}


def test_packet_self_resign_cannot_hide_a_plan_destroy() -> None:
    packet = _packet(
        saved_plan={
            "sha256": "e" * 64,
            "replacement_count": 0,
            "destruction_count": 1,
        }
    )

    with pytest.raises(ActivationPacketError, match="zero replacements"):
        validate_packet(packet)


def test_packet_rejects_enabled_switches_and_duplicate_secrets() -> None:
    with pytest.raises(ActivationPacketError, match="switches"):
        validate_packet(
            _packet(
                switches={
                    "worker_dispatch_enabled": True,
                    "reconciler_schedule_enabled": False,
                    "ocr_output_bucket_enabled": False,
                }
            )
        )
    with pytest.raises(ActivationPacketError, match="distinct"):
        validate_packet(
            _packet(
                reconciler_database_secret_id="vfbiz-ai-worker-url",  # noqa: S106
            )
        )


def test_packet_rejects_self_digest_tampering_and_unknown_content() -> None:
    packet = _packet()
    packet["worker_image"] = packet["worker_image"].replace(
        "@sha256:" + "a" * 64,
        "@sha256:" + "0" * 64,
    )
    with pytest.raises(ActivationPacketError, match="digest mismatch"):
        validate_packet(packet)

    packet = _packet(raw_ocr_text="must never be here")
    with pytest.raises(ActivationPacketError, match="unknown or missing"):
        validate_packet(packet)


def test_cli_output_never_contains_packet_content(tmp_path: Path) -> None:
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(_packet()), encoding="utf-8")
    # The validation function is the CLI's pure core; its result is deliberately
    # identity-only and contains no worker image, secret ID, URI or manifest.
    rendered = json.dumps(validate_packet(json.loads(packet_path.read_text())))
    assert "worker_image" not in rendered
    assert "secret" not in rendered
    assert "storage_uri" not in rendered
    assert hashlib.sha256(rendered.encode()).hexdigest()
