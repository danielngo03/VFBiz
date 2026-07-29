from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.datasets.application.curation.release_provenance import (
    DatasetReleaseProvenanceAuthority,
)
from app.modules.datasets.application.ports.registry import (
    DatasetSourceProvenance,
)
from app.modules.datasets.domain import (
    AllowedUse,
    DatasetFetch,
    DatasetScanEvidence,
    DatasetSource,
    DlpDecision,
    FetchState,
    SourceStatus,
)
from tests.unit.datasets.test_manifest_v4_migration import released_v4_manifest


class ProvenanceRegistryFixture:
    def __init__(self, resolution: DatasetSourceProvenance | None) -> None:
        self.resolution = resolution
        self.requests: list[tuple[str, str, str]] = []

    async def resolve_source_provenance(
        self,
        *,
        source_key: str,
        source_revision: str,
        artifact_sha256: str,
    ) -> DatasetSourceProvenance | None:
        self.requests.append((source_key, source_revision, artifact_sha256))
        return self.resolution


def approved_source(*, approved_use: AllowedUse = AllowedUse.CLASSIFIER_TRAINING) -> DatasetSource:
    return DatasetSource(
        source_id=uuid4(),
        source_key="approved-source",
        source_revision="revision-1",
        origin_uri="urn:vfbiz:dataset:approved-source",
        status=SourceStatus.PURPOSE_APPROVED,
        owner_ref="data-owner",
        classification="internal",
        proposed_uses=(AllowedUse.CLASSIFIER_TRAINING, AllowedUse.EVALUATION),
        approved_uses=(approved_use,),
        rights_evidence_ref="approval:rights:1",
        rights_evidence_sha256="a" * 64,
        terms_sha256="b" * 64,
    )


def scanned_fetch(source: DatasetSource) -> DatasetFetch:
    digest = "4" * 64
    return DatasetFetch(
        fetch_id=uuid4(),
        source_id=source.source_id,
        state=FetchState.SCAN_PASSED,
        requested_by="dataset-source-researcher",
        approval_evidence_ref="approval:fetch:1",
        approval_evidence_sha256="c" * 64,
        observed_sha256=digest,
        byte_size=42,
        quarantine_uri=f"file:///quarantine/{digest}",
        scan_evidence=DatasetScanEvidence(
            evidence_ref="scan://unit/1",
            evidence_sha256="d" * 64,
            artifact_sha256=digest,
            scanner_revision="vivi-dataset-inspection-v1",
            signature_revision="clamav-daily-28075",
            structural_valid=True,
            malware_passed=True,
            dlp_decision=DlpDecision.PASSED,
        ),
    )


@pytest.mark.asyncio
async def test_candidate_manifest_does_not_claim_registry_authority() -> None:
    manifest = released_v4_manifest()
    manifest["status"] = "candidate"
    registry = ProvenanceRegistryFixture(None)

    errors = await DatasetReleaseProvenanceAuthority(registry).errors(manifest)

    assert errors == []
    assert registry.requests == []


@pytest.mark.asyncio
async def test_release_requires_exact_purpose_approved_scanned_source() -> None:
    source = approved_source()
    registry = ProvenanceRegistryFixture(
        DatasetSourceProvenance(source=source, scan_passed_fetch=scanned_fetch(source))
    )

    errors = await DatasetReleaseProvenanceAuthority(registry).errors(
        released_v4_manifest()
    )

    assert errors == []
    assert registry.requests == [
        ("approved-source", "revision-1", "4" * 64),
    ]


@pytest.mark.asyncio
async def test_release_rechecks_source_identity_returned_by_registry() -> None:
    wrong_source = replace(approved_source(), source_key="different-source")
    registry = ProvenanceRegistryFixture(
        DatasetSourceProvenance(
            source=wrong_source,
            scan_passed_fetch=scanned_fetch(wrong_source),
        )
    )

    errors = await DatasetReleaseProvenanceAuthority(registry).errors(
        released_v4_manifest()
    )

    assert any("returned mismatched source identity" in error for error in errors)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resolution", "expected"),
    [
        (None, "does not resolve"),
        (
            DatasetSourceProvenance(
                source=approved_source(approved_use=AllowedUse.EVALUATION),
                scan_passed_fetch=None,
            ),
            "not approved for classifier-training",
        ),
        (
            DatasetSourceProvenance(
                source=replace(
                    approved_source(),
                    status=SourceStatus.FETCH_APPROVED,
                    approved_uses=(),
                ),
                scan_passed_fetch=None,
            ),
            "not purpose-approved",
        ),
        (
            DatasetSourceProvenance(
                source=approved_source(),
                scan_passed_fetch=DatasetFetch(
                    fetch_id=uuid4(),
                    source_id=approved_source().source_id,
                    state=FetchState.SCAN_PASSED,
                    requested_by="dataset-source-researcher",
                    approval_evidence_ref="approval:fetch:missing-scan",
                    approval_evidence_sha256="c" * 64,
                    observed_sha256="4" * 64,
                    byte_size=42,
                    quarantine_uri=f"file:///quarantine/{'4' * 64}",
                ),
            ),
            "has invalid scan evidence",
        ),
    ],
)
async def test_release_fails_closed_for_untrusted_registry_state(
    resolution: DatasetSourceProvenance | None,
    expected: str,
) -> None:
    errors = await DatasetReleaseProvenanceAuthority(
        ProvenanceRegistryFixture(resolution)
    ).errors(deepcopy(released_v4_manifest()))

    assert any(expected in error for error in errors)
