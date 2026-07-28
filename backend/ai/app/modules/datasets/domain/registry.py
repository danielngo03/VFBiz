from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import PurePosixPath
from uuid import UUID


class RegistryInvariantError(ValueError):
    """Raised when a registry transition would weaken a control invariant."""


class SourceStatus(StrEnum):
    CANDIDATE = "candidate"
    LEGAL_HOLD = "legal-hold"
    FETCH_APPROVED = "fetch-approved"
    PURPOSE_APPROVED = "purpose-approved"
    REJECTED = "rejected"
    TOMBSTONED = "tombstoned"


class FetchState(StrEnum):
    REQUESTED = "requested"
    DOWNLOADING = "downloading"
    QUARANTINED = "quarantined"
    VERIFIED = "verified"
    SCAN_PASSED = "scan-passed"
    REJECTED = "rejected"
    DELETED = "deleted"


class TrustZone(StrEnum):
    QUARANTINE = "quarantine"
    CANDIDATE = "candidate"
    RELEASED = "released"
    RESTRICTED_EVALUATION = "restricted-evaluation"
    RED_TEAM = "red-team"
    REVIEW_EVIDENCE = "review-evidence"
    TOMBSTONES = "tombstones"


class ProcessingStage(StrEnum):
    RAW = "raw"
    NORMALIZED = "normalized"
    FILTERED = "filtered"
    ENRICHED = "enriched"
    ADJUDICATED = "adjudicated"


class ArtifactStatus(StrEnum):
    ACTIVE = "active"
    REJECTED = "rejected"
    TOMBSTONED = "tombstoned"
    DELETED = "deleted"


class AllowedUse(StrEnum):
    KNOWLEDGE_INDEX = "knowledge-index"
    CLASSIFIER_TRAINING = "classifier-training"
    SFT = "sft"
    PREFERENCE = "preference"
    EMBEDDING = "embedding"
    RERANKER = "reranker"
    EVALUATION = "evaluation"
    RED_TEAM = "red-team"


class DlpDecision(StrEnum):
    PASSED = "passed"
    REVIEW_REQUIRED = "review-required"
    REJECTED = "rejected"


_SOURCE_TRANSITIONS: dict[SourceStatus, set[SourceStatus]] = {
    SourceStatus.CANDIDATE: {
        SourceStatus.LEGAL_HOLD,
        SourceStatus.FETCH_APPROVED,
        SourceStatus.REJECTED,
    },
    SourceStatus.LEGAL_HOLD: {SourceStatus.FETCH_APPROVED, SourceStatus.REJECTED},
    SourceStatus.FETCH_APPROVED: {SourceStatus.PURPOSE_APPROVED, SourceStatus.TOMBSTONED},
    SourceStatus.PURPOSE_APPROVED: {SourceStatus.TOMBSTONED},
    SourceStatus.REJECTED: set(),
    SourceStatus.TOMBSTONED: set(),
}

_FETCH_TRANSITIONS: dict[FetchState, set[FetchState]] = {
    FetchState.REQUESTED: {FetchState.DOWNLOADING, FetchState.REJECTED},
    FetchState.DOWNLOADING: {FetchState.QUARANTINED, FetchState.REJECTED},
    FetchState.QUARANTINED: {FetchState.VERIFIED, FetchState.REJECTED, FetchState.DELETED},
    FetchState.VERIFIED: {FetchState.SCAN_PASSED, FetchState.REJECTED, FetchState.DELETED},
    FetchState.SCAN_PASSED: {FetchState.DELETED},
    FetchState.REJECTED: {FetchState.DELETED},
    FetchState.DELETED: set(),
}


