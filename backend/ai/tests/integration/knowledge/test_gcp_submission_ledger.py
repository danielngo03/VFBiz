from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import create_engine, delete, insert, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.modules.knowledge.application.cloud_ingestion_ports import (
    CloudObjectIdentity,
    DocumentAiBatchRequest,
    DocumentAiExtractionEvidence,
    DocumentAiExtractionResult,
    DocumentAiOperationReceipt,
    DocumentAiOutputObject,
    DocumentAiPageExtraction,
    DocumentAiReconciliationFailureEvidence,
)
from app.modules.knowledge.application.ingestion_ports import (
    PermanentIngestionFailure,
    TransientIngestionFailure,
)
from app.modules.knowledge.infrastructure.cloud_ingestion_models import (
    DocumentAiExtractionEvidenceRecord,
    DocumentAiOperationObservationRecord,
    DocumentAiReconciliationFailureRecord,
    DocumentAiSubmissionRecord,
)
from app.modules.knowledge.infrastructure.postgres_cloud_ingestion import (
    PostgresDocumentAiReconciliationRepository,
    PostgresDocumentAiSubmissionLedger,
)
from app.platform.config import Settings
from scripts.provision_document_ai_database_identities import _preflight_database

pytestmark = pytest.mark.skipif(
    not os.environ.get("VFBIZ_AI_DATABASE_URL"),
    reason="PostgreSQL integration database is not configured",
)


def test_postgres_submission_reservation_survives_restart_and_prevents_replay() -> None:
    database_url = Settings().database_url
    assert database_url is not None
    engine = create_engine(
        database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    )
    sessions = sessionmaker(engine, class_=Session, expire_on_commit=False)
    job_id = uuid4()
    key = hashlib.sha256(str(job_id).encode()).hexdigest()
    now = datetime.now(UTC)
    request = DocumentAiBatchRequest(
        idempotency_key=key,
        job_id=job_id,
        input=CloudObjectIdentity(
            uri="gs://vinfast-503003-intake-dev/synthetic/object.pdf",
            generation=1,
            metageneration=1,
            sha256="a" * 64,
            byte_size=42,
            crc32c="zUSYPA==",
        ),
        output_prefix=f"gs://vinfast-503003-ocr-output-dev/jobs/{job_id}/",
        processor_revision="pretrained-ocr-v2.1-2024-06-21",
        page_count=3,
        fencing_token=1,
    )
    ledger = PostgresDocumentAiSubmissionLedger(sessions, clock=lambda: now)
    try:
        assert ledger.reserve(request) is None
        restarted = PostgresDocumentAiSubmissionLedger(sessions, clock=lambda: now)
        with pytest.raises(
            TransientIngestionFailure,
            match="DOCUMENT_AI_SUBMISSION_IN_PROGRESS",
        ):
            restarted.find(key)

        receipt = DocumentAiOperationReceipt(
            idempotency_key=key,
            job_id=job_id,
            operation_name=("projects/vinfast-503003/locations/asia-southeast1/operations/op-0199"),
            input=request.input,
            output_prefix=request.output_prefix,
            processor_revision=request.processor_revision,
            page_count=request.page_count,
            fencing_token=request.fencing_token,
            state="submitted",
            submitted_at=now,
            reconciled_at=now,
        )
        assert ledger.record(receipt) == receipt
        assert restarted.find(key) == receipt
        assert restarted.reserve(request) == receipt
        with pytest.raises(DBAPIError, match="ledger deletion refused"):
            with sessions.begin() as session:
                session.execute(
                    delete(DocumentAiSubmissionRecord).where(
                        DocumentAiSubmissionRecord.idempotency_key == key
                    )
                )
        with pytest.raises(
            DBAPIError,
            match="(ledger deletion refused|reconciliation evidence mutation refused)",
        ):
            with sessions.begin() as session:
                session.execute(
                    text(
                        "TRUNCATE ai_document_extraction_evidence, "
                        "ai_document_reconciliation_failure, "
                        "ai_document_reconciliation_claim, "
                        "ai_document_operation_observation, ai_document_submission"
                    )
                )
    finally:
        _privileged_test_cleanup(sessions)
        engine.dispose()


