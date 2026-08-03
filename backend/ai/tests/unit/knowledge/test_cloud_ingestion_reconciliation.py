from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.modules.knowledge.application.cloud_ingestion_ports import (
    CloudObjectIdentity,
    DocumentAiBatchRequest,
    DocumentAiExtractionEvidence,
    DocumentAiExtractionResult,
    DocumentAiOperationReceipt,
    DocumentAiOutputObject,
    DocumentAiPageExtraction,
)
from app.modules.knowledge.application.cloud_ingestion_reconciliation import (
    DocumentAiReconciliationService,
)
from app.modules.knowledge.application.ingestion_ports import (
    PermanentIngestionFailure,
    TransientIngestionFailure,
)
from app.modules.knowledge.infrastructure.memory_cloud_ingestion import (
    FakeDocumentAiBatchProcessor,
    InMemoryDocumentAiReconciliationRepository,
)

NOW = datetime(2026, 8, 1, 6, tzinfo=UTC)
JOB_ID = UUID("00000000-0000-4000-8000-000000000199")


def _request() -> DocumentAiBatchRequest:
    return DocumentAiBatchRequest(
        idempotency_key=hashlib.sha256(b"reconcile-0199").hexdigest(),
        job_id=JOB_ID,
        input=CloudObjectIdentity(
            uri="gs://vinfast-503003-derived-dev/document-ai-input/source.pdf",
            generation=11,
            metageneration=4,
            sha256="a" * 64,
            byte_size=42,
            crc32c="zUSYPA==",
        ),
        output_prefix="gs://vinfast-503003-ocr-output-dev/document-ai/jobs/0199/",
        processor_revision="pretrained-ocr-v2.1-2024-06-21",
        page_count=1,
        fencing_token=3,
    )


def _submitted() -> tuple[FakeDocumentAiBatchProcessor, DocumentAiOperationReceipt]:
    processor = FakeDocumentAiBatchProcessor(
        clock=lambda: NOW,
        processor_revision="pretrained-ocr-v2.1-2024-06-21",
    )
    return processor, processor.submit(_request())


def _extraction(receipt: DocumentAiOperationReceipt) -> DocumentAiExtractionResult:
    output = DocumentAiOutputObject(
        uri="gs://vinfast-503003-ocr-output-dev/document-ai/jobs/0199/output-1.json",
        generation=19,
        metageneration=2,
        byte_size=512,
        crc32c="zUSYPA==",
        sha256="b" * 64,
    )
    return DocumentAiExtractionResult(
        idempotency_key=receipt.idempotency_key,
        job_id=receipt.job_id,
        source=receipt.input,
        processor_revision=receipt.processor_revision,
        expected_page_count=1,
        output_objects=(output,),
        pages=(
            DocumentAiPageExtraction(
                source_sha256=receipt.input.sha256,
                page_number=1,
                text="Nội dung tổng hợp hoàn toàn giả lập.",
                confidence=0.97,
                disposition="document-ai",
                warnings=(),
                processor_revision=receipt.processor_revision,
                output_uri=output.uri,
                output_generation=output.generation,
            ),
        ),
    )


class _OutputReader:
    def __init__(self, extraction: DocumentAiExtractionResult) -> None:
        self._extraction = extraction
        self.calls = 0

    def read(self, receipt: DocumentAiOperationReceipt) -> DocumentAiExtractionResult:
        self.calls += 1
        assert receipt.state == "succeeded"
        return self._extraction


def test_reconciler_persists_running_observation_without_reading_output() -> None:
    processor, receipt = _submitted()
    reader = _OutputReader(_extraction(receipt))
    repository = InMemoryDocumentAiReconciliationRepository((receipt,))
    service = DocumentAiReconciliationService(
        processor=processor,
        output_reader=reader,
        repository=repository,
    )

    outcome = service.reconcile_pending()

    assert outcome.processed_count == 1
    assert outcome.outcomes[0].state == "running"
    assert outcome.outcomes[0].evidence_digest is None
    assert reader.calls == 0
    assert repository.observations[0].state == "running"


