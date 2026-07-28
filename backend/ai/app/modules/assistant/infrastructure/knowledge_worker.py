import hashlib

from app.modules.assistant.application import WorkerResult
from app.modules.assistant.domain import (
    ActiveTaskState,
    ConfirmedGlobalEntity,
    EvidenceReference,
    GraphControlState,
)
from app.modules.inference.application import (
    DeploymentPolicyDescriptor,
    Evidence,
    GenerationOutcome,
    GenerationRequest,
    InferenceBudget,
    InferenceFailure,
    ModelMesh,
)
from app.modules.knowledge.application.ports import (
    KnowledgeAssistantProfile,
    KnowledgeRetriever,
)


def citation_digest(*, evidence_id: str, source_revision: str) -> str:
    return hashlib.sha256(f"{evidence_id}:{source_revision}".encode()).hexdigest()


class KnowledgeGroundedWorker:
    """Retrieve grounded evidence, generate through Model Mesh, map the result.

    Constructed per turn (closing over budget/policy/prompt identity)
    for the same reason as `PostgresExecutionControlAdapter`:
    `GraphControlState` carries no customer subject or per-request budget,
    only the revision/fencing metadata the graph itself needs to stay
    provider- and business-neutral.

    Never calls Model Mesh when retrieval found no evidence: paying for a
    generation call the graph will refuse anyway is both wasted cost and a
    pointless retry surface, not a safety improvement.
    """

    def __init__(
        self,
        *,
        retriever: KnowledgeRetriever,
        model_mesh: ModelMesh,
        policy: DeploymentPolicyDescriptor,
        budget: InferenceBudget,
        prompt_revision: str,
        prompt_content_sha256: str,
        correlation_id: str,
    ) -> None:
        self._retriever = retriever
        self._model_mesh = model_mesh
        self._policy = policy
        self._prompt_revision = prompt_revision
        self._prompt_content_sha256 = prompt_content_sha256
        self._correlation_id = correlation_id
        self._remaining_input_tokens = budget.max_input_tokens
        self._remaining_output_tokens = budget.max_output_tokens
        self._remaining_cost_microusd = budget.max_cost_microusd

    async def execute(
        self,
        *,
        message: str,
        task: ActiveTaskState,
        global_entities: tuple[ConfirmedGlobalEntity, ...],
        control: GraphControlState,
    ) -> WorkerResult:
        query = build_retrieval_query(
            message=message,
            task=task,
            global_entities=global_entities,
        )
        evidence = await self._retriever.retrieve(
            query,
            KnowledgeAssistantProfile(control.assistant_profile),
        )
        if not evidence:
            return WorkerResult(
                kind="handoff_required",
                code="NO_KNOWLEDGE_EVIDENCE",
                fencing_token=control.fencing_token,
            )
        if (
            self._remaining_input_tokens < 1
            or self._remaining_output_tokens < 1
            or self._remaining_cost_microusd < 1
        ):
            return WorkerResult(
                kind="non_retryable_failure",
                code="TURN_INFERENCE_BUDGET_EXHAUSTED",
                fencing_token=control.fencing_token,
            )
        attempt_budget = InferenceBudget(
            max_input_tokens=self._remaining_input_tokens,
            max_output_tokens=self._remaining_output_tokens,
            max_cost_microusd=self._remaining_cost_microusd,
            max_attempts=1,
        )
        try:
            result = await self._model_mesh.generate(
                GenerationRequest(
                    question=message,
                    evidence=tuple(
                        Evidence(
                            evidence_id=item.evidence_id,
                            source_uri=item.source_uri,
                            source_revision=item.source_revision,
                            title=item.title,
                            excerpt=item.excerpt,
                            freshness=item.freshness,
                        )
                        for item in evidence
                    ),
                    budget=attempt_budget,
                    deadline_at=control.deadline_at,
                    required_policy=self._policy,
                    correlation_id=self._correlation_id,
                    expected_prompt_revision=self._prompt_revision,
                    expected_prompt_content_sha256=self._prompt_content_sha256,
                )
            )
        except InferenceFailure as failure:
            usage = failure.usage
            usage_is_unknown = usage is None
            input_tokens = (
                attempt_budget.max_input_tokens if usage_is_unknown else usage.input_tokens
            )
            output_tokens = (
                attempt_budget.max_output_tokens if usage_is_unknown else usage.output_tokens
            )
            incurred_cost = (
                attempt_budget.max_cost_microusd
                if failure.incurred_cost_microusd is None
                else failure.incurred_cost_microusd
            )
            self._consume_budget(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_microusd=incurred_cost,
            )
            return WorkerResult(
                kind=(
                    "retryable_failure"
                    if failure.retryable and not usage_is_unknown
                    else "handoff_required"
                ),
                code=failure.code.value.upper(),
                fencing_token=control.fencing_token,
                cost_microusd=incurred_cost,
                model_tokens=input_tokens + output_tokens,
            )
        self._consume_budget(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cost_microusd=result.estimated_cost_microusd,
        )
        if result.outcome != GenerationOutcome.ANSWERED:
            return WorkerResult(
                kind="handoff_required",
                code=result.outcome.value.upper(),
                fencing_token=control.fencing_token,
                cost_microusd=result.estimated_cost_microusd,
                model_tokens=result.usage.input_tokens + result.usage.output_tokens,
            )
        references = tuple(
            EvidenceReference(
                kind="citation",
                digest=citation_digest(
                    evidence_id=citation.evidence_id,
                    source_revision=citation.source_revision,
                ),
            )
            for citation in result.citations
        )
        return WorkerResult(
            kind="completed",
            code="ANSWERED",
            fencing_token=control.fencing_token,
            final_answer=result.answer,
            evidence=references,
            citations=result.citations,
            cost_microusd=result.estimated_cost_microusd,
            model_tokens=result.usage.input_tokens + result.usage.output_tokens,
        )

    def _consume_budget(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        cost_microusd: int,
    ) -> None:
        self._remaining_input_tokens = max(
            0,
            self._remaining_input_tokens - input_tokens,
        )
        self._remaining_output_tokens = max(
            0,
            self._remaining_output_tokens - output_tokens,
        )
        self._remaining_cost_microusd = max(
            0,
            self._remaining_cost_microusd - cost_microusd,
        )


def build_retrieval_query(
    *,
    message: str,
    task: ActiveTaskState,
    global_entities: tuple[ConfirmedGlobalEntity, ...],
) -> str:
    """Build a bounded public-knowledge query from authority-confirmed refs.

    Entity values are already constrained opaque identifiers. They help
    retrieval resolve references across turns but never become prompt policy
    or customer-private facts.
    """

    context = " ".join(
        f"{entity.kind}:{entity.reference}"
        for entity in global_entities
        if entity.classification == "non_sensitive"
    )
    suffix = f" intent:{task.intent}"
    if context:
        suffix += f" context:{context}"
    return f"{message.strip()}{suffix}"[:4_000]
