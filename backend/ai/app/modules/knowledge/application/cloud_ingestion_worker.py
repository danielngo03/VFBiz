from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.knowledge.application.cloud_ingestion_ports import (
    CloudObjectIdentity,
    CloudObjectStager,
    CloudObjectVerifier,
    DeadLetterPublisher,
    DeadLetterRecord,
    DocumentAiBatchProcessor,
    DocumentAiBatchRequest,
    PubSubEnvelopeDecoder,
    ReceivedPubSubDelivery,
)
from app.modules.knowledge.application.ingestion_ports import PermanentIngestionFailure


class CloudIngestionDispatchResult(BaseModel):
    """Sanitized acknowledgement. It never contains document bytes or extracted text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["accepted", "dead_lettered"]
    message_id: str
    receipt_id: str
    operation_name: str | None = Field(default=None, max_length=512)
    dead_letter_message_id: str | None = Field(default=None, max_length=256)


class CloudIngestionWorker:
    """Decode one pointer-only delivery and submit a bounded Document AI batch."""

    def __init__(
        self,
        *,
        decoder: PubSubEnvelopeDecoder,
        object_verifier: CloudObjectVerifier,
        object_stager: CloudObjectStager,
        processor: DocumentAiBatchProcessor,
        dead_letters: DeadLetterPublisher,
        output_bucket: str,
        processor_revision: str,
        clock: Callable[[], datetime],
    ) -> None:
        if not output_bucket or "/" in output_bucket:
            raise ValueError("output bucket identifier is invalid")
        if not processor_revision:
            raise ValueError("processor revision is required")
        self._decoder = decoder
        self._object_verifier = object_verifier
        self._object_stager = object_stager
        self._processor = processor
        self._dead_letters = dead_letters
        self._output_bucket = output_bucket
        self._processor_revision = processor_revision
        self._clock = clock

    def dispatch(self, body: bytes) -> CloudIngestionDispatchResult:
        received = self._decoder.decode(body)
        try:
            self._object_verifier.verify(received.delivery)
            staged = self._object_stager.stage(received.delivery)
            request = self._request(received, staged=staged)
            receipt = self._processor.submit(request)
        except PermanentIngestionFailure as error:
            failure_code = _failure_code(error)
            dead_letter_message_id = self._dead_letters.publish(
                DeadLetterRecord(
                    delivery=received.delivery,
                    failure_code=failure_code,
                    failed_at=self._clock(),
                    attempt=received.delivery_attempt,
                )
            )
            return CloudIngestionDispatchResult(
                status="dead_lettered",
                message_id=received.message_id,
                receipt_id=received.delivery.receipt_id,
                dead_letter_message_id=dead_letter_message_id,
            )
        return CloudIngestionDispatchResult(
            status="accepted",
            message_id=received.message_id,
            receipt_id=received.delivery.receipt_id,
            operation_name=receipt.operation_name,
        )

    def _request(
        self,
        received: ReceivedPubSubDelivery,
        *,
        staged: CloudObjectIdentity,
    ) -> DocumentAiBatchRequest:
        delivery = received.delivery
        output_prefix = (
            f"gs://{self._output_bucket}/document-ai/jobs/sha256-{delivery.object.sha256}/"
            f"source-generation-{delivery.object.generation}/"
            f"processor-{self._processor_revision}/"
        )
        canonical = "\n".join(
            (
                delivery.object.uri,
                str(delivery.object.generation),
                delivery.object.sha256,
                str(delivery.object.byte_size),
                delivery.object.crc32c,
                str(delivery.page_count),
                self._processor_revision,
                output_prefix,
            )
        ).encode("utf-8")
        return DocumentAiBatchRequest(
            idempotency_key=hashlib.sha256(canonical).hexdigest(),
            job_id=delivery.job_id,
            input=staged,
            output_prefix=output_prefix,
            processor_revision=self._processor_revision,
            page_count=delivery.page_count,
            fencing_token=delivery.fencing_token,
        )


def _failure_code(error: PermanentIngestionFailure) -> str:
    candidate = str(error).strip()
    if candidate and candidate.replace("_", "").isalnum() and candidate.isupper():
        return candidate[:80]
    return "PERMANENT_INGESTION_FAILURE"
