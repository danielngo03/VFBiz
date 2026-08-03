#!/usr/bin/env python3
"""Delete one local-bootstrap knowledge batch while retaining a minimal tombstone."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from app.modules.datasets.domain import RegistryInvariantError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object-root", required=True, type=Path)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--actor-ref", required=True)
    args = parser.parse_args()
    try:
        result = tombstone_local_batch(
            object_root=args.object_root,
            batch_id=args.batch_id,
            actor_ref=args.actor_ref,
        )
    except (OSError, ValueError, RegistryInvariantError) as error:
        print(f"FAILED-SAFELY: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


def tombstone_local_batch(
    *, object_root: Path, batch_id: str, actor_ref: str
) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", batch_id):
        raise RegistryInvariantError("batch ID is invalid")
    if object_root.is_symlink():
        raise RegistryInvariantError("object root must be a non-symlink directory")
    root = object_root.resolve(strict=True)
    if not root.is_dir():
        raise RegistryInvariantError("object root must be a non-symlink directory")
    control_root = root / ".control/local-bootstrap"
    _private_directory(control_root, anchor=root)
    lock_path = control_root / f"{batch_id}.lock"
    with lock_path.open("a+b") as lock:
        lock_path.chmod(0o600)
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RegistryInvariantError(
                "local bootstrap batch already has an active writer"
            ) from error
        return _tombstone_local_batch_unlocked(
            object_root=root,
            batch_id=batch_id,
            actor_ref=actor_ref,
        )


def _tombstone_local_batch_unlocked(
    *, object_root: Path, batch_id: str, actor_ref: str
) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", batch_id):
        raise RegistryInvariantError("batch ID is invalid")
    if object_root.is_symlink():
        raise RegistryInvariantError("object root must be a non-symlink directory")
    root = object_root.resolve(strict=True)
    if not root.is_dir():
        raise RegistryInvariantError("object root must be a non-symlink directory")
    intake_root = _contained(root, root / "intake/local-bootstrap" / batch_id)
    tombstone_root = root / "tombstones/local-bootstrap"
    _private_directory(tombstone_root, anchor=root)
    tombstone_path = _contained(
        tombstone_root, tombstone_root / f"{batch_id}.json"
    )
    pending = False
    deleted_files = 0
    deleted_bytes = 0
    deleted_hashes: list[str] = []
    if tombstone_path.is_file():
        value = json.loads(tombstone_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RegistryInvariantError("local tombstone is malformed")
        existing = cast(dict[str, object], value)
        if existing.get("state") == "complete":
            _assert_batch_absent(root, batch_id, existing)
            return existing
        if existing.get("state") != "pending" or existing.get("actor_ref") != actor_ref:
            raise RegistryInvariantError("local tombstone state is invalid")
        digest_values = existing.get("source_sha256s")
        if not isinstance(digest_values, list) or not all(
            isinstance(item, str) and re.fullmatch(r"[a-f0-9]{64}", item)
            for item in cast(list[object], digest_values)
        ):
            raise RegistryInvariantError("pending tombstone digest set is invalid")
        digests = set(cast(list[str], digest_values))
        pending = True
        deleted_files = _nonnegative_int(existing.get("deleted_file_count", 0))
        deleted_bytes = _nonnegative_int(existing.get("deleted_bytes", 0))
        prior_hashes = existing.get("deleted_hashes", [])
        if not isinstance(prior_hashes, list) or not all(
            isinstance(item, str) for item in cast(list[object], prior_hashes)
        ):
            raise RegistryInvariantError("pending tombstone deletion ledger is invalid")
        deleted_hashes = list(cast(list[str], prior_hashes))
    else:
        documents_path = intake_root / "documents.jsonl"
        if not documents_path.is_file() or documents_path.is_symlink():
            raise RegistryInvariantError("local bootstrap receipt set is unavailable")
        documents = _documents(documents_path)
        digests = {str(document["observed_sha256"]) for document in documents}
        _write_json_atomic(
            tombstone_path,
            {
                "schema_version": "vfbiz-local-bootstrap-tombstone/v1",
                "state": "pending",
                "batch_id": batch_id,
                "actor_ref": actor_ref,
                "source_sha256s": sorted(digests),
                "deleted_file_count": 0,
                "deleted_bytes": 0,
                "deleted_hashes": [],
                "started_at": datetime.now(UTC).isoformat(),
            },
        )
    shared = _shared_digests(root, excluding_batch=batch_id)
    def checkpoint() -> None:
        _write_json_atomic(
            tombstone_path,
            {
                "schema_version": "vfbiz-local-bootstrap-tombstone/v1",
                "state": "pending",
                "batch_id": batch_id,
                "actor_ref": actor_ref,
                "source_sha256s": sorted(digests),
                "deleted_file_count": deleted_files,
                "deleted_bytes": deleted_bytes,
                "deleted_hashes": deleted_hashes,
            },
            replace=True,
        )

    candidate_root = _contained(root, root / "candidate/knowledge")
    if candidate_root.is_dir():
        for batch_tree in sorted(candidate_root.glob(f"*/*/batches/{batch_id}")):
            resolved = _contained(candidate_root, batch_tree)
            count, byte_size, hashes = _delete_tree(resolved)
            deleted_files += count
            deleted_bytes += byte_size
            deleted_hashes.extend(hashes)
            checkpoint()

    for digest in sorted(digests):
        if digest not in shared:
            derived = _contained(root, root / "derived-quarantine" / digest)
            count, byte_size, hashes = _delete_tree(derived)
            deleted_files += count
            deleted_bytes += byte_size
            deleted_hashes.extend(hashes)
            quarantine = _contained(
                root,
                root / "quarantine" / digest[:2] / f"{digest}.pdf",
            )
            if quarantine.is_file() and not quarantine.is_symlink():
                if _hash_file(quarantine) != digest:
                    raise RegistryInvariantError("quarantine object digest is untrustworthy")
                deleted_files += 1
                deleted_bytes += quarantine.stat().st_size
                deleted_hashes.append(digest)
                quarantine.unlink()
            checkpoint()

    count, byte_size, hashes = _delete_tree(intake_root)
    deleted_files += count
    deleted_bytes += byte_size
    deleted_hashes.extend(hashes)
    checkpoint()
    tombstone: dict[str, object] = {
        "schema_version": "vfbiz-local-bootstrap-tombstone/v1",
        "state": "complete",
        "batch_id": batch_id,
        "actor_ref": actor_ref,
        "source_sha256s": sorted(digests),
        "source_object_count": len(digests),
        "shared_object_count": len(digests & shared),
        "deleted_file_count": deleted_files,
        "deleted_bytes": deleted_bytes,
        "deleted_tree_sha256": _digest_values(deleted_hashes),
        "deletion_resumed": pending,
        "tombstoned_at": datetime.now(UTC).isoformat(),
    }
    _write_json_atomic(tombstone_path, tombstone, replace=True)
    return tombstone


def _assert_batch_absent(
    root: Path, batch_id: str, tombstone: dict[str, object]
) -> None:
    if (root / "intake/local-bootstrap" / batch_id).exists():
        raise RegistryInvariantError("tombstoned batch intake was resurrected")
    candidate_root = root / "candidate/knowledge"
    if candidate_root.is_dir() and tuple(
        candidate_root.glob(f"*/*/batches/{batch_id}")
    ):
        raise RegistryInvariantError("tombstoned batch candidate was resurrected")
    digests = tombstone.get("source_sha256s", [])
    if not isinstance(digests, list):
        raise RegistryInvariantError("completed tombstone digest set is invalid")
    shared = _shared_digests(root, excluding_batch=batch_id)
    for value in cast(list[object], digests):
        if not isinstance(value, str) or value in shared:
            continue
        if (
            root / "quarantine" / value[:2] / f"{value}.pdf"
        ).exists() or (root / "derived-quarantine" / value).exists():
            raise RegistryInvariantError("tombstoned object lineage was resurrected")


def _documents(path: Path) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise RegistryInvariantError("intake receipt must be a JSON object")
        document = cast(dict[str, object], value)
        digest = document.get("observed_sha256")
        storage_uri = document.get("storage_uri")
        if (
            not isinstance(digest, str)
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or storage_uri != f"file://quarantine/{digest[:2]}/{digest}.pdf"
        ):
            raise RegistryInvariantError("intake receipt object binding is invalid")
        result.append(document)
    if not result:
        raise RegistryInvariantError("intake receipt set is empty")
    return result


def _shared_digests(root: Path, *, excluding_batch: str) -> set[str]:
    values: set[str] = set()
    intake = root / "intake/local-bootstrap"
    for path in sorted(intake.glob("*/documents.jsonl")):
        if path.parent.name == excluding_batch:
            continue
        tombstone = root / "tombstones/local-bootstrap" / f"{path.parent.name}.json"
        if tombstone.is_file():
            continue
        values.update(str(item["observed_sha256"]) for item in _documents(path))
    return values


def _delete_tree(path: Path) -> tuple[int, int, list[str]]:
    if not path.exists():
        return 0, 0, []
    if path.is_symlink() or not path.is_dir():
        raise RegistryInvariantError("derived artifact tree is not trustworthy")
    files = tuple(item for item in path.rglob("*") if item.is_file())
    if any(item.is_symlink() for item in files):
        raise RegistryInvariantError("derived artifact tree contains a symlink")
    byte_size = sum(item.stat().st_size for item in files)
    hashes = [_hash_file(item) for item in files]
    shutil.rmtree(path)
    return len(files), byte_size, hashes


def _contained(parent: Path, child: Path) -> Path:
    resolved_parent = parent.resolve(strict=True)
    resolved_child = child.resolve(strict=False)
    if resolved_child != resolved_parent and resolved_parent not in resolved_child.parents:
        raise RegistryInvariantError("local tombstone path escapes object root")
    return resolved_child


def _private_directory(path: Path, *, anchor: Path) -> None:
    anchor = anchor.resolve(strict=True)
    absolute = path.resolve(strict=False)
    if absolute != anchor and anchor not in absolute.parents:
        raise RegistryInvariantError("local tombstone path escapes object root")
    current = anchor
    for part in absolute.relative_to(anchor).parts:
        current = current / part
        if current.is_symlink():
            raise RegistryInvariantError("local tombstone path contains a symlink")
        current.mkdir(mode=0o700, exist_ok=True)
        if not current.is_dir():
            raise RegistryInvariantError("local tombstone path is not a directory")
        current.chmod(0o700)


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise RegistryInvariantError("tombstone deletion count is invalid")
    result = int(value)
    if result < 0:
        raise RegistryInvariantError("tombstone deletion count is invalid")
    return result


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _digest_values(values: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(sorted(values), separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_json_atomic(path: Path, value: object, *, replace: bool = False) -> None:
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise RegistryInvariantError("local tombstone artifact parent is untrustworthy")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.pending")
    rendered = json.dumps(value, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    try:
        with temporary.open("xb") as output:
            output.write(rendered)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        if path.exists() and not replace:
            raise RegistryInvariantError("immutable local tombstone conflict")
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
