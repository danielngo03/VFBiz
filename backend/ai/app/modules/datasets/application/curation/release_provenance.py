"""Registry-backed provenance authority for Dataset Release Manifest v4."""

from __future__ import annotations

from typing import Any, cast

from app.modules.datasets.application.ports.registry import DatasetProvenanceRegistry
from app.modules.datasets.domain import AllowedUse, FetchState, SourceStatus


class DatasetReleaseProvenanceAuthority:
    """Resolve immutable source evidence before promotion can proceed."""

    def __init__(self, registry: DatasetProvenanceRegistry) -> None:
        self._registry = registry

    async def errors(self, manifest: dict[str, Any]) -> list[str]:
        if manifest.get("status") not in {"decision-ready", "released"}:
            return []

        requested_use_value = manifest.get("allowed_use")
        try:
            requested_use = AllowedUse(str(requested_use_value))
        except ValueError:
            return [f"unsupported dataset allowed use {requested_use_value!r}"]

        provenance = manifest.get("provenance")
        source_values: object = None
        if isinstance(provenance, dict):
            source_values = cast(dict[str, Any], provenance).get("sources")
        if not isinstance(source_values, list):
            return ["decision-ready or released manifest requires provenance sources"]

        errors: list[str] = []
        for value in cast(list[object], source_values):
            if not isinstance(value, dict):
                errors.append("dataset provenance source is malformed")
                continue
            source = cast(dict[str, Any], value)
            source_key = source.get("source_id")
            source_revision = source.get("source_revision")
            artifact_digest = source.get("artifact_digest")
            if not all(
                isinstance(item, str) and item.strip()
                for item in (source_key, source_revision, artifact_digest)
            ):
                errors.append("dataset provenance source identity is incomplete")
                continue
            source_key = cast(str, source_key)
            source_revision = cast(str, source_revision)
            artifact_digest = cast(str, artifact_digest)
            artifact_sha256 = artifact_digest.removeprefix("sha256:")
            resolution = await self._registry.resolve_source_provenance(
                source_key=source_key,
                source_revision=source_revision,
                artifact_sha256=artifact_sha256,
            )
            identity = f"{source_key}@{source_revision}"
            if resolution is None:
                errors.append(
                    f"dataset provenance {identity} does not resolve to exact registry state"
                )
                continue
            if (
                resolution.source.source_key != source_key
                or resolution.source.source_revision != source_revision
            ):
                errors.append(
                    f"dataset provenance {identity} returned mismatched source identity"
                )
                continue
            if resolution.source.status is not SourceStatus.PURPOSE_APPROVED:
                errors.append(f"dataset provenance {identity} is not purpose-approved")
            if requested_use not in resolution.source.approved_uses:
                errors.append(
                    f"dataset provenance {identity} is not approved for "
                    f"{requested_use.value}"
                )
            fetch = resolution.scan_passed_fetch
            if fetch is None or fetch.state is not FetchState.SCAN_PASSED:
                errors.append(
                    f"dataset provenance {identity} has no scan-passed artifact "
                    f"matching sha256:{artifact_sha256}"
                )
                continue
            scan_evidence = fetch.scan_evidence
            if (
                fetch.source_id != resolution.source.source_id
                or fetch.observed_sha256 != artifact_sha256
                or scan_evidence is None
                or scan_evidence.artifact_sha256 != artifact_sha256
                or not scan_evidence.passed
            ):
                errors.append(
                    f"dataset provenance {identity} has invalid scan evidence "
                    f"for sha256:{artifact_sha256}"
                )
        return errors
