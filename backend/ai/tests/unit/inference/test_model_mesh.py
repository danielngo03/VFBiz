import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.inference.application import (
    Citation,
    ClaimSupportDecision,
    DeploymentPolicyDescriptor,
    DeploymentRoute,
    Evidence,
    GenerationOutcome,
    GenerationRequest,
    GenerationResult,
    InferenceBudget,
    InferenceFailure,
    InferenceFailureCode,
    InferenceUsage,
    ModelMesh,
    RetentionPolicy,
    normalized_evidence_digest,
)

POLICY = DeploymentPolicyDescriptor(
    revision="customer-grounded-v1",
    profile="customer-grounded-v1",
    safety_tier="customer-factual-v1",
    residency="global",
    retention=RetentionPolicy.STANDARD,
    schema_revision="grounded-answer-v2",
    model_release="model-v1",
    provider_project_id="proj_test",
    provider_organization_id="org_test",
    data_controls_approval_reference="approval-test-v1",
    data_controls_approval_sha256="b" * 64,
    release_manifest_sha256="c" * 64,
)
EVIDENCE = (
    Evidence(
        evidence_id="ev-1",
        source_uri="vfbiz://knowledge/source-1/revision-1/chunk-1",
        source_revision="revision-1",
        title="Approved source",
        excerpt="Approved evidence.",
        freshness="current",
    ),
)


class Validator:
    def __init__(self, supported: bool, *, bad_digest: bool = False) -> None:
        self.supported = supported
        self.bad_digest = bad_digest

    async def validate(
        self,
        request: GenerationRequest,
        result: GenerationResult,
    ) -> ClaimSupportDecision:
        del result
        return ClaimSupportDecision(
            supported=self.supported,
            validator_revision="test-validator-v1",
            evidence_digest=(
                "f" * 64
                if self.bad_digest
                else normalized_evidence_digest(request)
            ),
        )


