from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.modules.knowledge.application.cloud_ingestion_ports import (
    DocumentAiBatchRequest,
    DocumentAiExtractionEvidence,
    DocumentAiOperationReceipt,
    DocumentAiReconciliationFailureEvidence,
)
from app.modules.knowledge.application.ingestion_ports import (
    PermanentIngestionFailure,
    TransientIngestionFailure,
)
from app.modules.knowledge.infrastructure.cloud_ingestion_models import (
    DocumentAiExtractionEvidenceRecord,
    DocumentAiOperationObservationRecord,
    DocumentAiReconciliationClaimRecord,
    DocumentAiReconciliationFailureRecord,
    DocumentAiSubmissionRecord,
)


class PostgresDocumentAiSubmissionLedger:
    """Durable fail-closed reservation around non-idempotent provider submission."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        clock: Callable[[], datetime],
        reservation_ttl_seconds: int = 180,
        max_pages_per_day: int = 500,
    ) -> None:
        if reservation_ttl_seconds < 60 or reservation_ttl_seconds > 900:
            raise ValueError("Document AI reservation TTL must be between 60 and 900 seconds")
        if max_pages_per_day < 1 or max_pages_per_day > 50_000:
            raise ValueError("Document AI daily page budget is invalid")
        self._sessions = sessions
        self._clock = clock
        self._reservation_ttl = timedelta(seconds=reservation_ttl_seconds)
        self._max_pages_per_day = max_pages_per_day

    def find(self, idempotency_key: str) -> DocumentAiOperationReceipt | None:
        with self._sessions() as session:
            record = session.execute(
                select(DocumentAiSubmissionRecord).where(
                    DocumentAiSubmissionRecord.idempotency_key == idempotency_key
                )
            ).scalar_one_or_none()
            return _receipt_or_indeterminate(record, now=self._clock())

    def reserve(self, request: DocumentAiBatchRequest) -> DocumentAiOperationReceipt | None:
        request_payload = request.model_dump(mode="json")
        request_digest = _canonical_digest(request_payload)
        with self._sessions.begin() as session:
            session.execute(text("SELECT pg_advisory_xact_lock(1990021)"))
            now = self._clock()
            budget_date = now.date()
            inserted = session.execute(
                insert(DocumentAiSubmissionRecord)
                .values(
                    idempotency_key=request.idempotency_key,
                    request_digest=request_digest,
                    request_payload=request_payload,
                    state="reserved",
                    page_count=request.page_count,
                    budget_date=budget_date,
                    reservation_expires_at=now + self._reservation_ttl,
                )
                .on_conflict_do_nothing(constraint="uq_ai_document_submission_idempotency_key")
                .returning(DocumentAiSubmissionRecord.idempotency_key)
            ).scalar_one_or_none()
            if inserted is not None:
                used_pages = session.scalar(
                    select(func.coalesce(func.sum(DocumentAiSubmissionRecord.page_count), 0)).where(
                        DocumentAiSubmissionRecord.budget_date == budget_date
                    )
                )
                if not isinstance(used_pages, int) or used_pages > self._max_pages_per_day:
                    raise PermanentIngestionFailure("DOCUMENT_AI_DAILY_PAGE_BUDGET_EXCEEDED")
                return None
            record = session.execute(
                select(DocumentAiSubmissionRecord)
                .where(DocumentAiSubmissionRecord.idempotency_key == request.idempotency_key)
                .with_for_update()
            ).scalar_one()
            _assert_request(record, request_payload, request_digest)
            return _receipt_or_indeterminate(record, now=self._clock())

    def record(self, receipt: DocumentAiOperationReceipt) -> DocumentAiOperationReceipt:
        receipt_payload = receipt.model_dump(mode="json")
        with self._sessions.begin() as session:
            record = session.execute(
                select(DocumentAiSubmissionRecord)
                .where(DocumentAiSubmissionRecord.idempotency_key == receipt.idempotency_key)
                .with_for_update()
            ).scalar_one_or_none()
            if record is None:
                raise PermanentIngestionFailure("DOCUMENT_AI_RESERVATION_MISSING")
            try:
                request = DocumentAiBatchRequest.model_validate(record.request_payload)
            except ValueError as error:
                raise PermanentIngestionFailure("DOCUMENT_AI_LEDGER_REQUEST_INVALID") from error
            _assert_receipt_matches_request(receipt, request)
            if record.state == "submitted":
                existing = _receipt_or_indeterminate(record, now=self._clock())
                if existing is None:
                    raise PermanentIngestionFailure("DOCUMENT_AI_LEDGER_RECEIPT_INVALID")
                if existing != receipt:
                    raise PermanentIngestionFailure("DOCUMENT_AI_IDEMPOTENCY_CONFLICT")
                return existing
            record.state = "submitted"
            record.receipt_payload = receipt_payload
            session.flush()
        return receipt


class PostgresDocumentAiReconciliationRepository:
    """Append-only operation observations and content-free extraction evidence."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        clock: Callable[[], datetime] | None = None,
        claim_lease_seconds: int = 300,
        owner_token: str | None = None,
    ) -> None:
        if claim_lease_seconds < 60 or claim_lease_seconds > 300:
            raise ValueError("Document AI reconciliation claim lease is invalid")
        self._sessions = sessions
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_failure_attempts = 3
        self._claim_lease = timedelta(seconds=claim_lease_seconds)
        self._owner_token = owner_token or uuid4().hex + uuid4().hex
        self._claim_fences: dict[str, int] = {}

    def list_pending(self, *, limit: int) -> tuple[DocumentAiOperationReceipt, ...]:
        if limit < 1 or limit > 5:
            raise ValueError("Document AI reconciliation batch limit must be between 1 and 5")
        now = self._clock()
        extraction_exists = (
            select(DocumentAiExtractionEvidenceRecord.id)
            .where(
                DocumentAiExtractionEvidenceRecord.idempotency_key
                == DocumentAiSubmissionRecord.idempotency_key
            )
            .exists()
        )
        completed_terminal_exists = (
            select(DocumentAiOperationObservationRecord.id)
            .where(
                DocumentAiOperationObservationRecord.idempotency_key
                == DocumentAiSubmissionRecord.idempotency_key,
                (
                    DocumentAiOperationObservationRecord.state.in_(
                        ("failed", "cancelled")
                    )
                    | (
                        (DocumentAiOperationObservationRecord.state == "succeeded")
                        & extraction_exists
                    )
                ),
            )
            .exists()
        )
        latest_failure_attempt = (
            select(func.max(DocumentAiReconciliationFailureRecord.attempt))
            .where(
                DocumentAiReconciliationFailureRecord.idempotency_key
                == DocumentAiSubmissionRecord.idempotency_key
            )
            .correlate(DocumentAiSubmissionRecord)
            .scalar_subquery()
        )
        blocked_failure_exists = (
            select(DocumentAiReconciliationFailureRecord.id)
            .where(
                DocumentAiReconciliationFailureRecord.idempotency_key
                == DocumentAiSubmissionRecord.idempotency_key,
                DocumentAiReconciliationFailureRecord.attempt == latest_failure_attempt,
                (
                    DocumentAiReconciliationFailureRecord.disposition == "quarantined"
                )
                | (
                    DocumentAiReconciliationFailureRecord.next_retry_at
                    > now
                ),
            )
            .exists()
        )
        active_claim_exists = (
            select(DocumentAiReconciliationClaimRecord.id)
            .where(
                DocumentAiReconciliationClaimRecord.idempotency_key
                == DocumentAiSubmissionRecord.idempotency_key,
                DocumentAiReconciliationClaimRecord.released_at.is_(None),
                DocumentAiReconciliationClaimRecord.lease_until > now,
            )
            .exists()
        )
        with self._sessions.begin() as session:
            session.execute(text("SELECT pg_advisory_xact_lock(1990023)"))
            records = tuple(
                session.execute(
                select(DocumentAiSubmissionRecord)
                .where(
                    DocumentAiSubmissionRecord.state == "submitted",
                    ~completed_terminal_exists,
                    ~blocked_failure_exists,
                    ~active_claim_exists,
                )
                .order_by(DocumentAiSubmissionRecord.created_at)
                .limit(limit)
                ).scalars()
            )
            for record in records:
                fencing_token = session.execute(
                    insert(DocumentAiReconciliationClaimRecord)
                    .values(
                        idempotency_key=record.idempotency_key,
                        owner_token=self._owner_token,
                        fencing_token=1,
                        claimed_at=now,
                        lease_until=now + self._claim_lease,
                        released_at=None,
                    )
                    .on_conflict_do_update(
                        constraint="uq_ai_document_reconciliation_claim_idempotency_key",
                        set_={
                            "owner_token": self._owner_token,
                            "fencing_token": (
                                DocumentAiReconciliationClaimRecord.fencing_token + 1
                            ),
                            "claimed_at": now,
                            "lease_until": now + self._claim_lease,
                            "released_at": None,
                        },
                        where=(
                            DocumentAiReconciliationClaimRecord.released_at.is_not(None)
                            | (DocumentAiReconciliationClaimRecord.lease_until <= now)
                        ),
                    )
                    .returning(DocumentAiReconciliationClaimRecord.fencing_token)
                ).scalar_one_or_none()
                if not isinstance(fencing_token, int):
                    raise PermanentIngestionFailure(
                        "DOCUMENT_AI_RECONCILIATION_CLAIM_CONFLICT"
                    )
                self._claim_fences[record.idempotency_key] = fencing_token
            return tuple(_submitted_receipt(record) for record in records)

    def find_terminal(self, idempotency_key: str) -> DocumentAiOperationReceipt | None:
        with self._sessions() as session:
            record = session.execute(
                select(DocumentAiOperationObservationRecord)
                .where(
                    DocumentAiOperationObservationRecord.idempotency_key
                    == idempotency_key,
                    DocumentAiOperationObservationRecord.state.in_(
                        ("succeeded", "failed", "cancelled")
                    ),
                )
                .order_by(DocumentAiOperationObservationRecord.created_at)
            ).scalar_one_or_none()
            return _operation_receipt(record)

    def record_operation(
        self,
        receipt: DocumentAiOperationReceipt,
    ) -> DocumentAiOperationReceipt:
        if receipt.state == "submitted":
            raise PermanentIngestionFailure("DOCUMENT_AI_RECONCILIATION_STATE_INVALID")
        canonical_payload = _canonical_json(receipt.model_dump(mode="json"))
        observation_digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        with self._sessions.begin() as session:
            submission = session.execute(
                select(DocumentAiSubmissionRecord)
                .where(DocumentAiSubmissionRecord.idempotency_key == receipt.idempotency_key)
                .with_for_update()
            ).scalar_one_or_none()
            submitted = _submitted_receipt(submission)
            _assert_reconciled_matches_submission(receipt, submitted)
            terminal_record = session.execute(
                select(DocumentAiOperationObservationRecord).where(
                    DocumentAiOperationObservationRecord.idempotency_key
                    == receipt.idempotency_key,
                    DocumentAiOperationObservationRecord.state.in_(
                        ("succeeded", "failed", "cancelled")
                    ),
                )
            ).scalar_one_or_none()
            terminal = _operation_receipt(terminal_record)
            if terminal is not None:
                if not _same_terminal_operation(terminal, receipt):
                    raise PermanentIngestionFailure("DOCUMENT_AI_TERMINAL_STATE_CONFLICT")
                return terminal
            _assert_active_claim(
                session,
                idempotency_key=receipt.idempotency_key,
                owner_token=self._owner_token,
                fencing_token=self._claim_fence(receipt.idempotency_key),
                now=self._clock(),
            )
            latest_reconciliation = session.scalar(
                select(func.max(DocumentAiOperationObservationRecord.reconciled_at)).where(
                    DocumentAiOperationObservationRecord.idempotency_key
                    == receipt.idempotency_key
                )
            )
            if (
                isinstance(latest_reconciliation, datetime)
                and receipt.reconciled_at < latest_reconciliation
            ):
                raise PermanentIngestionFailure("DOCUMENT_AI_OBSERVATION_TIME_REGRESSION")
            inserted = session.execute(
                insert(DocumentAiOperationObservationRecord)
                .values(
                    idempotency_key=receipt.idempotency_key,
                    operation_name=receipt.operation_name,
                    state=receipt.state,
                    observation_digest=observation_digest,
                    canonical_payload=canonical_payload,
                    reconciled_at=receipt.reconciled_at,
                )
                .on_conflict_do_nothing(
                    constraint="uq_ai_document_operation_observation_digest"
                )
                .returning(DocumentAiOperationObservationRecord.observation_digest)
            ).scalar_one_or_none()
            if inserted is None:
                existing = session.execute(
                    select(DocumentAiOperationObservationRecord).where(
                        DocumentAiOperationObservationRecord.idempotency_key
                        == receipt.idempotency_key,
                        DocumentAiOperationObservationRecord.observation_digest
                        == observation_digest,
                    )
                ).scalar_one()
                if existing.canonical_payload != canonical_payload:
                    raise PermanentIngestionFailure("DOCUMENT_AI_OBSERVATION_DIGEST_CONFLICT")
            if receipt.state != "succeeded":
                _release_claim(
                    session,
                    idempotency_key=receipt.idempotency_key,
                    owner_token=self._owner_token,
                    fencing_token=self._claim_fence(receipt.idempotency_key),
                    now=self._clock(),
                )
                self._claim_fences.pop(receipt.idempotency_key, None)
        return receipt

    def find_extraction(
        self,
        idempotency_key: str,
    ) -> DocumentAiExtractionEvidence | None:
        with self._sessions() as session:
            record = session.execute(
                select(DocumentAiExtractionEvidenceRecord).where(
                    DocumentAiExtractionEvidenceRecord.idempotency_key == idempotency_key
                )
            ).scalar_one_or_none()
            return _extraction_evidence(record)

    def record_extraction(
        self,
        evidence: DocumentAiExtractionEvidence,
    ) -> DocumentAiExtractionEvidence:
        canonical_payload = evidence.canonical_payload()
        with self._sessions.begin() as session:
            submission = session.execute(
                select(DocumentAiSubmissionRecord)
                .where(
                    DocumentAiSubmissionRecord.idempotency_key
                    == evidence.idempotency_key
                )
                .with_for_update()
            ).scalar_one_or_none()
            submitted = _submitted_receipt(submission)
            existing_record = session.execute(
                select(DocumentAiExtractionEvidenceRecord).where(
                    DocumentAiExtractionEvidenceRecord.idempotency_key
                    == evidence.idempotency_key
                )
            ).scalar_one_or_none()
            existing_evidence = _extraction_evidence(existing_record)
            if existing_evidence is not None:
                if existing_evidence != evidence:
                    raise PermanentIngestionFailure(
                        "DOCUMENT_AI_EXTRACTION_EVIDENCE_CONFLICT"
                    )
                return existing_evidence
            _assert_active_claim(
                session,
                idempotency_key=evidence.idempotency_key,
                owner_token=self._owner_token,
                fencing_token=self._claim_fence(evidence.idempotency_key),
                now=self._clock(),
            )
            terminal_record = session.execute(
                select(DocumentAiOperationObservationRecord).where(
                    DocumentAiOperationObservationRecord.idempotency_key
                    == evidence.idempotency_key,
                    DocumentAiOperationObservationRecord.state == "succeeded",
                )
            ).scalar_one_or_none()
            terminal = _operation_receipt(terminal_record)
            if terminal is None:
                raise PermanentIngestionFailure("DOCUMENT_AI_SUCCEEDED_OBSERVATION_MISSING")
            _assert_reconciled_matches_submission(terminal, submitted)
            _assert_extraction_matches_receipt(evidence, terminal)
            inserted = session.execute(
                insert(DocumentAiExtractionEvidenceRecord)
                .values(
                    idempotency_key=evidence.idempotency_key,
                    evidence_digest=evidence.evidence_digest,
                    canonical_payload=canonical_payload,
                    expected_page_count=evidence.expected_page_count,
                    review_required_count=evidence.review_required_count,
                )
                .on_conflict_do_nothing(
                    constraint="uq_ai_document_extraction_idempotency_key"
                )
                .returning(DocumentAiExtractionEvidenceRecord.evidence_digest)
            ).scalar_one_or_none()
            if inserted is None:
                existing = session.execute(
                    select(DocumentAiExtractionEvidenceRecord).where(
                        DocumentAiExtractionEvidenceRecord.idempotency_key
                        == evidence.idempotency_key
                    )
                ).scalar_one()
                observed = _extraction_evidence(existing)
                if observed != evidence:
                    raise PermanentIngestionFailure(
                        "DOCUMENT_AI_EXTRACTION_EVIDENCE_CONFLICT"
                    )
                if observed is None:
                    raise PermanentIngestionFailure(
                        "DOCUMENT_AI_EXTRACTION_EVIDENCE_INVALID"
                    )
                return observed
            _release_claim(
                session,
                idempotency_key=evidence.idempotency_key,
                owner_token=self._owner_token,
                fencing_token=self._claim_fence(evidence.idempotency_key),
                now=self._clock(),
            )
            self._claim_fences.pop(evidence.idempotency_key, None)
        return evidence

    def record_failure(
        self,
        receipt: DocumentAiOperationReceipt,
        *,
        failure_code: str,
        retryable: bool,
    ) -> DocumentAiReconciliationFailureEvidence:
        with self._sessions.begin() as session:
            submission = session.execute(
                select(DocumentAiSubmissionRecord)
                .where(
                    DocumentAiSubmissionRecord.idempotency_key
                    == receipt.idempotency_key
                )
                .with_for_update()
            ).scalar_one_or_none()
            submitted = _submitted_receipt(submission)
            _assert_reconciled_matches_submission(receipt, submitted)
            _assert_active_claim(
                session,
                idempotency_key=receipt.idempotency_key,
                owner_token=self._owner_token,
                fencing_token=self._claim_fence(receipt.idempotency_key),
                now=self._clock(),
                allow_expired=True,
            )
            existing_quarantine = session.scalar(
                select(DocumentAiReconciliationFailureRecord.id).where(
                    DocumentAiReconciliationFailureRecord.idempotency_key
                    == receipt.idempotency_key,
                    DocumentAiReconciliationFailureRecord.disposition == "quarantined",
                )
            )
            if existing_quarantine is not None:
                raise PermanentIngestionFailure(
                    "DOCUMENT_AI_RECONCILIATION_ALREADY_QUARANTINED"
                )
            latest_attempt = session.scalar(
                select(
                    func.coalesce(
                        func.max(DocumentAiReconciliationFailureRecord.attempt),
                        0,
                    )
                ).where(
                    DocumentAiReconciliationFailureRecord.idempotency_key
                    == receipt.idempotency_key
                )
            )
            if not isinstance(latest_attempt, int):
                raise PermanentIngestionFailure("DOCUMENT_AI_FAILURE_LEDGER_INVALID")
            attempt = latest_attempt + 1
            if attempt > self._max_failure_attempts:
                raise PermanentIngestionFailure("DOCUMENT_AI_FAILURE_ATTEMPT_LIMIT_INVALID")
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
            session.execute(
                insert(DocumentAiReconciliationFailureRecord).values(
                    idempotency_key=evidence.idempotency_key,
                    attempt=evidence.attempt,
                    failure_code=evidence.failure_code,
                    retryable=evidence.retryable,
                    disposition=evidence.disposition,
                    evidence_digest=evidence.evidence_digest,
                    canonical_payload=evidence.canonical_payload(),
                    observed_at=evidence.observed_at,
                    next_retry_at=evidence.next_retry_at,
                )
            )
            _release_claim(
                session,
                idempotency_key=receipt.idempotency_key,
                owner_token=self._owner_token,
                fencing_token=self._claim_fence(receipt.idempotency_key),
                now=self._clock(),
                allow_expired=True,
            )
            self._claim_fences.pop(receipt.idempotency_key, None)
        return evidence

    def _claim_fence(self, idempotency_key: str) -> int:
        fencing_token = self._claim_fences.get(idempotency_key)
        if fencing_token is None:
            raise PermanentIngestionFailure("DOCUMENT_AI_RECONCILIATION_CLAIM_LOST")
        return fencing_token


