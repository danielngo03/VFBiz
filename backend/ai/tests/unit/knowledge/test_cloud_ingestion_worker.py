from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from app.modules.knowledge.application.cloud_ingestion_ports import (
    CloudObjectIdentity,
    PubSubIngestionDelivery,
)
from app.modules.knowledge.application.cloud_ingestion_worker import CloudIngestionWorker
from app.modules.knowledge.infrastructure.gcp_cloud_ingestion import (
    GcpPubSubPushEnvelopeDecoder,
)
from app.modules.knowledge.infrastructure.memory_cloud_ingestion import (
    AllowAllCloudObjectVerifier,
    FakeDocumentAiBatchProcessor,
    InMemoryDeadLetterPublisher,
    PassthroughCloudObjectStager,
)

NOW = datetime(2026, 7, 30, tzinfo=UTC)
JOB_ID = UUID("00000000-0000-4000-8000-000000000199")
SUBSCRIPTION = "projects/vinfast-503003/subscriptions/worker-dev"
PROCESSOR_REVISION = "pretrained-ocr-v2.1-2024-06-21"


def _body(*, page_count: int = 12, fencing_token: int = 3) -> bytes:
    delivery = PubSubIngestionDelivery(
        receipt_id="receipt.0199",
        job_id=JOB_ID,
        object=CloudObjectIdentity(
            uri="gs://vinfast-503003-intake-dev/sha256/aa/object.pdf",
            generation=7,
            metageneration=3,
            sha256="a" * 64,
            byte_size=42,
            crc32c="zUSYPA==",
        ),
        page_count=page_count,
        fencing_token=fencing_token,
        published_at=NOW,
    )
    return json.dumps(
        {
            "message": {
                "messageId": "message-1",
                "data": base64.b64encode(delivery.model_dump_json().encode()).decode(),
            },
            "subscription": SUBSCRIPTION,
            "deliveryAttempt": 1,
        }
    ).encode()


def _worker(
    processor: FakeDocumentAiBatchProcessor,
    dead_letters: InMemoryDeadLetterPublisher,
) -> CloudIngestionWorker:
    return CloudIngestionWorker(
        decoder=GcpPubSubPushEnvelopeDecoder(expected_subscription=SUBSCRIPTION),
        object_verifier=AllowAllCloudObjectVerifier(),
        object_stager=PassthroughCloudObjectStager(),
        processor=processor,
        dead_letters=dead_letters,
        output_bucket="vinfast-503003-ocr-output-dev",
        processor_revision=PROCESSOR_REVISION,
        clock=lambda: NOW,
    )


def test_worker_submits_pointer_only_request_idempotently() -> None:
    processor = FakeDocumentAiBatchProcessor(
        clock=lambda: NOW,
        processor_revision=PROCESSOR_REVISION,
    )
    dead_letters = InMemoryDeadLetterPublisher()
    worker = _worker(processor, dead_letters)

    first = worker.dispatch(_body())
    replay = worker.dispatch(_body())

    assert first.status == replay.status == "accepted"
    assert first.operation_name == replay.operation_name
    assert processor.submit_count == 1
    assert dead_letters.records == []


def test_worker_dead_letters_permanent_processor_failure_without_content() -> None:
    processor = FakeDocumentAiBatchProcessor(
        clock=lambda: NOW,
        processor_revision=PROCESSOR_REVISION,
        max_pages_per_batch=10,
    )
    dead_letters = InMemoryDeadLetterPublisher()

    result = _worker(processor, dead_letters).dispatch(_body(page_count=12))

    assert result.status == "dead_lettered"
    assert result.operation_name is None
    assert len(dead_letters.records) == 1
    assert dead_letters.records[0].failure_code == "DOCUMENT_AI_PAGE_LIMIT_EXCEEDED"
    assert "text" not in dead_letters.records[0].model_dump_json().lower()


def test_worker_rejects_changed_fence_without_resubmitting_same_source() -> None:
    processor = FakeDocumentAiBatchProcessor(
        clock=lambda: NOW,
        processor_revision=PROCESSOR_REVISION,
    )
    dead_letters = InMemoryDeadLetterPublisher()
    worker = _worker(processor, dead_letters)

    first = worker.dispatch(_body(fencing_token=3))
    second = worker.dispatch(_body(fencing_token=4))

    assert first.status == "accepted"
    assert second.status == "dead_lettered"
    assert processor.submit_count == 1
    assert dead_letters.records[0].failure_code == "DOCUMENT_AI_IDEMPOTENCY_CONFLICT"