def test_postgres_submission_reservation_enforces_daily_page_budget() -> None:
    database_url = Settings().database_url
    assert database_url is not None
    engine = create_engine(
        database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    )
    sessions = sessionmaker(engine, class_=Session, expire_on_commit=False)
    job_id = uuid4()
    now = datetime.now(UTC)
    request = DocumentAiBatchRequest(
        idempotency_key=hashlib.sha256(str(job_id).encode()).hexdigest(),
        job_id=job_id,
        input=CloudObjectIdentity(
            uri="gs://vinfast-503003-derived-dev/synthetic/budget.pdf",
            generation=1,
            metageneration=1,
            sha256="b" * 64,
            byte_size=42,
            crc32c="zUSYPA==",
        ),
        output_prefix=f"gs://vinfast-503003-ocr-output-dev/jobs/{job_id}/",
        processor_revision="pretrained-ocr-v2.1-2024-06-21",
        page_count=3,
        fencing_token=1,
    )
    ledger = PostgresDocumentAiSubmissionLedger(
        sessions,
        clock=lambda: now,
        max_pages_per_day=2,
    )
    try:
        with pytest.raises(
            PermanentIngestionFailure,
            match="DOCUMENT_AI_DAILY_PAGE_BUDGET_EXCEEDED",
        ):
            ledger.reserve(request)
        assert ledger.find(request.idempotency_key) is None
    finally:
        _privileged_test_cleanup(sessions)
        engine.dispose()


