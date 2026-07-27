from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.modules.knowledge.domain import (
    IngestionLimits,
    InvalidKnowledgeTransition,
    KnowledgeIngestionJob,
    KnowledgeScope,
    ScanEvidence,
    StageCheckpoint,
)

NOW = datetime(2026, 7, 25, tzinfo=UTC)


def limits(*, attempts: int = 3) -> IngestionLimits:
    return IngestionLimits(
        max_source_bytes=10_000,
        max_units=3,
        max_decoded_pixels_per_unit=1_000_000,
        max_expansion_ratio=20,
        max_archive_depth=0,
        max_extracted_files=1,
        max_stage_seconds=30,
        max_attempts_per_stage=attempts,
    )


def job(*, attempts: int = 3) -> KnowledgeIngestionJob:
    return KnowledgeIngestionJob(
        job_id=uuid4(),
        source_id="synthetic-warranty",
        source_revision="revision-1",
        source_snapshot_hash="a" * 64,
        expected_checksum_sha256="b" * 64,
        scope=KnowledgeScope(
            domain="warranty",
            locale="vi-VN",
            assistant_profile="public_customer",
            acl_namespace="public_customer:warranty:vi-VN",
        ),
        parser_revision="utf8-lines-v1",
        chunker_revision="semantic-v1",
        scanner_revision="deterministic-v1",
        embedding_revision="fake-embedding-v1",
        embedding_dimension=8,
        policy_revision="policy-v1",
        code_revision="1" * 40,
        candidate_namespace="candidate/public_customer/warranty/vi-vn/revision-1",
        limits=limits(attempts=attempts),
        created_at=NOW,
        updated_at=NOW,
    )


def checkpoint(
    stage: str,
    *,
    cursor: int = 1,
    count: int = 1,
    completed: bool = True,
) -> StageCheckpoint:
    return StageCheckpoint(
        stage=stage,
        unit_cursor=cursor,
        unit_count=count,
        input_hash="c" * 64,
        output_hash="d" * 64,
        artifact_ref=f"artifacts/{stage}/{cursor}",
        byte_count=32,
        record_count=1,
        completed=completed,
    )  # type: ignore[arg-type]


def evidence(phase: str) -> ScanEvidence:
    return ScanEvidence(
        phase=phase,
        scanner_revision="deterministic-v1",
        policy_revision="policy-v1",
        result="passed",
        finding_count=0,
        evidence_hash="e" * 64,
    )  # type: ignore[arg-type]


def claim(current: KnowledgeIngestionJob, token: int = 1) -> KnowledgeIngestionJob:
    return current.claim(
        fencing_token=token,
        lease_expires_at=NOW + timedelta(minutes=1),
        at=NOW,
    )


def complete(
    current: KnowledgeIngestionJob,
    *,
    scan: ScanEvidence | None = None,
    final: bool = False,
) -> KnowledgeIngestionJob:
    if current.status == "queued":
        current = claim(current, current.fencing_token + 1)
    current = current.checkpoint(
        checkpoint(current.current_stage), fencing_token=current.fencing_token, at=NOW
    )
    return current.complete_stage(
        fencing_token=current.fencing_token,
        at=NOW,
        scan_evidence=scan,
        final_manifest_ref="candidate/manifests/final.json" if final else None,
        final_manifest_hash="f" * 64 if final else None,
    )


def test_pipeline_requires_both_scan_gates_before_candidate_visibility() -> None:
    current = claim(job())
    current = complete(current)  # quarantine
    current = complete(current, scan=evidence("pre_parse"))
    current = complete(current)  # parse
    current = complete(current, scan=evidence("post_parse"))
    current = complete(current)  # chunk
    current = complete(current)  # embed
    current = complete(current, final=True)  # verify

    assert current.status == "candidate_ready"
    assert current.final_manifest_hash == "f" * 64


def test_checkpoint_is_monotonic_and_stale_worker_is_rejected() -> None:
    current = claim(job())
    current = current.checkpoint(
        checkpoint("quarantine", cursor=1, count=2, completed=False),
        fencing_token=1,
        at=NOW,
    )
    with pytest.raises(InvalidKnowledgeTransition, match="backwards"):
        current.checkpoint(
            checkpoint("quarantine", cursor=0, count=2, completed=False),
            fencing_token=1,
            at=NOW,
        )
    with pytest.raises(InvalidKnowledgeTransition, match="stale"):
        current.checkpoint(
            checkpoint("quarantine", cursor=2, count=2),
            fencing_token=2,
            at=NOW,
        )


def test_retry_resumes_same_stage_and_attempt_exhaustion_dead_letters() -> None:
    current = claim(job(attempts=2))
    retry = current.failed(
        code="PARSER_TIMEOUT",
        disposition="transient",
        next_attempt_at=NOW + timedelta(seconds=5),
        fencing_token=1,
        at=NOW,
    )
    assert retry.status == "retry_wait"
    assert retry.current_stage == "quarantine"

    running = retry.claim(
        fencing_token=2,
        lease_expires_at=NOW + timedelta(minutes=1),
        at=NOW + timedelta(seconds=5),
    )
    exhausted = running.failed(
        code="PARSER_TIMEOUT",
        disposition="transient",
        next_attempt_at=None,
        fencing_token=2,
        at=NOW + timedelta(seconds=5),
    )
    assert exhausted.status == "dead_lettered"
    assert exhausted.failure_stage == "quarantine"


def test_permanent_failure_never_retries() -> None:
    current = claim(job()).failed(
        code="MALWARE_DETECTED",
        disposition="permanent",
        next_attempt_at=None,
        fencing_token=1,
        at=NOW,
    )
    assert current.status == "failed_safely"


def test_deletion_keeps_locator_until_physical_evidence_exists() -> None:
    current = job().model_copy(
        update={
            "final_manifest_ref": "candidate/manifests/final.json",
            "final_manifest_hash": "f" * 64,
        }
    )
    pending = current.request_deletion(generation=1, at=NOW)
    assert pending.final_manifest_ref is not None
    deleting = pending.deletion_started(
        fencing_token=1,
        lease_expires_at=NOW + timedelta(minutes=1),
        at=NOW,
    )
    deleted = deleting.deletion_completed(evidence_hash="9" * 64, fencing_token=1, at=NOW)

    assert deleted.status == "tombstoned"
    assert deleted.final_manifest_ref is None
    assert deleted.checkpoints == ()
    assert deleted.deletion_evidence_hash == "9" * 64


def test_command_fingerprint_is_immutable_and_excludes_progress() -> None:
    initial = job()
    progressed = claim(initial)
    assert progressed.command_fingerprint == initial.command_fingerprint
    with pytest.raises(ValueError, match="fingerprint"):
        KnowledgeIngestionJob.model_validate(
            initial.model_dump() | {"parser_revision": "other-parser"}
        )
