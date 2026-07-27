from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from app.modules.assistant.application import EntityRevalidationPort
from app.modules.assistant.domain import (
    ActiveTaskState,
    ConfirmedGlobalEntity,
    EvidenceReference,
    GlobalEntityReference,
    GraphControlState,
    TaskIntent,
)
from app.modules.assistant.graph.state import ConversationGraphState
from app.platform.checkpoints import (
    ActiveTaskCheckpoint,
    CheckpointControlBinding,
    CheckpointEntityReference,
    CheckpointEnvelope,
    CheckpointIdentity,
    CheckpointState,
)

CURRENT_STATE_SCHEMA_VERSION = 1
_TASK_INTENTS = {
    "public_knowledge",
    "vehicle_question",
    "financing_question",
    "charging_question",
    "unknown",
}


@dataclass(frozen=True, slots=True)
class MigrationResult:
    global_entities: tuple[CheckpointEntityReference, ...]
    active_task: ActiveTaskState | None
    evidence: tuple[EvidenceReference, ...]
    action: Literal["resumed", "reset_active_task", "discarded"]
    reason: str


def project_checkpoint(
    state: ConversationGraphState,
    *,
    identity: CheckpointIdentity,
    created_at: datetime | None = None,
) -> CheckpointEnvelope:
    control = state["control"]
    active_task = state.get("active_task")
    return CheckpointEnvelope(
        schema_version=CURRENT_STATE_SCHEMA_VERSION,
        identity=identity,
        conversation_version=control.conversation_version,
        fencing_token=control.fencing_token,
        control=_checkpoint_control(control),
        state=CheckpointState(
            global_entities=tuple(
                CheckpointEntityReference(
                    kind=entity.kind,
                    reference=entity.reference,
                    source_revision=entity.source_revision,
                    classification=entity.classification,
                )
                for entity in state.get("global_entities", ())[:4]
            ),
            active_task=(
                ActiveTaskCheckpoint(
                    task_kind=active_task.intent,
                    stage=_outcome_code(state),
                    retry_count=active_task.retry_count,
                    pending_slot_names=active_task.required_arguments,
                )
                if active_task is not None
                else None
            ),
            evidence_refs=tuple(
                f"{reference.kind}:{reference.digest}"
                for reference in state.get("evidence", ())[:32]
            ),
        ),
        created_at=created_at or datetime.now(UTC),
    )


def migrate_checkpoint(
    checkpoint: CheckpointEnvelope,
    *,
    expected_identity: CheckpointIdentity,
    expected_control: GraphControlState,
) -> MigrationResult:
    if not _same_security_boundary(checkpoint, expected_identity, expected_control):
        return MigrationResult(
            global_entities=(),
            active_task=None,
            evidence=(),
            action="discarded",
            reason="checkpoint_security_boundary_changed",
        )
    exact = (
        checkpoint.schema_version == CURRENT_STATE_SCHEMA_VERSION
        and checkpoint.identity == expected_identity
        and checkpoint.identity.graph_version == expected_control.graph_version
        and checkpoint.control == _checkpoint_control(expected_control)
    )
    if not exact:
        return MigrationResult(
            global_entities=(),
            active_task=None,
            evidence=(),
            action="reset_active_task",
            reason="checkpoint_version_or_revision_changed",
        )
    return MigrationResult(
        global_entities=checkpoint.state.global_entities,
        active_task=_restore_active_task(checkpoint.state.active_task),
        evidence=tuple(
            EvidenceReference(
                kind=cast(
                    Literal["citation", "retrieval", "tool"], value.split(":", 1)[0]
                ),
                digest=value.split(":", 1)[1],
            )
            for value in checkpoint.state.evidence_refs
        ),
        action="resumed",
        reason="compatible_checkpoint",
    )


async def migrate_checkpoint_with_authority(
    checkpoint: CheckpointEnvelope,
    *,
    expected_identity: CheckpointIdentity,
    expected_control: GraphControlState,
    revalidator: EntityRevalidationPort,
) -> MigrationResult:
    result = migrate_checkpoint(
        checkpoint,
        expected_identity=expected_identity,
        expected_control=expected_control,
    )
    if result.action != "reset_active_task":
        return result
    candidates = tuple(
        GlobalEntityReference(
            kind=item.kind,
            reference=item.reference,
            source_revision=item.source_revision,
            classification=item.classification,
        )
        for item in checkpoint.state.global_entities
    )
    approved = await revalidator.revalidate(candidates, control=expected_control)
    candidate_set = set(candidates)
    if any(item not in candidate_set for item in approved):
        raise ValueError("entity revalidator returned an untrusted injected reference")
    return MigrationResult(
        global_entities=tuple(
            CheckpointEntityReference(
                kind=item.kind,
                reference=item.reference,
                source_revision=item.source_revision,
                classification=item.classification,
            )
            for item in approved
        ),
        active_task=None,
        evidence=(),
        action="reset_active_task",
        reason=result.reason,
    )


def checkpoint_entities(
    entities: tuple[ConfirmedGlobalEntity, ...],
) -> tuple[CheckpointEntityReference, ...]:
    return tuple(
        CheckpointEntityReference(
            kind=entity.kind,
            reference=entity.reference,
            source_revision=entity.source_revision,
            classification=entity.classification,
        )
        for entity in entities
    )


def _same_security_boundary(
    checkpoint: CheckpointEnvelope,
    expected_identity: CheckpointIdentity,
    expected_control: GraphControlState,
) -> bool:
    return (
        expected_identity.graph_version == expected_control.graph_version
        and
        checkpoint.identity.session_id == expected_identity.session_id
        and checkpoint.identity.turn_id == expected_identity.turn_id
        and checkpoint.conversation_version == expected_control.conversation_version
        and checkpoint.fencing_token == expected_control.fencing_token
        and checkpoint.control.assistant_profile == expected_control.assistant_profile
        and checkpoint.control.authorization_context_hash
        == expected_control.authorization_context_hash
    )


def _checkpoint_control(control: GraphControlState) -> CheckpointControlBinding:
    return CheckpointControlBinding(
        assistant_profile=control.assistant_profile,
        authorization_context_hash=control.authorization_context_hash,
        policy_revision=control.policy_revision,
        knowledge_revision=control.knowledge_revision,
    )


def _outcome_code(state: ConversationGraphState) -> str:
    outcome = state.get("outcome")
    return outcome.code if outcome is not None else "IN_PROGRESS"


def _restore_active_task(
    checkpoint: ActiveTaskCheckpoint | None,
) -> ActiveTaskState | None:
    if checkpoint is None or checkpoint.task_kind not in _TASK_INTENTS:
        return None
    return ActiveTaskState(
        intent=cast(TaskIntent, checkpoint.task_kind),
        required_arguments=checkpoint.pending_slot_names,
        retry_count=checkpoint.retry_count,
        last_failure=None,
    )
