import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote

import httpx

from app.infrastructure.embedding_providers.base import BaseEmbeddingAdapter
from app.infrastructure.embedding_providers.policy import EmbeddingAdapterPolicy
from app.modules.inference.application.embedding_ports import (
    EmbeddingFailure,
    EmbeddingFailureCode,
    EmbeddingPurpose,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingUsage,
    EmbeddingVector,
)

AccessTokenProvider = Callable[[], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class VertexEmbeddingDeploymentDescriptor:
    project_id: str
    location: str
    model_revision: str
    profile: str
    retention_policy: str
    pricing_revision: str
    data_controls_approval_sha256: str

    def __post_init__(self) -> None:
        for value in (
            self.project_id,
            self.location,
            self.model_revision,
            self.profile,
            self.retention_policy,
            self.pricing_revision,
        ):
            if not value.strip() or len(value) > 160:
                raise ValueError(
                    "Vertex embedding deployment identity must be bounded"
                )
        digest = self.data_controls_approval_sha256
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ValueError(
                "Vertex embedding data-control evidence must use SHA-256"
            )


class VertexEmbeddingAdapter(BaseEmbeddingAdapter):
    """Vertex embedding adapter with exact endpoint and response identity checks."""

    def __init__(
        self,
        policy: EmbeddingAdapterPolicy,
        *,
        deployment: VertexEmbeddingDeploymentDescriptor,
        access_token_provider: AccessTokenProvider,
        client: httpx.AsyncClient | None = None,
        owns_client: bool | None = None,
    ) -> None:
        super().__init__(policy)
        if policy.provider_id != "vertex":
            raise ValueError("Vertex embedding policy must use provider_id=vertex")
        if deployment.model_revision != policy.model_revision:
            raise ValueError(
                "Vertex embedding deployment model must match adapter policy"
            )
        if (
            policy.model_revision == "gemini-embedding-001"
            and policy.max_items_per_request != 1
        ):
            raise ValueError(
                "gemini-embedding-001 requires exactly one input per request"
            )
        self._deployment = deployment
        self._access_token_provider = access_token_provider
        self._owns_client = client is None if owns_client is None else owns_client
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(30),
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(
                max_connections=policy.max_concurrency,
                max_keepalive_connections=policy.max_concurrency,
            ),
        )
        api_host = (
            "aiplatform.googleapis.com"
            if deployment.location == "global"
            else f"{deployment.location}-aiplatform.googleapis.com"
        )
        self._url = (
            f"https://{api_host}/v1/"
            f"projects/{quote(deployment.project_id, safe='')}/locations/"
            f"{quote(deployment.location, safe='')}/publishers/google/models/"
            f"{quote(policy.model_revision, safe='')}:predict"
        )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        rendered, rendered_bytes, _, reserved_cost = self._preflight(request)
        try:
            try:
                token = await self._run_request(
                    request,
                    self._access_token_provider(),
                )
            except (EmbeddingFailure, asyncio.CancelledError):
                raise
            except Exception as error:
                raise self._failure(
                    EmbeddingFailureCode.PROVIDER_AUTHENTICATION_FAILED,
                    retryable=False,
                ) from error
            if not token.strip():
                raise self._failure(
                    EmbeddingFailureCode.PROVIDER_AUTHENTICATION_FAILED,
                    retryable=False,
                )
            task_type = (
                "RETRIEVAL_QUERY"
                if request.purpose is EmbeddingPurpose.RETRIEVAL_QUERY
                else "RETRIEVAL_DOCUMENT"
            )
            async with self._execution_slot(request):
                provider_request = self._client.build_request(
                    "POST",
                    self._url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "instances": [
                            {"content": text, "task_type": task_type}
                            for text in rendered
                        ],
                        "parameters": {
                            "autoTruncate": False,
                            "outputDimensionality": self._policy.output_dimension,
                        },
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
            result = self._parse(
                request,
                response,
                body,
                reserved_cost,
                rendered_bytes,
            )
        except EmbeddingFailure as error:
            if self._failure_counts_toward_circuit(error):
                await self._record_provider_failure()
            else:
                await self._release_half_open_probe()
            raise
        except httpx.TimeoutException as error:
            await self._record_provider_failure()
            raise self._failure(
                EmbeddingFailureCode.DEADLINE_EXCEEDED,
                retryable=True,
            ) from error
        except httpx.HTTPError as error:
            await self._record_provider_failure()
            raise self._failure(
                EmbeddingFailureCode.PROVIDER_UNAVAILABLE,
                retryable=True,
            ) from error
        except asyncio.CancelledError:
            await asyncio.shield(self._release_half_open_probe())
            raise
        except Exception as error:
            await self._release_half_open_probe()
            raise self._failure(
                EmbeddingFailureCode.PROVIDER_ADAPTER_FAILURE,
                retryable=False,
            ) from error
        await self._record_provider_success()
        return result

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _parse(
        self,
        request: EmbeddingRequest,
        response: httpx.Response,
        body: bytes,
        reserved_cost: int,
        rendered_bytes: int,
    ) -> EmbeddingResult:
        try:
            raw: object = json.loads(body)
            if not isinstance(raw, dict):
                raise TypeError
            payload = cast("dict[str, object]", raw)
            predictions = payload["predictions"]
            if not isinstance(predictions, list):
                raise TypeError
            typed_predictions = cast("list[object]", predictions)
            if len(typed_predictions) != len(request.inputs):
                raise self._failure(
                    EmbeddingFailureCode.RESPONSE_ORDER_MISMATCH,
                    retryable=False,
                )
            vectors: list[EmbeddingVector] = []
            input_tokens = 0
            for index, raw_prediction in enumerate(typed_predictions):
                if not isinstance(raw_prediction, dict):
                    raise TypeError
                prediction = cast("dict[str, object]", raw_prediction)
                embeddings = prediction["embeddings"]
                if not isinstance(embeddings, dict):
                    raise TypeError
                embedding = cast("dict[str, object]", embeddings)
                raw_values = embedding["values"]
                statistics = embedding["statistics"]
                if not isinstance(raw_values, list) or not isinstance(
                    statistics,
                    dict,
                ):
                    raise TypeError
                typed_values = cast("list[object]", raw_values)
                if len(typed_values) != request.expected_dimension:
                    raise self._failure(
                        EmbeddingFailureCode.DIMENSION_MISMATCH,
                        retryable=False,
                    )
                values = tuple(
                    float(value)
                    for value in typed_values
                    if not isinstance(value, bool)
                    and isinstance(value, (int, float))
                )
                if len(values) != len(typed_values) or not all(
                    math.isfinite(value) for value in values
                ):
                    raise self._failure(
                        EmbeddingFailureCode.NON_FINITE_VECTOR,
                        retryable=False,
                    )
                token_count = cast("dict[str, object]", statistics).get(
                    "token_count"
                )
                truncated = cast("dict[str, object]", statistics).get(
                    "truncated"
                )
                if (
                    not isinstance(token_count, int)
                    or isinstance(token_count, bool)
                    or token_count < 0
                    or truncated is not False
                ):
                    raise TypeError
                input_tokens += token_count
                vectors.append(EmbeddingVector(index=index, values=values))
        except EmbeddingFailure:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise self._failure(
                EmbeddingFailureCode.PROVIDER_INVALID_RESPONSE,
                retryable=False,
            ) from error
        incurred_cost = self._estimated_cost(input_tokens)
        if incurred_cost > request.budget.max_cost_microusd:
            raise self._failure(
                EmbeddingFailureCode.COST_BUDGET_EXCEEDED,
                retryable=False,
            )
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