def test_postgres_reconciliation_evidence_survives_restart_and_rejects_tamper() -> None:
    database_url = Settings().database_url
    assert database_url is not None
    engine = create_engine(
        database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    )
    sessions = sessionmaker(engine, class_=Session, expire_on_commit=False)
    job_id = uuid4()
    key = hashlib.sha256(str(job_id).encode()).hexdigest()
    now = datetime.now(UTC)
    request = DocumentAiBatchRequest(
        idempotency_key=key,
        job_id=job_id,
        input=CloudObjectIdentity(
            uri="gs://vinfast-503003-intake-dev/synthetic/reconcile.pdf",
            generation=7,
            metageneration=1,
            sha256="c" * 64,
            byte_size=42,
            crc32c="zUSYPA==",
        ),
        output_prefix=f"gs://vinfast-503003-ocr-output-dev/jobs/{job_id}/",
        processor_revision="pretrained-ocr-v2.1-2024-06-21",
        page_count=2,
        fencing_token=3,
    )
    submission = PostgresDocumentAiSubmissionLedger(sessions, clock=lambda: now)
    try:
        assert submission.reserve(request) is None
        submitted = DocumentAiOperationReceipt(
            idempotency_key=key,
            job_id=job_id,
            operation_name=(
                "projects/vinfast-503003/locations/asia-southeast1/operations/"
                "op-reconcile-0199"
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
        assert submission.record(submitted) == submitted

        reconciliation_clock = [now + timedelta(seconds=1)]
        repository = PostgresDocumentAiReconciliationRepository(
            sessions,
            clock=lambda: reconciliation_clock[0],
        )
        assert repository.list_pending(limit=1) == (submitted,)
        running = submitted.model_copy(
            update={"state": "running", "reconciled_at": now + timedelta(seconds=1)}
        )
        assert repository.record_operation(running) == running
        assert repository.list_pending(limit=1) == (submitted,)

        with pytest.raises(DBAPIError, match="invalid Document AI operation observation"):
            with sessions.begin() as session:
                session.execute(
                    insert(DocumentAiOperationObservationRecord).values(
                        idempotency_key=key,
                        operation_name=submitted.operation_name,
                        state="running",
                        observation_digest="d" * 64,
                        canonical_payload='{"forged":true}',
                        reconciled_at=now + timedelta(seconds=2),
                    )
                )

        succeeded = submitted.model_copy(
            update={"state": "succeeded", "reconciled_at": now + timedelta(seconds=3)}
        )
        assert repository.record_operation(succeeded) == succeeded
        assert repository.list_pending(limit=1) == ()
        reconciliation_clock[0] = now + timedelta(seconds=302)
        assert repository.list_pending(limit=1) == (submitted,)

        reconciliation_clock[0] = now + timedelta(seconds=303)
        failure = repository.record_failure(
            succeeded,
            failure_code="DOCUMENT_AI_OUTPUT_PROVIDER_UNAVAILABLE",
            retryable=True,
        )
        assert failure.attempt == 1
        assert failure.disposition == "retry-scheduled"
        assert repository.list_pending(limit=1) == ()
        reconciliation_clock[0] += timedelta(seconds=30)
        assert repository.list_pending(limit=1) == (submitted,)

        output = DocumentAiOutputObject(
            uri=f"{request.output_prefix}output-1.json",
            generation=11,
            metageneration=1,
            byte_size=128,
            crc32c="zUSYPA==",
            sha256="e" * 64,
        )
        extraction = DocumentAiExtractionResult(
            idempotency_key=key,
            job_id=job_id,
            source=request.input,
            processor_revision=request.processor_revision,
            expected_page_count=2,
            output_objects=(output,),
            pages=(
                DocumentAiPageExtraction(
                    source_sha256=request.input.sha256,
                    page_number=1,
                    text="Dữ liệu tổng hợp trang một.",
                    confidence=0.99,
                    disposition="document-ai",
                    warnings=(),
                    processor_revision=request.processor_revision,
                    output_uri=output.uri,
                    output_generation=output.generation,
                ),
                DocumentAiPageExtraction(
                    source_sha256=request.input.sha256,
                    page_number=2,
                    text="Dữ liệu tổng hợp trang hai cần xem lại.",
                    confidence=1e-7,
                    disposition="review-required",
                    warnings=("LOW_CONFIDENCE",),
                    processor_revision=request.processor_revision,
                    output_uri=output.uri,
                    output_generation=output.generation,
                ),
            ),
        )
        evidence = DocumentAiExtractionEvidence.issue(extraction)
        assert evidence.pages[1].confidence_micros == 0
        assert repository.record_extraction(evidence) == evidence
        assert repository.list_pending(limit=1) == ()

        with pytest.raises(
            PermanentIngestionFailure,
            match="DOCUMENT_AI_RECONCILIATION_CLAIM_LOST",
        ):
            repository.record_failure(
                succeeded,
                failure_code="DOCUMENT_AI_OUTPUT_PROVIDER_UNAVAILABLE",
                retryable=True,
            )
        forged_failure = DocumentAiReconciliationFailureEvidence.issue(
            receipt=succeeded,
            attempt=2,
            failure_code="DOCUMENT_AI_OUTPUT_PROVIDER_UNAVAILABLE",
            retryable=True,
            observed_at=reconciliation_clock[0],
            next_retry_at=reconciliation_clock[0] + timedelta(seconds=60),
        )
        with pytest.raises(DBAPIError, match="invalid Document AI reconciliation failure"):
            with sessions.begin() as session:
                session.execute(
                    insert(DocumentAiReconciliationFailureRecord).values(
                        idempotency_key=forged_failure.idempotency_key,
                        attempt=forged_failure.attempt,
                        failure_code=forged_failure.failure_code,
                        retryable=forged_failure.retryable,
                        disposition=forged_failure.disposition,
                        evidence_digest=forged_failure.evidence_digest,
                        canonical_payload=forged_failure.canonical_payload(),
                        observed_at=forged_failure.observed_at,
                        next_retry_at=forged_failure.next_retry_at,
                    )
                )

        forged_payload = evidence.model_dump(mode="json", exclude={"evidence_digest"})
        forged_uri = "gs://vinfast-503003-ocr-output-dev/other/output.json"
        forged_payload["output_objects"][0]["uri"] = forged_uri
        forged_payload["pages"][0]["output_uri"] = forged_uri
        forged_canonical = json.dumps(
            forged_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with pytest.raises(DBAPIError, match="invalid Document AI extraction evidence"):
            with sessions.begin() as session:
                session.execute(
                    insert(DocumentAiExtractionEvidenceRecord).values(
                        idempotency_key=key,
                        evidence_digest=hashlib.sha256(
                            forged_canonical.encode("utf-8")
                        ).hexdigest(),
                        canonical_payload=forged_canonical,
                        expected_page_count=2,
                        review_required_count=1,
                    )
                )

        missing_key_payload = evidence.model_dump(
            mode="json",
            exclude={"evidence_digest"},
        )
        del missing_key_payload["pages"][0]["confidence_micros"]
        missing_key_canonical = json.dumps(
            missing_key_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with pytest.raises(DBAPIError, match="invalid Document AI extraction evidence"):
            with sessions.begin() as session:
                session.execute(
                    insert(DocumentAiExtractionEvidenceRecord).values(
                        idempotency_key=key,
                        evidence_digest=hashlib.sha256(
                            missing_key_canonical.encode("utf-8")
                        ).hexdigest(),
                        canonical_payload=missing_key_canonical,
                        expected_page_count=2,
                        review_required_count=1,
                    )
                )

        extra_payload = evidence.model_dump(mode="json", exclude={"evidence_digest"})
        extra_payload["raw_document_text"] = "forbidden"
        extra_payload["pages"][0]["raw_text"] = "forbidden"
        extra_payload["output_objects"][0]["raw_provider_payload"] = "forbidden"
        extra_canonical = json.dumps(
            extra_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with pytest.raises(DBAPIError, match="invalid Document AI extraction evidence"):
            with sessions.begin() as session:
                session.execute(
                    insert(DocumentAiExtractionEvidenceRecord).values(
                        idempotency_key=key,
                        evidence_digest=hashlib.sha256(
                            extra_canonical.encode("utf-8")
                        ).hexdigest(),
                        canonical_payload=extra_canonical,
                        expected_page_count=2,
                        review_required_count=1,
                    )
                )

        restarted = PostgresDocumentAiReconciliationRepository(sessions)
        assert restarted.find_terminal(key) == succeeded
        assert restarted.find_extraction(key) == evidence
        assert restarted.record_operation(succeeded) == succeeded
        assert restarted.record_extraction(evidence) == evidence

        conflicting = DocumentAiExtractionEvidence.issue(
            extraction.model_copy(
                update={
                    "pages": (
                        extraction.pages[0].model_copy(update={"text": "Nội dung khác."}),
                        extraction.pages[1],
                    )
                }
            )
        )
        with pytest.raises(
            PermanentIngestionFailure,
            match="DOCUMENT_AI_EXTRACTION_EVIDENCE_CONFLICT",
        ):
            restarted.record_extraction(conflicting)

        for statement in (
            update(DocumentAiOperationObservationRecord)
            .where(DocumentAiOperationObservationRecord.idempotency_key == key)
            .values(state="cancelled"),
            delete(DocumentAiExtractionEvidenceRecord).where(
                DocumentAiExtractionEvidenceRecord.idempotency_key == key
            ),
        ):
            with pytest.raises(
                DBAPIError,
                match="Document AI reconciliation evidence mutation refused",
            ):
                with sessions.begin() as session:
                    session.execute(statement)

        with pytest.raises(
            DBAPIError,
            match="Document AI reconciliation evidence mutation refused",
        ):
            with sessions.begin() as session:
                session.execute(text("TRUNCATE ai_document_extraction_evidence"))
    finally:
        _privileged_test_cleanup(sessions)
        engine.dispose()


def test_postgres_reconciliation_claim_prevents_concurrent_duplicate_work() -> None:
    database_url = Settings().database_url
    assert database_url is not None
    engine = create_engine(
        database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    )
    sessions = sessionmaker(engine, class_=Session, expire_on_commit=False)
    job_id = uuid4()
    key = hashlib.sha256(str(job_id).encode()).hexdigest()
    now = datetime.now(UTC)
    request = DocumentAiBatchRequest(
        idempotency_key=key,
        job_id=job_id,
        input=CloudObjectIdentity(
            uri="gs://vinfast-503003-intake-dev/synthetic/concurrent.pdf",
            generation=1,
            metageneration=1,
            sha256="f" * 64,
            byte_size=42,
            crc32c="zUSYPA==",
        ),
        output_prefix=f"gs://vinfast-503003-ocr-output-dev/jobs/{job_id}/",
        processor_revision="pretrained-ocr-v2.1-2024-06-21",
        page_count=1,
        fencing_token=1,
    )
    ledger = PostgresDocumentAiSubmissionLedger(sessions, clock=lambda: now)
    try:
        assert ledger.reserve(request) is None
        submitted = DocumentAiOperationReceipt(
            idempotency_key=key,
            job_id=job_id,
            operation_name=(
                "projects/vinfast-503003/locations/asia-southeast1/operations/"
                "op-concurrent-0199"
            ),
            input=request.input,
            output_prefix=request.output_prefix,
            processor_revision=request.processor_revision,
            page_count=1,
            fencing_token=1,
            state="submitted",
            submitted_at=now,
            reconciled_at=now,
        )
        assert ledger.record(submitted) == submitted
        clocks = ([now], [now])
        repositories = (
            PostgresDocumentAiReconciliationRepository(
                sessions,
                clock=lambda: clocks[0][0],
                owner_token="a" * 64,
            ),
            PostgresDocumentAiReconciliationRepository(
                sessions,
                clock=lambda: clocks[1][0],
                owner_token="b" * 64,
            ),
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(_claim_once, repositories))

        assert sum(len(result) for result in results) == 1
        assert {receipt.idempotency_key for result in results for receipt in result} == {
            key
        }
        winner_index = 0 if results[0] else 1
        reclaimer_index = 1 - winner_index
        clocks[0][0] = now + timedelta(seconds=301)
        clocks[1][0] = now + timedelta(seconds=301)
        assert repositories[reclaimer_index].list_pending(limit=1) == (submitted,)

        running = submitted.model_copy(
            update={
                "state": "running",
                "reconciled_at": now + timedelta(seconds=301),
            }
        )
        with pytest.raises(
            PermanentIngestionFailure,
            match="DOCUMENT_AI_RECONCILIATION_CLAIM_LOST",
        ):
            repositories[winner_index].record_operation(running)
        assert repositories[reclaimer_index].record_operation(running) == running
        assert repositories[reclaimer_index].list_pending(limit=1) == (submitted,)
        clocks[reclaimer_index][0] = now + timedelta(seconds=602)
        expired_failure = repositories[reclaimer_index].record_failure(
            running,
            failure_code="DOCUMENT_AI_RECONCILIATION_DEADLINE_EXCEEDED",
            retryable=True,
        )
        assert expired_failure.disposition == "retry-scheduled"
    finally:
        _privileged_test_cleanup(sessions)
        engine.dispose()


def _privileged_test_cleanup(sessions: sessionmaker[Session]) -> None:
    """Reset only the disposable integration DB while bypassing audit triggers."""
    with sessions.begin() as session:
        session.execute(text("SET LOCAL session_replication_role = replica"))
        session.execute(
            text(
                "TRUNCATE ai_document_extraction_evidence, "
                "ai_document_reconciliation_failure, "
                "ai_document_reconciliation_claim, "
                "ai_document_operation_observation, ai_document_submission"
            )
        )


def test_document_ai_runtime_roles_are_disjoint_and_least_privileged() -> None:
    database_url = Settings().database_url
    assert database_url is not None
    engine = create_engine(
        database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    )
    try:
        with engine.connect() as connection:
            privileges = connection.execute(
                text(
                    """
                    SELECT
                      has_table_privilege(
                        'vfbiz_ai_document_submitter',
                        'public.ai_document_submission',
                        'SELECT,INSERT,UPDATE'
                      ) AS submitter_capability,
                      has_table_privilege(
                        'vfbiz_ai_document_submitter',
                        'public.ai_document_submission',
                        'DELETE'
                      ) AS submitter_can_delete,
                      has_table_privilege(
                        'vfbiz_ai_document_submitter',
                        'public.ai_document_operation_observation',
                        'INSERT'
                      ) AS submitter_can_reconcile,
                      has_table_privilege(
                        'vfbiz_ai_document_reconciler',
                        'public.ai_document_reconciliation_claim',
                        'SELECT,INSERT,UPDATE'
                      ) AS reconciler_claim_capability,
                      has_table_privilege(
                        'vfbiz_ai_document_reconciler',
                        'public.ai_document_reconciliation_claim',
                        'DELETE'
                      ) AS reconciler_can_delete_claim,
                      has_table_privilege(
                        'vfbiz_ai_document_reconciler',
                        'public.ai_document_extraction_evidence',
                        'SELECT,INSERT'
                      ) AS reconciler_evidence_capability,
                      has_table_privilege(
                        'vfbiz_ai_document_reconciler',
                        'public.ai_document_submission',
                        'INSERT,UPDATE'
                      ) AS reconciler_can_submit,
                      has_column_privilege(
                        'vfbiz_ai_document_reconciler',
                        'public.ai_document_submission',
                        'id',
                        'UPDATE'
                      ) AS reconciler_can_lock_submission,
                      NOT (
                        SELECT rolcanlogin OR rolsuper OR rolcreatedb
                          OR rolcreaterole OR rolreplication OR rolbypassrls
                        FROM pg_roles
                        WHERE rolname = 'vfbiz_ai_document_submitter'
                      ) AS submitter_is_restricted,
                      NOT (
                        SELECT rolcanlogin OR rolsuper OR rolcreatedb
                          OR rolcreaterole OR rolreplication OR rolbypassrls
                        FROM pg_roles
                        WHERE rolname = 'vfbiz_ai_document_reconciler'
                      ) AS reconciler_is_restricted
                    """
                )
            ).mappings().one()
        assert privileges == {
            "submitter_capability": True,
            "submitter_can_delete": False,
            "submitter_can_reconcile": False,
            "reconciler_claim_capability": True,
            "reconciler_can_delete_claim": False,
            "reconciler_evidence_capability": True,
            "reconciler_can_submit": False,
            "reconciler_can_lock_submission": True,
            "submitter_is_restricted": True,
            "reconciler_is_restricted": True,
        }
    finally:
        engine.dispose()


def test_document_ai_runtime_roles_execute_only_their_repository_paths() -> None:
    database_url = Settings().database_url
    assert database_url is not None
    psycopg_url = database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://", 1
    )
    admin_engine = create_engine(psycopg_url)
    submitter_engine = create_engine(
        psycopg_url,
        connect_args={"options": "-c role=vfbiz_ai_document_submitter"},
    )
    reconciler_engine = create_engine(
        psycopg_url,
        connect_args={"options": "-c role=vfbiz_ai_document_reconciler"},
    )
    admin_sessions = sessionmaker(admin_engine, class_=Session, expire_on_commit=False)
    submitter_sessions = sessionmaker(
        submitter_engine, class_=Session, expire_on_commit=False
    )
    reconciler_sessions = sessionmaker(
        reconciler_engine, class_=Session, expire_on_commit=False
    )
    now = datetime.now(UTC)
    job_id = uuid4()
    key = hashlib.sha256(f"runtime-role:{job_id}".encode()).hexdigest()
    request = DocumentAiBatchRequest(
        idempotency_key=key,
        job_id=job_id,
        input=CloudObjectIdentity(
            uri="gs://vinfast-503003-intake-dev/synthetic/runtime-role.pdf",
            generation=17,
            metageneration=1,
            sha256="f" * 64,
            byte_size=128,
            crc32c="zUSYPA==",
        ),
        output_prefix=f"gs://vinfast-503003-ocr-output-dev/jobs/{job_id}/",
        processor_revision="pretrained-ocr-v2.1.1-2025-01-31",
        page_count=2,
        fencing_token=1,
    )
    submitted = DocumentAiOperationReceipt(
        idempotency_key=key,
        job_id=job_id,
        operation_name=(
            "projects/vinfast-503003/locations/asia-southeast1/operations/"
            f"runtime-role-{job_id}"
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
    claim_owner_reference = hashlib.sha256(b"runtime-role-review").hexdigest()
    try:
        with submitter_engine.connect() as connection:
            assert connection.scalar(text("SELECT current_user")) == (
                "vfbiz_ai_document_submitter"
            )
        ledger = PostgresDocumentAiSubmissionLedger(
            submitter_sessions,
            clock=lambda: now,
        )
        assert ledger.reserve(request) is None
        assert ledger.record(submitted) == submitted
        with pytest.raises(DBAPIError, match="permission denied"):
            with submitter_sessions.begin() as session:
                session.execute(
                    insert(DocumentAiOperationObservationRecord).values(
                        idempotency_key=key,
                        operation_name=submitted.operation_name,
                        state="running",
                        observation_digest="e" * 64,
                        canonical_payload="{}",
                        reconciled_at=now,
                    )
                )

        with reconciler_engine.connect() as connection:
            assert connection.scalar(text("SELECT current_user")) == (
                "vfbiz_ai_document_reconciler"
            )
        repository = PostgresDocumentAiReconciliationRepository(
            reconciler_sessions,
            clock=lambda: now + timedelta(seconds=1),
            owner_token=claim_owner_reference,
        )
        assert repository.list_pending(limit=1) == (submitted,)
        running = submitted.model_copy(
            update={"state": "running", "reconciled_at": now + timedelta(seconds=1)}
        )
        assert repository.record_operation(running) == running
        with pytest.raises(DBAPIError, match="permission denied"):
            with reconciler_sessions.begin() as session:
                session.execute(
                    update(DocumentAiSubmissionRecord)
                    .where(DocumentAiSubmissionRecord.idempotency_key == key)
                    .values(state="failed")
                )
        with pytest.raises(DBAPIError, match="permission denied"):
            with reconciler_sessions.begin() as session:
                session.execute(
                    delete(DocumentAiSubmissionRecord).where(
                        DocumentAiSubmissionRecord.idempotency_key == key
                    )
                )
    finally:
        _privileged_test_cleanup(admin_sessions)
        submitter_engine.dispose()
        reconciler_engine.dispose()
        admin_engine.dispose()


def test_document_ai_operator_preflight_rejects_membership_and_acl_drift() -> None:
    database_url = Settings().database_url
    assert database_url is not None
    psycopg_url = database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://", 1
    )
    raw_psycopg_url = database_url.replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )
    engine = create_engine(psycopg_url)
    try:
        with psycopg.connect(raw_psycopg_url) as connection:
            _preflight_database(connection)
        with engine.begin() as connection:
            connection.execute(text("CREATE ROLE vfbiz_unexpected_document_actor NOLOGIN"))
            connection.execute(
                text(
                    "GRANT vfbiz_ai_document_submitter "
                    "TO vfbiz_unexpected_document_actor"
                )
            )
            connection.execute(
                text(
                    "GRANT DELETE ON public.ai_document_submission "
                    "TO vfbiz_ai_document_reconciler"
                )
            )
        with psycopg.connect(raw_psycopg_url) as connection:
            with pytest.raises(RuntimeError, match="unexpected role membership"):
                _preflight_database(connection)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "REVOKE vfbiz_ai_document_submitter "
                    "FROM vfbiz_unexpected_document_actor"
                )
            )
        with psycopg.connect(raw_psycopg_url) as connection:
            with pytest.raises(RuntimeError, match="ACLs do not match"):
                _preflight_database(connection)
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "REVOKE DELETE ON public.ai_document_submission "
                    "FROM vfbiz_ai_document_reconciler"
                )
            )
            connection.execute(text("DROP ROLE IF EXISTS vfbiz_unexpected_document_actor"))
        engine.dispose()


