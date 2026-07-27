import asyncio
import json
import math
from typing import cast

import httpx

from app.infrastructure.embedding_providers.base import BaseEmbeddingAdapter
from app.infrastructure.embedding_providers.policy import (
    EmbeddingAdapterPolicy,
    TeiDeploymentIdentity,
)
from app.modules.inference.application.embedding_ports import (
    EmbeddingFailure,
    EmbeddingFailureCode,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingUsage,
    EmbeddingVector,
)


class TeiEmbeddingAdapter(BaseEmbeddingAdapter):
    def __init__(
        self,
        policy: EmbeddingAdapterPolicy,
        *,
        client: httpx.AsyncClient,
        expected_identity: TeiDeploymentIdentity,
        api_token: str | None = None,
        owns_client: bool = False,
    ) -> None:
        super().__init__(policy)
        if expected_identity.model_revision != policy.model_revision:
            raise ValueError("TEI identity model revision must match policy")
        if expected_identity.input_template_revision != policy.input_template_revision:
            raise ValueError("TEI identity input template must match policy")
        self._client = client
        self._expected_identity = expected_identity
        self._headers = {"Authorization": f"Bearer {api_token}"} if api_token else {}
        self._owns_client = owns_client
        self._identity_verified = False
        self._identity_lock = asyncio.Lock()

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        rendered, rendered_bytes, rendered_tokens, reserved_cost = self._preflight(request)
        try:
            async with self._execution_slot(request):
                await self._ensure_identity(request)
                provider_request = self._client.build_request(
                    "POST",
                    "/embed",
                    headers=self._headers,
                    json={
                        "inputs": list(rendered),
                        "normalize": True,
                        "truncate": False,
                    },
                )
                response = await self._run_request(
                    request,
                    self._client.send(provider_request, stream=True),
                )
                try:
                    if response.status_code >= 400:
                        raise self._map_http_failure(response)
                    observed_deployment = response.headers.get(
                        "x-vfbiz-embedding-deployment-sha256"
                    )
                    if observed_deployment != self._expected_identity.deployment_sha256:
                        self._identity_verified = False
                        raise self._failure(
                            EmbeddingFailureCode.MODEL_REVISION_MISMATCH,
                            retryable=False,
                            provider_request_id=response.headers.get("x-request-id"),
                        )
                    body = await self._read_bounded_response(request, response)
                finally:
                    await response.aclose()
            result = self._parse_response(
                request,
                response,
                body,
                reserved_cost,
                rendered_bytes,
                rendered_tokens,
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

    async def _ensure_identity(self, request: EmbeddingRequest) -> None:
        if self._identity_verified:
            return
        async with self._identity_lock:
            if self._identity_verified:
                return
            identity_request = self._client.build_request(
                "GET",
                "/info",
                headers=self._headers,
            )
            response = await self._run_request(
                request,
                self._client.send(identity_request, stream=True),
            )
            try:
                if response.status_code >= 400:
                    raise self._map_http_failure(response)
                body = await self._read_bounded_response(request, response)
            finally:
                await response.aclose()
            try:
                payload = cast(object, json.loads(body))
                if not isinstance(payload, dict):
                    raise TypeError
                typed_payload = cast(dict[str, object], payload)
                identity_values = (
                    typed_payload["model_revision"],
                    typed_payload["tokenizer_sha256"],
                    typed_payload["weights_sha256"],
                    typed_payload["input_template_revision"],
                    typed_payload["deployment_sha256"],
                )
                if any(not isinstance(value, str) for value in identity_values):
                    raise TypeError
                observed = TeiDeploymentIdentity(
                    model_revision=cast(str, identity_values[0]),
                    tokenizer_sha256=cast(str, identity_values[1]),
                    weights_sha256=cast(str, identity_values[2]),
                    input_template_revision=cast(str, identity_values[3]),
                    deployment_sha256=cast(str, identity_values[4]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise self._failure(
                    EmbeddingFailureCode.PROVIDER_INVALID_RESPONSE,
                    retryable=False,
                ) from error
            if observed != self._expected_identity:
                raise self._failure(
                    EmbeddingFailureCode.MODEL_REVISION_MISMATCH,
                    retryable=False,
                )
            self._identity_verified = True

    def _parse_response(
        self,
        request: EmbeddingRequest,
        response: httpx.Response,
        body: bytes,
        reserved_cost: int,
        rendered_bytes: int,
        rendered_tokens: int,
    ) -> EmbeddingResult:
        try:
            payload = cast(object, json.loads(body))
            if not isinstance(payload, list):
                raise TypeError
            typed_payload = cast(list[object], payload)
            if len(typed_payload) != len(request.inputs):
                raise TypeError
            vectors: list[EmbeddingVector] = []
            for index, raw_vector in enumerate(typed_payload):
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
        except EmbeddingFailure:
            raise
        except (TypeError, ValueError, OverflowError) as error:
            raise self._failure(
                EmbeddingFailureCode.PROVIDER_INVALID_RESPONSE, retryable=False
            ) from error
        return EmbeddingResult(
            vectors=tuple(vectors),
            usage=EmbeddingUsage(
                input_tokens=rendered_tokens,
                item_count=len(vectors),
                input_bytes=rendered_bytes,
            ),
            reserved_cost_microusd=reserved_cost,
            incurred_cost_microusd=None,
            provider_id=self._policy.provider_id,
            generation=self._policy.generation,
            provider_request_id=response.headers.get("x-request-id"),
            correlation_id=request.correlation_id,
        )
