import hashlib
import json
from pathlib import Path

import pytest

from app.modules.datasets.application.evaluation.golden_rehearsal import (
    build_rehearsal_bundle,
)
from app.modules.datasets.domain import RegistryInvariantError
from app.modules.datasets.infrastructure.golden_rehearsal_store import (
    LocalGoldenRehearsalStore,
)


def test_local_rehearsal_store_is_private_content_addressed_and_idempotent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate" / "evaluation" / "vivi-rehearsal-v1"
    bundle = build_rehearsal_bundle()
    store = LocalGoldenRehearsalStore(root)

    first = store.put(bundle)
    second = store.put(bundle)

    assert first == second == root / bundle.bundle_digest
    assert store.verify(bundle.bundle_digest)["case_count"] == 100
    assert root.stat().st_mode & 0o777 == 0o700
    assert first.stat().st_mode & 0o777 == 0o700
    assert (first / "manifest.json").stat().st_mode & 0o777 == 0o600
    assert (first / "cases.jsonl").stat().st_mode & 0o777 == 0o600


def test_local_rehearsal_store_rejects_tamper(tmp_path: Path) -> None:
    bundle = build_rehearsal_bundle()
    store = LocalGoldenRehearsalStore(tmp_path / "rehearsal")
    stored = store.put(bundle)

    with (stored / "cases.jsonl").open("ab") as stream:
        stream.write(b"{}\n")

    with pytest.raises(RegistryInvariantError, match="digest mismatch"):
        store.verify(bundle.bundle_digest)


def test_local_rehearsal_store_rejects_rehashed_case_policy_mutation(
    tmp_path: Path,
) -> None:
    bundle = build_rehearsal_bundle()
    store = LocalGoldenRehearsalStore(tmp_path / "rehearsal")
    stored = store.put(bundle)
    manifest_path = stored / "manifest.json"
    cases_path = stored / "cases.jsonl"
    cases = [
        json.loads(line)
        for line in cases_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    cases[0]["allowed_use"] = "training"
    cases_bytes = b"".join(
        json.dumps(
            case,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
        for case in cases
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["cases_sha256"] = hashlib.sha256(cases_bytes).hexdigest()
    without_digest = {key: value for key, value in manifest.items() if key != "bundle_digest"}
    digest = hashlib.sha256(
        json.dumps(
            without_digest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    manifest["bundle_digest"] = digest
    mutated = stored.parent / digest
    stored.rename(mutated)
    cases_path = mutated / "cases.jsonl"
    manifest_path = mutated / "manifest.json"
    cases_path.write_bytes(cases_bytes)
    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    cases_path.chmod(0o600)
    manifest_path.chmod(0o600)
    with pytest.raises(RegistryInvariantError, match="evaluation-only"):
        store.verify(digest)


def test_local_rehearsal_store_rejects_permission_drift(tmp_path: Path) -> None:
    bundle = build_rehearsal_bundle()
    store = LocalGoldenRehearsalStore(tmp_path / "rehearsal")
    stored = store.put(bundle)
    (stored / "cases.jsonl").chmod(0o644)
    with pytest.raises(RegistryInvariantError, match="remain private"):
        store.verify(bundle.bundle_digest)


def test_local_rehearsal_store_rejects_symlink_root_and_bundle_files(
    tmp_path: Path,
) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(RegistryInvariantError, match="symlink"):
        LocalGoldenRehearsalStore(linked_root)

    bundle = build_rehearsal_bundle()
    store = LocalGoldenRehearsalStore(real_root)
    stored = store.put(bundle)
    cases = stored / "cases.jsonl"
    moved = stored / "cases.real"
    cases.rename(moved)
    cases.symlink_to(moved)
    with pytest.raises(RegistryInvariantError, match="symlink"):
        store.verify(bundle.bundle_digest)


@pytest.mark.parametrize(
    "digest",
    (
        "../escape",
        "A" * 64,
        "0" * 63,
        "0" * 65,
    ),
)
def test_local_rehearsal_store_rejects_invalid_digest(
    tmp_path: Path,
    digest: str,
) -> None:
    store = LocalGoldenRehearsalStore(tmp_path / "rehearsal")
    with pytest.raises(RegistryInvariantError, match="SHA-256"):
        store.verify(digest)
