from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.assistant.domain import (
    ActiveTaskState,
    ConfirmedGlobalEntity,
    GlobalEntityReference,
    GraphControlState,
)
from app.modules.assistant.graph import (
    migrate_checkpoint,
    migrate_checkpoint_with_authority,
    project_checkpoint,
)
from app.modules.assistant.graph.state import ConversationGraphState
from app.platform.checkpoints import CheckpointIdentity
from tests.unit.assistant.conversation_fakes import (
    EntityRevalidator,
    confirmed_entity,
    control,
    initial_state,
)


def identity(version: str = "graph-r1") -> CheckpointIdentity:
    return CheckpointIdentity(session_id=uuid4(), turn_id=uuid4(), graph_version=version)


def checkpoint(
    checkpoint_identity: CheckpointIdentity,
    graph_control: GraphControlState | None = None,
):
    state = cast(
        ConversationGraphState,
        {
            **initial_state(
                "Raw customer text is untracked",
                global_entities=(confirmed_entity(),),
                graph_control=graph_control or control(),
            ),
            "active_task": ActiveTaskState(
                intent="vehicle_question",
                required_arguments=("vehicle_variant",),
                retry_count=1,
            ),
        },
    )
    return project_checkpoint(state, identity=checkpoint_identity)


def test_security_boundary_mismatch_discards_all_entities() -> None:
    original = identity()
    persisted = checkpoint(original)
    result = migrate_checkpoint(
        persisted,
        expected_identity=CheckpointIdentity(
            session_id=uuid4(), turn_id=original.turn_id, graph_version="graph-r1"
        ),
        expected_control=control(),
    )
    assert result.action == "discarded"
    assert result.global_entities == ()
    assert result.active_task is None


@pytest.mark.asyncio
async def test_safe_graph_upgrade_keeps_only_revalidated_entities() -> None:
    original = identity("graph-old")
    persisted = checkpoint(
        original, control().model_copy(update={"graph_version": "graph-old"})
    )
    result = await migrate_checkpoint_with_authority(
        persisted,
        expected_identity=original.model_copy(update={"graph_version": "graph-r1"}),
        expected_control=control(),
        revalidator=EntityRevalidator(),
    )
    assert result.action == "reset_active_task"
    assert result.global_entities == persisted.state.global_entities
    assert result.evidence == ()


class InjectingRevalidator:
    async def revalidate(
        self,
        entities: tuple[GlobalEntityReference, ...],
        *,
        control: GraphControlState,
    ) -> tuple[GlobalEntityReference, ...]:
        _ = entities, control
        return (
            GlobalEntityReference(
                kind="vehicle_model",
                reference="vf-9",
                source_revision="d" * 64,
            ),
        )


@pytest.mark.asyncio
async def test_revalidator_cannot_inject_new_entity() -> None:
    original = identity("graph-old")
    persisted = checkpoint(
        original, control().model_copy(update={"graph_version": "graph-old"})
    )
    with pytest.raises(ValueError, match="untrusted injected"):
        await migrate_checkpoint_with_authority(
            persisted,
            expected_identity=original.model_copy(update={"graph_version": "graph-r1"}),
            expected_control=control(),
            revalidator=InjectingRevalidator(),
        )


def test_checkpoint_never_contains_raw_message_or_final_answer() -> None:
    persisted = checkpoint(identity())
    serialized = persisted.model_dump_json()
    assert "Raw customer text" not in serialized
    assert "final_answer" not in serialized


def test_checkpoint_entities_reject_vin_like_customer_data() -> None:
    with pytest.raises(ValidationError, match="approved lowercase slug"):
        ConfirmedGlobalEntity(
            kind="vehicle_model",
            reference="VF8VINRLZ123456789",
            source_revision="c" * 64,
            confirmed_at=datetime.now(UTC),
            confidence=1.0,
        )


def test_checkpoint_entity_rejects_pii_shaped_source_revision() -> None:
    with pytest.raises(ValidationError, match="source_revision"):
        ConfirmedGlobalEntity(
            kind="vehicle_model",
            reference="vf-8",
            source_revision="customer-email-anhtuan-example-com",
            confirmed_at=datetime.now(UTC),
            confidence=1.0,
        )


def test_checkpoint_entity_rejects_pii_prefixed_digest() -> None:
    with pytest.raises(ValidationError, match="source_revision"):
        ConfirmedGlobalEntity(
            kind="vehicle_model",
            reference="vf-8",
            source_revision=f"customer-anhtuan@{'a' * 64}",
            confirmed_at=datetime.now(UTC),
            confidence=1.0,
        )
