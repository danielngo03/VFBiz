from dataclasses import dataclass

from app.modules.governance.domain import AIReleaseCandidate


@dataclass(frozen=True, slots=True)
class ReleaseGateDecision:
    passed: bool
    failures: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    promoted: bool = False


def evaluate_release(candidate: AIReleaseCandidate) -> ReleaseGateDecision:
    failures: list[str] = []
    required_revisions = {
        "UNPINNED_MODEL": candidate.model_revision,
        "UNPINNED_PROMPT": candidate.prompt_revision,
        "UNPINNED_EMBEDDING": candidate.embedding_revision,
        "UNPINNED_RETRIEVER": candidate.retriever_revision,
        "UNPINNED_TOOL_REGISTRY": candidate.tool_registry_revision,
    }
    if not candidate.owner_ref.strip():
        failures.append("MISSING_OWNER")
    failures.extend(code for code, value in required_revisions.items() if not value.strip())
    if not candidate.dataset_revisions or any(
        not revision.strip() for revision in candidate.dataset_revisions
    ):
        failures.append("UNPINNED_DATASET")
    if candidate.acl_leakage_count != 0:
        failures.append("ACL_LEAKAGE_DETECTED")
    if candidate.pii_leakage_count != 0:
        failures.append("PII_LEAKAGE_DETECTED")
    if candidate.citation_correctness < 0.95:
        failures.append("CITATION_THRESHOLD_NOT_MET")
    if not candidate.rollback_ref.strip():
        failures.append("MISSING_ROLLBACK")
    if not candidate.kill_switch_available:
        failures.append("MISSING_KILL_SWITCH")

    evidence_ids = (
        candidate.release_id,
        *candidate.dataset_revisions,
        candidate.model_revision,
        candidate.prompt_revision,
        candidate.embedding_revision,
        candidate.retriever_revision,
        candidate.tool_registry_revision,
    )
    return ReleaseGateDecision(
        passed=not failures,
        failures=tuple(failures),
        evidence_ids=tuple(item for item in evidence_ids if item),
    )
