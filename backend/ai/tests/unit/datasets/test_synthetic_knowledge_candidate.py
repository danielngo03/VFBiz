from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.modules.datasets.application.evaluation.synthetic_knowledge_verifier import (
    build_synthetic_knowledge_candidate_bundle,
    verify_synthetic_knowledge_candidate_bundle,
)
from app.modules.datasets.domain import RegistryInvariantError
from app.modules.datasets.infrastructure.synthetic_knowledge_candidate_store import (
    build_current_synthetic_knowledge_candidate,
    verify_persisted_synthetic_knowledge_candidate,
    write_synthetic_knowledge_candidate,
)


def test_candidate_is_fact_free_restricted_and_page_anchored() -> None:
    bundle = build_current_synthetic_knowledge_candidate()

    assert len(bundle.bundle_digest) == 64
    assert bundle.rows_jsonl.count(b"\n") == 12
    assert b'"release_eligible":false' in bundle.rows_jsonl
    assert b'"cloud_ocr_performed":false' in bundle.rows_jsonl
    assert b'"citation"' in bundle.rows_jsonl
    assert b'"page_text_sha256"' in bundle.rows_jsonl
    assert b"VinFast" not in bundle.rows_jsonl


def test_verifier_rejects_row_tamper_and_full_resign() -> None:
    bundle = build_current_synthetic_knowledge_candidate()

    with pytest.raises(RegistryInvariantError, match="repository authority"):
        verify_synthetic_knowledge_candidate_bundle(
            replace(
                bundle,
                rows_jsonl=bundle.rows_jsonl.replace(
                    b"developer-only", b"public-release", 1
                ),
            ),
        )

    forged_generator = bundle.generator_source_bytes + b"\n# forged authority\n"
    with pytest.raises(RegistryInvariantError, match="generator authority mismatch"):
        build_synthetic_knowledge_candidate_bundle(
            generator_source_bytes=forged_generator,
            verifier_source_bytes=bundle.verifier_source_bytes,
        )


def test_store_is_atomic_idempotent_and_permission_bound(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    bundle = build_current_synthetic_knowledge_candidate()

    first = write_synthetic_knowledge_candidate(bundle, root)
    second = write_synthetic_knowledge_candidate(bundle, root)

    assert first == second
    assert (first.stat().st_mode & 0o777) == 0o700
    assert all(
        (path.stat().st_mode & 0o777) == 0o600
        for path in first.rglob("*")
        if path.is_file()
    )
    verify_persisted_synthetic_knowledge_candidate(first)


def test_store_rejects_existing_packet_mutation(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    bundle = build_current_synthetic_knowledge_candidate()
    target = write_synthetic_knowledge_candidate(bundle, root)
    (target / "records.jsonl").write_bytes(b"{}\n")

    with pytest.raises(RegistryInvariantError, match="differs"):
        write_synthetic_knowledge_candidate(bundle, root)


def test_persisted_verifier_rejects_identical_external_symlink(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    bundle = build_current_synthetic_knowledge_candidate()
    target = write_synthetic_knowledge_candidate(bundle, root)
    records = target / "records.jsonl"
    external = tmp_path / "external-records.jsonl"
    external.write_bytes(records.read_bytes())
    external.chmod(0o600)
    records.unlink()
    records.symlink_to(external)

    with pytest.raises(RegistryInvariantError, match="contains a symlink"):
        verify_persisted_synthetic_knowledge_candidate(target)