def _sha256(value: str, field: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RegistryInvariantError(f"{field} must be lowercase SHA-256 hex")
    return value


@dataclass(frozen=True, slots=True)
class DatasetScanEvidence:
    evidence_ref: str
    evidence_sha256: str
    artifact_sha256: str
    scanner_revision: str
    signature_revision: str
    structural_valid: bool
    malware_passed: bool
    dlp_decision: DlpDecision

    def __post_init__(self) -> None:
        if not self.evidence_ref.strip() or not self.scanner_revision.strip():
            raise RegistryInvariantError("scan evidence identity and scanner revision are required")
        if not self.signature_revision.strip():
            raise RegistryInvariantError("malware signature revision is required")
        _sha256(self.evidence_sha256, "scan evidence digest")
        _sha256(self.artifact_sha256, "scan artifact digest")

    @property
    def passed(self) -> bool:
        return (
            self.structural_valid
            and self.malware_passed
            and self.dlp_decision is DlpDecision.PASSED
        )


@dataclass(frozen=True, slots=True)
class DatasetSource:
    source_id: UUID
    source_key: str
    source_revision: str
    origin_uri: str
    status: SourceStatus
    owner_ref: str
    classification: str
    proposed_uses: tuple[AllowedUse, ...]
    approved_uses: tuple[AllowedUse, ...] = ()
    rights_evidence_ref: str | None = None
    rights_evidence_sha256: str | None = None
    terms_sha256: str | None = None
    row_version: int = 1

    def __post_init__(self) -> None:
        if not self.source_key.strip() or not self.source_revision.strip():
            raise RegistryInvariantError("source identity is required")
        if not self.origin_uri.startswith("https://") and not self.origin_uri.startswith(
            "urn:vfbiz:"
        ):
            raise RegistryInvariantError(
                "source origin must be allowlistable HTTPS or internal URN"
            )
        if not self.proposed_uses or len(set(self.proposed_uses)) != len(self.proposed_uses):
            raise RegistryInvariantError("proposed uses must be non-empty and unique")
        if not set(self.approved_uses).issubset(self.proposed_uses):
            raise RegistryInvariantError("approved uses must be proposed first")
        if self.row_version < 1:
            raise RegistryInvariantError("row version must be positive")
        if self.rights_evidence_sha256 is not None:
            _sha256(self.rights_evidence_sha256, "rights evidence digest")
        if self.terms_sha256 is not None:
            _sha256(self.terms_sha256, "terms digest")

    def transition(
        self,
        target: SourceStatus,
        *,
        approved_uses: tuple[AllowedUse, ...] | None = None,
        rights_evidence_ref: str | None = None,
        rights_evidence_sha256: str | None = None,
        terms_sha256: str | None = None,
    ) -> DatasetSource:
        if target not in _SOURCE_TRANSITIONS[self.status]:
            raise RegistryInvariantError(f"invalid source transition {self.status} -> {target}")
        next_uses = self.approved_uses if approved_uses is None else approved_uses
        next_rights_ref = rights_evidence_ref or self.rights_evidence_ref
        next_rights_sha = rights_evidence_sha256 or self.rights_evidence_sha256
        next_terms_sha = terms_sha256 or self.terms_sha256
        if target in {SourceStatus.FETCH_APPROVED, SourceStatus.PURPOSE_APPROVED}:
            if not next_rights_ref or not next_rights_sha or not next_terms_sha:
                raise RegistryInvariantError(
                    "rights and terms evidence are required before approval"
                )
        if target is SourceStatus.PURPOSE_APPROVED and not next_uses:
            raise RegistryInvariantError("purpose approval requires at least one approved use")
        return replace(
            self,
            status=target,
            approved_uses=next_uses,
            rights_evidence_ref=next_rights_ref,
            rights_evidence_sha256=next_rights_sha,
            terms_sha256=next_terms_sha,
            row_version=self.row_version + 1,
        )


@dataclass(frozen=True, slots=True)
class DatasetFetch:
    fetch_id: UUID
    source_id: UUID
    state: FetchState
    requested_by: str
    approval_evidence_ref: str
    approval_evidence_sha256: str
    observed_sha256: str | None = None
    observed_tree_sha256: str | None = None
    byte_size: int | None = None
    quarantine_uri: str | None = None
    scan_evidence: DatasetScanEvidence | None = None
    row_version: int = 1

    def __post_init__(self) -> None:
        _sha256(self.approval_evidence_sha256, "fetch approval digest")
        if self.observed_sha256 is not None:
            _sha256(self.observed_sha256, "observed content digest")
        if self.observed_tree_sha256 is not None:
            _sha256(self.observed_tree_sha256, "observed tree digest")
        if self.byte_size is not None and self.byte_size < 0:
            raise RegistryInvariantError("fetch byte size cannot be negative")

    def transition(
        self,
        target: FetchState,
        *,
        observed_sha256: str | None = None,
        observed_tree_sha256: str | None = None,
        byte_size: int | None = None,
        quarantine_uri: str | None = None,
        scan_evidence: DatasetScanEvidence | None = None,
    ) -> DatasetFetch:
        if target not in _FETCH_TRANSITIONS[self.state]:
            raise RegistryInvariantError(f"invalid fetch transition {self.state} -> {target}")
        digest = observed_sha256 or self.observed_sha256
        uri = quarantine_uri or self.quarantine_uri
        size = self.byte_size if byte_size is None else byte_size
        if target in {FetchState.QUARANTINED, FetchState.VERIFIED, FetchState.SCAN_PASSED}:
            if not digest or not uri or size is None:
                raise RegistryInvariantError("quarantined fetch requires digest, URI and byte size")
        next_scan_evidence = scan_evidence or self.scan_evidence
        if target is FetchState.SCAN_PASSED:
            if next_scan_evidence is None:
                raise RegistryInvariantError("scan-passed fetch requires immutable scan evidence")
            if next_scan_evidence.artifact_sha256 != digest:
                raise RegistryInvariantError("scan evidence does not bind the observed artifact")
            if not next_scan_evidence.passed:
                raise RegistryInvariantError("scan evidence has unresolved security blockers")
        return replace(
            self,
            state=target,
            observed_sha256=digest,
            observed_tree_sha256=observed_tree_sha256 or self.observed_tree_sha256,
            byte_size=size,
            quarantine_uri=uri,
            scan_evidence=next_scan_evidence,
            row_version=self.row_version + 1,
        )


@dataclass(frozen=True, slots=True)
class DatasetArtifact:
    artifact_id: UUID
    content_sha256: str
    trust_zone: TrustZone
    processing_stage: ProcessingStage
    allowed_uses: tuple[AllowedUse, ...]
    storage_uri: str
    media_type: str
    byte_size: int
    classification: str
    status: ArtifactStatus = ArtifactStatus.ACTIVE

    def __post_init__(self) -> None:
        _sha256(self.content_sha256, "artifact digest")
        if self.trust_zone is TrustZone.RESTRICTED_EVALUATION and set(self.allowed_uses) != {
            AllowedUse.EVALUATION
        }:
            raise RegistryInvariantError("restricted evaluation artifacts are evaluation-only")
        if len(self.allowed_uses) != 1:
            raise RegistryInvariantError("each artifact must have exactly one primary allowed use")
        if self.byte_size < 0:
            raise RegistryInvariantError("artifact byte size cannot be negative")
        path = PurePosixPath(self.storage_uri.removeprefix("file://"))
        if ".." in path.parts:
            raise RegistryInvariantError("artifact URI cannot traverse storage boundaries")

    @property
    def allowed_use(self) -> AllowedUse:
        return self.allowed_uses[0]
