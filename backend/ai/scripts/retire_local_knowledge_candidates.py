#!/usr/bin/env python3
"""Retire release-ineligible local knowledge candidates with tombstone evidence."""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from app.modules.datasets.domain import RegistryInvariantError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object-root", required=True, type=Path)
    parser.add_argument("--trash-root", required=True, type=Path)
    parser.add_argument("--actor-ref", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        result = retire_release_ineligible_candidates(
            object_root=args.object_root,
            trash_root=args.trash_root,
            actor_ref=args.actor_ref,
            execute=args.execute,
        )
    except (OSError, ValueError, RegistryInvariantError) as error:
        print(f"FAILED-SAFELY: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def retire_release_ineligible_candidates(
    *,
    object_root: Path,
    trash_root: Path,
    actor_ref: str,
    execute: bool,
) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@-]{2,159}", actor_ref):
        raise RegistryInvariantError("actor reference is invalid")
    root = _trusted_directory(object_root, "object root")
    candidate_root = _contained(root, root / "candidate/knowledge")
    if not candidate_root.exists():
        return _summary(execute=execute, candidates=[])
    if candidate_root.is_symlink() or not candidate_root.is_dir():
        raise RegistryInvariantError("knowledge candidate root is untrustworthy")
    trash = _trusted_directory(trash_root, "trash root")
    candidates = _discover_candidates(root, candidate_root)
    if not execute:
        return _summary(execute=False, candidates=candidates)

    control = _contained(root, root / ".control")
    _private_directory(control, anchor=root)
    lock_path = control / "candidate-knowledge-retirement.lock"
    with lock_path.open("a+b") as lock:
        lock_path.chmod(0o600)
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RegistryInvariantError(
                "knowledge candidate retirement already has an active writer"
            ) from error
        retired = [
            _retire_candidate(
                root=root,
                candidate_root=candidate_root,
                trash_root=trash,
                actor_ref=actor_ref,
                candidate=candidate,
            )
            for candidate in candidates
        ]
    return _summary(execute=True, candidates=retired)


def _discover_candidates(root: Path, candidate_root: Path) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for manifest in sorted(candidate_root.glob("*/*/batches/*/manifest.json")):
        if manifest.is_symlink() or not manifest.is_file():
            raise RegistryInvariantError("candidate manifest is untrustworthy")
        batch_root = _contained(candidate_root, manifest.parent)
        payload = _load_object(manifest)
        if payload.get("release_eligible") is not False:
            continue
        if payload.get("active_retriever_visible") is not False:
            raise RegistryInvariantError(
                "release-ineligible candidate is visible to the active retriever"
            )
        entries = _inventory(batch_root)
        relative = batch_root.relative_to(root).as_posix()
        tree_sha256 = _digest_json(entries)
        candidates.append(
            {
                "source_path": relative,
                "batch_id": batch_root.name,
                "manifest_sha256": _hash_file(manifest),
                "tree_sha256": tree_sha256,
                "file_count": len(entries),
                "byte_size": sum(cast(int, item["byte_size"]) for item in entries),
                "chunk_count": _chunk_count(payload),
                "release_eligible": False,
                "active_retriever_visible": False,
            }
        )
    return candidates


