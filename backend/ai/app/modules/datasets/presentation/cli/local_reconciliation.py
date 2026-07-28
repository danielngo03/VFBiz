from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from app.modules.datasets.domain import RegistryInvariantError, TrustZone
from app.modules.datasets.infrastructure.local_object_store import (
    LocalContentAddressedObjectStore,
)
from app.modules.datasets.infrastructure.scanners.quarantine import scan_quarantine_stream


def reconcile_local_downloads(
    *,
    evidence_path: Path,
    downloads_root: Path,
    object_store_root: Path,
    observed_at: str,
    portfolio_path: Path | None = None,
) -> dict[str, object]:
    _require_timestamp(observed_at)
    evidence = cast(
        dict[str, object],
        json.loads(evidence_path.read_text(encoding="utf-8")),
    )
    raw_artifacts = evidence.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise RegistryInvariantError("Wave A evidence must contain artifacts")
    artifacts = cast(list[object], raw_artifacts)
    files_by_hash = _index_files(downloads_root)
    store = LocalContentAddressedObjectStore(object_store_root)
    reconciled: list[dict[str, object]] = []
    for raw_artifact in artifacts:
        if not isinstance(raw_artifact, dict):
            raise RegistryInvariantError("Wave A artifact evidence must be an object")
        artifact = cast(dict[str, Any], raw_artifact)
        expected_sha256 = _required_string(artifact, "sha256")
        matches = files_by_hash.get(expected_sha256, ())
        if len(matches) != 1:
            raise RegistryInvariantError(
                f"expected exactly one local payload for {expected_sha256}; found {len(matches)}"
            )
        source_path = matches[0]
        media_type = _required_string(artifact, "media_type")
        byte_size = source_path.stat().st_size
        with source_path.open("rb") as source:
            scan = scan_quarantine_stream(
                source,
                media_type=media_type,
                byte_size=byte_size,
            )
            source.seek(0)
            stored = store.put_stream(
                zone=TrustZone.QUARANTINE,
                stream=source,
                media_type=media_type,
                max_bytes=byte_size,
            )
        if stored.sha256 != expected_sha256 or scan.observed_sha256 != expected_sha256:
            raise RegistryInvariantError("local payload no longer matches committed evidence")
        if not scan.structural_valid:
            raise RegistryInvariantError("local payload failed structural validation")
        reconciled.append(
            {
                "import_id": f"local-import-{expected_sha256[:16]}",
                "source_id": _required_string(artifact, "source_id"),
                "source_revision": _required_string(artifact, "revision"),
                "artifact_selector": _required_string(artifact, "selector"),
                "observed_sha256": expected_sha256,
                "byte_size": byte_size,
                "media_type": media_type,
                "content_address": stored.uri,
                "structural_scan": {
                    "scanner_revision": scan.scanner_revision,
                    "passed": scan.structural_valid,
                    "reasons": list(scan.reasons),
                },
                "origin_binding": "pending-exact-fetch-plan",
                "malware_scan": "pending-production-scanner",
                "dlp_scan": "pending-production-scanner",
                "purpose_approval": "not-granted",
                "release_eligible": False,
            }
        )
    report: dict[str, object] = {
        "schema_version": 1,
        "reconciliation_id": "vivi-wave-a-local-quarantine-v1",
        "source_evidence_id": evidence.get("evidence_id"),
        "observed_at": observed_at,
        "trust_zone": "quarantine",
        "artifact_count": len(reconciled),
        "artifacts": sorted(
            reconciled,
            key=lambda item: (
                str(item["source_id"]),
                str(item["artifact_selector"]),
            ),
        ),
        "promotion_blockers": [
            "exact fetch-plan/result origin binding",
            "production malware scan",
            "production DLP scan",
            "purpose approval",
            "independent quality review",
        ],
    }
    if portfolio_path is not None:
        report["portfolio_reconciliation"] = _reconcile_portfolio(
            portfolio_path=portfolio_path,
            artifacts=reconciled,
            source_scope=_source_scope(evidence),
        )
    return report


