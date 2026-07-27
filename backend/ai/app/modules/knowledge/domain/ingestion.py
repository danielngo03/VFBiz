import hashlib
import json
from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.knowledge.domain.errors import InvalidKnowledgeTransition
from app.modules.knowledge.domain.release import KnowledgeScope

IngestionStatus = Literal[
    "queued",
    "running",
    "retry_wait",
    "candidate_ready",
    "failed_safely",
    "dead_lettered",
    "deletion_pending",
    "deleting",
    "tombstoned",
]
IngestionStage = Literal[
    "quarantine",
    "pre_scan",
    "parse",
    "content_scan",
    "chunk",
    "embed",
    "verify",
    "delete",
]
FailureDisposition = Literal["transient", "permanent"]
ScanPhase = Literal["pre_parse", "post_parse"]
ScanResult = Literal["passed", "rejected", "indeterminate"]

_STAGE_ORDER: tuple[IngestionStage, ...] = (
    "quarantine",
    "pre_scan",
    "parse",
    "content_scan",
    "chunk",
    "embed",
    "verify",
)


class IngestionLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_source_bytes: int = Field(strict=True, ge=1, le=1_073_741_824)
    max_units: int = Field(strict=True, ge=1, le=10_000)
    max_decoded_pixels_per_unit: int = Field(strict=True, ge=1, le=400_000_000)
    max_expansion_ratio: int = Field(strict=True, ge=1, le=1_000)
    max_archive_depth: int = Field(strict=True, ge=0, le=8)
    max_extracted_files: int = Field(strict=True, ge=1, le=10_000)
    max_stage_seconds: int = Field(strict=True, ge=1, le=3_600)
    max_attempts_per_stage: int = Field(strict=True, ge=1, le=10)


class ScanEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: ScanPhase
    scanner_revision: str = Field(min_length=1, max_length=160)
    policy_revision: str = Field(min_length=1, max_length=160)
    result: ScanResult
    finding_count: int = Field(strict=True, ge=0)
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class StageCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: IngestionStage
    unit_cursor: int = Field(strict=True, ge=0)
    continuation_cursor: int | None = Field(default=None, strict=True, ge=0)
    unit_count: int | None = Field(default=None, strict=True, ge=0)
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_ref: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9/_=.-]{0,511}$")
    byte_count: int = Field(strict=True, ge=0)
    record_count: int = Field(strict=True, ge=0)
    completed: bool

    @model_validator(mode="after")
    def validate_cursor(self) -> Self:
        if self.unit_count is not None and self.unit_cursor > self.unit_count:
            raise ValueError("checkpoint cursor cannot exceed unit count")
        if self.completed and self.unit_count is not None and self.unit_cursor != self.unit_count:
            raise ValueError("completed checkpoint must reach its unit count")
        return self


class KnowledgeIngestionJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: UUID
    source_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    source_revision: str = Field(min_length=1, max_length=160)
    source_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scope: KnowledgeScope
    parser_revision: str = Field(min_length=1, max_length=160)
    chunker_revision: str = Field(min_length=1, max_length=160)
    scanner_revision: str = Field(min_length=1, max_length=160)
    embedding_revision: str = Field(min_length=1, max_length=160)
    embedding_dimension: int = Field(strict=True, ge=1, le=65_536)
    policy_revision: str = Field(min_length=1, max_length=160)
    code_revision: str = Field(pattern=r"^[a-f0-9]{40,64}$")
    candidate_namespace: str = Field(pattern=r"^candidate/[a-z0-9/_=.-]{1,480}$")
    limits: IngestionLimits
    command_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    status: IngestionStatus = "queued"
    current_stage: IngestionStage = "quarantine"
    stage_attempt: int = Field(default=0, strict=True, ge=0)
    next_attempt_at: datetime | None = None
    lease_expires_at: datetime | None = None
    fencing_token: int = Field(default=0, strict=True, ge=0)
    replay_generation: int = Field(default=0, strict=True, ge=0)
    deletion_generation: int = Field(default=0, strict=True, ge=0)
    checkpoints: tuple[StageCheckpoint, ...] = Field(default=(), max_length=16)
    scan_evidence: tuple[ScanEvidence, ...] = Field(default=(), max_length=4)
    final_manifest_ref: str | None = Field(default=None, max_length=512)
    final_manifest_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    failure_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    failure_stage: IngestionStage | None = None
    deletion_evidence_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    created_at: datetime
    updated_at: datetime
    version: int = Field(default=1, strict=True, ge=1)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        for value in (
            self.created_at,
            self.updated_at,
            self.next_attempt_at,
            self.lease_expires_at,
        ):
            if value is not None and value.tzinfo is None:
                raise ValueError("ingestion timestamps must include timezone")
        expected = ingestion_command_fingerprint(self)
        if self.command_fingerprint is None:
            object.__setattr__(self, "command_fingerprint", expected)
        elif self.command_fingerprint != expected:
            raise ValueError("ingestion command fingerprint does not match pinned inputs")
        if self.status == "candidate_ready" and (
            not self.final_manifest_ref
            or not self.final_manifest_hash
            or {item.phase for item in self.scan_evidence} != {"pre_parse", "post_parse"}
            or any(item.result != "passed" for item in self.scan_evidence)
        ):
            raise ValueError("candidate requires final manifest and both passing scan gates")
        if self.status == "tombstoned" and not self.deletion_evidence_hash:
            raise ValueError("tombstone requires physical deletion evidence")
        return self

    def claim(self, *, fencing_token: int, lease_expires_at: datetime, at: datetime) -> Self:
        self._require_status("queued", "retry_wait", "running")
        if (
            self.status == "running"
            and self.lease_expires_at is not None
            and self.lease_expires_at > at
        ):
            raise InvalidKnowledgeTransition("active worker lease has not expired")
        if self.next_attempt_at is not None and self.next_attempt_at > at:
            raise InvalidKnowledgeTransition("retry backoff has not elapsed")
        if fencing_token <= self.fencing_token or lease_expires_at <= at:
            raise InvalidKnowledgeTransition("worker lease or fencing token is invalid")
        return self._advance(
            at=at,
            status="running",
            fencing_token=fencing_token,
            lease_expires_at=lease_expires_at,
            stage_attempt=self.stage_attempt + 1,
            next_attempt_at=None,
            failure_code=None,
            failure_stage=None,
        )

    def checkpoint(self, checkpoint: StageCheckpoint, *, fencing_token: int, at: datetime) -> Self:
        self._require_worker(fencing_token, at)
        if checkpoint.stage != self.current_stage:
            raise InvalidKnowledgeTransition("checkpoint stage does not match current stage")
        prior = next((item for item in self.checkpoints if item.stage == checkpoint.stage), None)
        if prior is not None and checkpoint.unit_cursor < prior.unit_cursor:
            raise InvalidKnowledgeTransition("checkpoint cursor cannot move backwards")
        retained = tuple(item for item in self.checkpoints if item.stage != checkpoint.stage)
        return self._advance(at=at, checkpoints=retained + (checkpoint,))

    def complete_stage(
        self,
        *,
        fencing_token: int,
        at: datetime,
        scan_evidence: ScanEvidence | None = None,
        final_manifest_ref: str | None = None,
        final_manifest_hash: str | None = None,
    ) -> Self:
        self._require_worker(fencing_token, at)
        checkpoint = next(
            (item for item in self.checkpoints if item.stage == self.current_stage), None
        )
        if checkpoint is None or not checkpoint.completed:
            raise InvalidKnowledgeTransition("stage requires a completed durable checkpoint")
        expected_phase = {
            "pre_scan": "pre_parse",
            "content_scan": "post_parse",
        }.get(self.current_stage)
        evidence = self.scan_evidence
        if expected_phase is not None:
            if (
                scan_evidence is None
                or scan_evidence.phase != expected_phase
                or scan_evidence.scanner_revision != self.scanner_revision
                or scan_evidence.policy_revision != self.policy_revision
                or scan_evidence.result != "passed"
            ):
                raise InvalidKnowledgeTransition("scan gate did not pass deterministically")
            evidence += (scan_evidence,)
        if self.current_stage == "verify":
            if not final_manifest_ref or not final_manifest_hash:
                raise InvalidKnowledgeTransition("verify stage requires final manifest evidence")
            return self._advance(
                at=at,
                status="candidate_ready",
                scan_evidence=evidence,
                final_manifest_ref=final_manifest_ref,
                final_manifest_hash=final_manifest_hash,
                lease_expires_at=None,
                stage_attempt=0,
            )
        next_stage = _STAGE_ORDER[_STAGE_ORDER.index(self.current_stage) + 1]
        return self._advance(
            at=at,
            status="queued",
            current_stage=next_stage,
            scan_evidence=evidence,
            stage_attempt=0,
            lease_expires_at=None,
        )

    def pause_stage(self, *, fencing_token: int, at: datetime) -> Self:
        self._require_worker(fencing_token, at)
        return self._advance(
            at=at,
            status="queued",
            lease_expires_at=None,
            stage_attempt=0,
        )

    def failed(
        self,
        *,
        code: str,
        disposition: FailureDisposition,
        next_attempt_at: datetime | None,
        fencing_token: int,
        at: datetime,
    ) -> Self:
        self._require_worker(fencing_token, at)
        if disposition == "permanent":
            status: IngestionStatus = "failed_safely"
            retry_at = None
        elif self.stage_attempt >= self.limits.max_attempts_per_stage:
            status = "dead_lettered"
            retry_at = None
        else:
            if next_attempt_at is None or next_attempt_at <= at:
                raise InvalidKnowledgeTransition("transient failure requires future retry time")
            status = "retry_wait"
            retry_at = next_attempt_at
        return self._advance(
            at=at,
            status=status,
            next_attempt_at=retry_at,
            lease_expires_at=None,
            failure_code=code,
            failure_stage=self.current_stage,
        )

    def request_deletion(self, *, generation: int, at: datetime) -> Self:
        if generation <= self.deletion_generation:
            raise InvalidKnowledgeTransition("deletion generation must increase")
        return self._advance(
            at=at,
            status="deletion_pending",
            current_stage="delete",
            deletion_generation=generation,
            lease_expires_at=None,
        )

    def replay_dead_letter(self, *, generation: int, at: datetime) -> Self:
        self._require_status("dead_lettered")
        if generation <= self.replay_generation:
            raise InvalidKnowledgeTransition("replay generation must increase")
        return self._advance(
            at=at,
            status="queued",
            stage_attempt=0,
            next_attempt_at=None,
            lease_expires_at=None,
            failure_code=None,
            failure_stage=None,
            replay_generation=generation,
        )

    def deletion_started(
        self, *, fencing_token: int, lease_expires_at: datetime, at: datetime
    ) -> Self:
        self._require_status("deletion_pending")
        if fencing_token <= self.fencing_token or lease_expires_at <= at:
            raise InvalidKnowledgeTransition("deletion lease or fence is invalid")
        return self._advance(
            at=at,
            status="deleting",
            fencing_token=fencing_token,
            lease_expires_at=lease_expires_at,
        )

    def deletion_completed(self, *, evidence_hash: str, fencing_token: int, at: datetime) -> Self:
        self._require_worker(fencing_token, at, status="deleting")
        return self._advance(
            at=at,
            status="tombstoned",
            final_manifest_ref=None,
            checkpoints=(),
            lease_expires_at=None,
            deletion_evidence_hash=evidence_hash,
        )

    def _require_status(self, *allowed: IngestionStatus) -> None:
        if self.status not in allowed:
            raise InvalidKnowledgeTransition(
                f"ingestion transition is not allowed from {self.status}"
            )

    def _require_worker(
        self,
        fencing_token: int,
        at: datetime,
        *,
        status: IngestionStatus = "running",
    ) -> None:
        self._require_status(status)
        if (
            fencing_token != self.fencing_token
            or self.lease_expires_at is None
            or self.lease_expires_at <= at
        ):
            raise InvalidKnowledgeTransition("worker lease is stale or expired")

    def _advance(self, *, at: datetime, **changes: object) -> Self:
        if at.tzinfo is None:
            raise ValueError("transition time must include timezone")
        return self.model_copy(update={**changes, "updated_at": at, "version": self.version + 1})


def ingestion_command_fingerprint(job: KnowledgeIngestionJob) -> str:
    payload = {
        "source_id": job.source_id,
        "source_revision": job.source_revision,
        "source_snapshot_hash": job.source_snapshot_hash,
        "expected_checksum_sha256": job.expected_checksum_sha256,
        "scope": job.scope.model_dump(mode="json"),
        "parser_revision": job.parser_revision,
        "chunker_revision": job.chunker_revision,
        "scanner_revision": job.scanner_revision,
        "embedding_revision": job.embedding_revision,
        "embedding_dimension": job.embedding_dimension,
        "policy_revision": job.policy_revision,
        "code_revision": job.code_revision,
        "candidate_namespace": job.candidate_namespace,
        "limits": job.limits.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
