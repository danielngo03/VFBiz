from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from app.modules.knowledge.application.cloud_ingestion_ports import (
    CloudObjectIdentity,
    DocumentAiBatchRequest,
    DocumentAiOperationReceipt,
    PubSubIngestionDelivery,
)
from app.modules.knowledge.application.ingestion_ports import (
    PermanentIngestionFailure,
    TransientIngestionFailure,
)
from app.modules.knowledge.infrastructure.gcp_cloud_ingestion import (
    GcpCloudObjectStager,
    GcpCloudObjectVerifier,
    GcpDocumentAiBatchProcessor,
    GcpDocumentAiOutputReader,
    GcpMetadataAccessTokenSource,
    GcpPubSubPushEnvelopeDecoder,
)
from app.modules.knowledge.infrastructure.memory_cloud_ingestion import (
    InMemoryDocumentAiSubmissionLedger,
)

NOW = datetime(2026, 7, 30, tzinfo=UTC)
JOB_ID = UUID("00000000-0000-4000-8000-000000000199")


def _identity() -> CloudObjectIdentity:
    return CloudObjectIdentity(
        uri="gs://vinfast-503003-intake-dev/sha256/aa/object.pdf",
        generation=7,
        metageneration=3,
        sha256="a" * 64,
        byte_size=42,
        crc32c="zUSYPA==",
    )


def _content_addressed_identity() -> CloudObjectIdentity:
    digest = "a" * 64
    return CloudObjectIdentity(
        uri=f"gs://vinfast-503003-intake-dev/sha256/aa/{digest}",
        generation=7,
        metageneration=3,
        sha256=digest,
        byte_size=42,
        crc32c="zUSYPA==",
    )


def _request() -> DocumentAiBatchRequest:
    return DocumentAiBatchRequest(
        idempotency_key=hashlib.sha256(b"job-199").hexdigest(),
        job_id=JOB_ID,
        input=_identity(),
        output_prefix="gs://vinfast-503003-ocr-output-dev/jobs/0199/",
        processor_revision="pretrained-ocr-v2.1-2024-06-21",
        page_count=12,
        fencing_token=3,
    )


def _succeeded_receipt(*, page_count: int = 1) -> DocumentAiOperationReceipt:
    return DocumentAiOperationReceipt(
        idempotency_key=hashlib.sha256(b"job-199").hexdigest(),
        job_id=JOB_ID,
        operation_name=(
            "projects/vinfast-503003/locations/asia-southeast1/operations/op-0199"
        ),
        input=_identity(),
        output_prefix="gs://vinfast-503003-ocr-output-dev/jobs/0199/",
        processor_revision="pretrained-ocr-v2.1-2024-06-21",
        page_count=page_count,
        fencing_token=3,
        state="succeeded",
        submitted_at=NOW,
        reconciled_at=NOW,
    )


def _crc32c(content: bytes) -> str:
    crc = 0xFFFFFFFF
    for value in content:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return base64.b64encode((crc ^ 0xFFFFFFFF).to_bytes(4, "big")).decode("ascii")


