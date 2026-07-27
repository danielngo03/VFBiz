import asyncio
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest

from app.modules.assistant.application import WorkerResult
from app.modules.assistant.domain import GraphOutcome
from app.modules.assistant.graph.builder import build_conversation_graph
from app.modules.assistant.graph.runtime import (
    CompiledConversationGraph,
    ConversationGraphRuntime,
    ResumeRejected,
)
from app.modules.assistant.graph.state import ConversationGraphState
from app.platform.checkpoints import CheckpointIdentity
from tests.unit.assistant.conversation_fakes import (
    DeterministicSupervisor,
    EntityRevalidator,
    EvidenceAuthority,
    ExecutionControl,
    MemoryResumeClaims,
    SequenceWorker,
    confirmed_entity,
    control,
    evidence,
    initial_state,
    strict_saver,
)


class HungResumeClaims(MemoryResumeClaims):
    async def reserve_start(self, **_kwargs: object) -> str | None:
        await asyncio.Event().wait()
        return None


def runtime_for(worker: SequenceWorker) -> tuple[ConversationGraphRuntime, MemoryResumeClaims]:
    graph = build_conversation_graph(
        supervisor=DeterministicSupervisor(),
        worker=worker,
        execution_control=ExecutionControl(),
        evidence_authority=EvidenceAuthority(),
        checkpointer=strict_saver(),
    )
    claims = MemoryResumeClaims()
    return (
        ConversationGraphRuntime(
            cast(CompiledConversationGraph, graph), claims, EntityRevalidator()
        ),
        claims,
    )


def identity() -> CheckpointIdentity:
    return CheckpointIdentity(
        session_id=uuid4(), turn_id=uuid4(), graph_version="graph-r1"
    )


@pytest.mark.asyncio
async def test_clarification_is_a_terminal_turn_outcome() -> None:
    worker = SequenceWorker(
        [
            WorkerResult(kind="needs_clarification", code="MISSING_VARIANT", fencing_token=7),
            WorkerResult(
                kind="completed",
                code="ANSWERED",
                fencing_token=7,
                final_answer="Đã trả lời.",
                evidence=evidence(),
            ),
        ]
    )
    runtime, _ = runtime_for(worker)
    checkpoint_identity = identity()
    result = await runtime.start(
        cast(ConversationGraphState, initial_state("Cho tôi xem VF")),
        identity=checkpoint_identity,
    )
    assert cast(GraphOutcome, result["outcome"]).kind == "needs_clarification"
    assert "resume_nonce" not in result
    assert worker.calls == 1


@pytest.mark.asyncio
async def test_independent_sessions_keep_terminal_clarifications_isolated() -> None:
    worker = SequenceWorker(
        WorkerResult(kind="needs_clarification", code="MISSING_VARIANT", fencing_token=7)
        for _ in range(2)
    )
    runtime, _ = runtime_for(worker)
    first_identity, second_identity = identity(), identity()
    first = await runtime.start(
        cast(ConversationGraphState, initial_state("Cho tôi xem VF")),
        identity=first_identity,
    )
    second = await runtime.start(
        cast(ConversationGraphState, initial_state("Cho tôi xem VF")),
        identity=second_identity,
    )
    assert cast(GraphOutcome, first["outcome"]).kind == "needs_clarification"
    assert cast(GraphOutcome, second["outcome"]).kind == "needs_clarification"
    assert "resume_nonce" not in first
    assert "resume_nonce" not in second
    assert worker.calls == 2


