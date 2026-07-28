from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from app.modules.datasets.domain import RegistryInvariantError


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(frozen=True, slots=True)
class StoredObject:
    uri: str
    sha256: str
    byte_size: int


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
