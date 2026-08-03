from __future__ import annotations

import fcntl
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.modules.datasets.application.source_intake import (
    IntakeOrigin,
    SourceIntakeReceipt,
)
from app.modules.datasets.domain import RegistryInvariantError, TrustZone
from app.modules.datasets.infrastructure import LocalContentAddressedObjectStore
from scripts.import_local_knowledge import import_corpus


def test_local_pdf_receipt_uses_content_hash_as_revision() -> None:
    receipt = SourceIntakeReceipt(
        receipt_id="batch.document",
        batch_id="batch",
        origin=IntakeOrigin.LOCAL_BOOTSTRAP,
        actor_ref="human:owner",
        relative_path_token="car/user-manual/vf8.pdf",  # noqa: S106
        original_filename="HDSD VF 8.pdf",
        media_type="application/pdf",
        byte_size=8,
        observed_sha256="a" * 64,
        storage_uri=f"file://quarantine/aa/{'a' * 64}.pdf",
        document_family_id="vinfast-car-owner-manual-vf8-vi-vn",
        taxonomy={"locale": "vi-VN"},
        received_at=datetime(2026, 7, 30, tzinfo=UTC),
    )

    payload = receipt.contract_payload()

    assert receipt.content_revision == f"sha256:{'a' * 64}"
    assert payload["origin"] == "local-bootstrap"
    assert payload["release_eligible"] is False
    assert payload["visibility"] == "developer-only"


def test_local_object_store_preserves_pdf_suffix_and_is_idempotent(tmp_path: Path) -> None:
    store = LocalContentAddressedObjectStore(tmp_path / "objects")
    content = b"%PDF-1.7\nsafe\n%%EOF\n"

    first = store.put_stream(
        zone=TrustZone.QUARANTINE,
        stream=io.BytesIO(content),
        media_type="application/pdf",
        max_bytes=1024,
    )
    second = store.put_stream(
        zone=TrustZone.QUARANTINE,
        stream=io.BytesIO(content),
        media_type="application/pdf",
        max_bytes=1024,
    )

    assert first == second
    assert first.uri.endswith(".pdf")
    assert store.path_for_test(first).read_bytes() == content


def test_local_import_retains_distinct_receipts_for_duplicate_binary(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source/car/user_manual"
    source.mkdir(parents=True)
    content = b"%PDF-1.7\nsame\n%%EOF\n"
    (source / "VF 8.pdf").write_bytes(content)
    (source / "VF-8.pdf").write_bytes(content)
    object_root = tmp_path / "objects"

    first = import_corpus(
        source_root=tmp_path / "source",
        object_root=object_root,
        batch_id="batch",
        actor_ref="human:owner",
        process=False,
    )
    second = import_corpus(
        source_root=tmp_path / "source",
        object_root=object_root,
        batch_id="batch",
        actor_ref="human:owner",
        process=False,
    )

    receipts = [
        json.loads(line)
        for line in (
            object_root / "intake/local-bootstrap/batch/documents.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert first == second
    assert first["artifact_count"] == 2
    assert first["unique_object_count"] == 1
    assert len({item["receipt_id"] for item in receipts}) == 2
    assert len({item["relative_path_token"] for item in receipts}) == 2


def test_local_import_rejects_concurrent_batch_writer(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "fixture.pdf").write_bytes(b"%PDF-1.7\nfixture\n%%EOF\n")
    object_root = tmp_path / "objects"
    control = object_root / ".control/local-bootstrap"
    control.mkdir(parents=True)
    lock_path = control / "batch.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RegistryInvariantError, match="active writer"):
            import_corpus(
                source_root=source,
                object_root=object_root,
                batch_id="batch",
                actor_ref="human:owner",
                process=False,
            )


def test_local_import_hands_processing_to_google_document_ai(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "fixture.pdf").write_bytes(b"%PDF-1.7\nfixture\n%%EOF\n")
    object_root = tmp_path / "objects"

    result = import_corpus(
        source_root=source,
        object_root=object_root,
        batch_id="batch",
        actor_ref="human:owner",
        process=True,
    )

    report = json.loads(
        (object_root / "intake/local-bootstrap/batch/processing-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["processing_provider"] == "google-document-ai"
    assert result["processing_status"] == "awaiting-gcp-document-ai"
    assert result["processed_document_count"] == 0
    assert result["pending_document_count"] == 1
    assert report["schema_version"] == "vfbiz-local-processing-handoff/v2"
    assert report["processing_provider"] == "google-document-ai"
    assert report["release_eligible"] is False
    assert not (object_root / "candidate/knowledge").exists()
