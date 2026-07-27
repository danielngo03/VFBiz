import asyncio
import json
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar, cast
from urllib.parse import urlsplit

import httpx

from app.modules.inference.application import (
    CancellationSignal,
    Citation,
    DeploymentPolicyDescriptor,
    GenerationOutcome,
    GenerationRequest,
    GenerationResult,
    GroundedAnswerPrompt,
    InferenceFailure,
    InferenceFailureCode,
    InferenceUsage,
    dynamic_input_sha256,
    normalized_evidence_digest,
)

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class _BoundedResponse:
    status_code: int
    headers: httpx.Headers
    content: bytes


class OpenAIResponsesProvider:
    """Bounded OpenAI Responses adapter; authority remains outside the provider."""

    provider_id = "openai"

    def __init__(
        self,
        *,
        deployment_id: str,
        api_key: str,
        project_id: str,
        organization_id: str | None,
        model_revision: str,
        model_allowlist: tuple[str, ...],
        prompt: GroundedAnswerPrompt,
        policy: DeploymentPolicyDescriptor,
        base_url: str = "https://api.openai.com/v1",
        request_timeout_seconds: float = 30.0,
        max_input_tokens: int = 16_000,
        max_output_tokens: int = 1_200,
        max_response_bytes: int = 262_144,
        max_concurrency: int = 32,
        input_microusd_per_million_tokens: int = 0,
        output_microusd_per_million_tokens: int = 0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not deployment_id.strip() or len(deployment_id) > 160:
            raise ValueError("deployment_id must be non-empty and bounded")
        if not api_key.strip():
            raise ValueError("api_key must not be blank")
        if not project_id.strip() or len(project_id) > 160:
            raise ValueError("project_id must be non-empty and bounded")
        if policy.provider_project_id != project_id:
            raise ValueError("provider project must match deployment policy evidence")
        if organization_id is not None and (
            not organization_id.strip() or len(organization_id) > 160
        ):
            raise ValueError("organization_id must be non-empty and bounded")
        if policy.provider_organization_id != organization_id:
            raise ValueError("provider organization must match deployment policy evidence")
        if model_revision not in model_allowlist:
            raise ValueError("model_revision must be in the approved allowlist")
        if policy.model_release != model_revision:
            raise ValueError("deployment policy model_release must match the request model")
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if max_response_bytes < 1_024:
            raise ValueError("max_response_bytes is below the safe minimum")
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        if (
            min(
                input_microusd_per_million_tokens,
                output_microusd_per_million_tokens,
            )
            < 0
        ):
            raise ValueError("token prices cannot be negative")

        self._api_key = api_key
        self._project_id = project_id
        self._organization_id = organization_id
        self._deployment_id = deployment_id
        self._model_revision = model_revision
        self._model_allowlist = frozenset(model_allowlist)
        self._prompt = prompt
        self._policy = policy
        self._base_url = base_url.rstrip("/") + "/"
        parsed_base = urlsplit(self._base_url)
        if (
            not parsed_base.hostname
            or parsed_base.username
            or parsed_base.password
            or parsed_base.query
            or parsed_base.fragment
        ):
            raise ValueError("base_url must have a safe absolute origin")
        if parsed_base.scheme != "https" and not (
            parsed_base.scheme == "http"
            and parsed_base.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError("base_url must use HTTPS or local loopback HTTP")
        self._approved_origin = (
            parsed_base.scheme,
            parsed_base.hostname,
            parsed_base.port,
        )
        self._request_timeout_seconds = request_timeout_seconds
        self._max_input_tokens = max_input_tokens
        self._max_output_tokens = max_output_tokens
        self._max_response_bytes = max_response_bytes
        self._bulkhead = asyncio.Semaphore(max_concurrency)
        self._input_price = input_microusd_per_million_tokens
        self._output_price = output_microusd_per_million_tokens
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(request_timeout_seconds),
            follow_redirects=False,
            # Egress proxies must be configured explicitly at the deployment
            # boundary, never inherited accidentally from the process.
            trust_env=False,
            limits=httpx.Limits(
                max_connections=max_concurrency,
                max_keepalive_connections=max_concurrency,
            ),
        )

    @property
    def deployment_id(self) -> str:
        return self._deployment_id

    @property
    def policy(self) -> DeploymentPolicyDescriptor:
        return self._policy

    def estimate_max_cost_microusd(self, request: GenerationRequest) -> int:
        input_limit = min(
            request.budget.max_input_tokens,
            self._max_input_tokens,
        )
        output_limit = min(
            request.budget.max_output_tokens,
            self._max_output_tokens,
        )
        return _token_cost(input_limit, self._input_price) + _token_cost(
            output_limit,
            self._output_price,
        )

    async def aclose(self) -> None:
        """Close the shared client from the FastAPI lifespan owner."""
        if self._owns_client:
            await self._client.aclose()

    async def generate_response(self, request: GenerationRequest) -> GenerationResult:
        if request.required_policy != self.policy:
            raise InferenceFailure(
                InferenceFailureCode.NO_SAFE_DEPLOYMENT,
                retryable=False,
                provider_id=self.provider_id,
            )
        self._raise_if_cancelled(request.cancellation)

        rendered_input = self._prompt.render_input(request)
        estimated_input_tokens = _estimate_token_count(self._prompt.instructions + rendered_input)
        input_limit = min(
            request.budget.max_input_tokens,
            self._max_input_tokens,
        )
        if estimated_input_tokens > input_limit:
            raise InferenceFailure(
                InferenceFailureCode.INPUT_BUDGET_EXCEEDED,
                retryable=False,
                provider_id=self.provider_id,
            )

        remaining_seconds = self._remaining_seconds(request)
        output_limit = min(
            request.budget.max_output_tokens,
            self._max_output_tokens,
        )
        payload = self._build_payload(
            request=request,
            rendered_input=rendered_input,
            max_output_tokens=output_limit,
        )

        acquired = False
        try:
            await self._await_with_cancellation(
                self._bulkhead.acquire(),
                timeout_seconds=remaining_seconds,
                cancellation=request.cancellation,
                timeout_code=InferenceFailureCode.PROVIDER_BUSY,
            )
            acquired = True
            response = await self._post_bounded(
                payload=payload,
                timeout_seconds=min(
                    self._request_timeout_seconds,
                    self._remaining_seconds(request),
                ),
                cancellation=request.cancellation,
            )
        finally:
            if acquired:
                self._bulkhead.release()

        if 300 <= response.status_code < 400:
            raise InferenceFailure(
                InferenceFailureCode.PROVIDER_REJECTED_REQUEST,
                retryable=False,
                provider_id=self.provider_id,
                status_code=response.status_code,
                incurred_cost_microusd=0,
            )
        if response.status_code >= 400:
            raise _map_http_failure(response.status_code, self.provider_id)

        result = self._parse_with_evidence(
            response=response,
            request=request,
        )
        if result.usage.input_tokens > request.budget.max_input_tokens:
            raise InferenceFailure(
                InferenceFailureCode.INPUT_BUDGET_EXCEEDED,
                retryable=False,
                provider_id=self.provider_id,
            )
        if result.usage.output_tokens > output_limit:
            raise InferenceFailure(
                InferenceFailureCode.OUTPUT_BUDGET_EXCEEDED,
                retryable=False,
                provider_id=self.provider_id,
            )
        return result

    def _build_payload(
        self,
        *,
        request: GenerationRequest,
        rendered_input: str,
        max_output_tokens: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model_revision,
            "instructions": self._prompt.instructions,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": rendered_input}],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "vfbiz_grounded_answer",
                    "strict": True,
                    "schema": self._prompt.output_schema,
                }
            },
            "max_output_tokens": max_output_tokens,
            "store": False,
            "truncation": "disabled",
            "parallel_tool_calls": False,
            "metadata": {
                "correlation_id": request.correlation_id,
                "prompt_revision": self._prompt.revision,
                "prompt_content_sha256": self._prompt.content_sha256,
                "input_content_sha256": dynamic_input_sha256(request),
            },
        }
        if request.safety_identifier is not None:
            payload["safety_identifier"] = request.safety_identifier
        return payload

    async def _post_bounded(
        self,
        *,
        payload: dict[str, Any],
        timeout_seconds: float,
        cancellation: CancellationSignal | None,
    ) -> _BoundedResponse:
        request = self._client.build_request(
            "POST",
            f"{self._base_url}responses",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "OpenAI-Project": self._project_id,
                **(
                    {"OpenAI-Organization": self._organization_id}
                    if self._organization_id is not None
                    else {}
                ),
            },
            json=payload,
            timeout=timeout_seconds,
        )
        request_origin = (
            request.url.scheme,
            request.url.host,
            request.url.port,
        )
        if request_origin != self._approved_origin:
            raise InferenceFailure(
                InferenceFailureCode.PROVIDER_REJECTED_REQUEST,
                retryable=False,
                provider_id=self.provider_id,
                incurred_cost_microusd=0,
            )

        async def send_and_read() -> _BoundedResponse:
            response: httpx.Response | None = None
            try:
                response = await self._client.send(
                    request,
                    stream=True,
                    follow_redirects=False,
                )
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > self._max_response_bytes:
                        raise InferenceFailure(
                            InferenceFailureCode.RESPONSE_TOO_LARGE,
                            retryable=False,
                            provider_id=self.provider_id,
                        )
                    content.extend(chunk)
                return _BoundedResponse(
                    status_code=response.status_code,
                    headers=response.headers,
                    content=bytes(content),
                )
            finally:
                if response is not None:
                    await response.aclose()

        try:
            return await self._await_with_cancellation(
                send_and_read(),
                timeout_seconds=timeout_seconds,
                cancellation=cancellation,
                timeout_code=InferenceFailureCode.DEADLINE_EXCEEDED,
            )
        except httpx.TimeoutException as error:
            raise InferenceFailure(
                InferenceFailureCode.DEADLINE_EXCEEDED,
                retryable=True,
                provider_id=self.provider_id,
            ) from error
        except httpx.TransportError as error:
            raise InferenceFailure(
                InferenceFailureCode.PROVIDER_UNAVAILABLE,
                retryable=True,
                provider_id=self.provider_id,
            ) from error

    async def _await_with_cancellation(
        self,
        operation: Awaitable[_T],
        *,
        timeout_seconds: float,
        cancellation: CancellationSignal | None,
        timeout_code: InferenceFailureCode,
    ) -> _T:
        operation_task = asyncio.ensure_future(operation)
        cancellation_task: asyncio.Task[None] | None = None
        try:
            async with asyncio.timeout(timeout_seconds):
                if cancellation is not None:
                    cancellation_task = asyncio.create_task(cancellation.wait())
                    done, _ = await asyncio.wait(
                        {operation_task, cancellation_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if cancellation_task in done:
                        operation_task.cancel()
                        await asyncio.gather(operation_task, return_exceptions=True)
                        raise InferenceFailure(
                            InferenceFailureCode.CANCELLED,
                            retryable=False,
                            provider_id=self.provider_id,
                        )
                return await operation_task
        except TimeoutError as error:
            raise InferenceFailure(
                timeout_code,
                retryable=True,
                provider_id=self.provider_id,
                incurred_cost_microusd=(
                    0 if timeout_code is InferenceFailureCode.PROVIDER_BUSY else None
                ),
            ) from error
        finally:
            if not operation_task.done():
                operation_task.cancel()
                await asyncio.gather(operation_task, return_exceptions=True)
            if cancellation_task is not None:
                cancellation_task.cancel()
                await asyncio.gather(cancellation_task, return_exceptions=True)

    def _parse_with_evidence(
        self,
        *,
        response: _BoundedResponse,
        request: GenerationRequest,
    ) -> GenerationResult:
        try:
            raw_body: object = json.loads(response.content)
            body = _as_mapping(raw_body)
            if body.get("status") != "completed":
                raise ValueError("response is not completed")
            actual_model = body.get("model")
            if not isinstance(actual_model, str):
                raise ValueError("response model is missing")
            if (
                actual_model not in self._model_allowlist
                or actual_model != self._policy.model_release
            ):
                raise InferenceFailure(
                    InferenceFailureCode.MODEL_REVISION_MISMATCH,
                    retryable=False,
                    provider_id=self.provider_id,
                )
            raw_structured: object = json.loads(_extract_output_text(body))
            structured = _as_mapping(raw_structured)
            if set(structured) != {"outcome", "answer", "citation_ids"}:
                raise ValueError("structured output has an invalid shape")
            outcome = GenerationOutcome(structured["outcome"])
            raw_answer = structured["answer"]
            if raw_answer is not None and (
                not isinstance(raw_answer, str) or not raw_answer.strip() or len(raw_answer) > 8_000
            ):
                raise ValueError("answer exceeds local constraints")
            answer = raw_answer.strip() if isinstance(raw_answer, str) else None
            citation_ids = _parse_citation_ids(structured["citation_ids"])
            if outcome is GenerationOutcome.ANSWERED:
                if answer is None or not citation_ids:
                    raise ValueError("answered outcome requires answer and citations")
            elif citation_ids:
                raise ValueError("non-answer outcome cannot cite evidence")

            evidence_by_id = {item.evidence_id: item for item in request.evidence}
            if any(item not in evidence_by_id for item in citation_ids):
                raise ValueError("provider cited evidence outside the request")
            citations = tuple(
                Citation(
                    evidence_id=evidence_by_id[item].evidence_id,
                    source_uri=evidence_by_id[item].source_uri,
                    source_revision=evidence_by_id[item].source_revision,
                    title=evidence_by_id[item].title,
                    freshness=evidence_by_id[item].freshness,
                )
                for item in citation_ids
            )
            usage = _parse_usage(body.get("usage"))
            response_id = body.get("id")
            if response_id is not None and not isinstance(response_id, str):
                raise ValueError("response id is invalid")
        except InferenceFailure:
            raise
        except (TypeError, ValueError, json.JSONDecodeError, KeyError) as error:
            raise InferenceFailure(
                InferenceFailureCode.PROVIDER_INVALID_RESPONSE,
                retryable=False,
                provider_id=self.provider_id,
            ) from error

        try:
            estimated_cost = _token_cost(usage.input_tokens, self._input_price) + _token_cost(
                usage.output_tokens, self._output_price
            )
            return GenerationResult(
                outcome=outcome,
                answer=answer,
                citations=citations,
                usage=usage,
                estimated_cost_microusd=estimated_cost,
                deployment_id=self.deployment_id,
                provider_id=self.provider_id,
                deployment_policy=self.policy,
                model_revision=actual_model,
                prompt_revision=self._prompt.revision,
                prompt_content_sha256=self._prompt.content_sha256,
                evidence_digest=normalized_evidence_digest(request),
                correlation_id=request.correlation_id,
                provider_request_id=(response.headers.get("x-request-id") or response_id),
            )
        except ValueError as error:
            raise InferenceFailure(
                InferenceFailureCode.PROVIDER_INVALID_RESPONSE,
                retryable=False,
                provider_id=self.provider_id,
            ) from error

    def _remaining_seconds(self, request: GenerationRequest) -> float:
        remaining = (request.deadline_at - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise InferenceFailure(
                InferenceFailureCode.DEADLINE_EXCEEDED,
                retryable=False,
                provider_id=self.provider_id,
            )
        return remaining

    def _raise_if_cancelled(self, cancellation: CancellationSignal | None) -> None:
        if cancellation is not None and cancellation.is_cancelled:
            raise InferenceFailure(
                InferenceFailureCode.CANCELLED,
                retryable=False,
                provider_id=self.provider_id,
            )


def _estimate_token_count(value: str) -> int:
    return max(1, (len(value.encode("utf-8")) + 2) // 3)


def _token_cost(tokens: int, microusd_per_million_tokens: int) -> int:
    return (tokens * microusd_per_million_tokens + 999_999) // 1_000_000


def _map_http_failure(status_code: int, provider_id: str) -> InferenceFailure:
    if status_code in {401, 403}:
        code = InferenceFailureCode.PROVIDER_AUTHENTICATION_FAILED
        retryable = False
    elif status_code == 429:
        code = InferenceFailureCode.PROVIDER_RATE_LIMITED
        retryable = True
    elif status_code >= 500:
        code = InferenceFailureCode.PROVIDER_UNAVAILABLE
        retryable = True
    else:
        code = InferenceFailureCode.PROVIDER_REJECTED_REQUEST
        retryable = False
    return InferenceFailure(
        code,
        retryable=retryable,
        provider_id=provider_id,
        status_code=status_code,
    )


def _parse_citation_ids(raw_value: object) -> list[str]:
    if not isinstance(raw_value, list):
        raise ValueError("citation identifiers are invalid")
    untyped = cast("list[object]", raw_value)
    if len(untyped) > 32 or not all(
        isinstance(item, str) and 0 < len(item) <= 128 for item in untyped
    ):
        raise ValueError("citation identifiers exceed local constraints")
    citation_ids = cast("list[str]", untyped)
    if len(set(citation_ids)) != len(citation_ids):
        raise ValueError("citation identifiers must be unique")
    return citation_ids


def _extract_output_text(body: Mapping[str, Any]) -> str:
    output = body.get("output")
    if not isinstance(output, list):
        raise ValueError("output is missing")
    typed_output = cast("list[object]", output)
    texts: list[str] = []
    for raw_item in typed_output:
        if not isinstance(raw_item, dict):
            continue
        item = cast("dict[str, object]", raw_item)
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for raw_part in cast("list[object]", content):
            if not isinstance(raw_part, dict):
                continue
            part = cast("dict[str, object]", raw_part)
            if part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str):
                    texts.append(text)
    if len(texts) != 1:
        raise ValueError("exactly one output_text item is required")
    return texts[0]


def _parse_usage(raw_usage: object) -> InferenceUsage:
    if not isinstance(raw_usage, dict):
        raise ValueError("usage is missing")
    usage = cast("dict[str, object]", raw_usage)
    empty_details: dict[str, object] = {}
    input_details = usage.get("input_tokens_details") or empty_details
    output_details = usage.get("output_tokens_details") or empty_details
    if not isinstance(input_details, dict) or not isinstance(output_details, dict):
        raise ValueError("usage details are invalid")
    typed_input_details = cast("dict[str, object]", input_details)
    typed_output_details = cast("dict[str, object]", output_details)
    values = (
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        typed_input_details.get("cached_tokens", 0),
        typed_output_details.get("reasoning_tokens", 0),
    )
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        raise ValueError("usage values are invalid")
    return InferenceUsage(
        input_tokens=cast("int", values[0]),
        output_tokens=cast("int", values[1]),
        cached_input_tokens=cast("int", values[2]),
        reasoning_tokens=cast("int", values[3]),
    )


def _as_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("JSON value must be an object")
    untyped = cast("dict[object, object]", value)
    if not all(isinstance(key, str) for key in untyped):
        raise ValueError("JSON object keys must be strings")
    return cast("dict[str, object]", untyped)