def _assert_active_claim(
    session: Session,
    *,
    idempotency_key: str,
    owner_token: str,
    fencing_token: int,
    now: datetime,
    allow_expired: bool = False,
) -> DocumentAiReconciliationClaimRecord:
    claim = session.execute(
        select(DocumentAiReconciliationClaimRecord)
        .where(
            DocumentAiReconciliationClaimRecord.idempotency_key == idempotency_key
        )
        .with_for_update()
    ).scalar_one_or_none()
    if (
        claim is None
        or claim.owner_token != owner_token
        or claim.fencing_token != fencing_token
        or claim.released_at is not None
    ):
        raise PermanentIngestionFailure("DOCUMENT_AI_RECONCILIATION_CLAIM_LOST")
    if not allow_expired and claim.lease_until <= now:
        raise TransientIngestionFailure("DOCUMENT_AI_RECONCILIATION_CLAIM_EXPIRED")
    return claim


def _release_claim(
    session: Session,
    *,
    idempotency_key: str,
    owner_token: str,
    fencing_token: int,
    now: datetime,
    allow_expired: bool = False,
) -> None:
    predicates = [
        DocumentAiReconciliationClaimRecord.idempotency_key == idempotency_key,
        DocumentAiReconciliationClaimRecord.owner_token == owner_token,
        DocumentAiReconciliationClaimRecord.fencing_token == fencing_token,
        DocumentAiReconciliationClaimRecord.released_at.is_(None),
    ]
    if not allow_expired:
        predicates.append(DocumentAiReconciliationClaimRecord.lease_until > now)
    released = session.execute(
        update(DocumentAiReconciliationClaimRecord)
        .where(*predicates)
        .values(released_at=now)
        .returning(DocumentAiReconciliationClaimRecord.id)
    ).scalar_one_or_none()
    if released is None:
        raise PermanentIngestionFailure("DOCUMENT_AI_RECONCILIATION_CLAIM_LOST")