def test_reconciler_seals_content_free_evidence_once_and_replays_terminal() -> None:
    processor, receipt = _submitted()
    processor.set_outcome(receipt.operation_name, "succeeded")
    reader = _OutputReader(_extraction(receipt))
    repository = InMemoryDocumentAiReconciliationRepository((receipt,))
    service = DocumentAiReconciliationService(
        processor=processor,
        output_reader=reader,
        repository=repository,
    )

    first = service.reconcile(receipt)
    replay = service.reconcile(receipt)
    evidence = repository.find_extraction(receipt.idempotency_key)

    assert first == replay
    assert first.state == "succeeded"
    assert first.evidence_digest is not None
    assert reader.calls == 1
    assert evidence is not None
    assert evidence.pages[0].text_sha256 == hashlib.sha256(
        "Nội dung tổng hợp hoàn toàn giả lập.".encode()
    ).hexdigest()
    assert "Nội dung" not in evidence.model_dump_json()


def test_reconciler_recovers_extraction_after_terminal_observation_restart() -> None:
    processor, receipt = _submitted()
    terminal = receipt.model_copy(
        update={"state": "succeeded", "reconciled_at": NOW + timedelta(seconds=30)}
    )
    repository = InMemoryDocumentAiReconciliationRepository((receipt,))
    repository.record_operation(DocumentAiOperationReceipt.model_validate(terminal))
    reader = _OutputReader(_extraction(receipt))
    restarted = DocumentAiReconciliationService(
        processor=processor,
        output_reader=reader,
        repository=repository,
    )

    batch = restarted.reconcile_pending()
    outcome = batch.outcomes[0]

    assert batch.processed_count == 1
    assert outcome.state == "succeeded"
    assert outcome.evidence_digest is not None
    assert reader.calls == 1
    assert repository.list_pending(limit=1) == ()


def test_reconciler_rejects_provider_operation_identity_mutation() -> None:
    _processor, receipt = _submitted()

    class _MutatingProcessor:
        def submit(self, request: DocumentAiBatchRequest) -> DocumentAiOperationReceipt:
            _ = request
            return receipt

        def reconcile(
            self, receipt: DocumentAiOperationReceipt
        ) -> DocumentAiOperationReceipt:
            return receipt.model_copy(
                update={
                    "operation_name": (
                        "projects/attacker/locations/test/operations/forged"
                    ),
                    "state": "running",
                }
            )

    reader = _OutputReader(_extraction(receipt))
    repository = InMemoryDocumentAiReconciliationRepository((receipt,))
    service = DocumentAiReconciliationService(
        processor=_MutatingProcessor(),
        output_reader=reader,
        repository=repository,
    )

    with pytest.raises(
        PermanentIngestionFailure,
        match="DOCUMENT_AI_OPERATION_IDENTITY_MISMATCH",
    ):
        service.reconcile(receipt)

    assert repository.observations == []
    assert reader.calls == 0


def test_extraction_evidence_rejects_digest_tamper() -> None:
    _processor, receipt = _submitted()
    evidence = DocumentAiExtractionEvidence.issue(_extraction(receipt))

    with pytest.raises(ValueError, match="evidence digest is invalid"):
        DocumentAiExtractionEvidence.model_validate(
            {**evidence.model_dump(mode="json"), "review_required_count": 1}
        )


def test_extraction_evidence_quantizes_confidence_without_float_digest() -> None:
    _processor, receipt = _submitted()
    extraction = _extraction(receipt)
    evidence = DocumentAiExtractionEvidence.issue(
        extraction.model_copy(
            update={
                "pages": (
                    extraction.pages[0].model_copy(update={"confidence": 1e-7}),
                )
            }
        )
    )

    assert evidence.pages[0].confidence_micros == 0
    assert "1e-" not in evidence.canonical_payload()


