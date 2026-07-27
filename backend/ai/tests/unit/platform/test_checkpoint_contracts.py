from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.platform.checkpoints import (
    CheckpointEntityReference,
    CheckpointIdentity,
)
from app.platform.database.base import Base
from app.platform.database.model_registry import load_models


def test_checkpoint_source_revision_is_digest_only() -> None:
    entity = CheckpointEntityReference(
        kind="vehicle_model",
        reference="vf-8",
        source_revision="a" * 64,
        classification="non_sensitive",
    )

    assert entity.source_revision == "a" * 64


@pytest.mark.parametrize(
    "source_revision",
    [
        "catalog@" + "a" * 64,
        "owner@example.com",
        "customer-0901234567",
        "A" * 64,
        "a" * 63,
    ],
)
def test_checkpoint_source_revision_rejects_pii_shaped_or_non_digest_values(
    source_revision: str,
) -> None:
    with pytest.raises(ValidationError):
        CheckpointEntityReference(
            kind="vehicle_model",
            reference="vf-8",
            source_revision=source_revision,
            classification="non_sensitive",
        )


def test_checkpoint_identity_remains_execution_scoped() -> None:
    identity = CheckpointIdentity(
        session_id=uuid4(),
        turn_id=uuid4(),
        graph_version="graph-r1",
    )

    assert identity.session_id != identity.turn_id
    assert datetime.now(UTC).tzinfo is not None


def test_model_registry_includes_resume_gate() -> None:
    load_models()

    table = Base.metadata.tables["ai_conversation_resume_gate"]
    assert table.c.key_hash.unique is None
    assert {column.name for column in table.primary_key.columns} == {"id"}
    assert "uq_ai_conversation_resume_gate_key_hash" in {
        constraint.name for constraint in table.constraints
    }
