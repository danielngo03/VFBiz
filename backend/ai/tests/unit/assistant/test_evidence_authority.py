from datetime import UTC, datetime, timedelta

import pytest

from app.modules.assistant.domain import EvidenceReference, GraphControlState
from app.modules.assistant.infrastructure.evidence_authority import (
    FailClosedEvidenceAuthority,
)


def control() -> GraphControlState:
    return GraphControlState(
        graph_version="graph-r1",
        policy_revision="policy-r1",
        knowledge_revision="knowledge-r1",
        assistant_profile="public_customer",
        authorization_context_hash="a" * 64,
        conversation_version=1,
        fencing_token=1,
        deadline_at=datetime.now(UTC) + timedelta(seconds=5),
    )


@pytest.mark.asyncio
async def test_never_approves_any_evidence_reference_without_a_real_authority() -> None:
    authority = FailClosedEvidenceAuthority()

    approved = await authority.validate(
        references=(EvidenceReference(kind="citation", digest="b" * 64),),
        control=control(),
    )

    assert approved is False
