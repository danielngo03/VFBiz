from dataclasses import replace

from app.modules.evaluation.application.assistant_release_gate import (
    AssistantReleaseEvaluationEvidence,
    AssistantReleaseGatePolicy,
    evaluate_assistant_release,
)


def evidence() -> AssistantReleaseEvaluationEvidence:
    return AssistantReleaseEvaluationEvidence(
        suite_revision="assistant-held-out-v2",
        evaluator_revision="assistant-evaluator-v2",
        dataset_release_sha256="a" * 64,
        case_count=600,
        languages=("vi", "en"),
        unsupported_claim_false_negative_rate=0.0,
        refusal_accuracy=0.99,
        citation_entailment_accuracy=0.99,
        acl_leakage_count=0,
        pii_leakage_count=0,
        high_risk_case_count=120,
        high_risk_human_reviewed_count=120,
    )


def test_release_gate_accepts_complete_held_out_evidence() -> None:
    result = evaluate_assistant_release(evidence(), AssistantReleaseGatePolicy())

    assert result.passed is True
    assert result.failure_codes == ()


def test_release_gate_rejects_quality_security_and_human_review_gaps() -> None:
    item = replace(
        evidence(),
        case_count=100,
        languages=("vi",),
        unsupported_claim_false_negative_rate=0.02,
        refusal_accuracy=0.9,
        citation_entailment_accuracy=0.9,
        acl_leakage_count=1,
        pii_leakage_count=1,
        high_risk_human_reviewed_count=119,
    )

    result = evaluate_assistant_release(item, AssistantReleaseGatePolicy())

    assert result.passed is False
    assert result.failure_codes == (
        "INSUFFICIENT_HELD_OUT_CASES",
        "LANGUAGE_COVERAGE_INCOMPLETE",
        "UNSUPPORTED_CLAIM_FALSE_NEGATIVE_TOO_HIGH",
        "REFUSAL_ACCURACY_TOO_LOW",
        "CITATION_ENTAILMENT_TOO_LOW",
        "ACL_LEAKAGE_DETECTED",
        "PII_LEAKAGE_DETECTED",
        "HIGH_RISK_HUMAN_REVIEW_INCOMPLETE",
    )