def _retire_candidate(
    *,
    root: Path,
    candidate_root: Path,
    trash_root: Path,
    actor_ref: str,
    candidate: dict[str, object],
) -> dict[str, object]:
    source_path = cast(str, candidate["source_path"])
    batch_root = _contained(root, root / source_path)
    if not batch_root.is_dir() or batch_root.is_symlink():
        raise RegistryInvariantError("candidate changed after retirement inventory")
    current = _discover_candidates(root, candidate_root)
    match = next((item for item in current if item["source_path"] == source_path), None)
    if match != candidate:
        raise RegistryInvariantError("candidate changed after retirement inventory")

    identity = hashlib.sha256(source_path.encode("utf-8")).hexdigest()
    recovery_token = f"VFBiz-candidate-knowledge-{identity[:16]}"
    destination = _contained(trash_root, trash_root / recovery_token)
    if destination.exists():
        raise RegistryInvariantError("candidate recovery destination already exists")
    tombstone_root = _contained(root, root / "tombstones/candidate-knowledge")
    _private_directory(tombstone_root, anchor=root)
    tombstone_path = tombstone_root / f"{identity}.json"
    if tombstone_path.exists():
        raise RegistryInvariantError("candidate tombstone already exists")
    started_at = datetime.now(UTC).isoformat()
    _write_json_atomic(
        tombstone_path,
        {
            "schema_version": "vfbiz-candidate-knowledge-tombstone/v1",
            "state": "pending",
            "actor_ref": actor_ref,
            "started_at": started_at,
            "recovery_token": recovery_token,
            **candidate,
        },
    )
    try:
        os.replace(batch_root, destination)
    except OSError as error:
        if error.errno == errno.EXDEV:
            raise RegistryInvariantError(
                "trash root must be on the same filesystem for atomic retirement"
            ) from error
        raise
    _prune_empty_parents(batch_root.parent, stop=candidate_root)
    completed = {
        "schema_version": "vfbiz-candidate-knowledge-tombstone/v1",
        "state": "complete",
        "actor_ref": actor_ref,
        "started_at": started_at,
        "retired_at": datetime.now(UTC).isoformat(),
        "recovery_token": recovery_token,
        **candidate,
    }
    _write_json_atomic(tombstone_path, completed, replace=True)
    return completed


def _summary(*, execute: bool, candidates: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "vfbiz-candidate-knowledge-retirement/v1",
        "status": "retired" if execute else "planned",
        "candidate_count": len(candidates),
        "file_count": sum(cast(int, item["file_count"]) for item in candidates),
        "byte_size": sum(cast(int, item["byte_size"]) for item in candidates),
        "chunk_count": sum(cast(int, item["chunk_count"]) for item in candidates),
        "candidates": candidates,
    }


def _inventory(root: Path) -> list[dict[str, object]]:
    items = tuple(sorted(root.rglob("*")))
    if any(item.is_symlink() for item in items):
        raise RegistryInvariantError("candidate contains a symlink")
    files = tuple(item for item in items if item.is_file())
    if not files:
        raise RegistryInvariantError("candidate contains no files")
    return [
        {
            "path": item.relative_to(root).as_posix(),
            "byte_size": item.stat().st_size,
            "sha256": _hash_file(item),
        }
        for item in files
    ]


def _chunk_count(manifest: dict[str, object]) -> int:
    documents = manifest.get("documents")
    if not isinstance(documents, dict):
        raise RegistryInvariantError("candidate document inventory is invalid")
    total = 0
    for value in cast(dict[str, object], documents).values():
        if not isinstance(value, dict):
            raise RegistryInvariantError("candidate document entry is invalid")
        count = cast(dict[str, object], value).get("chunk_count", 0)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise RegistryInvariantError("candidate chunk count is invalid")
        total += count
    return total


def _load_object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RegistryInvariantError("candidate manifest must be an object")
    return cast(dict[str, object], value)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _digest_json(value: object) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _trusted_directory(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise RegistryInvariantError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise RegistryInvariantError(f"{label} must be a directory")
    return resolved


def _contained(parent: Path, child: Path) -> Path:
    resolved_parent = parent.resolve(strict=True)
    resolved_child = child.resolve(strict=False)
    if resolved_child != resolved_parent and resolved_parent not in resolved_child.parents:
        raise RegistryInvariantError("retirement path escapes its trusted root")
    return resolved_child


def _private_directory(path: Path, *, anchor: Path) -> None:
    absolute = _contained(anchor, path)
    current = anchor.resolve(strict=True)
    for part in absolute.relative_to(current).parts:
        current = current / part
        if current.is_symlink():
            raise RegistryInvariantError("retirement path contains a symlink")
        current.mkdir(mode=0o700, exist_ok=True)
        current.chmod(0o700)


def _write_json_atomic(path: Path, value: object, *, replace: bool = False) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.pending")
    flags = "w" if replace else "x"
    with temporary.open(flags, encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, path)


def _prune_empty_parents(path: Path, *, stop: Path) -> None:
    current = path
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


if __name__ == "__main__":
    raise SystemExit(main())
