from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AIReleaseCandidate:
    release_id: str
    owner_ref: str
    model_revision: str
    prompt_revision: str
    embedding_revision: str
    retriever_revision: str
    dataset_revisions: tuple[str, ...]
    tool_registry_revision: str
    rollback_ref: str
    kill_switch_available: bool
    citation_correctness: float
    acl_leakage_count: int
    pii_leakage_count: int
