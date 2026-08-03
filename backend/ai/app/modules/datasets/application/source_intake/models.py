from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from urllib.parse import unquote, urlparse

from app.modules.datasets.domain import RegistryInvariantError


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(frozen=True, slots=True)
class StoredObject:
    uri: str
    sha256: str
    byte_size: int
    # GCS adapters persist immutable object generations when available. Local
    # and in-memory stores intentionally leave these unset.
    generation: int | None = None
    metageneration: int | None = None


class IntakeOrigin(StrEnum):
    MANAGED_UPLOAD = "managed-upload"
    LOCAL_BOOTSTRAP = "local-bootstrap"


@dataclass(frozen=True, slots=True)
class SourceIntakeReceipt:
    receipt_id: str
    batch_id: str
    origin: IntakeOrigin
    actor_ref: str
    relative_path_token: str
    original_filename: str
    media_type: str
    byte_size: int
    observed_sha256: str
    storage_uri: str
    document_family_id: str
    taxonomy: Mapping[str, str]
    received_at: datetime
    environment: str = "development"

    def __post_init__(self) -> None:
        if not self.receipt_id or not self.batch_id or not self.actor_ref:
            raise RegistryInvariantError("intake receipt identity is required")
        if self.media_type not in {
            "application/pdf",
            "application/json",
            "application/x-ndjson",
            "text/csv",
            "application/vnd.apache.parquet",
        }:
            raise RegistryInvariantError("intake media type is not allowlisted")
        if self.byte_size <= 0:
            raise RegistryInvariantError("intake byte size must be positive")
        if not _is_sha256(self.observed_sha256):
            raise RegistryInvariantError("intake digest must be lowercase SHA-256")
        if not self.storage_uri.startswith(("file://", "gs://")):
            raise RegistryInvariantError("intake storage URI must use managed object storage")
        if self.received_at.tzinfo is None:
            raise RegistryInvariantError("intake timestamp must include timezone")
        if self.environment not in {"development", "staging", "production"}:
            raise RegistryInvariantError("intake environment is not supported")
        if self.origin is IntakeOrigin.LOCAL_BOOTSTRAP and self.environment != "development":
            raise RegistryInvariantError("local bootstrap is development-only")
        object.__setattr__(
            self,
            "taxonomy",
            MappingProxyType(dict(sorted(self.taxonomy.items()))),
        )

    @property
    def content_revision(self) -> str:
        return f"sha256:{self.observed_sha256}"

    def contract_payload(self) -> dict[str, object]:
        if self.origin is IntakeOrigin.LOCAL_BOOTSTRAP:
            allowed_use = "knowledge-index"
            visibility = "developer-only"
            provenance_status = "locally-supplied-first-party-candidate"
        else:
            allowed_use = "quarantine-only"
            visibility = "workforce-private"
            provenance_status = "managed-upload-pending-review"
        return {
            "schema_version": "vfbiz-source-intake-receipt/v1",
            "receipt_id": self.receipt_id,
            "batch_id": self.batch_id,
            "origin": self.origin.value,
            "actor_ref": self.actor_ref,
            "relative_path_token": self.relative_path_token,
            "original_filename": self.original_filename,
            "media_type": self.media_type,
            "byte_size": self.byte_size,
            "observed_sha256": self.observed_sha256,
            "content_revision": self.content_revision,
            "storage_uri": self.storage_uri,
            "environment": self.environment,
            "allowed_use": allowed_use,
            "visibility": visibility,
            "release_eligible": False,
            "provenance_status": provenance_status,
            "document_family_id": self.document_family_id,
            "taxonomy": dict(sorted(self.taxonomy.items())),
            "received_at": self.received_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ApprovedSourceFetchPlan:
    plan_id: str
    source_id: str
    source_revision: str
    artifact_selector: str
    url: str
    media_type: str
    max_bytes: int
    fetch_approval_digest: str
    upstream_sha256: str | None = None
    expected_byte_size: int | None = None
    allowed_redirect_hosts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.plan_id or not self.source_id or not self.source_revision:
            raise RegistryInvariantError("fetch plan identity is required")
        if self.max_bytes <= 0:
            raise RegistryInvariantError("fetch maximum size must be positive")
        if not _is_sha256(self.fetch_approval_digest):
            raise RegistryInvariantError("fetch approval digest must be lowercase SHA-256")
        if self.upstream_sha256 is not None and not _is_sha256(self.upstream_sha256):
            raise RegistryInvariantError("upstream digest must be lowercase SHA-256")
        if self.expected_byte_size is not None and self.expected_byte_size <= 0:
            raise RegistryInvariantError("expected byte size must be positive")
        parsed = urlparse(self.url)
        decoded_path = unquote(parsed.path)
        if self.source_revision not in decoded_path or self.artifact_selector not in decoded_path:
            raise RegistryInvariantError(
                "fetch URL must bind the exact source revision and artifact selector"
            )

    @property
    def digest(self) -> str:
        payload = {
            "allowed_redirect_hosts": list(self.allowed_redirect_hosts),
            "artifact_selector": self.artifact_selector,
            "expected_byte_size": self.expected_byte_size,
            "fetch_approval_digest": self.fetch_approval_digest,
            "max_bytes": self.max_bytes,
            "media_type": self.media_type,
            "plan_id": self.plan_id,
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "upstream_sha256": self.upstream_sha256,
            "url": self.url,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class ScanEvidence:
    scanner_revision: str
    observed_sha256: str
    media_type: str
    byte_size: int
    structural_valid: bool
    executable_content_detected: bool
    archive_content_detected: bool
    pii_candidate_count: int
    secret_candidate_count: int
    passed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QuarantinedFetch:
    stored: StoredObject
    evidence: ScanEvidence
    fetch_plan_sha256: str
