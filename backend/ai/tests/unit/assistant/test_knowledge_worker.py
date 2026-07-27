from datetime import UTC, datetime, timedelta

import pytest

from app.modules.assistant.domain import (
    ActiveTaskState,
    EvidenceReference,
    GraphControlState,
)
from app.modules.assistant.infrastructure.knowledge_worker import (
    KnowledgeGroundedWorker,
    citation_digest,
)
from app.modules.inference.application import (
    Citation,
    DeploymentPolicyDescriptor,
    GenerationOutcome,
    GenerationRequest,
    GenerationResult,
    InferenceBudget,
    InferenceFailure,
    InferenceFailureCode,
    InferenceUsage,
    RetentionPolicy,
)
from app.modules.knowledge.application import (
    KnowledgeAssistantProfile as AssistantProfile,
)
from app.modules.knowledge.application import (
    KnowledgeEvidence as Evidence,
)

POLICY = DeploymentPolicyDescriptor(
    revision="policy-r1",
    profile="baseline",
    safety_tier="standard",
    residency="vn",
    retention=RetentionPolicy.STANDARD,
    schema_revision="schema-r1",
    model_release="model-r1",
    provider_project_id="proj-1",
    provider_organization_id=None,
    data_controls_approval_reference="approval-1",
    data_controls_approval_sha256="a" * 64,
    release_manifest_sha256="b" * 64,
)
BUDGET = InferenceBudget(max_input_tokens=1_000, max_output_tokens=500, max_cost_microusd=10_000)
EVIDENCE = (
    Evidence(
        evidence_id="c" * 64,
        source_uri="https://vinfast.vn/vf8",
        source_revision="catalog-r1",
        title="VF 8 specs",
        excerpt="VF 8 range is 470km.",
        freshness="2026-07-01T00:00:00Z",
    ),
)


class FakeRetriever:
    def __init__(self, evidence: tuple[Evidence, ...] = ()) -> None:
        self.evidence = evidence
        self.calls: list[tuple[str, AssistantProfile, str]] = []

    async def retrieve(self, query: str, profile: AssistantProfile, subject: str):
        self.calls.append((query, profile, subject))
        return self.evidence


class FakeModelMesh:
    def __init__(self, *, result=None, error: InferenceFailure | None = None) -> None:
        self._result = result
        self._error = error
        self.requests: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def control(*, fencing_token: int = 5) -> GraphControlState:
    return GraphControlState(
        graph_version="graph-r1",
        policy_revision="policy-r1",
        knowledge_revision="knowledge-r1",
        assistant_profile="public_customer",
        authorization_context_hash="d" * 64,
        conversation_version=1,
        fencing_token=fencing_token,
        deadline_at=datetime.now(UTC) + timedelta(seconds=10),
    )


def task() -> ActiveTaskState:
    return ActiveTaskState(intent="vehicle_question", required_arguments=(), retry_count=0)


def worker(*, retriever: FakeRetriever, model_mesh: FakeModelMesh) -> KnowledgeGroundedWorker:
    return KnowledgeGroundedWorker(
        subject="customer-1",
        retriever=retriever,  # type: ignore[arg-type]
        model_mesh=model_mesh,  # type: ignore[arg-type]
        policy=POLICY,
        budget=BUDGET,
        prompt_revision="prompt-r1",
        prompt_content_sha256="e" * 64,
        correlation_id="corr-1",
    )


@pytest.mark.asyncio
async def test_hands_off_without_calling_model_mesh_when_no_evidence_is_found() -> None:
    retriever = FakeRetriever(evidence=())
    model_mesh = FakeModelMesh()
    instance = worker(retriever=retriever, model_mesh=model_mesh)

    result = await instance.execute(
        message="VF 8 giá bao nhiêu?",
        task=task(),
        global_entities=(),
        control=control(),
    )

    assert result.kind == "handoff_required"
    assert result.code == "NO_KNOWLEDGE_EVIDENCE"
    assert model_mesh.requests == []


@pytest.mark.asyncio
async def test_maps_a_retryable_inference_failure_to_a_retryable_worker_result() -> None:
    retriever = FakeRetriever(evidence=EVIDENCE)
    model_mesh = FakeModelMesh(
        error=InferenceFailure(
            InferenceFailureCode.PROVIDER_BUSY,
            retryable=True,
            incurred_cost_microusd=0,
            usage=InferenceUsage(0, 0, 0, 0),
        )
    )
    instance = worker(retriever=retriever, model_mesh=model_mesh)

    result = await instance.execute(
        message="VF 8 giá bao nhiêu?", task=task(), global_entities=(), control=control()
    )

    assert result.kind == "retryable_failure"
    assert result.code == "PROVIDER_BUSY"


@pytest.mark.asyncio
async def test_unknown_provider_usage_consumes_reservation_and_stops_retry() -> None:
    retriever = FakeRetriever(evidence=EVIDENCE)
    model_mesh = FakeModelMesh(
        error=InferenceFailure(
            InferenceFailureCode.PROVIDER_UNAVAILABLE,
            retryable=True,
        )
    )
    instance = worker(retriever=retriever, model_mesh=model_mesh)

    first = await instance.execute(
        message="VF 8 giá bao nhiêu?",
        task=task(),
        global_entities=(),
        control=control(),
    )
    second = await instance.execute(
        message="VF 8 giá bao nhiêu?",
        task=task(),
        global_entities=(),
        control=control(),
    )

    assert first.kind == "handoff_required"
    assert first.model_tokens == 1_500
    assert first.cost_microusd == 10_000
    assert second.kind == "non_retryable_failure"
    assert len(model_mesh.requests) == 1


