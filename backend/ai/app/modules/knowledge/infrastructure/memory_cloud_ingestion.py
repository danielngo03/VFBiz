from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.modules.knowledge.application.cloud_ingestion_ports import (
    CloudObjectIdentity,
    DeadLetterRecord,
    DocumentAiBatchRequest,
    DocumentAiExtractionEvidence,
    DocumentAiOperationReceipt,
    DocumentAiOperationState,
    DocumentAiReconciliationFailureEvidence,
    PubSubIngestionDelivery,
)
from app.modules.knowledge.application.ingestion_ports import (
    PermanentIngestionFailure,
    TransientIngestionFailure,
)


class AllowAllCloudObjectVerifier:
    def verify(self, delivery: PubSubIngestionDelivery) -> None:
        _ = delivery


class PassthroughCloudObjectStager:
    def stage(self, delivery: PubSubIngestionDelivery) -> CloudObjectIdentity:
        return delivery.object


class InMemoryDeadLetterPublisher:
    def __init__(self) -> None:
        self.records: list[DeadLetterRecord] = []

    def publish(self, record: DeadLetterRecord) -> str:
        self.records.append(record)
        return f"fake-dlq-{len(self.records):06d}"


class InMemoryDocumentAiSubmissionLedger:
    def __init__(self) -> None:
        self._receipts: dict[str, DocumentAiOperationReceipt] = {}
        self._reservations: dict[str, DocumentAiBatchRequest] = {}

    def find(self, idempotency_key: str) -> DocumentAiOperationReceipt | None:
        receipt = self._receipts.get(idempotency_key)
        if receipt is None and idempotency_key in self._reservations:
            raise TransientIngestionFailure("DOCUMENT_AI_SUBMISSION_IN_PROGRESS")
        return receipt

    def reserve(
        self, request: DocumentAiBatchRequest
    ) -> DocumentAiOperationReceipt | None:
        receipt = self._receipts.get(request.idempotency_key)
        if receipt is not None:
            return receipt
        existing = self._reservations.setdefault(request.idempotency_key, request)
        if existing != request:
            raise PermanentIngestionFailure("DOCUMENT_AI_IDEMPOTENCY_CONFLICT")
        if existing is not request:
            raise TransientIngestionFailure("DOCUMENT_AI_SUBMISSION_IN_PROGRESS")
        return None

    def record(
        self, receipt: DocumentAiOperationReceipt
    ) -> DocumentAiOperationReceipt:
        reservation = self._reservations.get(receipt.idempotency_key)
        if reservation is None:
            raise PermanentIngestionFailure("DOCUMENT_AI_RESERVATION_MISSING")
        existing = self._receipts.setdefault(receipt.idempotency_key, receipt)
        if existing != receipt:
            raise PermanentIngestionFailure("DOCUMENT_AI_IDEMPOTENCY_CONFLICT")
        return existing


class InMemoryDocumentAiReconciliationRepository:
    def __init__(
        self,
        pending_receipts: tuple[DocumentAiOperationReceipt, ...] = (),
        *,
        clock: Callable[[], datetime] | None = None,
        max_failure_attempts: int = 3,
    ) -> None:
        if max_failure_attempts < 1 or max_failure_attempts > 3:
            raise ValueError("Document AI failure attempt limit is invalid")
        self._pending = list(pending_receipts)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_failure_attempts = max_failure_attempts
        self.observations: list[DocumentAiOperationReceipt] = []
        self._terminal: dict[str, DocumentAiOperationReceipt] = {}
        self._extractions: dict[str, DocumentAiExtractionEvidence] = {}
        self.failures: list[DocumentAiReconciliationFailureEvidence] = []
        self._retry_after: dict[str, datetime] = {}

    def list_pending(self, *, limit: int) -> tuple[DocumentAiOperationReceipt, ...]:
        now = self._clock()
        ready = [
            receipt
            for receipt in self._pending
            if self._retry_after.get(receipt.idempotency_key, now) <= now
        ]
        return tuple(ready[:limit])

    def find_terminal(self, idempotency_key: str) -> DocumentAiOperationReceipt | None:
        return self._terminal.get(idempotency_key)

    def record_operation(
        self,
        receipt: DocumentAiOperationReceipt,
    ) -> DocumentAiOperationReceipt:
        if receipt.state == "submitted":
            raise PermanentIngestionFailure("DOCUMENT_AI_RECONCILIATION_STATE_INVALID")
        existing = self._terminal.get(receipt.idempotency_key)
        if existing is not None:
            if not _same_terminal_operation(existing, receipt):
                raise PermanentIngestionFailure("DOCUMENT_AI_TERMINAL_STATE_CONFLICT")
            return existing
        self.observations.append(receipt)
        if receipt.state in {"succeeded", "failed", "cancelled"}:
            self._terminal[receipt.idempotency_key] = receipt
        if receipt.state in {"failed", "cancelled"}:
            self._pending = [
                pending
                for pending in self._pending
                if pending.idempotency_key != receipt.idempotency_key
            ]
        return receipt

    def find_extraction(
        self,
        idempotency_key: str,
    ) -> DocumentAiExtractionEvidence | None:
        return self._extractions.get(idempotency_key)

    def record_extraction(
        self,
        evidence: DocumentAiExtractionEvidence,
    ) -> DocumentAiExtractionEvidence:
        existing = self._extractions.setdefault(evidence.idempotency_key, evidence)
        if existing != evidence:
            raise PermanentIngestionFailure("DOCUMENT_AI_EXTRACTION_EVIDENCE_CONFLICT")
        self._pending = [
            pending
            for pending in self._pending
            if pending.idempotency_key != evidence.idempotency_key
        ]
        return existing

    def record_failure(
        self,
        receipt: DocumentAiOperationReceipt,
        *,
        failure_code: str,
        retryable: bool,
    ) -> DocumentAiReconciliationFailureEvidence:
        attempt = 1 + sum(
            failure.idempotency_key == receipt.idempotency_key
            for failure in self.failures
        )
        observed_at = self._clock()
        next_retry_at = (
            observed_at + timedelta(seconds=30 * (2 ** (attempt - 1)))
            if retryable and attempt < self._max_failure_attempts
            else None
        )
        evidence = DocumentAiReconciliationFailureEvidence.issue(
            receipt=receipt,
            attempt=attempt,
            failure_code=failure_code,
            retryable=retryable,
            observed_at=observed_at,
            next_retry_at=next_retry_at,
        )
        self.failures.append(evidence)
        if next_retry_at is None:
            self._pending = [
                pending
                for pending in self._pending
                if pending.idempotency_key != receipt.idempotency_key
            ]
            self._retry_after.pop(receipt.idempotency_key, None)
        else:
            self._retry_after[receipt.idempotency_key] = next_retry_at
        return evidence


