import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.modules.assistant.application import WorkerResult
from app.modules.assistant.domain import EvidenceReference
from app.modules.assistant.graph.builder import build_conversation_graph
from app.modules.assistant.graph.state import merge_confirmed_entities
from app.modules.inference.application import Citation
from tests.unit.assistant.conversation_fakes import (
    DeterministicSupervisor,
    EvidenceAuthority,
    ExecutionControl,
    SequenceWorker,
    confirmed_entity,
    control,
    evidence,
    initial_state,
    strict_saver,
)


def graph_for(
    worker: SequenceWorker,
    *,
    execution_control: ExecutionControl | None = None,
    evidence_authority: EvidenceAuthority | None = None,
) -> Any:
    return build_conversation_graph(
        supervisor=DeterministicSupervisor(),
        worker=worker,
        execution_control=execution_control or ExecutionControl(),
        evidence_authority=evidence_authority or EvidenceAuthority(),
    )


@pytest.mark.asyncio
async def test_context_switch_keeps_latest_confirmed_vehicle() -> None:
    worker = SequenceWorker(
        WorkerResult(
            kind="completed",
            code="ANSWERED",
            fencing_token=7,
            final_answer="Đã trả lời.",
            evidence=evidence(),
        )
        for _ in range(3)
    )
    graph = graph_for(worker)
    first = await graph.ainvoke(
        initial_state("Cho tôi xem VF 8", global_entities=(confirmed_entity(),))
    )
    second = await graph.ainvoke(
        {**first, "message": "Tôi muốn hỏi chính sách vay", "outcome": None, "worker_attempts": 0}
    )
    third = await graph.ainvoke(
        {**second, "message": "Thế xe lúc nãy thì sao?", "outcome": None, "worker_attempts": 0}
    )
    assert third["global_entities"][0].reference == "vf-8"
    assert third["route_history"][-3:] == (
        "vehicle_question",
        "financing_question",
        "vehicle_question",
    )


def test_entity_reducer_keeps_one_newest_value_per_kind() -> None:
    older = datetime(2026, 7, 24, tzinfo=UTC)
    newer = older + timedelta(seconds=1)
    result = merge_confirmed_entities(
        (confirmed_entity("market", "VN", confirmed_at=older),),
        (
            confirmed_entity("market", "US", confirmed_at=newer),
            confirmed_entity("market", "VN", confirmed_at=older),
        ),
    )
    assert [(item.kind, item.reference) for item in result] == [("market", "US")]


@pytest.mark.asyncio
async def test_transient_failure_retries_only_three_times() -> None:
    worker = SequenceWorker(
        WorkerResult(kind="retryable_failure", code="PROVIDER_TIMEOUT", fencing_token=7)
        for _ in range(3)
    )
    result = await graph_for(worker).ainvoke(initial_state("Thông tin bảo hành"))
    assert result["outcome"].code == "RETRY_EXHAUSTED"
    assert worker.calls == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result_evidence", "authority", "code"),
    [
        ((), EvidenceAuthority(), "MISSING_GROUNDED_EVIDENCE"),
        (evidence("c" * 64), EvidenceAuthority(), "UNAPPROVED_GROUNDED_EVIDENCE"),
    ],
)
async def test_grounding_is_authoritative(
    result_evidence: tuple[EvidenceReference, ...], authority: EvidenceAuthority, code: str
) -> None:
    worker = SequenceWorker(
        [
            WorkerResult(
                kind="completed",
                code="ANSWERED",
                fencing_token=7,
                final_answer="Không được phát hành.",
                evidence=result_evidence,
            )
        ]
    )
    result = await graph_for(worker, evidence_authority=authority).ainvoke(
        initial_state("Thông tin bảo hành")
    )
    assert result["outcome"].code == code
    assert "final_answer" not in result