def write_report(report: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, output)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _index_files(root: Path) -> dict[str, tuple[Path, ...]]:
    if root.is_symlink() or not root.is_dir():
        raise RegistryInvariantError("downloads root must be a real directory")
    indexed: dict[str, list[Path]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RegistryInvariantError(f"download payload cannot be a symlink: {path}")
        if not path.is_file():
            continue
        indexed.setdefault(_hash_file(path), []).append(path)
    return {digest: tuple(paths) for digest, paths in indexed.items()}


def _reconcile_portfolio(
    *,
    portfolio_path: Path,
    artifacts: list[dict[str, object]],
    source_scope: set[str] | None,
) -> dict[str, object]:
    portfolio = cast(
        dict[str, object],
        json.loads(portfolio_path.read_text(encoding="utf-8")),
    )
    raw_sources = portfolio.get("sources")
    if not isinstance(raw_sources, list):
        raise RegistryInvariantError("Wave A portfolio must contain sources")
    all_sources = tuple(
        cast(dict[str, Any], source)
        for source in cast(list[object], raw_sources)
        if isinstance(source, dict)
    )
    sources = tuple(
        source
        for source in all_sources
        if source_scope is None or _required_string(source, "source_id") in source_scope
    )
    if source_scope is not None and len(sources) != len(source_scope):
        raise RegistryInvariantError("evidence source scope is not present in the portfolio")
    planned_ids = {_required_string(source, "source_id") for source in sources}
    observed_ids = {str(artifact["source_id"]) for artifact in artifacts}
    expected_selectors: dict[str, set[str]] = {
        _required_string(source, "source_id"): _selectors(source.get("selectors"))
        for source in sources
    }
    unplanned = sorted(
        f"{artifact['source_id']}:{artifact['artifact_selector']}"
        for artifact in artifacts
        if expected_selectors.get(str(artifact["source_id"]))
        and str(artifact["artifact_selector"]) not in expected_selectors[str(artifact["source_id"])]
    )
    return {
        "scope": "full" if source_scope is None else "incremental",
        "planned_source_count": len(planned_ids),
        "observed_source_count": len(observed_ids),
        "observed_source_ids": sorted(observed_ids),
        "pending_source_ids": sorted(planned_ids - observed_ids),
        "unplanned_artifacts": unplanned,
    }


def _source_scope(evidence: dict[str, object]) -> set[str] | None:
    raw_scope = evidence.get("source_scope")
    if raw_scope is None:
        return None
    if not isinstance(raw_scope, list) or not raw_scope:
        raise RegistryInvariantError("evidence source scope must be a non-empty array")
    values = cast(list[object], raw_scope)
    scope = {item.strip() for item in values if isinstance(item, str) and item.strip()}
    if len(scope) != len(values):
        raise RegistryInvariantError("evidence source scope must contain unique source IDs")
    return scope


def _selectors(raw: object) -> set[str]:
    if not isinstance(raw, dict):
        return set()
    selectors = cast(dict[str, Any], raw)
    files = selectors.get("files")
    if isinstance(files, list):
        return {_file_selector(item) for item in cast(list[object], files)}
    releases = selectors.get("releases")
    if isinstance(releases, list):
        selected: set[str] = set()
        for raw_release in cast(list[object], releases):
            if not isinstance(raw_release, dict):
                raise RegistryInvariantError("release selector must be an object")
            release = cast(dict[str, Any], raw_release)
            artifacts = release.get("artifacts")
            if not isinstance(artifacts, list):
                raise RegistryInvariantError("release selector must contain artifacts")
            selected.update(_file_selector(item) for item in cast(list[object], artifacts))
        return selected
    configs = selectors.get("configs")
    splits = selectors.get("splits")
    if isinstance(configs, list) and isinstance(splits, list):
        typed_configs = cast(list[object], configs)
        typed_splits = cast(list[object], splits)
        return {f"{config}/{split}" for config in typed_configs for split in typed_splits}
    return set()


def _file_selector(raw: object) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw
    if isinstance(raw, dict):
        path = cast(dict[str, Any], raw).get("path")
        if isinstance(path, str) and path.strip():
            return path
    raise RegistryInvariantError("file selector must be a path string or object")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _required_string(value: dict[str, Any], name: str) -> str:
    candidate = value.get(name)
    if not isinstance(candidate, str) or not candidate.strip():
        raise RegistryInvariantError(f"{name} must be a non-empty string")
    return candidate


def _require_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RegistryInvariantError("observed_at must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise RegistryInvariantError("observed_at must include a timezone")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile already-downloaded Wave A payloads into local quarantine."
    )
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--downloads-root", required=True, type=Path)
    parser.add_argument("--object-store-root", required=True, type=Path)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--portfolio", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    report = reconcile_local_downloads(
        evidence_path=arguments.evidence,
        downloads_root=arguments.downloads_root,
        object_store_root=arguments.object_store_root,
        observed_at=arguments.observed_at,
        portfolio_path=arguments.portfolio,
    )
    write_report(report, arguments.output)
    print(
        json.dumps(
            {
                "status": "quarantined-not-promoted",
                "artifacts": report["artifact_count"],
                "output": str(arguments.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