class FakeDocumentAiBatchProcessor:
    """Deterministic fake that models submit/reconcile without OCR text."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        processor_revision: str,
        max_pages_per_batch: int = 500,
    ) -> None:
        self._clock = clock
        self._processor_revision = processor_revision
        self._max_pages = max_pages_per_batch
        self._receipts: dict[str, DocumentAiOperationReceipt] = {}
        self._outcomes: dict[str, tuple[DocumentAiOperationState, str | None]] = {}
        self.submit_count = 0
        self.requests: list[DocumentAiBatchRequest] = []

    def submit(self, request: DocumentAiBatchRequest) -> DocumentAiOperationReceipt:
        existing = self._receipts.get(request.idempotency_key)
        if existing is not None:
            if (
                existing.job_id != request.job_id
                or existing.input != request.input
                or existing.fencing_token != request.fencing_token
            ):
                raise PermanentIngestionFailure("DOCUMENT_AI_IDEMPOTENCY_CONFLICT")
            return existing
        if request.processor_revision != self._processor_revision:
            raise PermanentIngestionFailure("DOCUMENT_AI_PROCESSOR_REVISION_MISMATCH")
        if request.page_count > self._max_pages:
            raise PermanentIngestionFailure("DOCUMENT_AI_PAGE_LIMIT_EXCEEDED")
        self.submit_count += 1
        self.requests.append(request)
        now = self._clock()
        receipt = DocumentAiOperationReceipt(
            idempotency_key=request.idempotency_key,
            job_id=request.job_id,
            operation_name=(
                "projects/synthetic/locations/test/operations/"
                f"fake-{self.submit_count:06d}"
            ),
            input=request.input,
            output_prefix=request.output_prefix,
            processor_revision=request.processor_revision,
            page_count=request.page_count,
            fencing_token=request.fencing_token,
            state="submitted",
            submitted_at=now,
            reconciled_at=now,
        )
        self._receipts[request.idempotency_key] = receipt
        return receipt

    def set_outcome(
        self,
        operation_name: str,
        state: DocumentAiOperationState,
        *,
        provider_error_code: str | None = None,
    ) -> None:
        if state == "failed" and provider_error_code is None:
            raise ValueError("failed fake operation requires an error code")
        if state != "failed" and provider_error_code is not None:
            raise ValueError("fake error code is only valid for failed operations")
        self._outcomes[operation_name] = (state, provider_error_code)

    def reconcile(
        self, receipt: DocumentAiOperationReceipt
    ) -> DocumentAiOperationReceipt:
        state, error = self._outcomes.get(receipt.operation_name, ("running", None))
        return DocumentAiOperationReceipt.model_validate(
            receipt.model_copy(
                update={
                    "state": state,
                    "provider_error_code": error,
                    "reconciled_at": self._clock(),
                }
            )
        )


def _same_terminal_operation(
    first: DocumentAiOperationReceipt,
    second: DocumentAiOperationReceipt,
) -> bool:
    return (
        first.idempotency_key == second.idempotency_key
        and first.job_id == second.job_id
        and first.operation_name == second.operation_name
        and first.input == second.input
        and first.output_prefix == second.output_prefix
        and first.processor_revision == second.processor_revision
        and first.page_count == second.page_count
        and first.fencing_token == second.fencing_token
        and first.state == second.state
        and first.provider_error_code == second.provider_error_code
        and first.submitted_at == second.submitted_at
    )
