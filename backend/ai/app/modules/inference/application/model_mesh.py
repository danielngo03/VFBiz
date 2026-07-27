import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from time import monotonic

from app.modules.inference.application.grounding import normalized_evidence_digest
from app.modules.inference.application.ports import (
    ClaimSupportValidator,
    GenerationOutcome,
    GenerationRequest,
    GenerationResult,
    InferenceAttempt,
    InferenceAttemptDisposition,
    InferenceFailure,
    InferenceFailureCode,
    InferenceUsage,
    ModelDeployment,
)


@dataclass(frozen=True, slots=True)
class DeploymentRoute:
    deployment: ModelDeployment
    priority: int


@dataclass(slots=True)
class _CircuitState:
    consecutive_failures: int = 0
    open_until: float = 0.0
    half_open_probe_active: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ModelMesh:
    """Policy-exact routing with bounded spend, attempts and concurrency-safe fallback."""

    def __init__(
        self,
        routes: tuple[DeploymentRoute, ...],
        *,
        claim_support_validator: ClaimSupportValidator,
        circuit_failure_threshold: int = 3,
        circuit_recovery_seconds: float = 30.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if circuit_failure_threshold < 1:
            raise ValueError("circuit_failure_threshold must be positive")
        if circuit_recovery_seconds <= 0:
            raise ValueError("circuit_recovery_seconds must be positive")
        deployment_ids = [route.deployment.deployment_id for route in routes]
        if len(set(deployment_ids)) != len(deployment_ids):
            raise ValueError("deployment_id must be unique within a ModelMesh")
        self._routes = tuple(sorted(routes, key=lambda route: route.priority))
        self._claim_support_validator = claim_support_validator
        self._circuit_failure_threshold = circuit_failure_threshold
        self._circuit_recovery_seconds = circuit_recovery_seconds
        self._clock = clock
        self._circuits = {
            route.deployment.deployment_id: _CircuitState() for route in routes
        }

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        eligible = tuple(
            route
            for route in self._routes
            if route.deployment.policy == request.required_policy
        )
        if not eligible:
            raise InferenceFailure(
                InferenceFailureCode.NO_SAFE_DEPLOYMENT,
                retryable=False,
            )

        last_retryable: InferenceFailure | None = None
        attempt_count = 0
        attempt_ledger: list[InferenceAttempt] = []
        committed_cost = 0
        for route in eligible:
            circuit = self._circuits[route.deployment.deployment_id]
            if not await self._acquire_circuit_permission(circuit):
                continue
            attempt_count += 1
            if attempt_count > request.budget.max_attempts:
                await self._release_probe(circuit)
                break
            try:
                attempt_cost = route.deployment.estimate_max_cost_microusd(
                    request
                )
            except Exception:
                # Cost estimation is local policy/configuration work. It must not
                # poison provider health or strand a half-open provider probe.
                await self._release_probe(circuit)
                failure = InferenceFailure(
                    InferenceFailureCode.PROVIDER_ADAPTER_FAILURE,
                    retryable=True,
                    provider_id=route.deployment.provider_id,
                    incurred_cost_microusd=0,
                )
                attempt_ledger.append(
                    self._failed_attempt(route, failure, 0, 0)
                )
                last_retryable = failure
                continue
            if committed_cost + attempt_cost > request.budget.max_cost_microusd:
                await self._release_probe(circuit)
                failure = InferenceFailure(
                    InferenceFailureCode.COST_BUDGET_EXCEEDED,
                    retryable=False,
                )
                failure.attempts = tuple(attempt_ledger)
                raise failure
            try:
                result = await route.deployment.generate_response(request)
            except asyncio.CancelledError:
                # Cancellation is caller control flow, not provider failure.
                # Preserve its semantics while making a later half-open probe
                # possible.
                await asyncio.shield(self._release_probe(circuit))
                raise
            except InferenceFailure as failure:
                incurred = self._incurred_cost(failure, attempt_cost)
                attempt_ledger.append(
                    self._failed_attempt(route, failure, attempt_cost, incurred)
                )
                if not failure.retryable:
                    await self._release_probe(circuit)
                    failure.attempts = tuple(attempt_ledger)
                    raise
                last_retryable = failure
                committed_cost += incurred
                if committed_cost > request.budget.max_cost_microusd:
                    await self._release_probe(circuit)
                    exhausted = InferenceFailure(
                        InferenceFailureCode.COST_BUDGET_EXCEEDED,
                        retryable=False,
                        incurred_cost_microusd=committed_cost,
                    )
                    exhausted.attempts = tuple(attempt_ledger)
                    raise exhausted from failure
                if failure.code is InferenceFailureCode.PROVIDER_BUSY:
                    await self._release_probe(circuit)
                else:
                    await self._record_failure(circuit)
                continue
            except Exception as error:
                failure = InferenceFailure(
                    InferenceFailureCode.PROVIDER_ADAPTER_FAILURE,
                    retryable=True,
                    provider_id=route.deployment.provider_id,
                    incurred_cost_microusd=attempt_cost,
                )
                attempt_ledger.append(
                    self._failed_attempt(
                        route,
                        failure,
                        attempt_cost,
                        attempt_cost,
                    )
                )
                last_retryable = failure
                committed_cost += attempt_cost
                await self._record_failure(circuit)
                if committed_cost > request.budget.max_cost_microusd:
                    exhausted = InferenceFailure(
                        InferenceFailureCode.COST_BUDGET_EXCEEDED,
                        retryable=False,
                        incurred_cost_microusd=committed_cost,
                    )
                    exhausted.attempts = tuple(attempt_ledger)
                    raise exhausted from error
                continue

            try:
                self._validate_result(route, request, result)
                if committed_cost + result.estimated_cost_microusd > (
                    request.budget.max_cost_microusd
                ):
                    raise InferenceFailure(
                        InferenceFailureCode.COST_BUDGET_EXCEEDED,
                        retryable=False,
                        provider_id=result.provider_id,
                        incurred_cost_microusd=(
                            committed_cost + result.estimated_cost_microusd
                        ),
                        usage=result.usage,
                    )
                if result.outcome is GenerationOutcome.ANSWERED:
                    try:
                        decision = await self._claim_support_validator.validate(
                            request,
                            result,
                        )
                    except asyncio.CancelledError:
                        await asyncio.shield(self._release_probe(circuit))
                        raise
                    if not decision.supported:
                        raise InferenceFailure(
                            InferenceFailureCode.GROUNDING_NOT_VERIFIED,
                            retryable=False,
                            provider_id=result.provider_id,
                            incurred_cost_microusd=(
                                committed_cost + result.estimated_cost_microusd
                            ),
                            usage=result.usage,
                        )
                    expected_digest = normalized_evidence_digest(request)
                    if (
                        decision.evidence_digest != expected_digest
                        or not decision.validator_revision
                        or len(decision.validator_revision) > 160
                    ):
                        raise InferenceFailure(
                            InferenceFailureCode.GROUNDING_NOT_VERIFIED,
                            retryable=False,
                            provider_id=result.provider_id,
                            incurred_cost_microusd=(
                                committed_cost + result.estimated_cost_microusd
                            ),
                            usage=result.usage,
                        )
            except InferenceFailure as failure:
                attempt_ledger.append(
                    self._failed_attempt(
                        route,
                        failure,
                        attempt_cost,
                        result.estimated_cost_microusd,
                        usage=result.usage,
                        terminal=True,
                    )
                )
                await self._release_probe(circuit)
                failure.attempts = tuple(attempt_ledger)
                raise
            except Exception as error:
                attempt_ledger.append(
                    InferenceAttempt(
                        deployment_id=route.deployment.deployment_id,
                        provider_id=route.deployment.provider_id,
                        disposition=InferenceAttemptDisposition.TERMINAL_FAILURE,
                        reserved_cost_microusd=attempt_cost,
                        incurred_cost_microusd=result.estimated_cost_microusd,
                        usage=result.usage,
                        failure_code=InferenceFailureCode.PROVIDER_ADAPTER_FAILURE,
                    )
                )
                await self._release_probe(circuit)
                failure = InferenceFailure(
                    InferenceFailureCode.PROVIDER_ADAPTER_FAILURE,
                    retryable=False,
                    provider_id=route.deployment.provider_id,
                    incurred_cost_microusd=(
                        committed_cost + result.estimated_cost_microusd
                    ),
                    usage=result.usage,
                )
                failure.attempts = tuple(attempt_ledger)
                raise failure from error

            attempt_ledger.append(
                InferenceAttempt(
                    deployment_id=route.deployment.deployment_id,
                    provider_id=route.deployment.provider_id,
                    disposition=InferenceAttemptDisposition.SUCCEEDED,
                    reserved_cost_microusd=attempt_cost,
                    incurred_cost_microusd=result.estimated_cost_microusd,
                    usage=result.usage,
                )
            )
            await self._record_success(circuit)
            aggregate_usage = self._aggregate_usage(attempt_ledger)
            return replace(
                result,
                usage=aggregate_usage,
                estimated_cost_microusd=(
                    committed_cost + result.estimated_cost_microusd
                ),
                attempts=tuple(attempt_ledger),
            )

        failure = InferenceFailure(
            InferenceFailureCode.PROVIDER_UNAVAILABLE,
            retryable=True,
            provider_id=(
                last_retryable.provider_id if last_retryable is not None else None
            ),
            incurred_cost_microusd=committed_cost,
        )
        failure.attempts = tuple(attempt_ledger)
        raise failure

    async def aclose(self) -> None:
        """FastAPI lifespan hook for shared provider transports."""
        await asyncio.gather(
            *(route.deployment.aclose() for route in self._routes)
        )

    def _validate_result(
        self,
        route: DeploymentRoute,
        request: GenerationRequest,
        result: GenerationResult,
    ) -> None:
        expected_digest = normalized_evidence_digest(request)
        evidence_by_id = {item.evidence_id: item for item in request.evidence}
        citations_match_request = all(
            citation.evidence_id in evidence_by_id
            and citation.source_uri
            == evidence_by_id[citation.evidence_id].source_uri
            and citation.source_revision
            == evidence_by_id[citation.evidence_id].source_revision
            and citation.title == evidence_by_id[citation.evidence_id].title
            and citation.freshness
            == evidence_by_id[citation.evidence_id].freshness
            for citation in result.citations
        )
        if (
            result.deployment_id != route.deployment.deployment_id
            or result.provider_id != route.deployment.provider_id
            or result.deployment_policy != route.deployment.policy
            or result.model_revision != request.required_policy.model_release
            or result.prompt_revision != request.expected_prompt_revision
            or result.prompt_content_sha256
            != request.expected_prompt_content_sha256
            or result.evidence_digest != expected_digest
            or result.correlation_id != request.correlation_id
            or not citations_match_request
        ):
            raise InferenceFailure(
                InferenceFailureCode.PROVIDER_INVALID_RESPONSE,
                retryable=False,
                provider_id=route.deployment.provider_id,
                incurred_cost_microusd=result.estimated_cost_microusd,
                usage=result.usage,
            )

    async def _acquire_circuit_permission(self, circuit: _CircuitState) -> bool:
        async with circuit.lock:
            now = self._clock()
            if circuit.open_until > now:
                return False
            if circuit.open_until > 0:
                if circuit.half_open_probe_active:
                    return False
                circuit.half_open_probe_active = True
            return True

    async def _record_success(self, circuit: _CircuitState) -> None:
        async with circuit.lock:
            circuit.consecutive_failures = 0
            circuit.open_until = 0.0
            circuit.half_open_probe_active = False

    async def _record_failure(self, circuit: _CircuitState) -> None:
        async with circuit.lock:
            circuit.consecutive_failures += 1
            circuit.half_open_probe_active = False
            if circuit.consecutive_failures >= self._circuit_failure_threshold:
                circuit.open_until = self._clock() + self._circuit_recovery_seconds

    async def _release_probe(self, circuit: _CircuitState) -> None:
        async with circuit.lock:
            circuit.half_open_probe_active = False

    @staticmethod
    def _incurred_cost(failure: InferenceFailure, reserved_cost: int) -> int:
        return (
            reserved_cost
            if failure.incurred_cost_microusd is None
            else failure.incurred_cost_microusd
        )

    @staticmethod
    def _failed_attempt(
        route: DeploymentRoute,
        failure: InferenceFailure,
        reserved_cost: int,
        incurred_cost: int,
        *,
        usage: InferenceUsage | None = None,
        terminal: bool = False,
    ) -> InferenceAttempt:
        return InferenceAttempt(
            deployment_id=route.deployment.deployment_id,
            provider_id=route.deployment.provider_id,
            disposition=(
                InferenceAttemptDisposition.TERMINAL_FAILURE
                if terminal or not failure.retryable
                else InferenceAttemptDisposition.RETRYABLE_FAILURE
            ),
            reserved_cost_microusd=reserved_cost,
            incurred_cost_microusd=incurred_cost,
            usage=usage
            or failure.usage
            or InferenceUsage(
                input_tokens=0,
                output_tokens=0,
                cached_input_tokens=0,
                reasoning_tokens=0,
            ),
            failure_code=failure.code,
        )

    @staticmethod
    def _aggregate_usage(attempts: list[InferenceAttempt]) -> InferenceUsage:
        return InferenceUsage(
            input_tokens=sum(item.usage.input_tokens for item in attempts),
            output_tokens=sum(item.usage.output_tokens for item in attempts),
            cached_input_tokens=sum(
                item.usage.cached_input_tokens for item in attempts
            ),
            reasoning_tokens=sum(item.usage.reasoning_tokens for item in attempts),
        )