@pytest.mark.asyncio
async def test_duplicate_start_does_not_reopen_terminal_clarification() -> None:
    worker = SequenceWorker(
        [WorkerResult(kind="needs_clarification", code="MISSING_VARIANT", fencing_token=7)]
    )
    runtime, _ = runtime_for(worker)
    checkpoint_identity = identity()
    first = await runtime.start(
        cast(ConversationGraphState, initial_state("Cho tôi xem VF")),
        identity=checkpoint_identity,
    )
    duplicate = await runtime.start(
        cast(ConversationGraphState, initial_state("Cho tôi xem VF 9")),
        identity=checkpoint_identity,
    )
    assert cast(GraphOutcome, first["outcome"]).kind == "needs_clarification"
    assert isinstance(duplicate["outcome"], ResumeRejected)
    assert duplicate["outcome"].code == "DUPLICATE_TURN_START"
    assert worker.calls == 1


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_start_rejects_a_state_control_pinned_to_a_different_graph_version() -> None:
    # execute_turn always derives both state["control"].graph_version and
    # identity.graph_version from the same signed claim, so this mismatch is
    # unreachable through the real HTTP router today (see
    # tests/contract/test_conversation_turn_outcome_mapping.py's module
    # docstring). It is still a real branch of start() itself — reachable by
    # any other caller that constructs state/identity independently — and is
    # covered here directly, at the one layer that can actually exercise it.
    worker = SequenceWorker([])
    runtime, _ = runtime_for(worker)
    mismatched_state = initial_state(
        "Cho tôi xem VF", graph_control=control(graph_version="graph-r2")
    )

    result = await runtime.start(
        cast(ConversationGraphState, mismatched_state),
        identity=identity(),
    )

    assert isinstance(result["outcome"], ResumeRejected)
    assert result["outcome"].code == "GRAPH_IDENTITY_MISMATCH"
    assert worker.calls == 0


@pytest.mark.asyncio
async def test_resume_gate_io_obeys_turn_deadline() -> None:
    graph = build_conversation_graph(
        supervisor=DeterministicSupervisor(),
        worker=SequenceWorker([]),
        execution_control=ExecutionControl(),
        evidence_authority=EvidenceAuthority(),
        checkpointer=strict_saver(),
    )
    runtime = ConversationGraphRuntime(
        cast(CompiledConversationGraph, graph), HungResumeClaims(), EntityRevalidator()
    )
    expired_control = control(deadline_at=datetime.now(UTC))
    result = await runtime.start(
        cast(
            ConversationGraphState,
            initial_state("Thông tin xe", graph_control=expired_control),
        ),
        identity=identity(),
    )
    assert isinstance(result["outcome"], ResumeRejected)
    assert result["outcome"].code == "TURN_DEADLINE_EXCEEDED"


@pytest.mark.asyncio
async def test_runtime_migration_invokes_entity_authority_for_safe_upgrade() -> None:
    worker = SequenceWorker(
        [WorkerResult(kind="needs_clarification", code="MISSING_VARIANT", fencing_token=7)]
    )
    runtime, _ = runtime_for(worker)
    previous = identity().model_copy(update={"graph_version": "graph-old"})
    old_control = control().model_copy(update={"graph_version": "graph-old"})
    await runtime.start(
        cast(
            ConversationGraphState,
            initial_state(
                "Cho tôi xem VF",
                graph_control=old_control,
                global_entities=(confirmed_entity(),),
            ),
        ),
        identity=previous,
    )
    migrated = await runtime.inspect_migration(
        previous_identity=previous,
        expected_identity=previous.model_copy(update={"graph_version": "graph-r1"}),
        expected_control=control(),
    )
    assert migrated.action == "reset_active_task"
    assert migrated.global_entities[0].reference == "vf-8"
    assert migrated.active_task is None


@pytest.mark.asyncio
async def test_runtime_migration_rejects_expected_identity_control_version_mismatch() -> None:
    runtime, _ = runtime_for(SequenceWorker([]))
    previous = identity().model_copy(update={"graph_version": "graph-old"})
    migrated = await runtime.inspect_migration(
        previous_identity=previous,
        expected_identity=previous.model_copy(update={"graph_version": "graph-r2"}),
        expected_control=control(),
    )
    assert migrated.action == "discarded"
    assert migrated.reason == "expected_graph_identity_control_mismatch"
    assert migrated.global_entities == ()
