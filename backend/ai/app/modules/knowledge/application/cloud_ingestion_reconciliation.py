from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.knowledge.application.cloud_ingestion_ports import (
    DocumentAiBatchProcessor,
    DocumentAiExtractionEvidence,
    DocumentAiOperationReceipt,
    DocumentAiOutputReader,
    DocumentAiReconciliationFailureEvidence,
    DocumentAiReconciliationRepository,
)
from app.modules.knowledge.application.ingestion_ports import (
    PermanentIngestionFailure,
    TransientIngestionFailure,
)


class DocumentAiReconciliationOutcome(BaseModel):
    """Content-free result safe for scheduler logs and operator APIs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_revision: Literal["document-ai-reconciliation-outcome-v1"] = (
        "document-ai-reconciliation-outcome-v1"
    )
    idempotency_key: str
    job_id: UUID
    operation_name: str
    state: Literal[
        "running",
        "succeeded",
        "failed",
        "cancelled",
        "retry-scheduled",
        "quarantined",
    ]
    reconciled_at: datetime
    evidence_digest: str | None
    review_required_count: int | None
    failure_code: str | None = None


class DocumentAiReconciliationBatchOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_revision: Literal["document-ai-reconciliation-batch-v1"] = (
        "document-ai-reconciliation-batch-v1"
    )
    processed_count: int
    outcomes: tuple[DocumentAiReconciliationOutcome, ...]


class DocumentAiReconciliationService:
    """Persist operation observations before deriving content-free extraction evidence."""

    def __init__(
        self,
        *,
        processor: DocumentAiBatchProcessor,
        output_reader: DocumentAiOutputReader,
        repository: DocumentAiReconciliationRepository,
    ) -> None:
        self._processor = processor
        self._output_reader = output_reader
        self._repository = repository

    def reconcile_pending(self, *, limit: int = 1) -> DocumentAiReconciliationBatchOutcome:
        if limit < 1 or limit > 5:
            raise ValueError("Document AI reconciliation batch limit must be between 1 and 5")
        outcomes: list[DocumentAiReconciliationOutcome] = []
        for receipt in self._repository.list_pending(limit=limit):
            try:
                outcomes.append(self.reconcile(receipt))
            except (PermanentIngestionFailure, TransientIngestionFailure) as error:
                failure = self._repository.record_failure(
                    receipt,
                    failure_code=error.code,
                    retryable=isinstance(error, TransientIngestionFailure),
                )
                outcomes.append(_failure_outcome(failure))
        return DocumentAiReconciliationBatchOutcome(
            processed_count=len(outcomes),
            outcomes=tuple(outcomes),
        )

    def reconcile(
        self,
        receipt: DocumentAiOperationReceipt,
    ) -> DocumentAiReconciliationOutcome:
        terminal = self._repository.find_terminal(receipt.idempotency_key)
        if terminal is None:
            observed = self._processor.reconcile(receipt)
            _assert_same_operation(receipt, observed)
            if observed.state == "submitted":
                raise PermanentIngestionFailure("DOCUMENT_AI_RECONCILIATION_STATE_INVALID")
            terminal_or_observed = self._repository.record_operation(observed)
        else:
            _assert_same_operation(receipt, terminal)
            terminal_or_observed = terminal

        if terminal_or_observed.state == "submitted":
            raise PermanentIngestionFailure("DOCUMENT_AI_RECONCILIATION_STATE_INVALID")

        evidence = self._extraction_evidence(terminal_or_observed)
        return DocumentAiReconciliationOutcome(
            idempotency_key=terminal_or_observed.idempotency_key,
            job_id=terminal_or_observed.job_id,
            operation_name=terminal_or_observed.operation_name,
            state=terminal_or_observed.state,
            reconciled_at=terminal_or_observed.reconciled_at,
            evidence_digest=evidence.evidence_digest if evidence is not None else None,
            review_required_count=(
                evidence.review_required_count if evidence is not None else None
            ),
        )

    def _extraction_evidence(
        self,
        receipt: DocumentAiOperationReceipt,
    ) -> DocumentAiExtractionEvidence | None:
        if receipt.state != "succeeded":
            return None
        existing = self._repository.find_extraction(receipt.idempotency_key)
        if existing is not None:
            _assert_evidence_matches_receipt(existing, receipt)
            return existing
        extraction = self._output_reader.read(receipt)
        evidence = DocumentAiExtractionEvidence.issue(extraction)
        _assert_evidence_matches_receipt(evidence, receipt)
        return self._repository.record_extraction(evidence)


def _assert_same_operation(
    expected: DocumentAiOperationReceipt,
    observed: DocumentAiOperationReceipt,
) -> None:
    if (
        observed.idempotency_key != expected.idempotency_key
        or observed.job_id != expected.job_id
        or observed.operation_name != expected.operation_name
        or observed.input != expected.input
        or observed.output_prefix != expected.output_prefix
        or observed.processor_revision != expected.processor_revision
        or observed.page_count != expected.page_count
        or observed.fencing_token != expected.fencing_token
        or observed.submitted_at != expected.submitted_at
    ):
        raise PermanentIngestionFailure("DOCUMENT_AI_OPERATION_IDENTITY_MISMATCH")


def _assert_evidence_matches_receipt(
    evidence: DocumentAiExtractionEvidence,
    receipt: DocumentAiOperationReceipt,
) -> None:
    if (
        evidence.idempotency_key != receipt.idempotency_key
        or evidence.job_id != receipt.job_id
        or evidence.source_sha256 != receipt.input.sha256
        or evidence.processor_revision != receipt.processor_revision
        or evidence.expected_page_count != receipt.page_count
        or any(
            not output.uri.startswith(receipt.output_prefix)
            for output in evidence.output_objects
        )
    ):
        raise PermanentIngestionFailure("DOCUMENT_AI_EXTRACTION_IDENTITY_MISMATCH")


def _failure_outcome(
    evidence: DocumentAiReconciliationFailureEvidence,
) -> DocumentAiReconciliationOutcome:
    return DocumentAiReconciliationOutcome(
        idempotency_key=evidence.idempotency_key,
        job_id=evidence.job_id,
        operation_name=evidence.operation_name,
        state=evidence.disposition,
        reconciled_at=evidence.observed_at,
        evidence_digest=evidence.evidence_digest,
        review_required_count=None,
        failure_code=evidence.failure_code,
    )


__all__ = [
    "DocumentAiReconciliationBatchOutcome",
    "DocumentAiReconciliationOutcome",
    "DocumentAiReconciliationService",
]