def _receipt_or_indeterminate(
    record: DocumentAiSubmissionRecord | None,
    *,
    now: datetime,
) -> DocumentAiOperationReceipt | None:
    if record is None:
        return None
    if record.state != "submitted" or record.receipt_payload is None:
        if record.reservation_expires_at > now:
            raise TransientIngestionFailure("DOCUMENT_AI_SUBMISSION_IN_PROGRESS")
        raise PermanentIngestionFailure("DOCUMENT_AI_SUBMISSION_INDETERMINATE")
    try:
        return DocumentAiOperationReceipt.model_validate(record.receipt_payload)
    except ValueError as error:
        raise PermanentIngestionFailure("DOCUMENT_AI_LEDGER_RECEIPT_INVALID") from error


def _assert_request(
    record: DocumentAiSubmissionRecord,
    request_payload: dict[str, object],
    request_digest: str,
) -> None:
    stored_payload = cast(dict[str, object], record.request_payload)
    if record.request_digest != request_digest or stored_payload != request_payload:
        raise PermanentIngestionFailure("DOCUMENT_AI_IDEMPOTENCY_CONFLICT")


def _canonical_digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _assert_receipt_matches_request(
    receipt: DocumentAiOperationReceipt,
    request: DocumentAiBatchRequest,
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


def _submitted_receipt(
    record: DocumentAiSubmissionRecord | None,
) -> DocumentAiOperationReceipt:
    if record is None or record.state != "submitted" or record.receipt_payload is None:
        raise PermanentIngestionFailure("DOCUMENT_AI_SUBMISSION_RECEIPT_MISSING")
    try:
        return DocumentAiOperationReceipt.model_validate(record.receipt_payload)
    except ValueError as error:
        raise PermanentIngestionFailure("DOCUMENT_AI_LEDGER_RECEIPT_INVALID") from error


def _operation_receipt(
    record: DocumentAiOperationObservationRecord | None,
) -> DocumentAiOperationReceipt | None:
    if record is None:
        return None
    try:
        payload: object = json.loads(record.canonical_payload)
        receipt = DocumentAiOperationReceipt.model_validate(payload)
    except (json.JSONDecodeError, ValueError) as error:
        raise PermanentIngestionFailure("DOCUMENT_AI_OBSERVATION_INVALID") from error
    expected_digest = hashlib.sha256(record.canonical_payload.encode("utf-8")).hexdigest()
    if (
        receipt.idempotency_key != record.idempotency_key
        or receipt.operation_name != record.operation_name
        or receipt.state != record.state
        or receipt.reconciled_at != record.reconciled_at
        or expected_digest != record.observation_digest
    ):
        raise PermanentIngestionFailure("DOCUMENT_AI_OBSERVATION_INVALID")
    return receipt


def _extraction_evidence(
    record: DocumentAiExtractionEvidenceRecord | None,
) -> DocumentAiExtractionEvidence | None:
    if record is None:
        return None
    try:
        payload: object = json.loads(record.canonical_payload)
        evidence = DocumentAiExtractionEvidence.model_validate(
            {**cast(dict[str, object], payload), "evidence_digest": record.evidence_digest}
        )
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise PermanentIngestionFailure("DOCUMENT_AI_EXTRACTION_EVIDENCE_INVALID") from error
    if (
        evidence.idempotency_key != record.idempotency_key
        or evidence.expected_page_count != record.expected_page_count
        or evidence.review_required_count != record.review_required_count
    ):
        raise PermanentIngestionFailure("DOCUMENT_AI_EXTRACTION_EVIDENCE_INVALID")
    return evidence


def _assert_reconciled_matches_submission(
    receipt: DocumentAiOperationReceipt,
    submitted: DocumentAiOperationReceipt,
) -> None:
    if (
        receipt.idempotency_key != submitted.idempotency_key
        or receipt.job_id != submitted.job_id
        or receipt.operation_name != submitted.operation_name
        or receipt.input != submitted.input
        or receipt.output_prefix != submitted.output_prefix
        or receipt.processor_revision != submitted.processor_revision
        or receipt.page_count != submitted.page_count
        or receipt.fencing_token != submitted.fencing_token
        or receipt.submitted_at != submitted.submitted_at
    ):
        raise PermanentIngestionFailure("DOCUMENT_AI_OPERATION_IDENTITY_MISMATCH")


def _assert_extraction_matches_receipt(
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
