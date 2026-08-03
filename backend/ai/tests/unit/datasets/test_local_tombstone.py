from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path

import pytest

from app.modules.datasets.domain import RegistryInvariantError
from scripts.tombstone_local_knowledge import tombstone_local_batch


def _write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def test_local_tombstone_deletes_lineage_and_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    content = b"%PDF-1.7\nfixture\n"
    digest = hashlib.sha256(content).hexdigest()
    quarantine = root / "quarantine" / digest[:2] / f"{digest}.pdf"
    _write(quarantine, content)
    _write(root / "derived-quarantine" / digest / "pipeline/pages/1.json", b"page")
    _write(
        root / "candidate/knowledge/profile/pipeline/batches/batch/chunks/r1/chunk.json",
        b"chunk",
    )
    receipts = root / "intake/local-bootstrap/batch/documents.jsonl"
    receipts.parent.mkdir(parents=True)
    receipts.write_text(
        json.dumps(
            {
                "observed_sha256": digest,
                "storage_uri": f"file://quarantine/{digest[:2]}/{digest}.pdf",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    first = tombstone_local_batch(
        object_root=root,
        batch_id="batch",
        actor_ref="human:data-owner",
    )
    second = tombstone_local_batch(
        object_root=root,
        batch_id="batch",
        actor_ref="human:data-owner",
    )

    assert first == second
    assert first["deleted_file_count"] == 4
    assert not quarantine.exists()
    assert not (root / "derived-quarantine" / digest).exists()
    assert not (
        root / "candidate/knowledge/profile/pipeline/batches/batch"
    ).exists()
    assert not receipts.parent.exists()
    assert (root / "tombstones/local-bootstrap/batch.json").is_file()


def test_tombstone_detects_resurrected_batch(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    content = b"%PDF-1.7\nfixture\n"
    digest = hashlib.sha256(content).hexdigest()
    quarantine = root / "quarantine" / digest[:2] / f"{digest}.pdf"
    _write(quarantine, content)
    receipts = root / "intake/local-bootstrap/batch/documents.jsonl"
    receipts.parent.mkdir(parents=True)
    receipts.write_text(
        json.dumps(
            {
                "observed_sha256": digest,
                "storage_uri": f"file://quarantine/{digest[:2]}/{digest}.pdf",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    tombstone_local_batch(
        object_root=root,
        batch_id="batch",
        actor_ref="human:data-owner",
    )
    _write(quarantine, content)

    with pytest.raises(RegistryInvariantError, match="resurrected"):
        tombstone_local_batch(
            object_root=root,
            batch_id="batch",
            actor_ref="human:data-owner",
        )


def test_tombstone_rejects_active_import_writer(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    content = b"%PDF-1.7\nfixture\n"
    digest = hashlib.sha256(content).hexdigest()
    receipt = root / "intake/local-bootstrap/batch/documents.jsonl"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "observed_sha256": digest,
                "storage_uri": f"file://quarantine/{digest[:2]}/{digest}.pdf",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    control = root / ".control/local-bootstrap"
    control.mkdir(parents=True)
    lock_path = control / "batch.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RegistryInvariantError, match="active writer"):
            tombstone_local_batch(
                object_root=root,
                batch_id="batch",
                actor_ref="human:data-owner",
            )


def test_tombstone_rejects_symlinked_evidence_root(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    receipt = root / "intake/local-bootstrap/batch/documents.jsonl"
    receipt.parent.mkdir(parents=True)
    content = b"%PDF-1.7\nfixture\n"
    digest = hashlib.sha256(content).hexdigest()
    receipt.write_text(
        json.dumps(
            {
                "observed_sha256": digest,
                "storage_uri": f"file://quarantine/{digest[:2]}/{digest}.pdf",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "tombstones").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RegistryInvariantError, match="symlink|escapes"):
        tombstone_local_batch(
            object_root=root,
            batch_id="batch",
            actor_ref="human:data-owner",
        )
def test_tombstone_preserves_content_object_referenced_by_another_batch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "objects"
    content = b"%PDF-1.7\nshared\n"
    digest = hashlib.sha256(content).hexdigest()
    quarantine = root / "quarantine" / digest[:2] / f"{digest}.pdf"
    _write(quarantine, content)
    receipt = (
        json.dumps(
            {
                "observed_sha256": digest,
                "storage_uri": f"file://quarantine/{digest[:2]}/{digest}.pdf",
            }
        )
        + "\n"
    )
    for batch in ("batch-a", "batch-b"):
        path = root / f"intake/local-bootstrap/{batch}/documents.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(receipt, encoding="utf-8")
        _write(
            root
            / f"candidate/knowledge/profile/pipeline/batches/{batch}/chunks/r1/chunk.json",
            batch.encode(),
        )
    _write(root / "derived-quarantine" / digest / "pipeline/pages/1.json", b"page")

    result = tombstone_local_batch(
        object_root=root,
        batch_id="batch-a",
        actor_ref="human:data-owner",
    )

    assert result["shared_object_count"] == 1
    assert quarantine.is_file()
    assert (root / "derived-quarantine" / digest).is_dir()
    assert not (
        root / "candidate/knowledge/profile/pipeline/batches/batch-a"
    ).exists()

    tombstone_local_batch(
        object_root=root,
        batch_id="batch-b",
        actor_ref="human:data-owner",
    )

    assert not quarantine.exists()
    assert not (root / "derived-quarantine" / digest).exists()
