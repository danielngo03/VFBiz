from io import BytesIO
from uuid import uuid4

import pytest

from app.modules.datasets.domain import (
    AllowedUse,
    DatasetArtifact,
    DatasetFetch,
    DatasetScanEvidence,
    DatasetSource,
    DlpDecision,
    FetchState,
    ProcessingStage,
    RegistryInvariantError,
    SourceStatus,
    TrustZone,
)
from app.modules.datasets.infrastructure import LocalContentAddressedObjectStore


def source() -> DatasetSource:
    return DatasetSource(
        source_id=uuid4(),
        source_key="massive",
        source_revision="refs/convert/parquet@abc123",
        origin_uri="https://huggingface.co/datasets/AmazonScience/massive",
        status=SourceStatus.CANDIDATE,
        owner_ref="data-owner",
        classification="public",
        proposed_uses=(AllowedUse.SFT, AllowedUse.EVALUATION),
    )


def test_source_requires_rights_evidence_before_fetch_approval() -> None:
    with pytest.raises(RegistryInvariantError, match="rights and terms"):
        source().transition(SourceStatus.FETCH_APPROVED)

    approved = source().transition(
        SourceStatus.FETCH_APPROVED,
        rights_evidence_ref="approval:legal:42",
        rights_evidence_sha256="a" * 64,
        terms_sha256="b" * 64,
    )
    purpose = approved.transition(
        SourceStatus.PURPOSE_APPROVED,
        approved_uses=(AllowedUse.EVALUATION,),
    )
    assert purpose.approved_uses == (AllowedUse.EVALUATION,)
    assert purpose.row_version == 3


def test_fetch_cannot_skip_quarantine_or_verify_without_observed_digest() -> None:
    fetch = DatasetFetch(
        fetch_id=uuid4(),
        source_id=uuid4(),
        state=FetchState.REQUESTED,
        requested_by="dataset-source-researcher",
        approval_evidence_ref="approval:fetch:42",
        approval_evidence_sha256="c" * 64,
    )
    with pytest.raises(RegistryInvariantError, match="invalid fetch transition"):
        fetch.transition(FetchState.VERIFIED)
    downloading = fetch.transition(FetchState.DOWNLOADING)
    with pytest.raises(RegistryInvariantError, match="requires digest"):
        downloading.transition(FetchState.QUARANTINED)


def test_fetch_scan_pass_requires_content_bound_clear_evidence() -> None:
    digest = "d" * 64
    fetch = DatasetFetch(
        fetch_id=uuid4(),
        source_id=uuid4(),
        state=FetchState.VERIFIED,
        requested_by="dataset-source-researcher",
        approval_evidence_ref="approval:fetch:42",
        approval_evidence_sha256="c" * 64,
        observed_sha256=digest,
        byte_size=42,
        quarantine_uri=f"file:///quarantine/{digest}",
    )
    with pytest.raises(RegistryInvariantError, match="immutable scan evidence"):
        fetch.transition(FetchState.SCAN_PASSED)

    review_required = DatasetScanEvidence(
        evidence_ref="scan://dataset/42",
        evidence_sha256="e" * 64,
        artifact_sha256=digest,
        scanner_revision="vivi-dataset-inspection-v1",
        signature_revision="clamav-daily-28075",
        structural_valid=True,
        malware_passed=True,
        dlp_decision=DlpDecision.REVIEW_REQUIRED,
    )
    with pytest.raises(RegistryInvariantError, match="unresolved security blockers"):
        fetch.transition(FetchState.SCAN_PASSED, scan_evidence=review_required)

    clear = DatasetScanEvidence(
        evidence_ref="scan://dataset/43",
        evidence_sha256="f" * 64,
        artifact_sha256=digest,
        scanner_revision="vivi-dataset-inspection-v1",
        signature_revision="clamav-daily-28075",
        structural_valid=True,
        malware_passed=True,
        dlp_decision=DlpDecision.PASSED,
    )
    passed = fetch.transition(FetchState.SCAN_PASSED, scan_evidence=clear)
    assert passed.scan_evidence == clear


def test_fetch_scan_evidence_must_bind_observed_artifact() -> None:
    fetch = DatasetFetch(
        fetch_id=uuid4(),
        source_id=uuid4(),
        state=FetchState.VERIFIED,
        requested_by="dataset-source-researcher",
        approval_evidence_ref="approval:fetch:42",
        approval_evidence_sha256="c" * 64,
        observed_sha256="a" * 64,
        byte_size=42,
        quarantine_uri="file:///quarantine/artifact",
    )
    evidence = DatasetScanEvidence(
        evidence_ref="scan://dataset/42",
        evidence_sha256="e" * 64,
        artifact_sha256="b" * 64,
        scanner_revision="vivi-dataset-inspection-v1",
        signature_revision="clamav-daily-28075",
        structural_valid=True,
        malware_passed=True,
        dlp_decision=DlpDecision.PASSED,
    )
    with pytest.raises(RegistryInvariantError, match="does not bind"):
        fetch.transition(FetchState.SCAN_PASSED, scan_evidence=evidence)


def test_restricted_evaluation_artifact_rejects_training_use() -> None:
    with pytest.raises(RegistryInvariantError, match="evaluation-only"):
        DatasetArtifact(
            artifact_id=uuid4(),
            content_sha256="d" * 64,
            trust_zone=TrustZone.RESTRICTED_EVALUATION,
            processing_stage=ProcessingStage.ADJUDICATED,
            allowed_uses=(AllowedUse.EVALUATION, AllowedUse.SFT),
            storage_uri="gs://vfbiz/restricted-evaluation/dd/dataset.jsonl",
            media_type="application/x-ndjson",
            byte_size=100,
            classification="restricted",
        )


def test_local_store_is_bounded_content_addressed_and_idempotent(tmp_path) -> None:
    store = LocalContentAddressedObjectStore(tmp_path / "datasets")
    first = store.put_stream(
        zone=TrustZone.QUARANTINE,
        stream=BytesIO(b'{"text":"xin chao"}\n'),
        media_type="application/x-ndjson",
        max_bytes=1024,
    )
    second = store.put_stream(
        zone=TrustZone.QUARANTINE,
        stream=BytesIO(b'{"text":"xin chao"}\n'),
        media_type="application/x-ndjson",
        max_bytes=1024,
    )
    assert first == second
    assert store.path_for_test(first).read_bytes() == b'{"text":"xin chao"}\n'

    with pytest.raises(RegistryInvariantError, match="byte limit"):
        store.put_stream(
            zone=TrustZone.CANDIDATE,
            stream=BytesIO(b"too-large"),
            media_type="application/octet-stream",
            max_bytes=3,
        )
