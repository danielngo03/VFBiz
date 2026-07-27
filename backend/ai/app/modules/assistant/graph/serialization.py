# pyright: reportMissingTypeStubs=false

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.modules.assistant.domain import (
    ActiveTaskState,
    ConfirmedGlobalEntity,
    EvidenceReference,
    GraphControlState,
    GraphOutcome,
)

_CHECKPOINT_TYPES = {
    (model.__module__, model.__qualname__)
    for model in (
        ActiveTaskState,
        ConfirmedGlobalEntity,
        EvidenceReference,
        GraphControlState,
        GraphOutcome,
    )
}


def require_strict_checkpointer(
    checkpointer: BaseCheckpointSaver[str],
) -> BaseCheckpointSaver[str]:
    """Reject permissive or pickle-capable serializers before graph compilation."""

    serde = checkpointer.serde
    if getattr(serde, "pickle_fallback", False):
        raise ValueError("checkpoint serializer must not enable pickle fallback")
    if getattr(serde, "_allowed_msgpack_modules", True) is True:
        raise ValueError(
            "checkpoint serializer must set allowed_msgpack_modules=None explicitly"
        )
    if getattr(serde, "_allowed_json_modules", True) is True:
        raise ValueError(
            "checkpoint serializer must set allowed_json_modules=None explicitly"
        )
    return checkpointer.with_allowlist(_CHECKPOINT_TYPES)