class FakeDeployment:
    def __init__(
        self,
        provider_id: str,
        policy: DeploymentPolicyDescriptor,
        outcome: GenerationResult | Exception,
        *,
        gate: asyncio.Event | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.deployment_id = f"{provider_id}-deployment"
        self.policy = policy
        self.outcome = outcome
        self.calls = 0
        self.gate = gate

    def estimate_max_cost_microusd(self, request: GenerationRequest) -> int:
        del request
        return 100

    async def generate_response(
        self, request: GenerationRequest
    ) -> GenerationResult:
        del request
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    async def aclose(self) -> None:
        return None


class FailingEstimatorDeployment(FakeDeployment):
    def __init__(
        self,
        provider_id: str,
        policy: DeploymentPolicyDescriptor,
        outcome: GenerationResult | Exception,
    ) -> None:
        super().__init__(provider_id, policy, outcome)
        self.fail_estimate = False

    def estimate_max_cost_microusd(self, request: GenerationRequest) -> int:
        if self.fail_estimate:
            raise RuntimeError("local estimator failure")
        return super().estimate_max_cost_microusd(request)


def request(
    *,
    max_attempts: int = 2,
    max_cost_microusd: int = 500,
) -> GenerationRequest:
    return GenerationRequest(
        question="Hello",
        evidence=EVIDENCE,
        budget=InferenceBudget(
            max_input_tokens=100,
            max_output_tokens=50,
            max_cost_microusd=max_cost_microusd,
            max_attempts=max_attempts,
        ),
        deadline_at=datetime.now(UTC) + timedelta(seconds=5),
        required_policy=POLICY,
        correlation_id="corr-unit-1",
        expected_prompt_revision="prompt-v1",
        expected_prompt_content_sha256="a" * 64,
    )


def result(
    provider_id: str,
    *,
    outcome: GenerationOutcome = GenerationOutcome.INSUFFICIENT_EVIDENCE,
) -> GenerationResult:
    answered = outcome is GenerationOutcome.ANSWERED
    return GenerationResult(
        outcome=outcome,
        answer="A grounded answer." if answered else None,
        citations=(
            (
                Citation(
                    evidence_id="ev-1",
                    source_uri=EVIDENCE[0].source_uri,
                    source_revision=EVIDENCE[0].source_revision,
                    title=EVIDENCE[0].title,
                    freshness=EVIDENCE[0].freshness,
                ),
            )
            if answered
            else ()
        ),
        usage=InferenceUsage(
            input_tokens=10,
            output_tokens=5,
            cached_input_tokens=0,
            reasoning_tokens=0,
        ),
        estimated_cost_microusd=20,
        deployment_id=f"{provider_id}-deployment",
        provider_id=provider_id,
        deployment_policy=POLICY,
        model_revision="model-v1",
        prompt_revision="prompt-v1",
        prompt_content_sha256="a" * 64,
        evidence_digest=normalized_evidence_digest(request()),
        correlation_id="corr-unit-1",
        provider_request_id=None,
    )


@pytest.mark.asyncio
async def test_mesh_falls_back_only_after_retryable_failure() -> None:
    primary = FakeDeployment(
        "primary",
        POLICY,
        InferenceFailure(
            InferenceFailureCode.PROVIDER_UNAVAILABLE,
            retryable=True,
            provider_id="primary",
        ),
    )
    fallback = FakeDeployment("fallback", POLICY, result("fallback"))
    mesh = ModelMesh(
        (
            DeploymentRoute(primary, priority=1),
            DeploymentRoute(fallback, priority=2),
        ),
        claim_support_validator=Validator(supported=True),
    )
    execution = await mesh.generate(request())
    assert execution.provider_id == "fallback"
    assert execution.estimated_cost_microusd == 120
    assert execution.usage.input_tokens == 10
    assert [attempt.disposition for attempt in execution.attempts] == [
        "retryable_failure",
        "succeeded",
    ]


@pytest.mark.asyncio
async def test_membership_alone_cannot_release_unrelated_answer() -> None:
    deployment = FakeDeployment(
        "primary",
        POLICY,
        result("primary", outcome=GenerationOutcome.ANSWERED),
    )
    mesh = ModelMesh(
        (DeploymentRoute(deployment, priority=1),),
        claim_support_validator=Validator(supported=False),
    )
    with pytest.raises(InferenceFailure) as caught:
        await mesh.generate(request())
    assert caught.value.code is InferenceFailureCode.GROUNDING_NOT_VERIFIED


@pytest.mark.asyncio
async def test_mesh_rejects_buggy_adapter_metadata_and_validator_digest() -> None:
    wrong_result = replace(result("primary"), correlation_id="wrong-correlation")
    deployment = FakeDeployment("primary", POLICY, wrong_result)
    mesh = ModelMesh(
        (DeploymentRoute(deployment, priority=1),),
        claim_support_validator=Validator(supported=True),
    )
    with pytest.raises(InferenceFailure) as metadata_failure:
        await mesh.generate(request())
    assert (
        metadata_failure.value.code
        is InferenceFailureCode.PROVIDER_INVALID_RESPONSE
    )

    answered = replace(
        result("primary", outcome=GenerationOutcome.ANSWERED),
        answer="Unsupported claim",
    )
    deployment.outcome = answered
    digest_mesh = ModelMesh(
        (DeploymentRoute(deployment, priority=1),),
        claim_support_validator=Validator(supported=True, bad_digest=True),
    )
    with pytest.raises(InferenceFailure) as digest_failure:
        await digest_mesh.generate(request())
    assert digest_failure.value.code is InferenceFailureCode.GROUNDING_NOT_VERIFIED


@pytest.mark.asyncio
async def test_mesh_does_not_fallback_across_policy_descriptor() -> None:
    other_policy = DeploymentPolicyDescriptor(
        revision=POLICY.revision,
        profile=POLICY.profile,
        safety_tier="lower-tier-v1",
        residency=POLICY.residency,
        retention=POLICY.retention,
        schema_revision=POLICY.schema_revision,
        model_release=POLICY.model_release,
        provider_project_id=POLICY.provider_project_id,
        provider_organization_id=POLICY.provider_organization_id,
        data_controls_approval_reference=(
            POLICY.data_controls_approval_reference
        ),
        data_controls_approval_sha256=POLICY.data_controls_approval_sha256,
        release_manifest_sha256=POLICY.release_manifest_sha256,
    )
    unsafe = FakeDeployment("unsafe", other_policy, result("unsafe"))
    mesh = ModelMesh(
        (DeploymentRoute(unsafe, priority=1),),
        claim_support_validator=Validator(supported=True),
    )
    with pytest.raises(InferenceFailure) as caught:
        await mesh.generate(request())
    assert caught.value.code is InferenceFailureCode.NO_SAFE_DEPLOYMENT
    assert unsafe.calls == 0


@pytest.mark.asyncio
async def test_mesh_opens_with_exactly_one_concurrent_half_open_probe() -> None:
    now = 100.0
    primary = FakeDeployment(
        "primary",
        POLICY,
        InferenceFailure(
            InferenceFailureCode.PROVIDER_UNAVAILABLE,
            retryable=True,
            provider_id="primary",
        ),
    )
    fallback = FakeDeployment("fallback", POLICY, result("fallback"))
    mesh = ModelMesh(
        (
            DeploymentRoute(primary, priority=1),
            DeploymentRoute(fallback, priority=2),
        ),
        claim_support_validator=Validator(supported=True),
        circuit_failure_threshold=1,
        circuit_recovery_seconds=30,
        clock=lambda: now,
    )
    assert (await mesh.generate(request())).provider_id == "fallback"

    now = 131.0
    gate = asyncio.Event()
    primary.outcome = result("primary")
    primary.gate = gate
    tasks = [asyncio.create_task(mesh.generate(request())) for _ in range(20)]
    await asyncio.sleep(0)
    gate.set()
    outcomes = await asyncio.gather(*tasks)
    assert primary.calls == 2
    assert sum(item.provider_id == "primary" for item in outcomes) == 1
    assert sum(item.provider_id == "fallback" for item in outcomes) == 19


@pytest.mark.asyncio
async def test_mesh_bounds_attempts_and_aggregate_reserved_cost() -> None:
    primary = FakeDeployment(
        "primary",
        POLICY,
        InferenceFailure(
            InferenceFailureCode.PROVIDER_UNAVAILABLE,
            retryable=True,
            provider_id="primary",
        ),
    )
    fallback = FakeDeployment("fallback", POLICY, result("fallback"))
    mesh = ModelMesh(
        (
            DeploymentRoute(primary, priority=1),
            DeploymentRoute(fallback, priority=2),
        ),
        claim_support_validator=Validator(supported=True),
    )
    with pytest.raises(InferenceFailure) as caught:
        await mesh.generate(request(max_attempts=1))
    assert caught.value.code is InferenceFailureCode.PROVIDER_UNAVAILABLE
    assert fallback.calls == 0

    with pytest.raises(InferenceFailure) as cost_failure:
        await mesh.generate(request(max_cost_microusd=150))
    assert cost_failure.value.code is InferenceFailureCode.COST_BUDGET_EXCEEDED


@pytest.mark.asyncio
async def test_mesh_accounts_failed_attempt_cost_before_fallback() -> None:
    primary = FakeDeployment(
        "primary",
        POLICY,
        InferenceFailure(
            InferenceFailureCode.PROVIDER_UNAVAILABLE,
            retryable=True,
            provider_id="primary",
            incurred_cost_microusd=200,
        ),
    )
    fallback = FakeDeployment("fallback", POLICY, result("fallback"))
    mesh = ModelMesh(
        (
            DeploymentRoute(primary, priority=1),
            DeploymentRoute(fallback, priority=2),
        ),
        claim_support_validator=Validator(supported=True),
    )
    with pytest.raises(InferenceFailure) as caught:
        await mesh.generate(request(max_cost_microusd=250))
    assert caught.value.code is InferenceFailureCode.COST_BUDGET_EXCEEDED
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_provider_busy_falls_back_without_opening_provider_circuit() -> None:
    primary = FakeDeployment(
        "primary",
        POLICY,
        InferenceFailure(
            InferenceFailureCode.PROVIDER_BUSY,
            retryable=True,
            provider_id="primary",
            incurred_cost_microusd=0,
        ),
    )
    fallback = FakeDeployment("fallback", POLICY, result("fallback"))
    mesh = ModelMesh(
        (
            DeploymentRoute(primary, priority=1),
            DeploymentRoute(fallback, priority=2),
        ),
        claim_support_validator=Validator(supported=True),
        circuit_failure_threshold=1,
    )
    assert (await mesh.generate(request())).provider_id == "fallback"
    assert (await mesh.generate(request())).provider_id == "fallback"
    assert primary.calls == 2


@pytest.mark.asyncio
async def test_unexpected_half_open_adapter_exception_releases_probe() -> None:
    now = 100.0
    primary = FakeDeployment(
        "primary",
        POLICY,
        InferenceFailure(
            InferenceFailureCode.PROVIDER_UNAVAILABLE,
            retryable=True,
            provider_id="primary",
        ),
    )
    fallback = FakeDeployment("fallback", POLICY, result("fallback"))
    mesh = ModelMesh(
        (
            DeploymentRoute(primary, priority=1),
            DeploymentRoute(fallback, priority=2),
        ),
        claim_support_validator=Validator(supported=True),
        circuit_failure_threshold=1,
        circuit_recovery_seconds=30,
        clock=lambda: now,
    )
    assert (await mesh.generate(request())).provider_id == "fallback"

    now = 131.0
    primary.outcome = RuntimeError("internal adapter detail")
    assert (await mesh.generate(request())).provider_id == "fallback"

    now = 162.0
    primary.outcome = result("primary")
    assert (await mesh.generate(request())).provider_id == "primary"


@pytest.mark.asyncio
async def test_half_open_estimator_failure_releases_probe_without_poisoning_circuit() -> None:
    now = 100.0
    primary = FailingEstimatorDeployment(
        "primary",
        POLICY,
        InferenceFailure(
            InferenceFailureCode.PROVIDER_UNAVAILABLE,
            retryable=True,
            provider_id="primary",
        ),
    )
    fallback = FakeDeployment("fallback", POLICY, result("fallback"))
    mesh = ModelMesh(
        (
            DeploymentRoute(primary, priority=1),
            DeploymentRoute(fallback, priority=2),
        ),
        claim_support_validator=Validator(supported=True),
        circuit_failure_threshold=1,
        circuit_recovery_seconds=30,
        clock=lambda: now,
    )
    assert (await mesh.generate(request())).provider_id == "fallback"

    now = 131.0
    primary.fail_estimate = True
    assert (await mesh.generate(request())).provider_id == "fallback"

    primary.fail_estimate = False
    primary.outcome = result("primary")
    assert (await mesh.generate(request())).provider_id == "primary"


@pytest.mark.asyncio
async def test_half_open_cancellation_releases_probe_without_poisoning_circuit() -> None:
    now = 100.0
    primary = FakeDeployment(
        "primary",
        POLICY,
        InferenceFailure(
            InferenceFailureCode.PROVIDER_UNAVAILABLE,
            retryable=True,
            provider_id="primary",
        ),
    )
    fallback = FakeDeployment("fallback", POLICY, result("fallback"))
    mesh = ModelMesh(
        (
            DeploymentRoute(primary, priority=1),
            DeploymentRoute(fallback, priority=2),
        ),
        claim_support_validator=Validator(supported=True),
        circuit_failure_threshold=1,
        circuit_recovery_seconds=30,
        clock=lambda: now,
    )
    assert (await mesh.generate(request())).provider_id == "fallback"

    now = 131.0
    gate = asyncio.Event()
    primary.outcome = result("primary")
    primary.gate = gate
    cancelled_probe = asyncio.create_task(mesh.generate(request()))
    await asyncio.sleep(0)
    cancelled_probe.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_probe

    primary.gate = None
    assert (await mesh.generate(request())).provider_id == "primary"
