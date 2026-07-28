from datetime import datetime

from app.modules.datasets.application.ports import (
    ArtifactScanner,
    FetchApprovalAuthority,
    ObjectStore,
    SourceReader,
)
from app.modules.datasets.application.source_intake.models import (
    ApprovedSourceFetchPlan,
    QuarantinedFetch,
)
from app.modules.datasets.domain import RegistryInvariantError, TrustZone


class QuarantineApprovedSource:
    """Coordinates an approved read, scan and immutable quarantine write."""

    def __init__(
        self,
        *,
        approval_authority: FetchApprovalAuthority,
        source_reader: SourceReader,
        scanner: ArtifactScanner,
        object_store: ObjectStore,
    ) -> None:
        self._approval_authority = approval_authority
        self._source_reader = source_reader
        self._scanner = scanner
        self._object_store = object_store

    def execute(
        self,
        plan: ApprovedSourceFetchPlan,
        *,
        now: datetime,
    ) -> QuarantinedFetch:
        self._approval_authority.assert_fetch_approved(plan, at=now)
        with self._source_reader.open(plan) as source:
            evidence = self._scanner.scan_stream(
                source.stream,
                media_type=plan.media_type,
                byte_size=source.byte_size,
            )
            source.stream.seek(0)
            stored = self._object_store.put_stream(
                zone=TrustZone.QUARANTINE,
                stream=source.stream,
                media_type=plan.media_type,
                max_bytes=plan.max_bytes,
            )
        if stored.sha256 != evidence.observed_sha256:
            raise RegistryInvariantError("object-store digest does not match scan evidence")
        if plan.upstream_sha256 is not None and stored.sha256 != plan.upstream_sha256:
            raise RegistryInvariantError("downloaded artifact does not match upstream digest")
        if plan.expected_byte_size is not None and stored.byte_size != plan.expected_byte_size:
            raise RegistryInvariantError("downloaded artifact does not match expected byte size")
        return QuarantinedFetch(
            stored=stored,
            evidence=evidence,
            fetch_plan_sha256=plan.digest,
        )
