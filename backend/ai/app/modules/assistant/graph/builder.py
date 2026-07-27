# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false

from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.modules.assistant.application import (
    EvidenceAuthorityPort,
    ExecutionControlPort,
    SupervisorPort,
    TaskWorkerPort,
)
from app.modules.assistant.graph.nodes import ConversationNodes, terminal_control_outcome
from app.modules.assistant.graph.serialization import require_strict_checkpointer
from app.modules.assistant.graph.state import ConversationGraphState


def build_conversation_graph(
    *,
    supervisor: SupervisorPort,
    worker: TaskWorkerPort,
    execution_control: ExecutionControlPort,
    evidence_authority: EvidenceAuthorityPort,
    checkpointer: BaseCheckpointSaver[str] | bool | None = None,
) -> Any:
    nodes = ConversationNodes(
        supervisor=supervisor,
        worker=worker,
        execution_control=execution_control,
        evidence_authority=evidence_authority,
    )
    graph = StateGraph(ConversationGraphState)
    graph.add_node("supervisor", nodes.supervise)
    graph.add_node("worker", nodes.execute)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {"execute": "worker", "end": END},
    )
    graph.add_conditional_edges(
        "worker",
        _route_after_worker,
        {"retry": "supervisor", "end": END},
    )
    if isinstance(checkpointer, BaseCheckpointSaver):
        checkpointer = require_strict_checkpointer(checkpointer)
    return graph.compile(checkpointer=checkpointer)


def _route_after_supervisor(
    state: ConversationGraphState,
) -> Literal["execute", "end"]:
    return "end" if state["outcome"] is not None else "execute"


def _route_after_worker(state: ConversationGraphState) -> Literal["retry", "end"]:
    outcome = state["outcome"]
    if outcome is None:
        return "retry"
    return "end"


__all__ = ["build_conversation_graph", "terminal_control_outcome"]