@pytest.mark.asyncio
async def test_approved_completion_carries_full_citations_for_the_http_response() -> None:
    citation = Citation(
        evidence_id="b" * 64,
        source_uri="https://vinfast.vn/vf8",
        source_revision="catalog-r1",
        title="VF 8 specs",
        freshness="2026-07-01T00:00:00Z",
    )
    worker = SequenceWorker(
        [
            WorkerResult(
                kind="completed",
                code="ANSWERED",
                fencing_token=7,
                final_answer="VF 8 có phạm vi hoạt động khoảng 470km.",
                evidence=evidence("b" * 64),
                citations=(citation,),
            )
        ]
    )

    result = await graph_for(worker).ainvoke(initial_state("Thông tin bảo hành"))

    assert result["outcome"].kind == "completed"
    assert result["citations"] == (citation,)


class HungWorker:
    def __init__(self) -> None:
        self.cancelled = False

    async def execute(self, **_kwargs: object) -> WorkerResult:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_deadline_cancels_inflight_worker() -> None:
    worker = HungWorker()
    graph = build_conversation_graph(
        supervisor=DeterministicSupervisor(),
        worker=worker,
        execution_control=ExecutionControl(),
        evidence_authority=EvidenceAuthority(),
    )
    result = await graph.ainvoke(
        initial_state(
            "Thông tin xe",
            graph_control=control(
                deadline_at=datetime.now(UTC) + timedelta(milliseconds=20)
            ),
        )
    )
    assert result["outcome"].code == "TURN_DEADLINE_EXCEEDED"
    assert worker.cancelled is True


class HungSupervisor:
    async def route(self, **_kwargs: object):
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class HungEvidenceAuthority:
    async def validate(self, **_kwargs: object) -> bool:
        await asyncio.Event().wait()
        return False


@pytest.mark.asyncio
async def test_supervisor_and_evidence_ports_obey_turn_deadline() -> None:
    deadline = datetime.now(UTC) + timedelta(milliseconds=20)
    supervisor_graph = build_conversation_graph(
        supervisor=HungSupervisor(),
        worker=SequenceWorker([]),
        execution_control=ExecutionControl(),
        evidence_authority=EvidenceAuthority(),
    )
    supervisor_result = await supervisor_graph.ainvoke(
        initial_state("Thông tin xe", graph_control=control(deadline_at=deadline))
    )
    evidence_graph = build_conversation_graph(
        supervisor=DeterministicSupervisor(),
        worker=SequenceWorker(
            [
                WorkerResult(
                    kind="completed",
                    code="ANSWERED",
                    fencing_token=7,
                    final_answer="Must not pass",
                    evidence=evidence(),
                )
            ]
        ),
        execution_control=ExecutionControl(),
        evidence_authority=HungEvidenceAuthority(),
    )
    evidence_result = await evidence_graph.ainvoke(
        initial_state(
            "Thông tin xe",
            graph_control=control(
                deadline_at=datetime.now(UTC) + timedelta(milliseconds=20)
            ),
        )
    )
    assert supervisor_result["outcome"].code == "SUPERVISOR_DEADLINE_EXCEEDED"
    assert evidence_result["outcome"].code == "EVIDENCE_AUTHORITY_TIMEOUT"


def test_permissive_checkpoint_serializer_is_rejected() -> None:
    with pytest.raises(ValueError, match="allowed_msgpack_modules=None"):
        build_conversation_graph(
            supervisor=DeterministicSupervisor(),
            worker=SequenceWorker([]),
            execution_control=ExecutionControl(),
            evidence_authority=EvidenceAuthority(),
            checkpointer=InMemorySaver(),
        )


def test_strict_serializer_does_not_reconstruct_unregistered_type() -> None:
    @dataclass
    class UnregisteredPayload:
        content: str

    serializer = strict_saver().serde
    payload = serializer.dumps_typed(UnregisteredPayload(content="do-not-import"))
    restored = serializer.loads_typed(payload)
    assert not isinstance(restored, UnregisteredPayload)
    assert restored == {"content": "do-not-import"}
