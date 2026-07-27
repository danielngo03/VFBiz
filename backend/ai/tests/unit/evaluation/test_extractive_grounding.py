from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.evaluation.application import (
    DeterministicExtractiveGroundingValidator,
)
from app.modules.inference.application import (
    Citation,
    DeploymentPolicyDescriptor,
    Evidence,
    GenerationOutcome,
    GenerationRequest,
    GenerationResult,
    InferenceBudget,
    InferenceUsage,
    RetentionPolicy,
    normalized_evidence_digest,
)

POLICY = DeploymentPolicyDescriptor(
    revision="policy-v1",
    profile="customer-grounded-v1",
    safety_tier="customer-factual-v1",
    residency="vn",
    retention=RetentionPolicy.ZERO_DATA_RETENTION,
    schema_revision="grounded-answer-v2",
    model_release="model-v1",
    provider_project_id="project-v1",
    provider_organization_id=None,
    data_controls_approval_reference="approval-v1",
    data_controls_approval_sha256="a" * 64,
    release_manifest_sha256="b" * 64,
)
EVIDENCE = Evidence(
    evidence_id="evidence-1",
    source_uri="vfbiz://knowledge/source/revision/chunk",
    source_revision="revision-1",
    title="Approved policy",
    excerpt="Thời hạn bảo hành là 10 năm và không vượt quá 200.000 km.",
    freshness="current",
)


def _request() -> GenerationRequest:
    return GenerationRequest(
        question="Thời hạn bảo hành là bao lâu?",
        evidence=(EVIDENCE,),
        budget=InferenceBudget(
            max_input_tokens=1_000,
            max_output_tokens=200,
            max_cost_microusd=1_000,
        ),
        deadline_at=datetime.now(UTC) + timedelta(seconds=5),
        required_policy=POLICY,
        correlation_id="grounding-test-1",
        expected_prompt_revision="prompt-v1",
        expected_prompt_content_sha256="c" * 64,
    )


def _result(request: GenerationRequest) -> GenerationResult:
    return GenerationResult(
        outcome=GenerationOutcome.ANSWERED,
        answer="Thời hạn bảo hành là 10 năm",
        citations=(
            Citation(
                evidence_id=EVIDENCE.evidence_id,
                source_uri=EVIDENCE.source_uri,
                source_revision=EVIDENCE.source_revision,
                title=EVIDENCE.title,
                freshness=EVIDENCE.freshness,
            ),
        ),
        usage=InferenceUsage(100, 20, 0, 0),
        estimated_cost_microusd=10,
        deployment_id="deployment-v1",
        provider_id="provider-v1",
        deployment_policy=POLICY,
        model_revision="model-v1",
        prompt_revision="prompt-v1",
        prompt_content_sha256="c" * 64,
        evidence_digest=normalized_evidence_digest(request),
        correlation_id=request.correlation_id,
        provider_request_id=None,
    )


@pytest.mark.asyncio
async def test_accepts_extract_from_issued_evidence() -> None:
    request = _request()
    decision = await DeterministicExtractiveGroundingValidator().validate(
        request,
        _result(request),
    )
    assert decision.supported is True


@pytest.mark.asyncio
async def test_rejects_invented_number() -> None:
    request = _request()
    decision = await DeterministicExtractiveGroundingValidator().validate(
        request,
        replace(_result(request), answer="Thời hạn bảo hành là 15 năm"),
    )
    assert decision.supported is False


@pytest.mark.asyncio
async def test_rejects_unknown_citation_and_negation_change() -> None:
    request = _request()
    result = _result(request)
    unknown = replace(
        result.citations[0],
        evidence_id="evidence-not-issued",
    )
    unknown_decision = await DeterministicExtractiveGroundingValidator().validate(
        request,
        replace(result, citations=(unknown,)),
    )
    negation_decision = await DeterministicExtractiveGroundingValidator().validate(
        request,
        replace(result, answer="Thời hạn bảo hành chưa là 10 năm"),
    )
    assert unknown_decision.supported is False
    assert negation_decision.supported is False