def test_document_ai_operator_preflight_rejects_effective_login_and_public_drift() -> None:
    database_url = Settings().database_url
    assert database_url is not None
    psycopg_url = database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://", 1
    )
    raw_psycopg_url = database_url.replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )
    engine = create_engine(psycopg_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE ROLE vfbiz_ai_document_submitter_login LOGIN")
            )
            connection.execute(
                text(
                    "GRANT vfbiz_ai_document_submitter "
                    "TO vfbiz_ai_document_submitter_login WITH ADMIN OPTION"
                )
            )
        with psycopg.connect(raw_psycopg_url) as connection:
            with pytest.raises(RuntimeError, match="unexpected role membership"):
                _preflight_database(connection)

        with engine.begin() as connection:
            connection.execute(
                text(
                    "REVOKE ADMIN OPTION FOR vfbiz_ai_document_submitter "
                    "FROM vfbiz_ai_document_submitter_login"
                )
            )
            connection.execute(
                text(
                    "GRANT DELETE ON public.ai_document_submission "
                    "TO vfbiz_ai_document_submitter_login"
                )
            )
        with psycopg.connect(raw_psycopg_url) as connection:
            with pytest.raises(RuntimeError, match="ACLs do not match"):
                _preflight_database(connection)

        with engine.begin() as connection:
            connection.execute(
                text(
                    "REVOKE DELETE ON public.ai_document_submission "
                    "FROM vfbiz_ai_document_submitter_login"
                )
            )
            connection.execute(
                text("GRANT DELETE ON public.ai_document_submission TO PUBLIC")
            )
        with psycopg.connect(raw_psycopg_url) as connection:
            with pytest.raises(RuntimeError, match="ACLs do not match"):
                _preflight_database(connection)
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("REVOKE DELETE ON public.ai_document_submission FROM PUBLIC")
            )
            connection.execute(
                text(
                    "REVOKE DELETE ON public.ai_document_submission "
                    "FROM vfbiz_ai_document_submitter_login"
                )
            )
            connection.execute(
                text(
                    "REVOKE vfbiz_ai_document_submitter "
                    "FROM vfbiz_ai_document_submitter_login"
                )
            )
            connection.execute(
                text("DROP ROLE IF EXISTS vfbiz_ai_document_submitter_login")
            )
        engine.dispose()


def _claim_once(
    repository: PostgresDocumentAiReconciliationRepository,
) -> tuple[DocumentAiOperationReceipt, ...]:
    return repository.list_pending(limit=1)
