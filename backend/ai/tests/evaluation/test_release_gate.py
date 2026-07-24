from dataclasses import replace

from app.modules.evaluation.application.release_gate import evaluate_release
from app.modules.governance.domain.release_manifest import AIReleaseCandidate


def valid_candidate() -> AIReleaseCandidate:
    return AIReleaseCandidate(
        release_id="ai-release-20260722.1",
        owner_ref="ai-platform-owner",
        model_revision="model:2026-07-22",
        prompt_revision="prompt:2026-07-22",
        embedding_revision="embedding:2026-07-22",
        retriever_revision="retriever:2026-07-22",
        dataset_revisions=("dataset:public-2026-07-22",),
        tool_registry_revision="tools:read-only-2026-07-22",
        rollback_ref="runbook:ai-rollback-v1",
        kill_switch_available=True,
        citation_correctness=0.97,
        acl_leakage_count=0,
        pii_leakage_count=0,
    )


def test_accepts_evidence_complete_candidate_without_promoting_it() -> None:
    decision = evaluate_release(valid_candidate())

    assert decision.passed is True
    assert decision.failures == ()
    assert decision.promoted is False


def test_rejects_unpinned_or_unowned_release() -> None:
    candidate = valid_candidate()
    invalid = replace(candidate, owner_ref="", prompt_revision="")

    decision = evaluate_release(invalid)

    assert decision.passed is False
    assert "MISSING_OWNER" in decision.failures
    assert "UNPINNED_PROMPT" in decision.failures


def test_zero_leakage_is_a_hard_gate() -> None:
    candidate = valid_candidate()
    invalid = replace(candidate, acl_leakage_count=1, pii_leakage_count=1)

    decision = evaluate_release(invalid)

    assert "ACL_LEAKAGE_DETECTED" in decision.failures
    assert "PII_LEAKAGE_DETECTED" in decision.failures


def test_citation_and_rollback_controls_are_required() -> None:
    candidate = valid_candidate()
    invalid = replace(
        candidate,
        citation_correctness=0.94,
        rollback_ref="",
        kill_switch_available=False,
    )

    decision = evaluate_release(invalid)

    assert "CITATION_THRESHOLD_NOT_MET" in decision.failures
    assert "MISSING_ROLLBACK" in decision.failures
    assert "MISSING_KILL_SWITCH" in decision.failures
