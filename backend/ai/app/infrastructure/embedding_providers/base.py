import asyncio
import time
from collections.abc import AsyncGenerator, Awaitable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from typing import TypeVar, cast

import httpx

from app.infrastructure.embedding_providers.policy import EmbeddingAdapterPolicy
from app.modules.inference.application.embedding_ports import (
    EmbeddingFailure,
    EmbeddingFailureCode,
    EmbeddingRequest,
)

T = TypeVar("T")


class BaseEmbeddingAdapter:
    def __init__(self, policy: EmbeddingAdapterPolicy) -> None:
        self._policy = policy
        self._bulkhead = asyncio.Semaphore(policy.max_concurrency)
        self._circuit_lock = asyncio.Lock()
        self._consecutive_failures = 0
        self._open_until = 0.0
        self._half_open_probe_active = False

    def _preflight(self, request: EmbeddingRequest) -> tuple[tuple[str, ...], int, int, int]:
        if request.expected_generation != self._policy.generation:
            raise self._failure(EmbeddingFailureCode.MODEL_REVISION_MISMATCH, retryable=False)
        if request.expected_dimension != self._policy.output_dimension:
            raise self._failure(EmbeddingFailureCode.DIMENSION_MISMATCH, retryable=False)
        rendered, rendered_bytes, rendered_tokens = self._policy.rendered_usage(request)
        if (
            len(request.inputs) > self._policy.max_items_per_request
            or rendered_bytes > self._policy.max_input_bytes_per_request
            or rendered_tokens > self._policy.max_input_tokens_per_request
            or rendered_bytes > request.budget.max_input_bytes
            or rendered_tokens > request.budget.max_input_tokens
        ):
            raise self._failure(EmbeddingFailureCode.INPUT_BUDGET_EXCEEDED, retryable=False)
        if len(request.inputs) * request.expected_dimension > self._policy.max_output_elements:
            raise self._failure(EmbeddingFailureCode.RESPONSE_TOO_LARGE, retryable=False)
        estimated_cost = self._estimated_cost(rendered_tokens)
        if estimated_cost > request.budget.max_cost_microusd:
            raise self._failure(EmbeddingFailureCode.COST_BUDGET_EXCEEDED, retryable=False)
        if request.cancellation is not None and request.cancellation.is_set():
            raise self._failure(EmbeddingFailureCode.CANCELLED, retryable=False)
        if request.deadline_at <= datetime.now(UTC):
            raise self._failure(EmbeddingFailureCode.DEADLINE_EXCEEDED, retryable=True)
        return rendered, rendered_bytes, rendered_tokens, estimated_cost

    def _estimated_cost(self, input_tokens: int) -> int:
        variable = (
            Decimal(input_tokens)
            * Decimal(self._policy.input_microusd_per_million_tokens)
            / Decimal(1_000_000)
        ).quantize(Decimal("1"), rounding=ROUND_CEILING)
        return int(variable) + self._policy.fixed_request_cost_microusd

    async def _run_request(self, request: EmbeddingRequest, operation: Awaitable[T]) -> T:
        timeout = (request.deadline_at - datetime.now(UTC)).total_seconds()
        if timeout <= 0:
            if hasattr(operation, "close"):
                operation.close()  # type: ignore[attr-defined]
            raise self._failure(EmbeddingFailureCode.DEADLINE_EXCEEDED, retryable=True)
        operation_task: asyncio.Future[T] = asyncio.ensure_future(operation)
        cancellation_task: asyncio.Task[object] | None = None
        if request.cancellation is not None:
            cancellation_task = asyncio.create_task(request.cancellation.wait())
        try:
            wait_for: set[asyncio.Future[object]] = {cast(asyncio.Future[object], operation_task)}
            if cancellation_task is not None:
                wait_for.add(cancellation_task)
            done, _ = await asyncio.wait(
                wait_for,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancellation_task is not None and cancellation_task in done:
                operation_task.cancel()
                await asyncio.gather(operation_task, return_exceptions=True)
                raise self._failure(EmbeddingFailureCode.CANCELLED, retryable=False)
            if operation_task not in done:
                operation_task.cancel()
                await asyncio.gather(operation_task, return_exceptions=True)
                raise self._failure(EmbeddingFailureCode.DEADLINE_EXCEEDED, retryable=True)
            return await operation_task
        finally:
            if not operation_task.done():
                operation_task.cancel()
                await asyncio.gather(operation_task, return_exceptions=True)
            if cancellation_task is not None:
                cancellation_task.cancel()
                await asyncio.gather(cancellation_task, return_exceptions=True)

    @asynccontextmanager
    async def _execution_slot(self, request: EmbeddingRequest) -> AsyncGenerator[None]:
        if not await self._acquire_circuit_permission():
            raise self._failure(EmbeddingFailureCode.CIRCUIT_OPEN, retryable=True)
        acquired = False
        yielded = False
        try:
            await self._run_request(request, self._bulkhead.acquire())
            acquired = True
            yielded = True
            yield
        finally:
            if acquired:
                self._bulkhead.release()
            if not yielded:
                await asyncio.shield(self._release_half_open_probe())

    async def _read_bounded_response(
        self,
        request: EmbeddingRequest,
        response: httpx.Response,
    ) -> bytes:
        body = bytearray()
        iterator = response.aiter_bytes()
        while True:
            try:
                chunk = await self._run_request(request, anext(iterator))
            except StopAsyncIteration:
                break
            if len(body) + len(chunk) > self._policy.max_response_bytes:
                raise self._failure(
                    EmbeddingFailureCode.RESPONSE_TOO_LARGE,
                    retryable=False,
                    provider_request_id=response.headers.get("x-request-id"),
                )
            body.extend(chunk)
        return bytes(body)

    def _map_http_failure(self, response: httpx.Response) -> EmbeddingFailure:
        status = response.status_code
        if status in {401, 403}:
            code = EmbeddingFailureCode.PROVIDER_AUTHENTICATION_FAILED
            retryable = False
        elif status == 429:
            code = EmbeddingFailureCode.PROVIDER_RATE_LIMITED
            retryable = True
        elif status >= 500:
            code = EmbeddingFailureCode.PROVIDER_UNAVAILABLE
            retryable = True
        else:
            code = EmbeddingFailureCode.PROVIDER_REJECTED_REQUEST
            retryable = False
        return self._failure(
            code,
            retryable=retryable,
            status_code=status,
            provider_request_id=response.headers.get("x-request-id"),
        )

    async def _acquire_circuit_permission(self) -> bool:
        async with self._circuit_lock:
            now = time.monotonic()
            if self._open_until > now:
                return False
            if self._open_until > 0:
                if self._half_open_probe_active:
                    return False
                self._half_open_probe_active = True
            return True

    async def _record_provider_success(self) -> None:
        async with self._circuit_lock:
            self._consecutive_failures = 0
            self._open_until = 0.0
            self._half_open_probe_active = False

    async def _record_provider_failure(self) -> None:
        async with self._circuit_lock:
            self._consecutive_failures += 1
            self._half_open_probe_active = False
            if self._consecutive_failures >= self._policy.circuit_failure_threshold:
                self._open_until = time.monotonic() + self._policy.circuit_recovery_seconds

    async def _release_half_open_probe(self) -> None:
        async with self._circuit_lock:
            self._half_open_probe_active = False

    @staticmethod
    def _failure_counts_toward_circuit(failure: EmbeddingFailure) -> bool:
        return failure.code in {
            EmbeddingFailureCode.PROVIDER_UNAVAILABLE,
            EmbeddingFailureCode.PROVIDER_INVALID_RESPONSE,
        }

    def _failure(
        self,
        code: EmbeddingFailureCode,
        *,
        retryable: bool,
        status_code: int | None = None,
        provider_request_id: str | None = None,
    ) -> EmbeddingFailure:
        return EmbeddingFailure(
            code,
            retryable=retryable,
            provider_id=self._policy.provider_id,
            status_code=status_code,
            provider_request_id=provider_request_id,
        )
