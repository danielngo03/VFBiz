from dataclasses import dataclass
from typing import Protocol

_EVALUATION_REFERENCE_PREFIX = "evaluation://"
_VINFAST_ACCEPTANCE = "vinfast-acceptance"
_NEEDS_HUMAN_DECISION = "needs-human-decision"
_DECISION_READY = "decision_ready"


@dataclass(frozen=True, slots=True)
class AssistantReleaseEvidenceQuery:
    evidence_ref: str
    evidence_sha256: str
    candidate_release_id: str
    candidate_manifest_sha256: str


@dataclass(frozen=True, slots=True)
class AssistantReleaseEvidenceSnapshot:
    """Public, content-free projection of one immutable sealed evidence row."""

    run_id: str
    run_state: str
    run_evidence_bundle_digest: str | None
    run_candidate_release_id: str | None
    run_candidate_manifest_digest: str | None
    bundle_run_id: str
    bundle_digest: str
    bundle_authority_class: str
    bundle_recommendation: str
    document_bundle_digest: str | None
    document_authority_class: str | None
    document_recommendation: str | None
    document_human_approval_included: bool | None
    document_candidate_release_id: str | None
    document_candidate_manifest_digest: str | None
    document_run_id: str | None
    document_run_state: str | None


class AssistantReleaseEvidenceReader(Protocol):
    async def get_for_run(
        self,
        run_id: str,
    ) -> AssistantReleaseEvidenceSnapshot | None: ...


class AssistantReleaseEvidenceAuthority(Protocol):
    async def verify(self, query: AssistantReleaseEvidenceQuery) -> bool: ...


class SealedAssistantReleaseEvidenceAuthority:
    """Bind semantic evaluation; Governance separately verifies human approvals."""

    def __init__(self, reader: AssistantReleaseEvidenceReader) -> None:
        self._reader = reader

    async def verify(self, query: AssistantReleaseEvidenceQuery) -> bool:
        run_id = _run_id_from_reference(query.evidence_ref)
        if run_id is None:
            return False
        snapshot = await self._reader.get_for_run(run_id)
        if snapshot is None:
            return False

        expected_bundle_digest = f"sha256:{query.evidence_sha256}"
        expected_candidate_digest = f"sha256:{query.candidate_manifest_sha256}"
        return (
            snapshot.run_id == run_id
            and snapshot.bundle_run_id == run_id
            and snapshot.document_run_id == run_id
            and snapshot.run_state == _DECISION_READY
            and snapshot.document_run_state == _DECISION_READY
            and snapshot.run_evidence_bundle_digest == expected_bundle_digest
            and snapshot.bundle_digest == expected_bundle_digest
            and snapshot.document_bundle_digest == expected_bundle_digest
            and snapshot.run_candidate_release_id == query.candidate_release_id
            and snapshot.document_candidate_release_id == query.candidate_release_id
            and snapshot.run_candidate_manifest_digest == expected_candidate_digest
            and snapshot.document_candidate_manifest_digest == expected_candidate_digest
            and snapshot.bundle_authority_class == _VINFAST_ACCEPTANCE
            and snapshot.document_authority_class == _VINFAST_ACCEPTANCE
            and snapshot.bundle_recommendation == _NEEDS_HUMAN_DECISION
            and snapshot.document_recommendation == _NEEDS_HUMAN_DECISION
            and snapshot.document_human_approval_included is False
        )


def _run_id_from_reference(reference: str) -> str | None:
    if not reference.startswith(_EVALUATION_REFERENCE_PREFIX):
        return None
    run_id = reference.removeprefix(_EVALUATION_REFERENCE_PREFIX)
    if (
        not run_id
        or len(run_id) > 160
        or run_id != run_id.strip("/")
        or any(ord(character) < 32 for character in run_id)
    ):
        return None
    return run_id