def _document_ai_output(
    *,
    text: str = "Xin chào khách hàng.\nThông tin đã được trích xuất.",
    confidence: float = 0.97,
    page_number: int = 1,
) -> bytes:
    return json.dumps(
        {
            "text": text,
            "pages": [
                {
                    "pageNumber": page_number,
                    "layout": {
                        "textAnchor": {
                            "textSegments": [{"endIndex": str(len(text))}],
                        },
                        "confidence": confidence,
                    },
                }
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


def _document_ai_output_handler(
    content: bytes,
    *,
    name: str = "jobs/0199/op-0199/0/output-1.json",
    crc32c: str | None = None,
) -> httpx.MockTransport:
    metadata = {
        "bucket": "vinfast-503003-ocr-output-dev",
        "name": name,
        "generation": "19",
        "metageneration": "2",
        "size": str(len(content)),
        "crc32c": crc32c or _crc32c(content),
        "contentType": "application/json",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("alt") == "media":
            assert request.url.params["generation"] == "19"
            return httpx.Response(200, request=request, content=content)
        if "prefix" in request.url.params:
            assert request.url.params["prefix"] == "jobs/0199/"
            return httpx.Response(200, request=request, json={"items": [metadata]})
        assert request.url.params["generation"] == "19"
        return httpx.Response(200, request=request, json=metadata)

    return httpx.MockTransport(handler)


def _delivery(identity: CloudObjectIdentity) -> PubSubIngestionDelivery:
    return PubSubIngestionDelivery(
        receipt_id="receipt.0199",
        job_id=JOB_ID,
        object=identity,
        page_count=12,
        fencing_token=3,
        published_at=NOW,
    )


def test_pubsub_decoder_accepts_pointer_only_delivery() -> None:
    delivery = PubSubIngestionDelivery(
        receipt_id="receipt.0199",
        job_id=JOB_ID,
        object=_identity(),
        page_count=12,
        fencing_token=3,
        published_at=NOW,
    )
    body = json.dumps(
        {
            "message": {
                "messageId": "message-1",
                "data": base64.b64encode(delivery.model_dump_json().encode()).decode(),
            },
            "subscription": "projects/vinfast-503003/subscriptions/worker-dev",
            "deliveryAttempt": 1,
        }
    ).encode()

    decoded = GcpPubSubPushEnvelopeDecoder(
        expected_subscription="projects/vinfast-503003/subscriptions/worker-dev"
    ).decode(body)

    assert decoded.delivery.object == _identity()
    assert "pdf" not in delivery.model_dump_json().lower().replace("object.pdf", "")


def test_pubsub_decoder_rejects_wrong_subscription() -> None:
    body = json.dumps(
        {
            "message": {
                "messageId": "message-1",
                "data": base64.b64encode(b"{}").decode(),
            },
            "subscription": "projects/other/subscriptions/worker",
        }
    ).encode()

    with pytest.raises(PermanentIngestionFailure, match="SUBSCRIPTION_MISMATCH"):
        GcpPubSubPushEnvelopeDecoder(
            expected_subscription="projects/vinfast-503003/subscriptions/worker-dev"
        ).decode(body)


def test_gcs_verifier_revalidates_exact_generation_and_metadata() -> None:
    content = b"x" * 42
    digest = hashlib.sha256(content).hexdigest()
    identity = CloudObjectIdentity(
        uri=f"gs://vinfast-503003-intake-dev/sha256/{digest[:2]}/{digest}",
        generation=7,
        metageneration=3,
        sha256=digest,
        byte_size=len(content),
        crc32c="zUSYPA==",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["generation"] == "7"
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, request=request, content=content)
        return httpx.Response(
            200,
            request=request,
            json={
                "bucket": "vinfast-503003-intake-dev",
                "name": f"sha256/{digest[:2]}/{digest}",
                "generation": "7",
                "metageneration": "3",
                "size": "42",
                "crc32c": "zUSYPA==",
                "contentType": "application/pdf",
                "metadata": {
                    "sha256": digest,
                    "page-count": "12",
                    "authority-class": "synthetic-smoke-only",
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        GcpCloudObjectVerifier(
            allowed_buckets=("vinfast-503003-intake-dev",),
            approved_smoke_documents={digest: 12},
            access_token=lambda: "workload-token",
            client=client,
        ).verify(_delivery(identity))


def test_gcs_verifier_rejects_forged_sha256_metadata() -> None:
    identity = _content_addressed_identity()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, request=request, content=b"y" * identity.byte_size)
        return httpx.Response(
            200,
            request=request,
            json={
                "bucket": "vinfast-503003-intake-dev",
                "name": f"sha256/aa/{identity.sha256}",
                "generation": "7",
                "metageneration": "3",
                "size": str(identity.byte_size),
                "crc32c": identity.crc32c,
                "contentType": "application/pdf",
                "metadata": {
                    "sha256": identity.sha256,
                    "page-count": "12",
                    "authority-class": "synthetic-smoke-only",
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        verifier = GcpCloudObjectVerifier(
            allowed_buckets=("vinfast-503003-intake-dev",),
            approved_smoke_documents={identity.sha256: 12},
            access_token=lambda: "workload-token",
            client=client,
        )
        with pytest.raises(PermanentIngestionFailure, match="GCS_OBJECT_CONTENT_MISMATCH"):
            verifier.verify(_delivery(identity))


def test_gcs_verifier_rejects_non_content_addressed_pointer_before_provider() -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as client:
        verifier = GcpCloudObjectVerifier(
            allowed_buckets=("vinfast-503003-intake-dev",),
            approved_smoke_documents={"a" * 64: 12},
            access_token=lambda: "workload-token",
            client=client,
        )
        with pytest.raises(
            PermanentIngestionFailure,
            match="GCS_OBJECT_IDENTITY_NOT_ALLOWLISTED",
        ):
            verifier.verify(_delivery(_identity()))


def test_gcs_verifier_rejects_unreviewed_smoke_digest_before_provider() -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as client:
        verifier = GcpCloudObjectVerifier(
            allowed_buckets=("vinfast-503003-intake-dev",),
            approved_smoke_documents={"b" * 64: 12},
            access_token=lambda: "workload-token",
            client=client,
        )
        with pytest.raises(
            PermanentIngestionFailure,
            match="SYNTHETIC_SMOKE_AUTHORITY_MISMATCH",
        ):
            verifier.verify(_delivery(_content_addressed_identity()))


def test_gcs_stager_copies_exact_generation_to_create_only_input() -> None:
    source = _content_addressed_identity()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.params["sourceGeneration"] == "7"
        assert request.url.params["ifGenerationMatch"] == "0"
        return httpx.Response(
            200,
            request=request,
            json={
                "done": True,
                "resource": {
                    "bucket": "vinfast-503003-derived-dev",
                    "name": (f"document-ai-input/sha256/aa/{'a' * 64}/source-generation-7.pdf"),
                    "generation": "11",
                    "metageneration": "4",
                    "size": "42",
                    "crc32c": "zUSYPA==",
                    "contentType": "application/pdf",
                    "metadata": {
                        "sha256": "a" * 64,
                        "source-generation": "7",
                        "page-count": "12",
                        "authority-class": "synthetic-smoke-only",
                    },
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        staged = GcpCloudObjectStager(
            destination_bucket="vinfast-503003-derived-dev",
            access_token=lambda: "workload-token",
            client=client,
        ).stage(_delivery(source))

    assert staged.generation == 11
    assert staged.sha256 == source.sha256
    assert staged.uri.endswith("source-generation-7.pdf")


def test_gcs_stager_rehashes_valid_preexisting_412_destination() -> None:
    content = b"x" * 42
    digest = hashlib.sha256(content).hexdigest()
    source = CloudObjectIdentity(
        uri=f"gs://vinfast-503003-intake-dev/sha256/{digest[:2]}/{digest}",
        generation=7,
        metageneration=3,
        sha256=digest,
        byte_size=len(content),
        crc32c=_crc32c(content),
    )
    destination_name = (
        f"document-ai-input/sha256/{digest[:2]}/{digest}/source-generation-7.pdf"
    )
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method + ("/media" if request.url.params.get("alt") else ""))
        if request.method == "POST":
            return httpx.Response(412, request=request)
        if request.url.params.get("alt") == "media":
            assert request.url.params["generation"] == "11"
            assert request.url.params["ifGenerationMatch"] == "11"
            assert request.url.params["ifMetagenerationMatch"] == "4"
            return httpx.Response(200, request=request, content=content)
        return httpx.Response(
            200,
            request=request,
            json={
                "bucket": "vinfast-503003-derived-dev",
                "name": destination_name,
                "generation": "11",
                "metageneration": "4",
                "size": str(len(content)),
                "crc32c": _crc32c(content),
                "contentType": "application/pdf",
                "metadata": {
                    "sha256": digest,
                    "source-generation": "7",
                    "page-count": "12",
                    "authority-class": "synthetic-smoke-only",
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        staged = GcpCloudObjectStager(
            destination_bucket="vinfast-503003-derived-dev",
            access_token=lambda: "workload-token",
            client=client,
        ).stage(_delivery(source))

    assert staged.generation == 11
    assert calls == ["POST", "GET", "GET/media"]


def test_gcs_stager_rejects_forged_preexisting_412_payload() -> None:
    content = b"x" * 42
    forged = b"y" * 42
    digest = hashlib.sha256(content).hexdigest()
    source = CloudObjectIdentity(
        uri=f"gs://vinfast-503003-intake-dev/sha256/{digest[:2]}/{digest}",
        generation=7,
        metageneration=3,
        sha256=digest,
        byte_size=len(content),
        crc32c=_crc32c(content),
    )
    destination_name = (
        f"document-ai-input/sha256/{digest[:2]}/{digest}/source-generation-7.pdf"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(412, request=request)
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, request=request, content=forged)
        return httpx.Response(
            200,
            request=request,
            json={
                "bucket": "vinfast-503003-derived-dev",
                "name": destination_name,
                "generation": "11",
                "metageneration": "4",
                "size": str(len(content)),
                "crc32c": _crc32c(content),
                "contentType": "application/pdf",
                "metadata": {
                    "sha256": digest,
                    "source-generation": "7",
                    "page-count": "12",
                    "authority-class": "synthetic-smoke-only",
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(
            PermanentIngestionFailure, match="GCS_STAGED_OBJECT_CONTENT_MISMATCH"
        ):
            GcpCloudObjectStager(
                destination_bucket="vinfast-503003-derived-dev",
                access_token=lambda: "workload-token",
                client=client,
            ).stage(_delivery(source))


def test_document_ai_submit_is_idempotent_and_reconcile_is_separate() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["documentOutputConfig"]["gcsOutputConfig"]["fieldMask"] == (
                "text,pages.pageNumber,pages.layout,pages.tokens.layout,shardInfo,error"
            )
            return httpx.Response(
                200,
                request=request,
                json={
                    "name": ("projects/vinfast-503003/locations/asia-southeast1/operations/op-0199")
                },
            )
        return httpx.Response(200, request=request, json={"done": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        processor = GcpDocumentAiBatchProcessor(
            project_id="vinfast-503003",
            location="asia-southeast1",
            processor_id="4d2384d940a52fa5",
            processor_revision="pretrained-ocr-v2.1-2024-06-21",
            allowed_input_buckets=("vinfast-503003-intake-dev",),
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
            ledger=InMemoryDocumentAiSubmissionLedger(),
            clock=lambda: NOW,
        )
        first = processor.submit(_request())
        replay = processor.submit(_request())
        completed = processor.reconcile(first)

    assert first == replay
    assert calls == ["POST", "GET"]
    assert completed.state == "succeeded"


def test_document_ai_output_reader_extracts_vietnamese_page_with_exact_lineage() -> None:
    content = _document_ai_output()
    with httpx.Client(transport=_document_ai_output_handler(content)) as client:
        result = GcpDocumentAiOutputReader(
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
        ).read(_succeeded_receipt())

    assert result.pages[0].text == "Xin chào khách hàng.\nThông tin đã được trích xuất."
    assert result.pages[0].disposition == "document-ai"
    assert result.pages[0].output_generation == 19
    assert result.output_objects[0].sha256 == hashlib.sha256(content).hexdigest()


def test_document_ai_output_reader_routes_low_confidence_page_to_review() -> None:
    content = _document_ai_output(text="Mờ", confidence=0.42)
    with httpx.Client(transport=_document_ai_output_handler(content)) as client:
        result = GcpDocumentAiOutputReader(
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
        ).read(_succeeded_receipt())

    assert result.pages[0].disposition == "review-required"
    assert result.pages[0].warnings == ("OCR_LOW_CONFIDENCE", "OCR_TEXT_TOO_SHORT")


def test_document_ai_output_reader_rejects_oversized_page_without_text_in_error() -> None:
    marker = "PRIVATE_OCR_MARKER_0199"
    content = _document_ai_output(text=marker + "x" * 2_000_001)
    with httpx.Client(transport=_document_ai_output_handler(content)) as client:
        reader = GcpDocumentAiOutputReader(
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
            max_output_object_bytes=len(content) + 1,
        )
        with pytest.raises(
            PermanentIngestionFailure,
            match="DOCUMENT_AI_OUTPUT_PAGE_TEXT_TOO_LARGE",
        ) as captured:
            reader.read(_succeeded_receipt())

    assert marker not in str(captured.value)
    assert captured.value.__cause__ is None


def test_document_ai_output_reader_enforces_aggregate_text_memory_bound() -> None:
    content = _document_ai_output()
    with httpx.Client(transport=_document_ai_output_handler(content)) as client:
        reader = GcpDocumentAiOutputReader(
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
            max_extracted_text_bytes=10,
        )
        with pytest.raises(
            PermanentIngestionFailure,
            match="DOCUMENT_AI_EXTRACTED_TEXT_LIMIT_EXCEEDED",
        ):
            reader.read(_succeeded_receipt())


def test_document_ai_output_reader_classifies_http_outage_as_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reader = GcpDocumentAiOutputReader(
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
        )
        with pytest.raises(
            TransientIngestionFailure,
            match="DOCUMENT_AI_OUTPUT_PROVIDER_UNAVAILABLE",
        ):
            reader.read(_succeeded_receipt())


def test_document_ai_output_reader_rejects_malformed_success_json_without_content() -> None:
    marker = "PRIVATE_PROVIDER_MARKER_0199"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=("{" + marker).encode(),
            headers={"content-type": "application/json"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reader = GcpDocumentAiOutputReader(
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
        )
        with pytest.raises(
            PermanentIngestionFailure,
            match="DOCUMENT_AI_OUTPUT_LIST_INVALID",
        ) as captured:
            reader.read(_succeeded_receipt())

    assert marker not in str(captured.value)
    assert captured.value.__cause__ is None


def test_document_ai_output_reader_enforces_global_reconciliation_deadline() -> None:
    calls = 0
    elapsed = -10.0

    def monotonic() -> float:
        nonlocal elapsed
        elapsed += 10.0
        return elapsed

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request, json={"items": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reader = GcpDocumentAiOutputReader(
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
            deadline_seconds=60,
            monotonic=monotonic,
        )
        with pytest.raises(
            TransientIngestionFailure,
            match="DOCUMENT_AI_RECONCILIATION_DEADLINE_EXCEEDED",
        ):
            reader.read(_succeeded_receipt())

    assert calls == 1


def test_document_ai_output_reader_rejects_tail_work_after_deadline() -> None:
    content = _document_ai_output()
    checks = 0

    def monotonic() -> float:
        nonlocal checks
        checks += 1
        return 31.0 if checks >= 22 else 0.0

    with httpx.Client(transport=_document_ai_output_handler(content)) as client:
        reader = GcpDocumentAiOutputReader(
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
            deadline_seconds=30,
            monotonic=monotonic,
        )
        with pytest.raises(
            TransientIngestionFailure,
            match="DOCUMENT_AI_RECONCILIATION_DEADLINE_EXCEEDED",
        ):
            reader.read(_succeeded_receipt())


def test_document_ai_output_reader_hard_caps_output_objects_at_twenty() -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as client:
        with pytest.raises(ValueError, match="output object limit"):
            GcpDocumentAiOutputReader(
                output_bucket="vinfast-503003-ocr-output-dev",
                access_token=lambda: "workload-token",
                client=client,
                max_output_objects=21,
            )


def test_document_ai_output_reader_rejects_incomplete_page_set() -> None:
    content = _document_ai_output()
    with httpx.Client(transport=_document_ai_output_handler(content)) as client:
        reader = GcpDocumentAiOutputReader(
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
        )
        with pytest.raises(
            PermanentIngestionFailure,
            match="DOCUMENT_AI_PAGE_COMPLETENESS_INVALID",
        ):
            reader.read(_succeeded_receipt(page_count=2))


def test_document_ai_output_reader_rejects_crc_mismatch() -> None:
    content = _document_ai_output()
    with httpx.Client(
        transport=_document_ai_output_handler(content, crc32c="AAAAAA==")
    ) as client:
        reader = GcpDocumentAiOutputReader(
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
        )
        with pytest.raises(
            PermanentIngestionFailure,
            match="DOCUMENT_AI_OUTPUT_CONTENT_MISMATCH",
        ):
            reader.read(_succeeded_receipt())


def test_document_ai_output_reader_rejects_prefix_escape() -> None:
    content = _document_ai_output()
    with httpx.Client(
        transport=_document_ai_output_handler(content, name="jobs/0199/../escape.json")
    ) as client:
        reader = GcpDocumentAiOutputReader(
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
        )
        with pytest.raises(
            PermanentIngestionFailure,
            match="DOCUMENT_AI_OUTPUT_METADATA_INVALID",
        ):
            reader.read(_succeeded_receipt())


def test_document_ai_output_reader_rejects_unfinished_receipt_before_provider_call() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    receipt = _succeeded_receipt().model_copy(update={"state": "running"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reader = GcpDocumentAiOutputReader(
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
        )
        with pytest.raises(PermanentIngestionFailure, match="DOCUMENT_AI_OUTPUT_NOT_READY"):
            reader.read(DocumentAiOperationReceipt.model_validate(receipt))

    assert calls == 0


def test_document_ai_rejects_more_than_500_pages_before_provider_call() -> None:
    with pytest.raises(ValueError):
        DocumentAiBatchRequest.model_validate(
            {**_request().model_dump(), "page_count": 501}
        )


def test_metadata_token_source_caches_and_validates_workload_token() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["Metadata-Flavor"] == "Google"
        return httpx.Response(
            200,
            request=request,
            json={
                "access_token": "workload-token",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        source = GcpMetadataAccessTokenSource(client=client, monotonic=lambda: 100.0)
        first = source()
        second = source()

    assert first == second == "workload-token"
    assert calls == 1


def test_document_ai_ambiguous_provider_failure_is_not_resubmitted() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("ambiguous provider outcome", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        processor = GcpDocumentAiBatchProcessor(
            project_id="vinfast-503003",
            location="asia-southeast1",
            processor_id="4d2384d940a52fa5",
            processor_revision="pretrained-ocr-v2.1-2024-06-21",
            allowed_input_buckets=("vinfast-503003-intake-dev",),
            output_bucket="vinfast-503003-ocr-output-dev",
            access_token=lambda: "workload-token",
            client=client,
            ledger=InMemoryDocumentAiSubmissionLedger(),
            clock=lambda: NOW,
        )
        with pytest.raises(httpx.ReadTimeout):
            processor.submit(_request())
        with pytest.raises(
            TransientIngestionFailure,
            match="DOCUMENT_AI_SUBMISSION_IN_PROGRESS",
        ):
            processor.submit(_request())

    assert calls == 1