def test_reconciler_rejects_extraction_outside_receipt_output_prefix() -> None:
    processor, receipt = _submitted()
    processor.set_outcome(receipt.operation_name, "succeeded")
    extraction = _extraction(receipt)
    outside = extraction.output_objects[0].model_copy(
        update={"uri": "gs://vinfast-503003-derived-dev/other/output.json"}
    )
    forged = extraction.model_copy(
        update={
            "output_objects": (outside,),
            "pages": (
                extraction.pages[0].model_copy(update={"output_uri": outside.uri}),
            ),
        }
    )
    service = DocumentAiReconciliationService(
        processor=processor,
        output_reader=_OutputReader(forged),
        repository=InMemoryDocumentAiReconciliationRepository((receipt,)),
    )

    outcome = service.reconcile_pending().outcomes[0]

    assert outcome.state == "quarantined"
    assert outcome.failure_code == "DOCUMENT_AI_EXTRACTION_IDENTITY_MISMATCH"


def test_permanent_poison_output_is_quarantined_without_starving_next_job() -> None:
    processor, first = _submitted()
    processor.set_outcome(first.operation_name, "succeeded")
    second = first.model_copy(
        update={
            "idempotency_key": hashlib.sha256(b"reconcile-0200").hexdigest(),
            "job_id": UUID("00000000-0000-4000-8000-000000000200"),
            "operation_name": "projects/synthetic/locations/test/operations/fake-000002",
        }
    )

    class _PoisonReader:
        def read(
            self,
            receipt: DocumentAiOperationReceipt,
        ) -> DocumentAiExtractionResult:
            assert receipt.idempotency_key == first.idempotency_key
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_JSON_INVALID")

    repository = InMemoryDocumentAiReconciliationRepository((first, second))
    service = DocumentAiReconciliationService(
        processor=processor,
        output_reader=_PoisonReader(),
        repository=repository,
    )

    batch = service.reconcile_pending(limit=2)

    assert [outcome.state for outcome in batch.outcomes] == ["quarantined", "running"]
    assert batch.outcomes[0].failure_code == "DOCUMENT_AI_OUTPUT_JSON_INVALID"
    assert [item.idempotency_key for item in repository.list_pending(limit=2)] == [
        second.idempotency_key
    ]
    assert [item.state for item in repository.observations] == ["succeeded", "running"]


def test_transient_poison_output_uses_bounded_backoff_then_quarantines() -> None:
    processor, receipt = _submitted()
    processor.set_outcome(receipt.operation_name, "succeeded")
    current = [NOW]

    class _UnavailableReader:
        def read(
            self,
            receipt: DocumentAiOperationReceipt,
        ) -> DocumentAiExtractionResult:
            _ = receipt
            raise TransientIngestionFailure("DOCUMENT_AI_OUTPUT_PROVIDER_UNAVAILABLE")

    repository = InMemoryDocumentAiReconciliationRepository(
        (receipt,),
        clock=lambda: current[0],
    )
    service = DocumentAiReconciliationService(
        processor=processor,
        output_reader=_UnavailableReader(),
        repository=repository,
    )

    first = service.reconcile_pending()
    immediate = service.reconcile_pending()
    current[0] += timedelta(seconds=30)
    second = service.reconcile_pending()
    current[0] += timedelta(seconds=60)
    third = service.reconcile_pending()

    assert first.outcomes[0].state == "retry-scheduled"
    assert immediate.processed_count == 0
    assert second.outcomes[0].state == "retry-scheduled"
    assert third.outcomes[0].state == "quarantined"
    assert repository.list_pending(limit=1) == ()
    assert [failure.attempt for failure in repository.failures] == [1, 2, 3]


def test_reconcile_batch_limit_is_bounded() -> None:
    processor, receipt = _submitted()
    service = DocumentAiReconciliationService(
        processor=processor,
        output_reader=_OutputReader(_extraction(receipt)),
        repository=InMemoryDocumentAiReconciliationRepository((receipt,)),
    )

    with pytest.raises(ValueError, match="between 1 and 5"):
        service.reconcile_pending(limit=6)
