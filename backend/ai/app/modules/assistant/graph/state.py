# pyright: reportMissingTypeStubs=false

from operator import add
from typing import Annotated, NotRequired, TypedDict

from langgraph.channels import UntrackedValue

from app.modules.assistant.domain import (
    ActiveTaskState,
    ConfirmedGlobalEntity,
    EvidenceReference,
    GraphControlState,
    GraphOutcome,
    TaskIntent,
)
from app.modules.inference.application import Citation


def merge_confirmed_entities(
    current: tuple[ConfirmedGlobalEntity, ...],
    additions: tuple[ConfirmedGlobalEntity, ...],
) -> tuple[ConfirmedGlobalEntity, ...]:
    """Keep exactly one current entity per semantic kind.

    Newer authoritative confirmations replace older values. Equal timestamps favor
    the incoming value so a deliberate confirmation is not discarded by sorting.
    """

    merged = {item.kind: item for item in current}
    for item in additions:
        existing = merged.get(item.kind)
        if existing is None or item.confirmed_at >= existing.confirmed_at:
            merged[item.kind] = item
    return tuple(merged[kind] for kind in sorted(merged))


ConfirmedEntities = Annotated[
    tuple[ConfirmedGlobalEntity, ...],
    merge_confirmed_entities,
]


class ConversationGraphState(TypedDict):
    message: Annotated[str, UntrackedValue(str)]
    final_answer: Annotated[str, UntrackedValue(str)]
    # Full citation content (title/uri/sourceId/retrievedAt) the HTTP response
    # contract requires. Never checkpointed: only the sanitized digest in
    # `evidence` is tracked/durable, matching the same untracked pattern as
    # `final_answer` — available to the caller of this invocation only.
    citations: Annotated[tuple[Citation, ...], UntrackedValue(tuple)]
    global_entities: ConfirmedEntities
    active_task: ActiveTaskState | None
    control: GraphControlState
    evidence: tuple[EvidenceReference, ...]
    outcome: GraphOutcome | None
    worker_attempts: int
    route_history: tuple[TaskIntent, ...]
    cost_microusd: NotRequired[Annotated[int, add]]
    model_tokens: NotRequired[Annotated[int, add]]


__all__ = [
    "ActiveTaskState",
    "Citation",
    "ConfirmedGlobalEntity",
    "ConversationGraphState",
    "EvidenceReference",
    "GraphControlState",
    "GraphOutcome",
    "TaskIntent",
    "merge_confirmed_entities",
]
