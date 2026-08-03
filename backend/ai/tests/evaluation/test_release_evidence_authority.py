from dataclasses import replace

import pytest

from app.modules.evaluation.application import (
    AssistantReleaseEvidenceQuery,
    AssistantReleaseEvidenceSnapshot,
    SealedAssistantReleaseEvidenceAuthority,
)

RUN_ID = "assistant-release/run-01"
RAW_DIGEST = "a" * 64
BUNDLE_DIGEST = f"sha256:{RAW_DIGEST}"
CANDIDATE_ID = "candidate-01"
CANDIDATE_DIGEST = "b" * 64
MANIFEST_DIGEST = f"sha256:{CANDIDATE_DIGEST}"


class Reader:
    def __init__(self, snapshot: AssistantReleaseEvidenceSnapshot | None) -> None:
        self.snapshot = snapshot
        self.requested_run_ids: list[str] = []

    async def get_for_run(
        self,
        run_id: str,
    ) -> AssistantReleaseEvidenceSnapshot | None:
        self.requested_run_ids.append(run_id)
        return self.snapshot


def snapshot() -> AssistantReleaseEvidenceSnapshot:
    return AssistantReleaseEvidenceSnapshot(
        run_id=RUN_ID,
        run_state="decision_ready",
        run_evidence_bundle_digest=BUNDLE_DIGEST,
        run_candidate_release_id=CANDIDATE_ID,
        run_candidate_manifest_digest=MANIFEST_DIGEST,
        bundle_run_id=RUN_ID,
        bundle_digest=BUNDLE_DIGEST,
        bundle_authority_class="vinfast-acceptance",
        bundle_recommendation="needs-human-decision",
        document_bundle_digest=BUNDLE_DIGEST,
        document_authority_class="vinfast-acceptance",
        document_recommendation="needs-human-decision",
        document_human_approval_included=False,
        document_candidate_release_id=CANDIDATE_ID,
        document_candidate_manifest_digest=MANIFEST_DIGEST,
        document_run_id=RUN_ID,
        document_run_state="decision_ready",
    )


def query() -> AssistantReleaseEvidenceQuery:
    return AssistantReleaseEvidenceQuery(
        evidence_ref=f"evaluation://{RUN_ID}",
        evidence_sha256=RAW_DIGEST,
        candidate_release_id=CANDIDATE_ID,
        candidate_manifest_sha256=CANDIDATE_DIGEST,
    )


@pytest.mark.asyncio
async def test_exact_sealed_release_evidence_is_accepted() -> None:
    reader = Reader(snapshot())

    assert await SealedAssistantReleaseEvidenceAuthority(reader).verify(query())
    assert reader.requested_run_ids == [RUN_ID]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        {"run_id": "wrong-run"},
        {"bundle_run_id": "wrong-run"},
        {"document_run_id": "wrong-run"},
        {"run_evidence_bundle_digest": f"sha256:{'c' * 64}"},
        {"bundle_digest": f"sha256:{'c' * 64}"},
        {"document_bundle_digest": f"sha256:{'c' * 64}"},
        {"run_state": "completed"},
        {"document_run_state": "completed"},
        {"bundle_authority_class": "public-diagnostic"},
        {"document_authority_class": "public-diagnostic"},
        {"bundle_recommendation": "recommend"},
        {"document_recommendation": "recommend"},
        {"document_human_approval_included": True},
        {"run_candidate_release_id": "other-candidate"},
        {"document_candidate_release_id": "other-candidate"},
        {"run_candidate_manifest_digest": f"sha256:{'c' * 64}"},
        {"document_candidate_manifest_digest": f"sha256:{'c' * 64}"},
    ],
)
async def test_any_semantic_binding_mismatch_fails_closed(
    mutation: dict[str, object],
) -> None:
    authority = SealedAssistantReleaseEvidenceAuthority(Reader(replace(snapshot(), **mutation)))

    assert not await authority.verify(query())


@pytest.mark.asyncio
async def test_reference_identity_and_candidate_query_cannot_be_replayed() -> None:
    authority = SealedAssistantReleaseEvidenceAuthority(Reader(snapshot()))

    assert not await authority.verify(replace(query(), evidence_ref="evaluation://other-run"))
    assert not await authority.verify(replace(query(), evidence_sha256="c" * 64))
    assert not await authority.verify(replace(query(), candidate_release_id="other-candidate"))
    assert not await authority.verify(replace(query(), candidate_manifest_sha256="c" * 64))


@pytest.mark.asyncio
async def test_missing_or_non_evaluation_reference_fails_without_a_bypass() -> None:
    missing = SealedAssistantReleaseEvidenceAuthority(Reader(None))
    invalid_reader = Reader(snapshot())
    invalid = SealedAssistantReleaseEvidenceAuthority(invalid_reader)

    assert not await missing.verify(query())
    assert not await invalid.verify(
        replace(query(), evidence_ref="artifact://assistant-release/run-01")
    )
    assert invalid_reader.requested_run_ids == []
