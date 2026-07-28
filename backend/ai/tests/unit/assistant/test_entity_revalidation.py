from datetime import UTC, datetime, timedelta

import pytest

from app.modules.assistant.domain import ConfirmedGlobalEntity, GraphControlState
from app.modules.assistant.infrastructure.entity_revalidation import (
    FailClosedEntityRevalidator,
)


def control() -> GraphControlState:
    return GraphControlState(
        graph_version="graph-r2",
        policy_revision="policy-r2",
        knowledge_revision="knowledge-r2",
        assistant_profile="public_customer",
        authorization_context_hash="a" * 64,
        conversation_version=1,
        fencing_token=1,
        deadline_at=datetime.now(UTC) + timedelta(seconds=5),
    )


@pytest.mark.asyncio
async def test_never_carries_forward_any_entity_without_a_real_catalog_check() -> None:
    revalidator = FailClosedEntityRevalidator()
    confirmed_at = datetime.now(UTC)
    entities = (
        ConfirmedGlobalEntity(
            kind="vehicle_model",
            reference="vf-8",
            source_revision="a" * 64,
            authority_digest="b" * 64,
            confirmed_at=confirmed_at,
            expires_at=confirmed_at + timedelta(days=1),
            confidence=0.9,
        ),
    )

    result = await revalidator.revalidate(entities, control=control())

    assert result == ()
