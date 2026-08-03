import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar, cast
from urllib.parse import quote, urlsplit

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
    normalized_evidence_digest,
)

_T = TypeVar("_T")
AccessTokenProvider = Callable[[], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class _BoundedResponse:
    status_code: int
    headers: httpx.Headers
    content: bytes


class VertexGenerationProvider:
    """Bounded Vertex generateContent adapter; it grants no release authority."""

    provider_id = "vertex"

    def __init__(
        self,
        *,
        deployment_id: str,
        project_id: str,
        location: str,
        model_revision: str,
        model_allowlist: tuple[str, ...],
        prompt: GroundedAnswerPrompt,
        policy: DeploymentPolicyDescriptor,
        access_token_provider: AccessTokenProvider,
        request_timeout_seconds: float = 30.0,
        max_input_tokens: int = 16_000,
        max_output_tokens: int = 1_200,
        max_response_bytes: int = 262_144,
        max_concurrency: int = 8,
        input_microusd_per_million_tokens: int = 0,
        output_microusd_per_million_tokens: int = 0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        for name, value in (
            ("deployment_id", deployment_id),
            ("project_id", project_id),
            ("location", location),
            ("model_revision", model_revision),
        ):
            if not value.strip() or len(value) > 160:
                raise ValueError(f"{name} must be non-empty and bounded")
        if policy.provider_project_id != project_id:
            raise ValueError("provider project must match deployment policy")
        if policy.residency != location:
            raise ValueError("provider location must match deployment policy")
        if policy.provider_organization_id is not None:
            raise ValueError("Vertex policy must not declare an organization")
        if model_revision not in model_allowlist:
            raise ValueError("model_revision must be in the approved allowlist")
        if policy.model_release != model_revision:
            raise ValueError("deployment policy model_release must match the model")
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if min(max_input_tokens, max_output_tokens, max_concurrency) < 1:
            raise ValueError("provider limits must be positive")
        if max_response_bytes < 1_024:
            raise ValueError("max_response_bytes is below the safe minimum")
        if min(
            input_microusd_per_million_tokens,
            output_microusd_per_million_tokens,
        ) < 1:
            raise ValueError(
                "live-capable Vertex token prices must be positive"
            )

        self._deployment_id = deployment_id
        self._project_id = project_id
        self._location = location
        self._model_revision = model_revision
        self._model_allowlist = frozenset(model_allowlist)
        self._prompt = prompt
        self._policy = policy
        self._access_token_provider = access_token_provider
        self._request_timeout_seconds = request_timeout_seconds
        self._max_input_tokens = max_input_tokens
        self._max_output_tokens = max_output_tokens
        self._max_response_bytes = max_response_bytes
        self._bulkhead = asyncio.Semaphore(max_concurrency)
        self._input_price = input_microusd_per_million_tokens
        self._output_price = output_microusd_per_million_tokens
        api_host = (
            "aiplatform.googleapis.com"
            if location == "global"
            else f"{location}-aiplatform.googleapis.com"
        )
        self._base_url = (
            f"https://{api_host}/v1/"
            f"projects/{quote(project_id, safe='')}/locations/"
            f"{quote(location, safe='')}/publishers/google/models/"
        )
        parsed = urlsplit(self._base_url)
        self._approved_origin = (parsed.scheme, parsed.hostname, parsed.port)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(request_timeout_seconds),
            follow_redirects=False,
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
        input_limit = min(request.budget.max_input_tokens, self._max_input_tokens)
        output_limit = min(
            request.budget.max_output_tokens,
            self._max_output_tokens,
        )
        return _token_cost(input_limit, self._input_price) + _token_cost(
            output_limit,
            self._output_price,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate_response(self, request: GenerationRequest) -> GenerationResult:
        if request.required_policy != self.policy:
            raise self._failure(
                InferenceFailureCode.NO_SAFE_DEPLOYMENT,
                retryable=False,
            )
        if request.cancellation is not None and request.cancellation.is_cancelled:
            raise self._failure(InferenceFailureCode.CANCELLED, retryable=False)

        rendered = self._prompt.render_input(request)
        estimated_input_tokens = _estimate_token_count(
            self._prompt.instructions + rendered
        )
        input_limit = min(request.budget.max_input_tokens, self._max_input_tokens)
        if estimated_input_tokens > input_limit:
            raise self._failure(
                InferenceFailureCode.INPUT_BUDGET_EXCEEDED,
                retryable=False,
            )
        if self.estimate_max_cost_microusd(request) > (
            request.budget.max_cost_microusd
        ):
            raise self._failure(
                InferenceFailureCode.COST_BUDGET_EXCEEDED,
                retryable=False,
                incurred_cost_microusd=0,
            )
        output_limit = min(
            request.budget.max_output_tokens,
            self._max_output_tokens,
        )
        remaining = self._remaining_seconds(request)

        acquired = False
        try:
            await self._await_with_cancellation(
                self._bulkhead.acquire(),
                timeout_seconds=remaining,
                cancellation=request.cancellation,
                timeout_code=InferenceFailureCode.PROVIDER_BUSY,
            )
            acquired = True
            response = await self._post(
                request=request,
                rendered=rendered,
                output_limit=output_limit,
                timeout_seconds=min(
                    self._request_timeout_seconds,
                    self._remaining_seconds(request),
                ),
            )
        finally:
            if acquired:
                self._bulkhead.release()

        if response.status_code >= 400:
            raise _map_http_failure(response.status_code, self.provider_id)
        result = self._parse(response, request)
        if result.usage.input_tokens > input_limit:
            raise self._failure(
                InferenceFailureCode.INPUT_BUDGET_EXCEEDED,
                retryable=False,
            )
        if result.usage.output_tokens > output_limit:
            raise self._failure(
                InferenceFailureCode.OUTPUT_BUDGET_EXCEEDED,
                retryable=False,
            )
        if result.estimated_cost_microusd > request.budget.max_cost_microusd:
            raise self._failure(
                InferenceFailureCode.COST_BUDGET_EXCEEDED,
                retryable=False,
            )
        return result

    async def _post(
        self,
        *,
        request: GenerationRequest,
        rendered: str,
        output_limit: int,
        timeout_seconds: float,
    ) -> _BoundedResponse:
        try:
            token = await self._await_with_cancellation(
                self._access_token_provider(),
                timeout_seconds=timeout_seconds,
                cancellation=request.cancellation,
                timeout_code=InferenceFailureCode.DEADLINE_EXCEEDED,
            )
        except InferenceFailure:
            raise
        except Exception as error:
            raise self._failure(
                InferenceFailureCode.PROVIDER_AUTHENTICATION_FAILED,
                retryable=False,
                incurred_cost_microusd=0,
            ) from error
        if not token.strip():
            raise self._failure(
                InferenceFailureCode.PROVIDER_AUTHENTICATION_FAILED,
                retryable=False,
                incurred_cost_microusd=0,
            )

        url = f"{self._base_url}{quote(self._model_revision, safe='')}:generateContent"
        provider_request = self._client.build_request(
            "POST",
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "systemInstruction": {
                    "role": "system",
                    "parts": [{"text": self._prompt.instructions}],
                },
                "contents": [
                    {"role": "user", "parts": [{"text": rendered}]}
                ],
                "generationConfig": {
                    "candidateCount": 1,
                    "maxOutputTokens": output_limit,
                    "temperature": 0,
                    "responseMimeType": "application/json",
                    "responseJsonSchema": self._prompt.output_schema,
                },
            },
            timeout=timeout_seconds,
        )
        origin = (
            provider_request.url.scheme,
            provider_request.url.host,
            provider_request.url.port,
        )
        if origin != self._approved_origin:
            raise self._failure(
                InferenceFailureCode.PROVIDER_REJECTED_REQUEST,
                retryable=False,
                incurred_cost_microusd=0,
            )

        async def send_and_read() -> _BoundedResponse:
            provider_response: httpx.Response | None = None
            try:
                provider_response = await self._client.send(
                    provider_request,
                    stream=True,
                    follow_redirects=False,
                )
                body = bytearray()
                async for chunk in provider_response.aiter_bytes():
                    if len(body) + len(chunk) > self._max_response_bytes:
                        raise self._failure(
                            InferenceFailureCode.RESPONSE_TOO_LARGE,
                            retryable=False,
                        )
                    body.extend(chunk)
                return _BoundedResponse(
                    status_code=provider_response.status_code,
                    headers=provider_response.headers,
                    content=bytes(body),
                )
            finally:
                if provider_response is not None:
                    await provider_response.aclose()

        try:
            return await self._await_with_cancellation(
                send_and_read(),
                timeout_seconds=timeout_seconds,
                cancellation=request.cancellation,
                timeout_code=InferenceFailureCode.DEADLINE_EXCEEDED,
            )
        except httpx.TimeoutException as error:
            raise self._failure(
                InferenceFailureCode.DEADLINE_EXCEEDED,
                retryable=True,
            ) from error
        except httpx.TransportError as error:
            raise self._failure(
                InferenceFailureCode.PROVIDER_UNAVAILABLE,
                retryable=True,
            ) from error

    def _parse(
        self,
        response: _BoundedResponse,
        request: GenerationRequest,
    ) -> GenerationResult:
        try:
            raw: object = json.loads(response.content)
            body = _mapping(raw)
            model_version = body.get("modelVersion")
            if (
                not isinstance(model_version, str)
                or model_version not in self._model_allowlist
                or model_version != self._policy.model_release
            ):
                raise self._failure(
                    InferenceFailureCode.MODEL_REVISION_MISMATCH,
                    retryable=False,
                )
            candidates = body.get("candidates")
            if not isinstance(candidates, list):
                raise ValueError("exactly one candidate is required")
            typed_candidates = cast("list[object]", candidates)
            if len(typed_candidates) != 1:
                raise ValueError("exactly one candidate is required")
            candidate = _mapping(typed_candidates[0])
            if candidate.get("finishReason") != "STOP":
                raise ValueError("candidate did not finish safely")
            content = _mapping(candidate.get("content"))
            parts = content.get("parts")
            if not isinstance(parts, list):
                raise ValueError("exactly one response part is required")
            typed_parts = cast("list[object]", parts)
            if len(typed_parts) != 1:
                raise ValueError("exactly one response part is required")
            part = _mapping(typed_parts[0])
            text = part.get("text")
            if not isinstance(text, str):
                raise ValueError("response text is missing")
            structured = _mapping(json.loads(text))
            if set(structured) != {"outcome", "answer", "citation_ids"}:
                raise ValueError("structured output has an invalid shape")
            outcome = GenerationOutcome(structured["outcome"])
            answer = _parse_answer(structured["answer"])
            citation_ids = _parse_citation_ids(structured["citation_ids"])
            if outcome is GenerationOutcome.ANSWERED:
                if answer is None or not citation_ids:
                    raise ValueError("answered outcome requires citations")
            elif answer is not None or citation_ids:
                raise ValueError("non-answer outcome cannot contain claims")
            evidence_by_id = {item.evidence_id: item for item in request.evidence}
            if any(item not in evidence_by_id for item in citation_ids):
                raise ValueError("citation is outside request evidence")
            usage = _parse_usage(body.get("usageMetadata"))
            response_id = body.get("responseId")
            if response_id is not None and (
                not isinstance(response_id, str)
                or not response_id
                or len(response_id) > 256
            ):
                raise ValueError("response identifier is invalid")
        except InferenceFailure:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise self._failure(
                InferenceFailureCode.PROVIDER_INVALID_RESPONSE,
                retryable=False,
            ) from error

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
        return GenerationResult(
            outcome=outcome,
            answer=answer,
            citations=citations,
            usage=usage,
            estimated_cost_microusd=(
                _token_cost(usage.input_tokens, self._input_price)
                + _token_cost(usage.output_tokens, self._output_price)
            ),
            deployment_id=self.deployment_id,
            provider_id=self.provider_id,
            deployment_policy=self.policy,
            model_revision=model_version,
            prompt_revision=self._prompt.revision,
            prompt_content_sha256=self._prompt.content_sha256,
            evidence_digest=normalized_evidence_digest(request),
            correlation_id=request.correlation_id,
            provider_request_id=(
                response.headers.get("x-request-id")
                or response_id
            ),
        )

    async def _await_with_cancellation(
        self,
        operation: Awaitable[_T],
        *,
        timeout_seconds: float,
        cancellation: CancellationSignal | None,
        timeout_code: InferenceFailureCode,
    ) -> _T:
        task = asyncio.ensure_future(operation)
        cancellation_task: asyncio.Task[None] | None = None
        try:
            async with asyncio.timeout(timeout_seconds):
                if cancellation is not None:
                    cancellation_task = asyncio.create_task(cancellation.wait())
                    done, _ = await asyncio.wait(
                        {task, cancellation_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if cancellation_task in done:
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                        raise self._failure(
                            InferenceFailureCode.CANCELLED,
                            retryable=False,
                        )
                return await task
        except TimeoutError as error:
            raise self._failure(
                timeout_code,
                retryable=True,
                incurred_cost_microusd=(
                    0 if timeout_code is InferenceFailureCode.PROVIDER_BUSY else None
                ),
            ) from error
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            if cancellation_task is not None:
                cancellation_task.cancel()
                await asyncio.gather(cancellation_task, return_exceptions=True)

    def _remaining_seconds(self, request: GenerationRequest) -> float:
        remaining = (request.deadline_at - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise self._failure(
                InferenceFailureCode.DEADLINE_EXCEEDED,
                retryable=False,
            )
        return remaining

    def _failure(
        self,
        code: InferenceFailureCode,
        *,
        retryable: bool,
        incurred_cost_microusd: int | None = None,
    ) -> InferenceFailure:
        return InferenceFailure(
            code,
            retryable=retryable,
            provider_id=self.provider_id,
            incurred_cost_microusd=incurred_cost_microusd,
        )


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("JSON value must be an object")
    raw = cast("dict[object, object]", value)
    if not all(isinstance(key, str) for key in raw):
        raise ValueError("JSON object keys must be strings")
    return cast("dict[str, object]", raw)


def _parse_answer(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 8_000:
        raise ValueError("answer is invalid")
    return value.strip()


def _parse_citation_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("citation identifiers are invalid")
    raw = cast("list[object]", value)
    if len(raw) > 32 or not all(
        isinstance(item, str) and 0 < len(item) <= 128 for item in raw
    ):
        raise ValueError("citation identifiers are invalid")
    result = cast("list[str]", raw)
    if len(set(result)) != len(result):
        raise ValueError("citation identifiers must be unique")
    return result


def _parse_usage(value: object) -> InferenceUsage:
    usage = _mapping(value)
    prompt = usage.get("promptTokenCount")
    output = usage.get("candidatesTokenCount")
    cached = usage.get("cachedContentTokenCount", 0)
    reasoning = usage.get("thoughtsTokenCount", 0)
    values = (prompt, output, cached, reasoning)
    if not all(
        isinstance(item, int) and not isinstance(item, bool) and item >= 0
        for item in values
    ):
        raise ValueError("usage metadata is invalid")
    return InferenceUsage(
        input_tokens=cast("int", prompt),
        output_tokens=cast("int", output),
        cached_input_tokens=cast("int", cached),
        reasoning_tokens=min(cast("int", reasoning), cast("int", output)),
    )


def _estimate_token_count(value: str) -> int:
    return max(1, (len(value.encode("utf-8")) + 2) // 3)


def _token_cost(tokens: int, microusd_per_million_tokens: int) -> int:
    return (tokens * microusd_per_million_tokens + 999_999) // 1_000_000


def _map_http_failure(status: int, provider_id: str) -> InferenceFailure:
    if status in {401, 403}:
        code = InferenceFailureCode.PROVIDER_AUTHENTICATION_FAILED
        retryable = False
    elif status == 429:
        code = InferenceFailureCode.PROVIDER_RATE_LIMITED
        retryable = True
    elif status >= 500:
        code = InferenceFailureCode.PROVIDER_UNAVAILABLE
        retryable = True
    else:
        code = InferenceFailureCode.PROVIDER_REJECTED_REQUEST
        retryable = False
    return InferenceFailure(
        code,
        retryable=retryable,
        provider_id=provider_id,
        status_code=status,
    )
