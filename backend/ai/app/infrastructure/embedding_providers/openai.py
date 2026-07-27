import asyncio
import json
import math
from typing import cast

import httpx

from app.infrastructure.embedding_providers.base import BaseEmbeddingAdapter
from app.infrastructure.embedding_providers.policy import EmbeddingAdapterPolicy
from app.modules.inference.application.embedding_ports import (
    EmbeddingFailure,
    EmbeddingFailureCode,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingUsage,
    EmbeddingVector,
)


class OpenAIEmbeddingAdapter(BaseEmbeddingAdapter):
    def __init__(
        self,
        policy: EmbeddingAdapterPolicy,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        project_id: str,
        organization_id: str | None = None,
        owns_client: bool = False,
    ) -> None:
        super().__init__(policy)
        if not api_key or not project_id:
            raise ValueError("managed embedding credentials must be non-empty")
        self._client = client
        self._owns_client = owns_client
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Project": project_id,
        }
        if organization_id:
            self._headers["OpenAI-Organization"] = organization_id

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        rendered, rendered_bytes, _, reserved_cost = self._preflight(request)
        try:
            async with self._execution_slot(request):
                provider_request = self._client.build_request(
                    "POST",
                    "/embeddings",
                    headers=self._headers,
                    json={
                        "model": self._policy.model_revision,
                        "input": list(rendered),
                        "encoding_format": "float",
                        "dimensions": self._policy.output_dimension,
                    },
                )
                response = await self._run_request(
                    request,
                    self._client.send(provider_request, stream=True),
                )
                try:
                    if response.status_code >= 400:
                        raise self._map_http_failure(response)
                    body = await self._read_bounded_response(request, response)
                finally:
                    await response.aclose()
            result = self._parse_response(
                request, response, body, reserved_cost, rendered_bytes
            )
        except EmbeddingFailure as error:
            if self._failure_counts_toward_circuit(error):
                await self._record_provider_failure()
            else:
                await self._release_half_open_probe()
            raise
        except httpx.TimeoutException as error:
            await self._record_provider_failure()
            raise self._failure(EmbeddingFailureCode.DEADLINE_EXCEEDED, retryable=True) from error
        except httpx.HTTPError as error:
            await self._record_provider_failure()
            raise self._failure(
                EmbeddingFailureCode.PROVIDER_UNAVAILABLE, retryable=True
            ) from error
        except asyncio.CancelledError:
            await asyncio.shield(self._release_half_open_probe())
            raise
        except Exception as error:
            await self._release_half_open_probe()
            raise self._failure(
                EmbeddingFailureCode.PROVIDER_ADAPTER_FAILURE, retryable=False
            ) from error
        await self._record_provider_success()
        return result

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _parse_response(
        self,
        request: EmbeddingRequest,
        response: httpx.Response,
        body: bytes,
        reserved_cost: int,
        rendered_bytes: int,
    ) -> EmbeddingResult:
        try:
            payload = cast(object, json.loads(body))
            if not isinstance(payload, dict):
                raise TypeError
            typed_payload = cast(dict[str, object], payload)
            model = typed_payload["model"]
            data = typed_payload["data"]
            usage = typed_payload["usage"]
            if (
                not isinstance(model, str)
                or not isinstance(data, list)
                or not isinstance(usage, dict)
            ):
                raise TypeError
        except (KeyError, TypeError, ValueError) as error:
            raise self._failure(
                EmbeddingFailureCode.PROVIDER_INVALID_RESPONSE, retryable=False
            ) from error
        if model != request.expected_model_revision:
            raise self._failure(EmbeddingFailureCode.MODEL_REVISION_MISMATCH, retryable=False)
        typed_data = cast(list[object], data)
        indices = [
            cast(dict[str, object], item).get("index")
            for item in typed_data
            if isinstance(item, dict)
        ]
        if indices != list(range(len(request.inputs))):
            raise self._failure(EmbeddingFailureCode.RESPONSE_ORDER_MISMATCH, retryable=False)
        vectors: list[EmbeddingVector] = []
        try:
            for index, item in enumerate(typed_data):
                if not isinstance(item, dict):
                    raise TypeError
                raw_vector = cast(dict[str, object], item)["embedding"]
                if not isinstance(raw_vector, list):
                    raise TypeError
                typed_vector = cast(list[object], raw_vector)
                if len(typed_vector) != request.expected_dimension:
                    raise self._failure(EmbeddingFailureCode.DIMENSION_MISMATCH, retryable=False)
                if any(
                    isinstance(value, bool) or not isinstance(value, (int, float))
                    for value in typed_vector
                ):
                    raise TypeError
                values = tuple(float(value) for value in cast(list[int | float], typed_vector))
                if not all(math.isfinite(value) for value in values):
                    raise self._failure(EmbeddingFailureCode.NON_FINITE_VECTOR, retryable=False)
                vectors.append(EmbeddingVector(index=index, values=values))
            typed_usage = cast(dict[str, object], usage)
            input_tokens = typed_usage["prompt_tokens"]
            total_tokens = typed_usage["total_tokens"]
            if (
                not isinstance(input_tokens, int)
                or not isinstance(total_tokens, int)
                or input_tokens < 0
                or total_tokens < input_tokens
            ):
                raise TypeError
        except EmbeddingFailure:
            raise
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise self._failure(
                EmbeddingFailureCode.PROVIDER_INVALID_RESPONSE, retryable=False
            ) from error
        incurred_cost = self._estimated_cost(input_tokens)
        if incurred_cost > request.budget.max_cost_microusd:
            raise self._failure(EmbeddingFailureCode.COST_BUDGET_EXCEEDED, retryable=False)
        return EmbeddingResult(
            vectors=tuple(vectors),
            usage=EmbeddingUsage(
                input_tokens=input_tokens,
                item_count=len(vectors),
                input_bytes=rendered_bytes,
            ),
            reserved_cost_microusd=reserved_cost,
            incurred_cost_microusd=incurred_cost,
            provider_id=self._policy.provider_id,
            generation=self._policy.generation,
            provider_request_id=response.headers.get("x-request-id"),
            correlation_id=request.correlation_id,
        )
