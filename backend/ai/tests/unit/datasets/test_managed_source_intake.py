from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.datasets.application.source_intake.models import (
    IntakeOrigin,
    SourceIntakeReceipt,
)
from app.modules.datasets.domain import RegistryInvariantError


def _managed_receipt(**overrides: object) -> SourceIntakeReceipt:
    values: dict[str, object] = {
        "receipt_id": "receipt.managed.vf8",
        "batch_id": "workforce-upload-20260730",
        "origin": IntakeOrigin.MANAGED_UPLOAD,
        "actor_ref": "workforce:user-123",
        "relative_path_token": "uploads/vf8.pdf",
        "original_filename": "HDSD xe VF 8.pdf",
        "media_type": "application/pdf",
        "byte_size": 42,
        "observed_sha256": "a" * 64,
        "storage_uri": "gs://vfbiz-quarantine/aa/object.pdf",
        "document_family_id": "vinfast-car-owner-manual-vf8-vi-vn",
        "taxonomy": {"locale": "vi-VN"},
        "received_at": datetime(2026, 7, 30, tzinfo=UTC),
        "environment": "staging",
    }
    values.update(overrides)
    return SourceIntakeReceipt(**values)  # type: ignore[arg-type]


def test_managed_upload_has_distinct_quarantine_policy() -> None:
    payload = _managed_receipt().contract_payload()

    assert payload["origin"] == "managed-upload"
    assert payload["environment"] == "staging"
    assert payload["allowed_use"] == "quarantine-only"
    assert payload["visibility"] == "workforce-private"
    assert payload["release_eligible"] is False
    assert payload["provenance_status"] == "managed-upload-pending-review"


def test_local_bootstrap_cannot_claim_staging_environment() -> None:
    with pytest.raises(RegistryInvariantError, match="development-only"):
        _managed_receipt(
            origin=IntakeOrigin.LOCAL_BOOTSTRAP,
            environment="staging",
        )
