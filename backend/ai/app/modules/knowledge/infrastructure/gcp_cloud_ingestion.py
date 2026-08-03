from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
import unicodedata
from collections.abc import Callable
from datetime import datetime
from typing import cast
from urllib.parse import quote, unquote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.modules.knowledge.application.cloud_ingestion_ports import (
    CloudObjectIdentity,
    DeadLetterRecord,
    DocumentAiBatchRequest,
    DocumentAiExtractionResult,
    DocumentAiOperationReceipt,
    DocumentAiOutputObject,
    DocumentAiPageExtraction,
    DocumentAiSubmissionLedger,
    PubSubIngestionDelivery,
    ReceivedPubSubDelivery,
)
from app.modules.knowledge.application.ingestion_ports import (
    PermanentIngestionFailure,
    TransientIngestionFailure,
)

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_DOCUMENT_AI_FIELD_MASK = (
    "text,pages.pageNumber,pages.layout,pages.tokens.layout,shardInfo,error"
)


class _PubSubMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    data: str = Field(min_length=4, max_length=24_000)
    messageId: str = Field(  # noqa: N815 - Google wire name
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$"
    )


class _PubSubPush(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: _PubSubMessage
    subscription: str = Field(min_length=1, max_length=512)
    deliveryAttempt: int = Field(  # noqa: N815 - Google wire name
        default=1, strict=True, ge=1, le=100
    )


class GcpPubSubPushEnvelopeDecoder:
    """Decode the bounded Pub/Sub push wire shape into a pointer-only delivery."""

    def __init__(self, *, expected_subscription: str, max_envelope_bytes: int = 32_768) -> None:
        if not expected_subscription or len(expected_subscription) > 512:
            raise ValueError("expected Pub/Sub subscription is invalid")
        if max_envelope_bytes < 1_024 or max_envelope_bytes > 65_536:
            raise ValueError("Pub/Sub envelope limit must be between 1 KiB and 64 KiB")
        self._expected_subscription = expected_subscription
        self._max_envelope_bytes = max_envelope_bytes

    def decode(self, body: bytes) -> ReceivedPubSubDelivery:
        if not body or len(body) > self._max_envelope_bytes:
            raise PermanentIngestionFailure("PUBSUB_ENVELOPE_SIZE_INVALID")
        try:
            envelope = _PubSubPush.model_validate_json(body)
            if envelope.subscription != self._expected_subscription:
                raise PermanentIngestionFailure("PUBSUB_SUBSCRIPTION_MISMATCH")
            decoded = base64.b64decode(envelope.message.data, validate=True)
            delivery = PubSubIngestionDelivery.model_validate_json(decoded)
        except PermanentIngestionFailure:
            raise
        except (ValueError, TypeError) as error:
            raise PermanentIngestionFailure("PUBSUB_ENVELOPE_INVALID") from error
        return ReceivedPubSubDelivery(
            message_id=envelope.message.messageId,
            subscription=envelope.subscription,
            delivery_attempt=envelope.deliveryAttempt,
            delivery=delivery,
        )


class GcpMetadataAccessTokenSource:
    """Bounded, cached workload-identity token source for Cloud Run."""

    _ENDPOINT = (
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
    )

    def __init__(
        self,
        *,
        client: httpx.Client,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._monotonic = monotonic
        self._token = ""
        self._refresh_at = 0.0
        self._lock = threading.Lock()

    def __call__(self) -> str:
        now = self._monotonic()
        if self._token and now < self._refresh_at:
            return self._token
        with self._lock:
            now = self._monotonic()
            if self._token and now < self._refresh_at:
                return self._token
            response = self._client.get(
                self._ENDPOINT,
                headers={"Metadata-Flavor": "Google"},
                timeout=5,
            )
            response.raise_for_status()
            payload = _response_json_object(response, "GCP_WORKLOAD_TOKEN_INVALID")
            token = payload.get("access_token")
            expires_in = payload.get("expires_in")
            token_type = payload.get("token_type")
            if (
                not isinstance(token, str)
                or not token
                or len(token) > 8_192
                or not isinstance(expires_in, int)
                or expires_in < 60
                or expires_in > 86_400
                or token_type != "Bearer"  # noqa: S105 - OAuth token type, not a credential
            ):
                raise PermanentIngestionFailure("GCP_WORKLOAD_TOKEN_INVALID")
            self._token = token
            self._refresh_at = now + max(30, expires_in - 60)
            return token


class GcpCloudObjectVerifier:
    """Revalidate the exact immutable GCS generation immediately before OCR submit."""

    def __init__(
        self,
        *,
        allowed_buckets: tuple[str, ...],
        approved_smoke_documents: dict[str, int],
        access_token: Callable[[], str],
        client: httpx.Client,
        max_source_bytes: int = 1_073_741_824,
    ) -> None:
        if not allowed_buckets or any(
            not _RESOURCE_ID.fullmatch(value) for value in allowed_buckets
        ):
            raise ValueError("GCS verifier buckets must be explicitly allowlisted")
        self._allowed_buckets = frozenset(allowed_buckets)
        if not approved_smoke_documents or any(
            not re.fullmatch(r"[a-f0-9]{64}", digest) or page_count < 1 or page_count > 500
            for digest, page_count in approved_smoke_documents.items()
        ):
            raise ValueError("reviewed synthetic smoke manifest is required")
        self._approved_smoke_documents = dict(approved_smoke_documents)
        self._access_token = access_token
        self._client = client
        if max_source_bytes < 1 or max_source_bytes > 1_073_741_824:
            raise ValueError("GCS verifier source byte limit is invalid")
        self._max_source_bytes = max_source_bytes

    def verify(self, delivery: PubSubIngestionDelivery) -> None:
        identity = delivery.object
        if self._approved_smoke_documents.get(identity.sha256) != delivery.page_count:
            raise PermanentIngestionFailure("SYNTHETIC_SMOKE_AUTHORITY_MISMATCH")
        parsed = urlsplit(identity.uri)
        bucket = parsed.netloc
        object_name = parsed.path.lstrip("/")
        expected_name = f"sha256/{identity.sha256[:2]}/{identity.sha256}"
        if bucket not in self._allowed_buckets or object_name != expected_name:
            raise PermanentIngestionFailure("GCS_OBJECT_IDENTITY_NOT_ALLOWLISTED")
        response = self._client.get(
            "https://storage.googleapis.com/storage/v1/b/"
            f"{quote(bucket, safe='')}/o/{quote(object_name, safe='')}",
            params={"generation": str(identity.generation)},
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=30,
        )
        response.raise_for_status()
        payload = _response_json_object(response, "GCS_OBJECT_METADATA_INVALID")
        custom = payload.get("metadata")
        metadata = cast(dict[str, object], custom) if isinstance(custom, dict) else {}
        if (
            payload.get("bucket") not in {None, bucket}
            or payload.get("name") not in {None, object_name}
            or payload.get("generation") != str(identity.generation)
            or payload.get("metageneration") != str(identity.metageneration)
            or payload.get("size") != str(identity.byte_size)
            or payload.get("crc32c") != identity.crc32c
            or payload.get("contentType") != "application/pdf"
            or metadata.get("sha256") != identity.sha256
            or metadata.get("page-count") != str(delivery.page_count)
            or metadata.get("authority-class") != delivery.authority_class
        ):
            raise PermanentIngestionFailure("GCS_OBJECT_IDENTITY_MISMATCH")

        # Custom metadata is not a content-integrity proof.  Re-read the exact
        # generation and hash the bytes immediately before OCR dispatch so a
        # forged ``sha256`` label cannot authorize arbitrary content.
        media_response = self._client.stream(
            "GET",
            "https://storage.googleapis.com/storage/v1/b/"
            f"{quote(bucket, safe='')}/o/{quote(object_name, safe='')}",
            params={
                "generation": str(identity.generation),
                "ifGenerationMatch": str(identity.generation),
                "ifMetagenerationMatch": str(identity.metageneration),
                "alt": "media",
            },
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=30,
        )
        digest = hashlib.sha256()
        total = 0
        with media_response as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > self._max_source_bytes:
                    raise PermanentIngestionFailure("GCS_OBJECT_SOURCE_TOO_LARGE")
                digest.update(chunk)
        if total != identity.byte_size or digest.hexdigest() != identity.sha256:
            raise PermanentIngestionFailure("GCS_OBJECT_CONTENT_MISMATCH")


class GcpCloudObjectStager:
    """Copy one exact source generation to a create-only OCR input object."""

    def __init__(
        self,
        *,
        destination_bucket: str,
        access_token: Callable[[], str],
        client: httpx.Client,
        max_rewrite_calls: int = 6,
    ) -> None:
        _validate_resource_id(destination_bucket, "GCS staging bucket")
        if max_rewrite_calls < 1 or max_rewrite_calls > 128:
            raise ValueError("GCS rewrite call limit is invalid")
        self._destination_bucket = destination_bucket
        self._access_token = access_token
        self._client = client
        self._max_rewrite_calls = max_rewrite_calls

    def stage(self, delivery: PubSubIngestionDelivery) -> CloudObjectIdentity:
        identity = delivery.object
        parsed = urlsplit(identity.uri)
        source_bucket = parsed.netloc
        source_name = parsed.path.lstrip("/")
        destination_name = (
            f"document-ai-input/sha256/{identity.sha256[:2]}/{identity.sha256}/"
            f"source-generation-{identity.generation}.pdf"
        )
        endpoint = (
            "https://storage.googleapis.com/storage/v1/b/"
            f"{quote(source_bucket, safe='')}/o/{quote(source_name, safe='')}/rewriteTo/b/"
            f"{quote(self._destination_bucket, safe='')}/o/"
            f"{quote(destination_name, safe='')}"
        )
        token: str | None = None
        for _ in range(self._max_rewrite_calls):
            params = {
                "sourceGeneration": str(identity.generation),
                "ifGenerationMatch": "0",
            }
            if token is not None:
                params["rewriteToken"] = token
            response = self._client.post(
                endpoint,
                params=params,
                headers={"Authorization": f"Bearer {self._access_token()}"},
                json={
                    "contentType": "application/pdf",
                    "cacheControl": "no-store",
                    "metadata": {
                        "sha256": identity.sha256,
                        "source-generation": str(identity.generation),
                        "page-count": str(delivery.page_count),
                        "authority-class": delivery.authority_class,
                    },
                },
                timeout=30,
            )
            if response.status_code == 412:
                staged = self._read_staged_identity(destination_name, delivery)
                self._verify_staged_content(staged, delivery)
                return staged
            response.raise_for_status()
            payload = _response_json_object(response, "GCS_REWRITE_RECEIPT_INVALID")
            done = payload.get("done")
            if done is True:
                resource = payload.get("resource")
                if not isinstance(resource, dict):
                    raise PermanentIngestionFailure("GCS_REWRITE_RECEIPT_INVALID")
                return self._validated_staged_identity(
                    cast(dict[str, object], resource), destination_name, delivery
                )
            next_token = payload.get("rewriteToken")
            if done is not False or not isinstance(next_token, str) or not next_token:
                raise PermanentIngestionFailure("GCS_REWRITE_RECEIPT_INVALID")
            token = next_token
        raise PermanentIngestionFailure("GCS_REWRITE_CALL_LIMIT_EXCEEDED")

    def _read_staged_identity(
        self,
        destination_name: str,
        delivery: PubSubIngestionDelivery,
    ) -> CloudObjectIdentity:
        response = self._client.get(
            "https://storage.googleapis.com/storage/v1/b/"
            f"{quote(self._destination_bucket, safe='')}/o/"
            f"{quote(destination_name, safe='')}",
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=30,
        )
        response.raise_for_status()
        raw = _response_json_object(response, "GCS_STAGED_OBJECT_INVALID")
        return self._validated_staged_identity(
            raw, destination_name, delivery
        )

    def _validated_staged_identity(
        self,
        payload: dict[str, object],
        destination_name: str,
        delivery: PubSubIngestionDelivery,
    ) -> CloudObjectIdentity:
        source = delivery.object
        custom = payload.get("metadata")
        metadata = cast(dict[str, object], custom) if isinstance(custom, dict) else {}
        generation_value = payload.get("generation")
        metageneration_value = payload.get("metageneration")
        try:
            generation = int(generation_value) if isinstance(generation_value, str) else 0
            metageneration = (
                int(metageneration_value) if isinstance(metageneration_value, str) else 0
            )
        except ValueError as error:
            raise PermanentIngestionFailure("GCS_STAGED_OBJECT_INVALID") from error
        if (
            payload.get("bucket") not in {None, self._destination_bucket}
            or payload.get("name") not in {None, destination_name}
            or payload.get("size") != str(source.byte_size)
            or payload.get("crc32c") != source.crc32c
            or payload.get("contentType") != "application/pdf"
            or metadata.get("sha256") != source.sha256
            or metadata.get("source-generation") != str(source.generation)
            or metadata.get("page-count") != str(delivery.page_count)
            or metadata.get("authority-class") != delivery.authority_class
            or generation < 1
            or metageneration < 1
        ):
            raise PermanentIngestionFailure("GCS_STAGED_OBJECT_INVALID")
        return CloudObjectIdentity(
            uri=f"gs://{self._destination_bucket}/{destination_name}",
            generation=generation,
            metageneration=metageneration,
            sha256=source.sha256,
            byte_size=source.byte_size,
            crc32c=source.crc32c,
        )

    def _verify_staged_content(
        self,
        identity: CloudObjectIdentity,
        delivery: PubSubIngestionDelivery,
    ) -> None:
        """Rehash a pre-existing 412 destination before allowing OCR submit.

        Destination metadata is caller-visible bookkeeping, not a content
        proof. Generation and metageneration preconditions make the media read
        fail closed if another writer replaces the staged object between the
        metadata read and this verification.
        """
        source = delivery.object
        digest = hashlib.sha256()
        crc32c = 0xFFFFFFFF
        total = 0
        # The object name is already validated by _read_staged_identity. Keep
        # the full path in the URL rather than trusting the final segment only.
        object_name = identity.uri.split(f"gs://{self._destination_bucket}/", 1)[-1]
        endpoint = (
            "https://storage.googleapis.com/download/storage/v1/b/"
            f"{quote(self._destination_bucket, safe='')}/o/{quote(object_name, safe='')}"
        )
        with self._client.stream(
            "GET",
            endpoint,
            params={
                "alt": "media",
                "generation": str(identity.generation),
                "ifGenerationMatch": str(identity.generation),
                "ifMetagenerationMatch": str(identity.metageneration),
            },
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=30,
        ) as response:
            if response.status_code == 412:
                raise PermanentIngestionFailure("GCS_STAGED_OBJECT_CHANGED")
            response.raise_for_status()
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > source.byte_size:
                    raise PermanentIngestionFailure("GCS_STAGED_OBJECT_CONTENT_MISMATCH")
                digest.update(chunk)
                crc32c = _crc32c_update(crc32c, chunk)
        if (
            total != source.byte_size
            or digest.hexdigest() != source.sha256
            or _crc32c_base64(crc32c ^ 0xFFFFFFFF) != source.crc32c
        ):
            raise PermanentIngestionFailure("GCS_STAGED_OBJECT_CONTENT_MISMATCH")


class GcpPubSubDeadLetterPublisher:
    def __init__(
        self,
        *,
        project_id: str,
        topic_id: str,
        access_token: Callable[[], str],
        client: httpx.Client,
        max_record_bytes: int = 32_768,
    ) -> None:
        _validate_resource_id(project_id, "GCP project")
        _validate_resource_id(topic_id, "Pub/Sub topic")
        if max_record_bytes < 1_024 or max_record_bytes > 65_536:
            raise ValueError("dead-letter record limit must be between 1 KiB and 64 KiB")
        self._endpoint = (
            "https://pubsub.googleapis.com/v1/projects/"
            f"{quote(project_id, safe='')}/topics/{quote(topic_id, safe='')}:publish"
        )
        self._access_token = access_token
        self._client = client
        self._max_record_bytes = max_record_bytes

    def publish(self, record: DeadLetterRecord) -> str:
        payload = record.model_dump_json().encode()
        if len(payload) > self._max_record_bytes:
            raise PermanentIngestionFailure("DEAD_LETTER_RECORD_TOO_LARGE")
        response = self._client.post(
            self._endpoint,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            json={
                "messages": [
                    {
                        "data": base64.b64encode(payload).decode("ascii"),
                        "attributes": {
                            "schema-revision": record.schema_revision,
                            "receipt-id": record.delivery.receipt_id,
                        },
                    }
                ]
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = _response_json_object(response, "DEAD_LETTER_RECEIPT_INVALID")
        message_ids = payload.get("messageIds")
        if not isinstance(message_ids, list):
            raise PermanentIngestionFailure("DEAD_LETTER_RECEIPT_INVALID")
        bounded_ids = cast(list[object], message_ids)
        if len(bounded_ids) != 1 or not isinstance(bounded_ids[0], str) or not bounded_ids[0]:
            raise PermanentIngestionFailure("DEAD_LETTER_RECEIPT_INVALID")
        return bounded_ids[0]


class GcpDocumentAiBatchProcessor:
    """Submit once through a ledger and reconcile provider operation state."""

    def __init__(
        self,
        *,
        project_id: str,
        location: str,
        processor_id: str,
        processor_revision: str,
        allowed_input_buckets: tuple[str, ...],
        output_bucket: str,
        access_token: Callable[[], str],
        client: httpx.Client,
        ledger: DocumentAiSubmissionLedger,
        clock: Callable[[], datetime],
        max_pages_per_batch: int = 500,
        max_source_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        for value, label in (
            (project_id, "GCP project"),
            (location, "Document AI location"),
            (processor_id, "Document AI processor"),
            (processor_revision, "Document AI processor revision"),
            (output_bucket, "Document AI output bucket"),
        ):
            _validate_resource_id(value, label)
        if not allowed_input_buckets or any(
            not _RESOURCE_ID.fullmatch(value) for value in allowed_input_buckets
        ):
            raise ValueError("Document AI input buckets must be explicitly allowlisted")
        if max_pages_per_batch < 1 or max_pages_per_batch > 500:
            raise ValueError("Document AI batch page limit must be between 1 and 500")
        if max_source_bytes < 1 or max_source_bytes > 1_073_741_824:
            raise ValueError("Document AI source byte limit is invalid")
        self._operation_prefix = f"projects/{project_id}/locations/{location}/operations/"
        self._endpoint = (
            f"https://{location}-documentai.googleapis.com/v1/projects/"
            f"{quote(project_id, safe='')}/locations/{quote(location, safe='')}/processors/"
            f"{quote(processor_id, safe='')}/processorVersions/"
            f"{quote(processor_revision, safe='')}:batchProcess"
        )
        self._operations_endpoint = f"https://{location}-documentai.googleapis.com/v1/"
        self._processor_revision = processor_revision
        self._allowed_input_buckets = frozenset(allowed_input_buckets)
        self._output_bucket = output_bucket
        self._access_token = access_token
        self._client = client
        self._ledger = ledger
        self._clock = clock
        self._max_pages = max_pages_per_batch
        self._max_source_bytes = max_source_bytes

    def submit(self, request: DocumentAiBatchRequest) -> DocumentAiOperationReceipt:
        existing = self._ledger.find(request.idempotency_key)
        if existing is not None:
            _assert_same_submission(existing, request)
            return existing
        if request.processor_revision != self._processor_revision:
            raise PermanentIngestionFailure("DOCUMENT_AI_PROCESSOR_REVISION_MISMATCH")
        if request.page_count > self._max_pages:
            raise PermanentIngestionFailure("DOCUMENT_AI_PAGE_LIMIT_EXCEEDED")
        if request.input.byte_size > self._max_source_bytes:
            raise PermanentIngestionFailure("DOCUMENT_AI_SOURCE_SIZE_LIMIT_EXCEEDED")
        input_bucket = _gcs_bucket(request.input.uri)
        output_bucket = _gcs_bucket(request.output_prefix)
        if input_bucket not in self._allowed_input_buckets or output_bucket != self._output_bucket:
            raise PermanentIngestionFailure("DOCUMENT_AI_BUCKET_NOT_ALLOWLISTED")
        reserved = self._ledger.reserve(request)
        if reserved is not None:
            _assert_same_submission(reserved, request)
            return reserved
        response = self._client.post(
            self._endpoint,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            json={
                "inputDocuments": {
                    "gcsDocuments": {
                        "documents": [
                            {
                                "gcsUri": request.input.uri,
                                "mimeType": request.mime_type,
                            }
                        ]
                    }
                },
                "documentOutputConfig": {
                    "gcsOutputConfig": {
                        "gcsUri": request.output_prefix,
                        "fieldMask": _DOCUMENT_AI_FIELD_MASK,
                    }
                },
                "skipHumanReview": True,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = _response_json_object(response, "DOCUMENT_AI_OPERATION_RECEIPT_INVALID")
        operation_name = payload.get("name")
        if (
            not isinstance(operation_name, str)
            or not operation_name.startswith(self._operation_prefix)
            or not _RESOURCE_ID.fullmatch(operation_name.removeprefix(self._operation_prefix))
        ):
            raise PermanentIngestionFailure("DOCUMENT_AI_OPERATION_RECEIPT_INVALID")
        now = self._clock()
        receipt = DocumentAiOperationReceipt(
            idempotency_key=request.idempotency_key,
            job_id=request.job_id,
            operation_name=operation_name,
            input=request.input,
            output_prefix=request.output_prefix,
            processor_revision=request.processor_revision,
            page_count=request.page_count,
            fencing_token=request.fencing_token,
            state="submitted",
            submitted_at=now,
            reconciled_at=now,
        )
        recorded = self._ledger.record(receipt)
        _assert_same_submission(recorded, request)
        return recorded

    def reconcile(self, receipt: DocumentAiOperationReceipt) -> DocumentAiOperationReceipt:
        if (
            not receipt.operation_name.startswith(self._operation_prefix)
            or receipt.processor_revision != self._processor_revision
        ):
            raise PermanentIngestionFailure("DOCUMENT_AI_OPERATION_IDENTITY_MISMATCH")
        try:
            response = self._client.get(
                f"{self._operations_endpoint}{quote(receipt.operation_name, safe='/')}",
                headers={"Authorization": f"Bearer {self._access_token()}"},
                timeout=30,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            raise TransientIngestionFailure(
                "DOCUMENT_AI_OPERATION_PROVIDER_UNAVAILABLE"
            ) from None
        payload = _response_json_object(
            response,
            "DOCUMENT_AI_OPERATION_RESPONSE_INVALID",
        )
        done = payload.get("done", False)
        if not isinstance(done, bool):
            raise PermanentIngestionFailure("DOCUMENT_AI_OPERATION_RESPONSE_INVALID")
        state = "running"
        error_code = None
        if done:
            error = payload.get("error")
            if error is None:
                state = "succeeded"
            elif isinstance(error, dict):
                error_payload = cast(dict[str, object], error)
                numeric_code = error_payload.get("code")
                if not isinstance(numeric_code, int):
                    raise PermanentIngestionFailure("DOCUMENT_AI_OPERATION_RESPONSE_INVALID")
                state = "cancelled" if numeric_code == 1 else "failed"
                if state == "failed":
                    error_code = f"DOCUMENT_AI_{numeric_code}"
            else:
                raise PermanentIngestionFailure("DOCUMENT_AI_OPERATION_RESPONSE_INVALID")
        updated = receipt.model_copy(
            update={
                "state": state,
                "reconciled_at": self._clock(),
                "provider_error_code": error_code,
            }
        )
        return DocumentAiOperationReceipt.model_validate(updated)


class _GcsJsonMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bucket: str
    name: str
    generation: int
    metageneration: int
    byte_size: int
    crc32c: str


class GcpDocumentAiOutputReader:
    """Read exact Document AI JSON generations and emit page-scoped text lineage."""

    def __init__(
        self,
        *,
        output_bucket: str,
        access_token: Callable[[], str],
        client: httpx.Client,
        max_output_objects: int = 20,
        max_output_object_bytes: int = 16 * 1024 * 1024,
        max_output_total_bytes: int = 128 * 1024 * 1024,
        max_extracted_text_bytes: int = 32 * 1024 * 1024,
        min_page_confidence: float = 0.85,
        min_page_text_characters: int = 20,
        deadline_seconds: float = 180,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        _validate_resource_id(output_bucket, "Document AI output bucket")
        if max_output_objects < 1 or max_output_objects > 20:
            raise ValueError("Document AI output object limit is invalid")
        if max_output_object_bytes < 1 or max_output_object_bytes > 67_108_864:
            raise ValueError("Document AI output object byte limit is invalid")
        if (
            max_output_total_bytes < max_output_object_bytes
            or max_output_total_bytes > 268_435_456
        ):
            raise ValueError("Document AI total output byte limit is invalid")
        if max_extracted_text_bytes < 1 or max_extracted_text_bytes > 67_108_864:
            raise ValueError("Document AI extracted text byte limit is invalid")
        if min_page_confidence < 0.0 or min_page_confidence > 1.0:
            raise ValueError("Document AI page confidence threshold is invalid")
        if min_page_text_characters < 1 or min_page_text_characters > 10_000:
            raise ValueError("Document AI minimum page text length is invalid")
        if deadline_seconds < 30 or deadline_seconds > 210:
            raise ValueError("Document AI reconciliation deadline is invalid")
        self._output_bucket = output_bucket
        self._access_token = access_token
        self._client = client
        self._max_output_objects = max_output_objects
        self._max_output_object_bytes = max_output_object_bytes
        self._max_output_total_bytes = max_output_total_bytes
        self._max_extracted_text_bytes = max_extracted_text_bytes
        self._min_page_confidence = min_page_confidence
        self._min_page_text_characters = min_page_text_characters
        self._deadline_seconds = deadline_seconds
        self._monotonic = monotonic

    def read(self, receipt: DocumentAiOperationReceipt) -> DocumentAiExtractionResult:
        deadline = self._monotonic() + self._deadline_seconds
        try:
            return self._read_verified(receipt, deadline=deadline)
        except httpx.HTTPError:
            raise TransientIngestionFailure(
                "DOCUMENT_AI_OUTPUT_PROVIDER_UNAVAILABLE"
            ) from None

    def _read_verified(
        self,
        receipt: DocumentAiOperationReceipt,
        *,
        deadline: float,
    ) -> DocumentAiExtractionResult:
        self._assert_deadline(deadline)
        if receipt.state != "succeeded":
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_NOT_READY")
        bucket, prefix = _gcs_prefix(receipt.output_prefix)
        if bucket != self._output_bucket:
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_BUCKET_MISMATCH")
        listed = self._list_output_objects(prefix, deadline=deadline)
        if not listed:
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_MISSING")
        if sum(item.byte_size for item in listed) > self._max_output_total_bytes:
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_TOTAL_SIZE_EXCEEDED")

        outputs: list[DocumentAiOutputObject] = []
        pages: list[DocumentAiPageExtraction] = []
        extracted_text_bytes = 0
        for item in listed:
            self._assert_deadline(deadline)
            verified = self._read_metadata(item, deadline=deadline)
            raw, sha256 = self._download_json(verified, deadline=deadline)
            output = DocumentAiOutputObject(
                uri=f"gs://{verified.bucket}/{verified.name}",
                generation=verified.generation,
                metageneration=verified.metageneration,
                byte_size=verified.byte_size,
                crc32c=verified.crc32c,
                sha256=sha256,
            )
            outputs.append(output)
            parsed_pages = self._parse_document(
                raw,
                receipt=receipt,
                output=output,
                deadline=deadline,
            )
            extracted_text_bytes += sum(
                len(page.text.encode("utf-8")) for page in parsed_pages
            )
            if extracted_text_bytes > self._max_extracted_text_bytes:
                raise PermanentIngestionFailure(
                    "DOCUMENT_AI_EXTRACTED_TEXT_LIMIT_EXCEEDED"
                )
            pages.extend(parsed_pages)

        pages.sort(key=lambda page: page.page_number)
        self._assert_deadline(deadline)
        try:
            result = DocumentAiExtractionResult(
                idempotency_key=receipt.idempotency_key,
                job_id=receipt.job_id,
                source=receipt.input,
                processor_revision=receipt.processor_revision,
                expected_page_count=receipt.page_count,
                output_objects=tuple(outputs),
                pages=tuple(pages),
            )
        except ValueError as error:
            raise PermanentIngestionFailure("DOCUMENT_AI_PAGE_COMPLETENESS_INVALID") from error
        self._assert_deadline(deadline)
        return result

    def _list_output_objects(
        self,
        prefix: str,
        *,
        deadline: float,
    ) -> list[_GcsJsonMetadata]:
        objects: list[_GcsJsonMetadata] = []
        page_token: str | None = None
        while True:
            self._assert_deadline(deadline)
            params = {"prefix": prefix, "versions": "false"}
            if page_token is not None:
                params["pageToken"] = page_token
            response = self._client.get(
                "https://storage.googleapis.com/storage/v1/b/"
                f"{quote(self._output_bucket, safe='')}/o",
                params=params,
                headers={"Authorization": f"Bearer {self._access_token()}"},
                timeout=self._remaining_timeout(deadline),
            )
            response.raise_for_status()
            self._assert_deadline(deadline)
            payload = _response_json_object(response, "DOCUMENT_AI_OUTPUT_LIST_INVALID")
            self._assert_deadline(deadline)
            items = payload.get("items", [])
            if not isinstance(items, list):
                raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_LIST_INVALID")
            for item in cast(list[object], items):
                self._assert_deadline(deadline)
                if not isinstance(item, dict):
                    raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_LIST_INVALID")
                objects.append(self._parse_output_metadata(cast(dict[str, object], item), prefix))
                if len(objects) > self._max_output_objects:
                    raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_OBJECT_LIMIT_EXCEEDED")
            next_token = payload.get("nextPageToken")
            if next_token is None:
                break
            if not isinstance(next_token, str) or not next_token or next_token == page_token:
                raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_LIST_INVALID")
            page_token = next_token
        objects.sort(key=lambda item: (item.name, item.generation))
        self._assert_deadline(deadline)
        if len({item.name for item in objects}) != len(objects):
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_DUPLICATE_OBJECT")
        return objects

    def _read_metadata(
        self,
        listed: _GcsJsonMetadata,
        *,
        deadline: float,
    ) -> _GcsJsonMetadata:
        self._assert_deadline(deadline)
        response = self._client.get(
            "https://storage.googleapis.com/storage/v1/b/"
            f"{quote(listed.bucket, safe='')}/o/{quote(listed.name, safe='')}",
            params={"generation": str(listed.generation)},
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=self._remaining_timeout(deadline),
        )
        response.raise_for_status()
        self._assert_deadline(deadline)
        raw = _response_json_object(response, "DOCUMENT_AI_OUTPUT_METADATA_INVALID")
        self._assert_deadline(deadline)
        observed = self._parse_output_metadata(
            raw,
            listed.name.rsplit("/", 1)[0] + "/",
        )
        self._assert_deadline(deadline)
        if observed != listed:
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_METADATA_CHANGED")
        return observed

    def _parse_output_metadata(
        self,
        payload: dict[str, object],
        prefix: str,
    ) -> _GcsJsonMetadata:
        name = payload.get("name")
        generation_value = payload.get("generation")
        metageneration_value = payload.get("metageneration")
        size_value = payload.get("size")
        crc32c = payload.get("crc32c")
        try:
            generation = int(generation_value) if isinstance(generation_value, str) else 0
            metageneration = (
                int(metageneration_value) if isinstance(metageneration_value, str) else 0
            )
            byte_size = int(size_value) if isinstance(size_value, str) else 0
        except ValueError as error:
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_METADATA_INVALID") from error
        if (
            payload.get("bucket") not in {None, self._output_bucket}
            or not isinstance(name, str)
            or not name.startswith(prefix)
            or name == prefix
            or not name.endswith(".json")
            or ".." in name.split("/")
            or payload.get("contentType") != "application/json"
            or generation < 1
            or metageneration < 1
            or byte_size < 1
            or byte_size > self._max_output_object_bytes
            or not isinstance(crc32c, str)
            or re.fullmatch(r"[A-Za-z0-9+/]{6}==", crc32c) is None
        ):
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_METADATA_INVALID")
        return _GcsJsonMetadata(
            bucket=self._output_bucket,
            name=name,
            generation=generation,
            metageneration=metageneration,
            byte_size=byte_size,
            crc32c=crc32c,
        )

    def _download_json(
        self,
        identity: _GcsJsonMetadata,
        *,
        deadline: float,
    ) -> tuple[dict[str, object], str]:
        self._assert_deadline(deadline)
        digest = hashlib.sha256()
        crc32c = 0xFFFFFFFF
        content = bytearray()
        with self._client.stream(
            "GET",
            "https://storage.googleapis.com/download/storage/v1/b/"
            f"{quote(identity.bucket, safe='')}/o/{quote(identity.name, safe='')}",
            params={
                "alt": "media",
                "generation": str(identity.generation),
                "ifGenerationMatch": str(identity.generation),
                "ifMetagenerationMatch": str(identity.metageneration),
            },
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=self._remaining_timeout(deadline),
        ) as response:
            response.raise_for_status()
            self._assert_deadline(deadline)
            for chunk in response.iter_bytes():
                self._assert_deadline(deadline)
                if len(content) + len(chunk) > self._max_output_object_bytes:
                    raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_OBJECT_SIZE_EXCEEDED")
                content.extend(chunk)
                digest.update(chunk)
                crc32c = _crc32c_update(crc32c, chunk)
        if (
            len(content) != identity.byte_size
            or _crc32c_base64(crc32c ^ 0xFFFFFFFF) != identity.crc32c
        ):
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_CONTENT_MISMATCH")
        try:
            raw = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_JSON_INVALID") from error
        if not isinstance(raw, dict):
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_JSON_INVALID")
        self._assert_deadline(deadline)
        return cast(dict[str, object], raw), digest.hexdigest()

    def _assert_deadline(self, deadline: float) -> None:
        if self._monotonic() >= deadline:
            raise TransientIngestionFailure(
                "DOCUMENT_AI_RECONCILIATION_DEADLINE_EXCEEDED"
            )

    def _remaining_timeout(self, deadline: float) -> float:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise TransientIngestionFailure(
                "DOCUMENT_AI_RECONCILIATION_DEADLINE_EXCEEDED"
            )
        return min(30.0, remaining)

    def _parse_document(
        self,
        payload: dict[str, object],
        *,
        receipt: DocumentAiOperationReceipt,
        output: DocumentAiOutputObject,
        deadline: float,
    ) -> list[DocumentAiPageExtraction]:
        self._assert_deadline(deadline)
        document_error = payload.get("error")
        if document_error is not None and document_error != {}:
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_DOCUMENT_ERROR")
        text_value = payload.get("text")
        pages_value = payload.get("pages")
        if not isinstance(text_value, str) or len(text_value) > 32_000_000:
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_TEXT_INVALID")
        if not isinstance(pages_value, list) or not pages_value:
            raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_PAGES_INVALID")
        shard_offset = _document_shard_text_offset(payload.get("shardInfo"))
        parsed_pages: list[DocumentAiPageExtraction] = []
        for raw_page in cast(list[object], pages_value):
            self._assert_deadline(deadline)
            if not isinstance(raw_page, dict):
                raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_PAGE_INVALID")
            page = cast(dict[str, object], raw_page)
            page_number = page.get("pageNumber")
            layout = page.get("layout")
            if (
                isinstance(page_number, bool)
                or not isinstance(page_number, int)
                or page_number < 1
                or page_number > receipt.page_count
                or not isinstance(layout, dict)
            ):
                raise PermanentIngestionFailure("DOCUMENT_AI_OUTPUT_PAGE_INVALID")
            layout_payload = cast(dict[str, object], layout)
            page_text = _extract_text_anchor(
                text_value,
                layout_payload.get("textAnchor"),
                shard_offset=shard_offset,
            )
            normalized = _normalize_page_text(page_text)
            self._assert_deadline(deadline)
            if len(normalized) > 2_000_000:
                raise PermanentIngestionFailure(
                    "DOCUMENT_AI_OUTPUT_PAGE_TEXT_TOO_LARGE"
                )
            confidence = _page_confidence(page, layout_payload)
            warnings: list[str] = []
            if confidence is None:
                warnings.append("OCR_CONFIDENCE_MISSING")
            elif confidence < self._min_page_confidence:
                warnings.append("OCR_LOW_CONFIDENCE")
            if len(normalized) < self._min_page_text_characters:
                warnings.append("OCR_TEXT_TOO_SHORT")
            parsed_pages.append(
                DocumentAiPageExtraction(
                    source_sha256=receipt.input.sha256,
                    page_number=page_number,
                    text=normalized,
                    confidence=confidence,
                    disposition="review-required" if warnings else "document-ai",
                    warnings=tuple(warnings),
                    processor_revision=receipt.processor_revision,
                    output_uri=output.uri,
                    output_generation=output.generation,
                )
            )
        self._assert_deadline(deadline)
        return parsed_pages


def _validate_resource_id(value: str, label: str) -> None:
    if not _RESOURCE_ID.fullmatch(value):
        raise ValueError(f"{label} identifier is invalid")


def _response_json_object(
    response: httpx.Response,
    failure_code: str,
) -> dict[str, object]:
    try:
        raw = response.json()
    except (UnicodeDecodeError, ValueError):
        raise PermanentIngestionFailure(failure_code) from None
    if not isinstance(raw, dict):
        raise PermanentIngestionFailure(failure_code)
    return cast(dict[str, object], raw)


def _gcs_bucket(uri: str) -> str:
    parsed = urlsplit(uri)
    if parsed.scheme != "gs" or not parsed.netloc:
        raise PermanentIngestionFailure("DOCUMENT_AI_GCS_URI_INVALID")
    return parsed.netloc


def _gcs_prefix(uri: str) -> tuple[str, str]:
    parsed = urlsplit(uri)
    prefix = unquote(parsed.path.lstrip("/"))
    if (
        parsed.scheme != "gs"
        or not parsed.netloc
        or not prefix
        or not prefix.endswith("/")
        or prefix.startswith("/")
        or ".." in prefix.split("/")
    ):
        raise PermanentIngestionFailure("DOCUMENT_AI_GCS_PREFIX_INVALID")
    return parsed.netloc, prefix


def _document_shard_text_offset(value: object) -> int:
    if value is None:
        return 0
    if not isinstance(value, dict):
        raise PermanentIngestionFailure("DOCUMENT_AI_SHARD_INFO_INVALID")
    raw_offset = cast(dict[str, object], value).get("textOffset", "0")
    if not isinstance(raw_offset, str) or not raw_offset.isdigit():
        raise PermanentIngestionFailure("DOCUMENT_AI_SHARD_INFO_INVALID")
    offset = int(raw_offset)
    if offset < 0 or offset > 2_147_483_647:
        raise PermanentIngestionFailure("DOCUMENT_AI_SHARD_INFO_INVALID")
    return offset


def _extract_text_anchor(text: str, value: object, *, shard_offset: int) -> str:
    if not isinstance(value, dict):
        raise PermanentIngestionFailure("DOCUMENT_AI_TEXT_ANCHOR_INVALID")
    segments_value = cast(dict[str, object], value).get("textSegments")
    if not isinstance(segments_value, list):
        raise PermanentIngestionFailure("DOCUMENT_AI_TEXT_ANCHOR_INVALID")
    segments = cast(list[object], segments_value)
    if not segments or len(segments) > 10_000:
        raise PermanentIngestionFailure("DOCUMENT_AI_TEXT_ANCHOR_INVALID")
    slices: list[str] = []
    previous_end = 0
    for raw_segment in segments:
        if not isinstance(raw_segment, dict):
            raise PermanentIngestionFailure("DOCUMENT_AI_TEXT_ANCHOR_INVALID")
        segment = cast(dict[str, object], raw_segment)
        raw_start = segment.get("startIndex", "0")
        raw_end = segment.get("endIndex")
        if (
            not isinstance(raw_start, str)
            or not raw_start.isdigit()
            or not isinstance(raw_end, str)
            or not raw_end.isdigit()
        ):
            raise PermanentIngestionFailure("DOCUMENT_AI_TEXT_ANCHOR_INVALID")
        start = int(raw_start)
        end = int(raw_end)
        if shard_offset and start >= shard_offset and end >= shard_offset:
            start -= shard_offset
            end -= shard_offset
        if start < previous_end or end <= start or end > len(text):
            raise PermanentIngestionFailure("DOCUMENT_AI_TEXT_ANCHOR_INVALID")
        slices.append(text[start:end])
        previous_end = end
    return "".join(slices)


def _page_confidence(
    page: dict[str, object],
    page_layout: dict[str, object],
) -> float | None:
    confidence = _bounded_confidence(page_layout.get("confidence"))
    if confidence is not None:
        return confidence
    tokens = page.get("tokens")
    if not isinstance(tokens, list) or not tokens:
        return None
    token_confidences: list[float] = []
    for token in cast(list[object], tokens):
        if not isinstance(token, dict):
            continue
        layout = cast(dict[str, object], token).get("layout")
        if not isinstance(layout, dict):
            continue
        observed = _bounded_confidence(cast(dict[str, object], layout).get("confidence"))
        if observed is not None:
            token_confidences.append(observed)
    if not token_confidences:
        return None
    return sum(token_confidences) / len(token_confidences)


def _bounded_confidence(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PermanentIngestionFailure("DOCUMENT_AI_CONFIDENCE_INVALID")
    confidence = float(value)
    if confidence < 0.0 or confidence > 1.0:
        raise PermanentIngestionFailure("DOCUMENT_AI_CONFIDENCE_INVALID")
    return confidence


def _normalize_page_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[\t ]+", " ", line).strip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def _crc32c_update(crc: int, content: bytes) -> int:
    for value in content:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return crc


def _crc32c_base64(value: int) -> str:
    return base64.b64encode(value.to_bytes(4, "big")).decode("ascii")


def _assert_same_submission(
    receipt: DocumentAiOperationReceipt, request: DocumentAiBatchRequest
) -> None:
    if (
        receipt.idempotency_key != request.idempotency_key
        or receipt.job_id != request.job_id
        or receipt.input != request.input
        or receipt.output_prefix != request.output_prefix
        or receipt.processor_revision != request.processor_revision
        or receipt.page_count != request.page_count
        or receipt.fencing_token != request.fencing_token
    ):
        raise PermanentIngestionFailure("DOCUMENT_AI_IDEMPOTENCY_CONFLICT")
