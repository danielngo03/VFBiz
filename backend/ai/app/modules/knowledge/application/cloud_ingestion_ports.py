from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal, Protocol, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CloudObjectIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    uri: str = Field(min_length=6, max_length=1_024)
    generation: int = Field(strict=True, ge=1)
    metageneration: int = Field(strict=True, ge=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_size: int = Field(strict=True, ge=0, le=1_073_741_824)
    crc32c: str = Field(pattern=r"^[A-Za-z0-9+/]{6}==$")

    @model_validator(mode="after")
    def validate_uri(self) -> Self:
        parsed = urlsplit(self.uri)
        if (
            parsed.scheme != "gs"
            or not parsed.netloc
            or not parsed.path.lstrip("/")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or ".." in parsed.path.split("/")
        ):
            raise ValueError("cloud object must be a pinned gs:// locator")
        return self


class PubSubIngestionDelivery(BaseModel):
    """Pointer-only worker delivery. Source bytes and extracted text are forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_revision: Literal["gcp-knowledge-intake-v1"] = "gcp-knowledge-intake-v1"
    receipt_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{0,159}$")
    job_id: UUID
    object: CloudObjectIdentity
    authority_class: Literal["synthetic-smoke-only"] = "synthetic-smoke-only"
    page_count: int = Field(strict=True, ge=1, le=500)
    fencing_token: int = Field(strict=True, ge=1)
    published_at: datetime

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        if self.published_at.tzinfo is None:
            raise ValueError("delivery timestamp must include timezone")
        return self


class ReceivedPubSubDelivery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    subscription: str = Field(min_length=1, max_length=512)
    delivery_attempt: int = Field(strict=True, ge=1, le=100)
    delivery: PubSubIngestionDelivery


class DeadLetterRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_revision: Literal["gcp-knowledge-dlq-v1"] = "gcp-knowledge-dlq-v1"
    delivery: PubSubIngestionDelivery
    failure_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    failed_at: datetime
    attempt: int = Field(strict=True, ge=1, le=100)

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        if self.failed_at.tzinfo is None:
            raise ValueError("dead-letter timestamp must include timezone")
        return self


class DocumentAiBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_revision: Literal["document-ai-batch-v1"] = "document-ai-batch-v1"
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    job_id: UUID
    input: CloudObjectIdentity
    output_prefix: str = Field(min_length=6, max_length=1_024)
    processor_revision: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
    mime_type: Literal["application/pdf"] = "application/pdf"
    page_count: int = Field(strict=True, ge=1, le=500)
    fencing_token: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def validate_output_prefix(self) -> Self:
        parsed = urlsplit(self.output_prefix)
        if (
            parsed.scheme != "gs"
            or not parsed.netloc
            or not parsed.path.lstrip("/")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or ".." in parsed.path.split("/")
        ):
            raise ValueError("Document AI output must use a bounded gs:// prefix")
        if not self.output_prefix.endswith("/"):
            raise ValueError("Document AI output prefix must end with '/'")
        return self


DocumentAiOperationState = Literal[
    "submitted",
    "running",
    "succeeded",
    "failed",
    "cancelled",
]


class DocumentAiOperationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_revision: Literal["document-ai-operation-v1"] = "document-ai-operation-v1"
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    job_id: UUID
    operation_name: str = Field(
        pattern=r"^projects/[A-Za-z0-9._-]+/locations/[A-Za-z0-9._-]+/operations/"
        r"[A-Za-z0-9._-]+$"
    )
    input: CloudObjectIdentity
    output_prefix: str
    processor_revision: str
    page_count: int = Field(strict=True, ge=1, le=500)
    fencing_token: int = Field(strict=True, ge=1)
    state: DocumentAiOperationState
    submitted_at: datetime
    reconciled_at: datetime
    provider_error_code: str | None = Field(default=None, pattern=r"^[A-Z0-9][A-Z0-9_.-]{0,79}$")

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        if self.submitted_at.tzinfo is None or self.reconciled_at.tzinfo is None:
            raise ValueError("Document AI receipt timestamps must include timezone")
        if self.reconciled_at < self.submitted_at:
            raise ValueError("Document AI reconciliation cannot precede submission")
        if self.state == "failed" and self.provider_error_code is None:
            raise ValueError("failed Document AI operation requires a provider error code")
        if self.state != "failed" and self.provider_error_code is not None:
            raise ValueError("provider error code is only valid for failed operations")
        return self


class DocumentAiOutputObject(BaseModel):
    """One immutable JSON shard emitted by Document AI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    uri: str = Field(min_length=6, max_length=1_024)
    generation: int = Field(strict=True, ge=1)
    metageneration: int = Field(strict=True, ge=1)
    byte_size: int = Field(strict=True, ge=1, le=536_870_912)
    crc32c: str = Field(pattern=r"^[A-Za-z0-9+/]{6}==$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_uri(self) -> Self:
        parsed = urlsplit(self.uri)
        if (
            parsed.scheme != "gs"
            or not parsed.netloc
            or not parsed.path.lstrip("/").endswith(".json")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or ".." in parsed.path.split("/")
        ):
            raise ValueError("Document AI output must be a pinned GCS JSON object")
        return self


DocumentAiPageDisposition = Literal["document-ai", "review-required"]


class DocumentAiPageExtraction(BaseModel):
    """Normalized page text with immutable source and output lineage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    page_number: int = Field(strict=True, ge=1, le=500)
    text: str = Field(max_length=2_000_000)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    disposition: DocumentAiPageDisposition
    warnings: tuple[str, ...] = Field(max_length=20)
    processor_revision: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
    output_uri: str = Field(min_length=6, max_length=1_024)
    output_generation: int = Field(strict=True, ge=1)


class DocumentAiExtractionResult(BaseModel):
    """Complete, ordered page extraction for one succeeded batch receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_revision: Literal["document-ai-extraction-v1"] = "document-ai-extraction-v1"
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    job_id: UUID
    source: CloudObjectIdentity
    processor_revision: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
    expected_page_count: int = Field(strict=True, ge=1, le=500)
    output_objects: tuple[DocumentAiOutputObject, ...] = Field(min_length=1, max_length=1_000)
    pages: tuple[DocumentAiPageExtraction, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_complete_lineage(self) -> Self:
        expected_pages = list(range(1, self.expected_page_count + 1))
        observed_pages = [page.page_number for page in self.pages]
        output_identities = {
            (output.uri, output.generation) for output in self.output_objects
        }
        if observed_pages != expected_pages:
            raise ValueError("Document AI extraction must contain every page exactly once")
        if any(
            page.source_sha256 != self.source.sha256
            or page.processor_revision != self.processor_revision
            or (page.output_uri, page.output_generation) not in output_identities
            for page in self.pages
        ):
            raise ValueError("Document AI page lineage does not match extraction authority")
        return self


class DocumentAiPageEvidence(BaseModel):
    """Content-free page evidence safe for PostgreSQL and operator receipts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page_number: int = Field(strict=True, ge=1, le=500)
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    text_byte_size: int = Field(strict=True, ge=0, le=8_000_000)
    confidence_micros: int | None = Field(default=None, strict=True, ge=0, le=1_000_000)
    disposition: DocumentAiPageDisposition
    warnings: tuple[str, ...] = Field(max_length=20)
    output_uri: str = Field(min_length=6, max_length=1_024)
    output_generation: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def validate_warnings(self) -> Self:
        if any(
            not warning
            or len(warning) > 80
            or not warning.replace("_", "").isalnum()
            or not warning.isupper()
            for warning in self.warnings
        ):
            raise ValueError("Document AI page warning is invalid")
        if (self.disposition == "review-required") != bool(self.warnings):
            raise ValueError("Document AI review disposition must match page warnings")
        return self


class DocumentAiExtractionEvidence(BaseModel):
    """Canonical content-free evidence derived from one exact extraction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_revision: Literal["document-ai-extraction-evidence-v1"] = (
        "document-ai-extraction-evidence-v1"
    )
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    job_id: UUID
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    processor_revision: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
    expected_page_count: int = Field(strict=True, ge=1, le=500)
    output_objects: tuple[DocumentAiOutputObject, ...] = Field(min_length=1, max_length=1_000)
    pages: tuple[DocumentAiPageEvidence, ...] = Field(min_length=1, max_length=500)
    review_required_count: int = Field(strict=True, ge=0, le=500)
    evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def issue(cls, extraction: DocumentAiExtractionResult) -> DocumentAiExtractionEvidence:
        pages = tuple(
            DocumentAiPageEvidence(
                page_number=page.page_number,
                text_sha256=hashlib.sha256(page.text.encode("utf-8")).hexdigest(),
                text_byte_size=len(page.text.encode("utf-8")),
                confidence_micros=(
                    round(page.confidence * 1_000_000)
                    if page.confidence is not None
                    else None
                ),
                disposition=page.disposition,
                warnings=page.warnings,
                output_uri=page.output_uri,
                output_generation=page.output_generation,
            )
            for page in extraction.pages
        )
        document: dict[str, object] = {
            "schema_revision": "document-ai-extraction-evidence-v1",
            "idempotency_key": extraction.idempotency_key,
            "job_id": str(extraction.job_id),
            "source_sha256": extraction.source.sha256,
            "processor_revision": extraction.processor_revision,
            "expected_page_count": extraction.expected_page_count,
            "output_objects": [
                output.model_dump(mode="json") for output in extraction.output_objects
            ],
            "pages": [page.model_dump(mode="json") for page in pages],
            "review_required_count": sum(
                page.disposition == "review-required" for page in pages
            ),
        }
        return cls.model_validate(
            {**document, "evidence_digest": _canonical_digest(document)}
        )

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        document = self.model_dump(mode="json", exclude={"evidence_digest"})
        if self.evidence_digest != _canonical_digest(document):
            raise ValueError("Document AI extraction evidence digest is invalid")
        if [page.page_number for page in self.pages] != list(
            range(1, self.expected_page_count + 1)
        ):
            raise ValueError("Document AI evidence must contain every page exactly once")
        if self.review_required_count != sum(
            page.disposition == "review-required" for page in self.pages
        ):
            raise ValueError("Document AI review-required count is invalid")
        outputs = {(item.uri, item.generation) for item in self.output_objects}
        if any(
            (page.output_uri, page.output_generation) not in outputs
            for page in self.pages
        ):
            raise ValueError("Document AI evidence page output lineage is invalid")
        return self

    def canonical_payload(self) -> str:
        return _canonical_json(self.model_dump(mode="json", exclude={"evidence_digest"}))


class DocumentAiReconciliationFailureEvidence(BaseModel):
    """Content-free durable failure/backoff evidence for one reconciliation attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_revision: Literal["document-ai-reconciliation-failure-v1"] = (
        "document-ai-reconciliation-failure-v1"
    )
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    job_id: UUID
    operation_name: str
    attempt: int = Field(strict=True, ge=1, le=3)
    failure_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    retryable: bool
    disposition: Literal["retry-scheduled", "quarantined"]
    observed_at: datetime
    next_retry_at: datetime | None
    evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def issue(
        cls,
        *,
        receipt: DocumentAiOperationReceipt,
        attempt: int,
        failure_code: str,
        retryable: bool,
        observed_at: datetime,
        next_retry_at: datetime | None,
    ) -> DocumentAiReconciliationFailureEvidence:
        disposition = "retry-scheduled" if next_retry_at is not None else "quarantined"
        document: dict[str, object] = {
            "schema_revision": "document-ai-reconciliation-failure-v1",
            "idempotency_key": receipt.idempotency_key,
            "job_id": str(receipt.job_id),
            "operation_name": receipt.operation_name,
            "attempt": attempt,
            "failure_code": failure_code,
            "retryable": retryable,
            "disposition": disposition,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "next_retry_at": (
                next_retry_at.isoformat().replace("+00:00", "Z")
                if next_retry_at is not None
                else None
            ),
        }
        return cls.model_validate(
            {**document, "evidence_digest": _canonical_digest(document)}
        )

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if self.observed_at.tzinfo is None or (
            self.next_retry_at is not None and self.next_retry_at.tzinfo is None
        ):
            raise ValueError("Document AI failure timestamps must include timezone")
        if self.next_retry_at is not None and self.next_retry_at <= self.observed_at:
            raise ValueError("Document AI retry must be scheduled after the failure")
        if (self.disposition == "retry-scheduled") != (self.next_retry_at is not None):
            raise ValueError("Document AI failure disposition does not match retry schedule")
        if self.disposition == "retry-scheduled" and not self.retryable:
            raise ValueError("Permanent Document AI failures cannot be retried")
        document = self.model_dump(mode="json", exclude={"evidence_digest"})
        if self.evidence_digest != _canonical_digest(document):
            raise ValueError("Document AI failure evidence digest is invalid")
        return self

    def canonical_payload(self) -> str:
        return _canonical_json(self.model_dump(mode="json", exclude={"evidence_digest"}))


class PubSubEnvelopeDecoder(Protocol):
    def decode(self, body: bytes) -> ReceivedPubSubDelivery: ...


class CloudObjectVerifier(Protocol):
    def verify(self, delivery: PubSubIngestionDelivery) -> None: ...


class CloudObjectStager(Protocol):
    def stage(self, delivery: PubSubIngestionDelivery) -> CloudObjectIdentity: ...


class DeadLetterPublisher(Protocol):
    def publish(self, record: DeadLetterRecord) -> str: ...


class DocumentAiBatchProcessor(Protocol):
    def submit(self, request: DocumentAiBatchRequest) -> DocumentAiOperationReceipt: ...

    def reconcile(self, receipt: DocumentAiOperationReceipt) -> DocumentAiOperationReceipt: ...


class DocumentAiOutputReader(Protocol):
    def read(self, receipt: DocumentAiOperationReceipt) -> DocumentAiExtractionResult: ...


class DocumentAiReconciliationRepository(Protocol):
    def list_pending(self, *, limit: int) -> tuple[DocumentAiOperationReceipt, ...]: ...

    def find_terminal(self, idempotency_key: str) -> DocumentAiOperationReceipt | None: ...

    def record_operation(
        self,
        receipt: DocumentAiOperationReceipt,
    ) -> DocumentAiOperationReceipt: ...

    def find_extraction(
        self,
        idempotency_key: str,
    ) -> DocumentAiExtractionEvidence | None: ...

    def record_extraction(
        self,
        evidence: DocumentAiExtractionEvidence,
    ) -> DocumentAiExtractionEvidence: ...

    def record_failure(
        self,
        receipt: DocumentAiOperationReceipt,
        *,
        failure_code: str,
        retryable: bool,
    ) -> DocumentAiReconciliationFailureEvidence: ...


class DocumentAiSubmissionLedger(Protocol):
    def find(self, idempotency_key: str) -> DocumentAiOperationReceipt | None: ...

    def reserve(self, request: DocumentAiBatchRequest) -> DocumentAiOperationReceipt | None: ...

    def record(self, receipt: DocumentAiOperationReceipt) -> DocumentAiOperationReceipt: ...


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
