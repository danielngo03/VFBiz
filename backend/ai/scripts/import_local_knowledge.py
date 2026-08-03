#!/usr/bin/env python3
"""Import a local PDF corpus into release-ineligible VFBiz knowledge quarantine."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, cast

from app.modules.datasets.application.source_intake import IntakeOrigin, SourceIntakeReceipt
from app.modules.datasets.domain import RegistryInvariantError, TrustZone
from app.modules.datasets.infrastructure import LocalContentAddressedObjectStore

_BATCH_SCHEMA = "vfbiz-local-bootstrap-batch/v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--object-root", required=True, type=Path)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--actor-ref", default="human:local-project-owner")
    parser.add_argument("--skip-processing", action="store_true")
    args = parser.parse_args()
    try:
        summary = import_corpus(
            source_root=args.source_root,
            object_root=args.object_root,
            batch_id=args.batch_id,
            actor_ref=args.actor_ref,
            process=not args.skip_processing,
        )
    except (OSError, ValueError, RegistryInvariantError) as error:
        print(f"FAILED-SAFELY: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


def import_corpus(
    *,
    source_root: Path,
    object_root: Path,
    batch_id: str,
    actor_ref: str,
    process: bool,
) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", batch_id):
        raise RegistryInvariantError("batch ID is invalid")
    if object_root.is_symlink():
        raise RegistryInvariantError("object root must be a non-symlink directory")
    objects = object_root.resolve()
    objects.mkdir(mode=0o700, parents=True, exist_ok=True)
    objects.chmod(0o700)
    tombstone_path = objects / "tombstones/local-bootstrap" / f"{batch_id}.json"
    if tombstone_path.is_file():
        raise RegistryInvariantError(
            "tombstoned batch ID cannot be reused without an audited restore"
        )
    control_root = objects / ".control/local-bootstrap"
    _private_directory(control_root, anchor=objects)
    lock_path = control_root / f"{batch_id}.lock"
    with lock_path.open("a+b") as lock:
        lock_path.chmod(0o600)
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RegistryInvariantError(
                "local bootstrap batch already has an active writer"
            ) from error
        if tombstone_path.is_file():
            raise RegistryInvariantError(
                "tombstoned batch ID cannot be reused without an audited restore"
            )
        return _import_corpus_unlocked(
            source_root=source_root,
            object_root=objects,
            batch_id=batch_id,
            actor_ref=actor_ref,
            process=process,
        )


def _import_corpus_unlocked(
    *,
    source_root: Path,
    object_root: Path,
    batch_id: str,
    actor_ref: str,
    process: bool,
) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", batch_id):
        raise RegistryInvariantError("batch ID is invalid")
    if source_root.is_symlink():
        raise RegistryInvariantError("source root must be a non-symlink directory")
    root = source_root.resolve(strict=True)
    if not root.is_dir():
        raise RegistryInvariantError("source root must be a non-symlink directory")
    if object_root.is_symlink():
        raise RegistryInvariantError("object root must be a non-symlink directory")
    objects = object_root.resolve()
    objects.mkdir(mode=0o700, parents=True, exist_ok=True)
    objects.chmod(0o700)
    if (objects / "tombstones/local-bootstrap" / f"{batch_id}.json").is_file():
        raise RegistryInvariantError(
            "tombstoned batch ID cannot be reused without an audited restore"
        )
    intake_root = objects / "intake/local-bootstrap" / batch_id
    _private_directory(intake_root, anchor=objects)
    received_at = _batch_timestamp(intake_root / "batch-receipt.json")

    files = _source_files(root)
    store = LocalContentAddressedObjectStore(objects)
    existing_receipts = _existing_receipts_by_token(intake_root / "documents.jsonl")
    receipts: list[SourceIntakeReceipt] = []
    for source in files:
        relative = source.relative_to(root)
        before = source.stat()
        with source.open("rb") as stream:
            _assert_pdf(stream, relative)
            stream.seek(0)
            stored = store.put_stream(
                zone=TrustZone.QUARANTINE,
                stream=stream,
                media_type="application/pdf",
                max_bytes=1_073_741_824,
            )
        after = source.stat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise RegistryInvariantError("source mutated during local bootstrap copy")
        if _hash_file(source) != stored.sha256:
            raise RegistryInvariantError("source and quarantine digest mismatch")
        proposed_token = _relative_token(relative)
        legacy_token = _legacy_relative_token(relative)
        existing = existing_receipts.get(proposed_token) or existing_receipts.get(
            legacy_token
        )
        token = (
            str(existing["relative_path_token"])
            if existing is not None
            and existing.get("observed_sha256") == stored.sha256
            else proposed_token
        )
        taxonomy = _taxonomy(relative)
        family = _document_family(taxonomy, source.stem)
        artifact_key = hashlib.sha256(
            relative.as_posix().encode("utf-8")
        ).hexdigest()[:16]
        receipt_id = (
            str(existing["receipt_id"])
            if existing is not None
            and existing.get("observed_sha256") == stored.sha256
            else f"{batch_id}.{artifact_key}.{stored.sha256[:16]}"
        )
        receipt = SourceIntakeReceipt(
            receipt_id=receipt_id,
            batch_id=batch_id,
            origin=IntakeOrigin.LOCAL_BOOTSTRAP,
            actor_ref=actor_ref,
            relative_path_token=token,
            original_filename=source.name,
            media_type="application/pdf",
            byte_size=stored.byte_size,
            observed_sha256=stored.sha256,
            storage_uri=stored.uri,
            document_family_id=family,
            taxonomy=taxonomy,
            received_at=received_at,
        )
        receipts.append(receipt)

    document_payloads = [receipt.contract_payload() for receipt in receipts]
    tree_digest = _digest_json(
        [
            {
                "relative_path_token": receipt.relative_path_token,
                "sha256": receipt.observed_sha256,
                "bytes": receipt.byte_size,
            }
            for receipt in receipts
        ]
    )
    batch_payload = {
        "schema_version": _BATCH_SCHEMA,
        "batch_id": batch_id,
        "origin": "local-bootstrap",
        "actor_ref": actor_ref,
        "received_at": received_at.isoformat(),
        "artifact_count": len(receipts),
        "unique_object_count": len({item.observed_sha256 for item in receipts}),
        "total_bytes": sum(item.byte_size for item in receipts),
        "corpus_tree_sha256": tree_digest,
        "allowed_use": "knowledge-index",
        "visibility": "developer-only",
        "release_eligible": False,
        "provenance_status": "locally-supplied-first-party-candidate",
    }
    _write_json_atomic(intake_root / "batch-receipt.json", batch_payload)
    _write_jsonl_atomic(intake_root / "documents.jsonl", document_payloads)
    _write_text_atomic(
        intake_root / "checksums.sha256",
        "".join(
            f"{item.observed_sha256}  {item.relative_path_token}\n"
            for item in sorted(receipts, key=lambda value: value.relative_path_token)
        ),
    )

    processing_status = "awaiting-gcp-document-ai" if process else "intake-only"
    processing: dict[str, object] = {
        receipt.receipt_id: {
            "status": processing_status,
            "source_sha256": receipt.observed_sha256,
            "content_revision": receipt.content_revision,
            "provider": "google-document-ai" if process else None,
        }
        for receipt in receipts
    }
    _write_processing_report(
        intake_root / "processing-report.json",
        batch_id=batch_id,
        processing_status=processing_status,
        documents=processing,
    )
    return {
        "batch_id": batch_id,
        "artifact_count": len(receipts),
        "unique_object_count": len({item.observed_sha256 for item in receipts}),
        "corpus_tree_sha256": tree_digest,
        "processing_provider": "google-document-ai" if process else None,
        "processing_status": processing_status,
        "processed_document_count": 0,
        "pending_document_count": len(receipts) if process else 0,
        "release_eligible": False,
    }


def _source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    unsupported: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RegistryInvariantError("source corpus contains a symlink")
        if not path.is_file() or path.name == ".DS_Store":
            continue
        if path.suffix.lower() != ".pdf":
            unsupported.append(path.relative_to(root).as_posix())
        else:
            files.append(path)
    if unsupported:
        raise RegistryInvariantError(
            f"source corpus contains unsupported files: {', '.join(unsupported[:3])}"
        )
    if not files:
        raise RegistryInvariantError("source corpus contains no PDFs")
    return files


def _existing_receipts_by_token(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_file():
        return {}
    result: dict[str, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise RegistryInvariantError("existing intake receipt must be an object")
        receipt = cast(dict[str, object], value)
        token = receipt.get("relative_path_token")
        receipt_id = receipt.get("receipt_id")
        digest = receipt.get("observed_sha256")
        if (
            not isinstance(token, str)
            or not isinstance(receipt_id, str)
            or not isinstance(digest, str)
        ):
            raise RegistryInvariantError("existing intake receipt identity is invalid")
        if token in result:
            raise RegistryInvariantError("existing intake receipt token is duplicated")
        result[token] = receipt
    return result


def _assert_pdf(stream: BinaryIO, relative: Path) -> None:
    if stream.read(5) != b"%PDF-":
        raise RegistryInvariantError(f"file extension and PDF signature disagree: {relative}")


def _relative_token(relative: Path) -> str:
    parts = [_slug(part) for part in relative.with_suffix("").parts]
    path_hash = hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest()[:12]
    token = "/".join(parts) + f"--path-{path_hash}.pdf"
    if len(token) > 512:
        raise RegistryInvariantError("relative path token exceeds the contract limit")
    return token


def _legacy_relative_token(relative: Path) -> str:
    token = "/".join(_slug(part) for part in relative.with_suffix("").parts) + ".pdf"
    if len(token) > 512:
        raise RegistryInvariantError("relative path token exceeds the contract limit")
    return token


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug or "document"


def _taxonomy(relative: Path) -> dict[str, str]:
    parts = relative.parts
    vehicle = {"car": "car", "motobike": "motorbike"}.get(parts[0], "shared")
    document_type = {
        "user_manual": "owner-manual",
        "warranty_policy": "warranty-policy",
        "brochure": "brochure",
        "emergency_guideline": "emergency-guide",
        "shared": "shared-guide",
    }.get(parts[1] if len(parts) > 1 else "", "other")
    return {
        "vehicle_type": vehicle,
        "document_type": document_type,
        "locale": "vi-VN",
        "market": "VN",
        "audience": "customer",
        "model_hint": _slug(relative.stem),
    }


def _document_family(taxonomy: dict[str, str], stem: str) -> str:
    value = "-".join(
        (
            "vinfast",
            taxonomy["vehicle_type"],
            taxonomy["document_type"],
            _slug(stem),
            "vi-vn",
        )
    )
    return value[:160].rstrip("-")


def _batch_timestamp(path: Path) -> datetime:
    if path.is_file():
        value = json.loads(path.read_text(encoding="utf-8"))
        timestamp = value.get("received_at")
        if isinstance(timestamp, str):
            return datetime.fromisoformat(timestamp)
    return datetime.now(UTC)


def _write_processing_report(
    path: Path,
    *,
    batch_id: str,
    processing_status: str,
    documents: dict[str, object],
) -> None:
    _write_json_atomic(
        path,
        {
            "schema_version": "vfbiz-local-processing-handoff/v2",
            "batch_id": batch_id,
            "processing_status": processing_status,
            "processing_provider": (
                "google-document-ai"
                if processing_status == "awaiting-gcp-document-ai"
                else None
            ),
            "processed_document_count": 0,
            "pending_document_count": (
                len(documents)
                if processing_status == "awaiting-gcp-document-ai"
                else 0
            ),
            "documents": dict(sorted(documents.items())),
            "release_eligible": False,
        },
        replace=True,
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _digest_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _private_directory(path: Path, *, anchor: Path) -> None:
    anchor = anchor.resolve(strict=True)
    absolute = path.resolve(strict=False)
    if absolute != anchor and anchor not in absolute.parents:
        raise RegistryInvariantError("local intake path escapes object root")
    current = anchor
    for part in absolute.relative_to(anchor).parts:
        current = current / part
        if current.is_symlink():
            raise RegistryInvariantError("local intake path contains a symlink")
        current.mkdir(mode=0o700, exist_ok=True)
        if not current.is_dir():
            raise RegistryInvariantError("local intake path is not a directory")
        current.chmod(0o700)


def _write_json_atomic(path: Path, value: object, *, replace: bool = False) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    _write_text_atomic(path, rendered, replace=replace)


def _write_jsonl_atomic(path: Path, values: list[dict[str, object]]) -> None:
    rendered = "".join(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for value in values
    )
    _write_text_atomic(path, rendered)


def _write_text_atomic(path: Path, value: str, *, replace: bool = False) -> None:
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise RegistryInvariantError("local intake artifact parent is untrustworthy")
    encoded = value.encode("utf-8")
    if path.exists() and not replace:
        if path.read_bytes() != encoded:
            raise RegistryInvariantError("immutable local intake artifact conflict")
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.pending")
    try:
        with temporary.open("xb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
