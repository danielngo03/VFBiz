from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.modules.assistant.domain import (
    EvidenceReference,
    GraphControlState,
)
from app.modules.assistant.infrastructure.knowledge_worker import citation_digest
from app.modules.assistant.infrastructure.released_knowledge import (
    ReleasedEvidenceAuthority,
    ReleasedKnowledgeRetriever,
)
from app.modules.knowledge.application import (
    KnowledgeAssistantProfile as AssistantProfile,
)
from app.modules.knowledge.domain import KnowledgeScope
from app.modules.knowledge.domain.retrieval import (
    RetrievalResult,
    RetrievalSnapshot,
    RetrievalSourcePin,
    RetrievalStatus,
    RetrievedEvidence,
    SnapshotResolution,
    SnapshotStatus,
)

NOW = datetime.now(UTC)
RELEASE_ID = UUID("00000000-0000-4000-8000-000000000101")
SOURCE_ID = UUID("00000000-0000-4000-8000-000000000102")
INDEX_ID = UUID("00000000-0000-4000-8000-000000000103")
SCOPE = KnowledgeScope(
    domain="customer-support",
    locale="vi",
    assistant_profile="authenticated_customer",
    acl_namespace="authenticated_customer:customer-support:vi",
)


class RetrievalService:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result

    async def retrieve(self, **_: object) -> RetrievalResult:
        return self.result


class Snapshots:
    def __init__(self, resolution: SnapshotResolution) -> None:
        self.resolution = resolution

    async def resolve(self, scope: KnowledgeScope) -> SnapshotResolution:
        assert scope == SCOPE
        return self.resolution


def _snapshot(*, pointer_version: int = 7) -> RetrievalSnapshot:
    return RetrievalSnapshot(
        release_id=RELEASE_ID,
        pointer_version=pointer_version,
        barrier_generation=2,
        scope=SCOPE,
        sources=(
            RetrievalSourcePin(
                source_id=SOURCE_ID,
                source_revision="source-v1",
            ),
        ),
        effective_at=NOW - timedelta(minutes=1),
        freshness_expires_at=NOW + timedelta(hours=1),
        index_generation_id=INDEX_ID,
        embedding_revision="embedding-v1",
        embedding_dimension=3,
        retriever_revision="retriever-v1",
        index_checksum="a" * 64,
        materialization_checksum="b" * 64,
        materialized_chunk_count=1,
    )


def _retrieval_result() -> RetrievalResult:
    return RetrievalResult(
        status=RetrievalStatus.EVIDENCE,
        reason="APPROVED_EVIDENCE_RETRIEVED",
        release_id=RELEASE_ID,
        pointer_version=7,
        evidence=(
            RetrievedEvidence(
                evidence_id="c" * 64,
                release_id=RELEASE_ID,
                pointer_version=7,
                source_id=SOURCE_ID,
                source_uri="https://example.test/approved/source",
                source_revision="source-v1",
                title="Approved source",
                excerpt="Approved fact.",
                freshness=NOW,
                score=1.0,
            ),
            RetrievedEvidence(
                evidence_id="e" * 64,
                release_id=RELEASE_ID,
                pointer_version=7,
                source_id=SOURCE_ID,
                source_uri="https://example.test/approved/source",
                source_revision="source-v1",
                title="Additional approved source passage",
                excerpt="Another approved fact.",
                freshness=NOW,
                score=0.8,
            ),
        ),
    )


def _control() -> GraphControlState:
    return GraphControlState(
        graph_version="graph-v1",
        policy_revision="policy-v1",
        knowledge_revision=str(RELEASE_ID),
        assistant_profile="authenticated_customer",
        authorization_context_hash="d" * 64,
        conversation_version=1,
        fencing_token=1,
        deadline_at=NOW + timedelta(seconds=10),
    )


@pytest.mark.asyncio
async def test_retrieval_and_evidence_authority_bind_exact_active_snapshot() -> None:
    retriever = ReleasedKnowledgeRetriever(
        service=RetrievalService(_retrieval_result()),  # type: ignore[arg-type]
        scope=SCOPE,
        expected_release_id=RELEASE_ID,
    )
    evidence = await retriever.retrieve(
        "approved fact",
        AssistantProfile.AUTHENTICATED_CUSTOMER,
    )
    digest = citation_digest(
        evidence_id=evidence[0].evidence_id,
        source_revision=evidence[0].source_revision,
    )
    authority = ReleasedEvidenceAuthority(
        retriever=retriever,
        snapshots=Snapshots(
            SnapshotResolution(
                status=SnapshotStatus.ACTIVE,
                snapshot=_snapshot(),
                reason="ACTIVE_RELEASE_RESOLVED",
            )
        ),
    )
    assert await authority.validate(
        # The answer may cite only the supporting subset of retrieved passages.
        references=(EvidenceReference(kind="citation", digest=digest),),
        control=_control(),
    )


@pytest.mark.asyncio
async def test_rejects_pointer_drift_and_cross_profile_retrieval() -> None:
    retriever = ReleasedKnowledgeRetriever(
        service=RetrievalService(_retrieval_result()),  # type: ignore[arg-type]
        scope=SCOPE,
        expected_release_id=RELEASE_ID,
    )
    assert (
        await retriever.retrieve(
            "approved fact",
            AssistantProfile.PUBLIC_CUSTOMER,
        )
        == ()
    )
    evidence = await retriever.retrieve(
        "approved fact",
        AssistantProfile.AUTHENTICATED_CUSTOMER,
    )
    authority = ReleasedEvidenceAuthority(
        retriever=retriever,
        snapshots=Snapshots(
            SnapshotResolution(
                status=SnapshotStatus.ACTIVE,
                snapshot=_snapshot(pointer_version=8),
                reason="ACTIVE_RELEASE_RESOLVED",
            )
        ),
    )
    assert not await authority.validate(
        references=(
            EvidenceReference(
                kind="citation",
                digest=citation_digest(
                    evidence_id=evidence[0].evidence_id,
                    source_revision=evidence[0].source_revision,
                ),
            ),
        ),
        control=_control(),
    )