@pytest.mark.asyncio
async def test_retry_uses_only_the_remaining_turn_budget() -> None:
    retriever = FakeRetriever(evidence=EVIDENCE)
    failure = InferenceFailure(
        InferenceFailureCode.PROVIDER_BUSY,
        retryable=True,
        incurred_cost_microusd=4_000,
        usage=InferenceUsage(
            input_tokens=600,
            output_tokens=200,
            cached_input_tokens=0,
            reasoning_tokens=100,
        ),
    )
    model_mesh = FakeModelMesh(error=failure)
    instance = worker(retriever=retriever, model_mesh=model_mesh)

    first = await instance.execute(
        message="VF 8 giá bao nhiêu?",
        task=task(),
        global_entities=(),
        control=control(),
    )
    second = await instance.execute(
        message="VF 8 giá bao nhiêu?",
        task=task(),
        global_entities=(),
        control=control(),
    )

    assert first.model_tokens == 800
    assert first.cost_microusd == 4_000
    assert model_mesh.requests[0].budget == BUDGET
    assert model_mesh.requests[1].budget == InferenceBudget(
        max_input_tokens=400,
        max_output_tokens=300,
        max_cost_microusd=6_000,
    )
    assert second.model_tokens == 800


@pytest.mark.asyncio
async def test_maps_a_non_retryable_inference_failure_to_a_handoff() -> None:
    retriever = FakeRetriever(evidence=EVIDENCE)
    model_mesh = FakeModelMesh(
        error=InferenceFailure(InferenceFailureCode.NO_SAFE_DEPLOYMENT, retryable=False)
    )
    instance = worker(retriever=retriever, model_mesh=model_mesh)

    result = await instance.execute(
        message="VF 8 giá bao nhiêu?", task=task(), global_entities=(), control=control()
    )

    assert result.kind == "handoff_required"
    assert result.code == "NO_SAFE_DEPLOYMENT"


@pytest.mark.asyncio
async def test_hands_off_when_model_mesh_answers_with_insufficient_evidence() -> None:
    retriever = FakeRetriever(evidence=EVIDENCE)
    result_obj = GenerationResult(
        outcome=GenerationOutcome.INSUFFICIENT_EVIDENCE,
        answer=None,
        citations=(),
        usage=InferenceUsage(
            input_tokens=10, output_tokens=0, cached_input_tokens=0, reasoning_tokens=0
        ),
        estimated_cost_microusd=0,
        deployment_id="deploy-1",
        provider_id="openai",
        deployment_policy=POLICY,
        model_revision="model-r1",
        prompt_revision="prompt-r1",
        prompt_content_sha256="e" * 64,
        evidence_digest="f" * 64,
        correlation_id="corr-1",
        provider_request_id=None,
    )
    model_mesh = FakeModelMesh(result=result_obj)
    instance = worker(retriever=retriever, model_mesh=model_mesh)

    result = await instance.execute(
        message="VF 8 giá bao nhiêu?", task=task(), global_entities=(), control=control()
    )

    assert result.kind == "handoff_required"
    assert result.code == "INSUFFICIENT_EVIDENCE"
    assert result.model_tokens == 10


@pytest.mark.asyncio
async def test_completes_with_evidence_references_derived_from_citations() -> None:
    retriever = FakeRetriever(evidence=EVIDENCE)
    citation = Citation(
        evidence_id="c" * 64,
        source_uri="https://vinfast.vn/vf8",
        source_revision="catalog-r1",
        title="VF 8 specs",
        freshness="2026-07-01T00:00:00Z",
    )
    result_obj = GenerationResult(
        outcome=GenerationOutcome.ANSWERED,
        answer="VF 8 có phạm vi hoạt động khoảng 470km.",
        citations=(citation,),
        usage=InferenceUsage(
            input_tokens=120, output_tokens=40, cached_input_tokens=0, reasoning_tokens=0
        ),
        estimated_cost_microusd=500,
        deployment_id="deploy-1",
        provider_id="openai",
        deployment_policy=POLICY,
        model_revision="model-r1",
        prompt_revision="prompt-r1",
        prompt_content_sha256="e" * 64,
        evidence_digest="f" * 64,
        correlation_id="corr-1",
        provider_request_id="req-123",
    )
    model_mesh = FakeModelMesh(result=result_obj)
    instance = worker(retriever=retriever, model_mesh=model_mesh)

    result = await instance.execute(
        message="VF 8 phạm vi hoạt động bao nhiêu?",
        task=task(),
        global_entities=(),
        control=control(),
    )

    assert result.kind == "completed"
    assert result.code == "ANSWERED"
    assert result.final_answer == "VF 8 có phạm vi hoạt động khoảng 470km."
    assert result.citations == (citation,)
    assert result.evidence == (
        EvidenceReference(
            kind="citation",
            digest=citation_digest(
                evidence_id=citation.evidence_id,
                source_revision=citation.source_revision,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_retrieval_receives_the_control_profile_and_worker_subject() -> None:
    retriever = FakeRetriever(evidence=())
    model_mesh = FakeModelMesh()
    instance = worker(retriever=retriever, model_mesh=model_mesh)

    await instance.execute(
        message="VF 8 giá bao nhiêu?", task=task(), global_entities=(), control=control()
    )

    assert retriever.calls == [
        ("VF 8 giá bao nhiêu?", AssistantProfile.PUBLIC_CUSTOMER, "customer-1")
    ]
