from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from time import monotonic
from typing import Protocol, cast
from urllib.parse import quote

import google.auth
import httpx
from google.api_core.exceptions import PreconditionFailed
from google.auth import impersonated_credentials
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.cloud import storage  # pyright: ignore[reportMissingTypeStubs]

from app.infrastructure.model_providers.vertex_smoke_authority import (
    CANONICAL_FIXTURES,
    FileSmokeLedger,
    IamEvidence,
    SmokeAuthorization,
    SmokeCapability,
    SmokeDispatchReceipt,
    SmokeOutcome,
    SmokePreflightFailure,
    SmokePreflightFailureCode,
    VertexSmokeAuthority,
    VertexSmokeManifest,
    authorize_and_reserve,
    execute_authorized_smoke,
)

_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_MAX_RESPONSE_BYTES = 262_144


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return sha256(
        value if isinstance(value, bytes) else _canonical_bytes(value)
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class BoundVertexRequest:
    capability: SmokeCapability
    url: str
    body: bytes
    body_sha256: str


@dataclass(frozen=True, slots=True)
class SanitizedVertexSmokeResult:
    authorization_evidence: dict[str, object]
    capability: SmokeCapability
    request_sha256: str
    response_sha256: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    incurred_cost_microusd: int
    receipt_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "authorization": self.authorization_evidence,
            "capability": self.capability.value,
            "incurredCostMicrousd": self.incurred_cost_microusd,
            "inputTokens": self.input_tokens,
            "latencyMs": self.latency_ms,
            "outputTokens": self.output_tokens,
            "receiptSha256": self.receipt_sha256,
            "requestSha256": self.request_sha256,
            "responseSha256": self.response_sha256,
            "schemaVersion": 1,
        }


class ImpersonatedVertexTokenProvider:
    """Mint a short-lived keyless token for exactly one smoke service account."""

    def __init__(self, *, target_principal: str) -> None:
        if not target_principal.endswith(".gserviceaccount.com"):
            raise ValueError("target principal must be a service account")
        self._target_principal = target_principal

    @property
    def principal(self) -> str:
        return self._target_principal

    def __call__(self) -> str:
        credentials = _impersonated_credentials(self._target_principal)
        credentials.refresh(  # pyright: ignore[reportUnknownMemberType]
            GoogleAuthRequest()
        )
        token = cast(
            "str | None",
            credentials.token,  # pyright: ignore[reportUnknownMemberType]
        )
        if not isinstance(token, str) or len(token) < 20 or any(
            character.isspace() for character in token
        ):
            raise RuntimeError("impersonated token was not bounded")
        return token


def _impersonated_credentials(target_principal: str) -> Credentials:
    source, _ = cast(
        "tuple[Credentials, str | None]",
        google.auth.default(  # pyright: ignore[reportUnknownMemberType]
            scopes=[_CLOUD_PLATFORM_SCOPE]
        ),
    )
    return impersonated_credentials.Credentials(
        source_credentials=source,
        target_principal=target_principal,
        target_scopes=[_CLOUD_PLATFORM_SCOPE],
        lifetime=300,
    )


class BoundVertexTokenProvider(Protocol):
    @property
    def principal(self) -> str: ...

    def __call__(self) -> str: ...


class DispatchWitness(Protocol):
    def claim(
        self,
        *,
        manifest: VertexSmokeManifest,
        capability: SmokeCapability,
    ) -> None: ...


class GcsDispatchWitness:
    """Create one durable admission marker outside the local ledger."""

    def __init__(
        self,
        *,
        project_id: str,
        bucket_name: str,
        principal: str,
        prefix: str = "vertex-synthetic-smoke",
    ) -> None:
        if (
            not project_id.strip()
            or not bucket_name.strip()
            or not principal.endswith(".gserviceaccount.com")
            or not prefix.strip("/")
            or ".." in prefix
        ):
            raise ValueError("GCS witness identity must be bounded")
        self._project_id = project_id
        self._bucket_name = bucket_name
        self._principal = principal
        self._prefix = prefix.strip("/")

    def claim(
        self,
        *,
        manifest: VertexSmokeManifest,
        capability: SmokeCapability,
    ) -> None:
        object_name = (
            f"{self._prefix}/{manifest.run_id}/{capability.value}.json"
        )
        payload = _canonical_bytes(
            {
                "authorityClass": manifest.authority_class,
                "capability": capability.value,
                "fixtureDigest": manifest.fixture_digests[capability],
                "manifestDigest": manifest.digest,
                "runId": manifest.run_id,
                "schemaVersion": 1,
            }
        )
        replayed = False
        witness_failed = False
        try:
            client = storage.Client(
                project=self._project_id,
                credentials=_impersonated_credentials(self._principal),
            )
            bucket = client.bucket(  # pyright: ignore[reportUnknownMemberType]
                self._bucket_name
            )
            bucket.reload()  # pyright: ignore[reportUnknownMemberType]
            required_retention_seconds = int(
                (manifest.expires_at - manifest.created_at).total_seconds()
            )
            retention_period = (
                bucket.retention_period  # pyright: ignore[reportUnknownMemberType]
            )
            versioning_enabled = cast(
                "bool",
                bucket.versioning_enabled,  # pyright: ignore[reportUnknownMemberType]
            )
            if (
                not versioning_enabled
                or retention_period is None
                or retention_period < required_retention_seconds
            ):
                witness_failed = True
            else:
                blob = bucket.blob(  # pyright: ignore[reportUnknownMemberType]
                    object_name
                )
                blob.upload_from_string(  # pyright: ignore[reportUnknownMemberType]
                    payload,
                    content_type="application/json",
                    if_generation_match=0,
                )
        except PreconditionFailed:
            replayed = True
        except Exception:
            witness_failed = True
        if replayed:
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.REPLAY_REJECTED
            )
        if witness_failed:
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.LEDGER_TAMPERED
            )


class VertexSmokeDispatchError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Vertex smoke dispatch failed: {code}")


class VertexSmokeRunner:
    """Execute an authority-sealed request without accepting provider input."""

    def __init__(
        self,
        *,
        authority: VertexSmokeAuthority,
        ledger: FileSmokeLedger,
        manifest: VertexSmokeManifest,
        principal: str,
        witness_bucket: str,
    ) -> None:
        if not principal.endswith(".gserviceaccount.com"):
            raise ValueError("smoke principal must be a service account")
        self._authority = authority
        self._ledger = ledger
        self._manifest = manifest
        self._token_provider: BoundVertexTokenProvider = (
            ImpersonatedVertexTokenProvider(target_principal=principal)
        )
        self._witness: DispatchWitness = GcsDispatchWitness(
            project_id=manifest.generation_endpoint.project_id,
            bucket_name=witness_bucket,
            principal=principal,
        )
        self._client = httpx.Client(
            timeout=httpx.Timeout(20.0),
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(
                max_connections=1,
                max_keepalive_connections=0,
            ),
        )

    def close(self) -> None:
        self._client.close()

    def run(
        self,
        *,
        capability: SmokeCapability,
        iam: IamEvidence,
        now: datetime,
        is_cancelled: Callable[[], bool] = lambda: False,
    ) -> SanitizedVertexSmokeResult | None:
        if self._token_provider.principal != iam.principal:
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.PRINCIPAL_INVALID
            )
        fixture = CANONICAL_FIXTURES[capability]
        self._authority.validate_ledger(self._ledger)
        self._authority.preflight(
            manifest=self._manifest,
            capability=capability,
            fixture=fixture,
            iam=iam,
            now=now,
        )
        self._witness.claim(
            manifest=self._manifest,
            capability=capability,
        )
        authorization = authorize_and_reserve(
            authority=self._authority,
            ledger=self._ledger,
            manifest=self._manifest,
            capability=capability,
            fixture=fixture,
            iam=iam,
            now=now,
        )
        bound_request = self._bind_request(authorization)
        sanitized_result: SanitizedVertexSmokeResult | None = None

        def dispatch(token: str) -> SmokeDispatchReceipt:
            nonlocal sanitized_result
            receipt, sanitized_result = self._dispatch(
                authorization=authorization,
                request=bound_request,
                token=token,
            )
            return receipt

        receipt = execute_authorized_smoke(
            authorization=authorization,
            ledger=self._ledger,
            manifest=self._manifest,
            is_cancelled=is_cancelled,
            acquire_token=self._token_provider,
            dispatch=dispatch,
        )
        if receipt is None:
            return None
        if sanitized_result is None or (
            sanitized_result.receipt_sha256 != receipt.receipt_sha256
        ):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.RECONCILIATION_INVALID
            )
        return sanitized_result

    def _bind_request(
        self,
        authorization: SmokeAuthorization,
    ) -> BoundVertexRequest:
        self._ledger.verify_authorization(authorization)
        capability = authorization.capability
        fixture = CANONICAL_FIXTURES[capability]
        expected_endpoint = (
            self._manifest.generation_endpoint
            if capability is SmokeCapability.GENERATION
            else self._manifest.embedding_endpoint
        )
        if (
            authorization.run_id != self._manifest.run_id
            or authorization.manifest_digest != self._manifest.digest
            or authorization.fixture_digest != fixture.digest
            or authorization.endpoint != expected_endpoint
            or authorization.reservation_microusd
            != self._manifest.reservation_microusd[capability]
            or authorization.principal != self._token_provider.principal
        ):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.RECONCILIATION_INVALID
            )

        project = quote(expected_endpoint.project_id, safe="")
        location = quote(expected_endpoint.location, safe="")
        model = quote(expected_endpoint.model_revision, safe="")
        host = (
            "aiplatform.googleapis.com"
            if expected_endpoint.location == "global"
            else f"{expected_endpoint.location}-aiplatform.googleapis.com"
        )
        model_path = (
            f"projects/{project}/locations/{location}/"
            f"publishers/google/models/{model}"
        )
        if capability is SmokeCapability.GENERATION:
            question = fixture.payload.get("question")
            evidence = fixture.payload.get("evidence")
            if not isinstance(question, str) or not isinstance(evidence, list):
                raise SmokePreflightFailure(
                    SmokePreflightFailureCode.FIXTURE_TAMPERED
                )
            evidence_items = cast("list[object]", evidence)
            evidence_text = _canonical_bytes(evidence_items).decode("utf-8")
            body_value: object = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": (
                                    "Answer only from this synthetic evidence. "
                                    f"Evidence: {evidence_text}. "
                                    f"Question: {question}"
                                )
                            }
                        ],
                        "role": "user",
                    }
                ],
                "generationConfig": {
                    "candidateCount": 1,
                    "maxOutputTokens": self._manifest.output_token_caps[
                        capability
                    ],
                    "temperature": 0,
                },
            }
            url = (
                f"https://{host}/v1/{model_path}:generateContent"
            )
        else:
            text = fixture.payload.get("text")
            purpose = fixture.payload.get("purpose")
            if not isinstance(text, str) or purpose != "retrieval_query":
                raise SmokePreflightFailure(
                    SmokePreflightFailureCode.FIXTURE_TAMPERED
                )
            body_value = {
                "instances": [
                    {
                        "content": text,
                        "task_type": "RETRIEVAL_QUERY",
                    }
                ],
                "parameters": {
                    "autoTruncate": False,
                    "outputDimensionality": 768,
                },
            }
            url = f"https://{host}/v1/{model_path}:predict"
        body = _canonical_bytes(body_value)
        return BoundVertexRequest(
            capability=capability,
            url=url,
            body=body,
            body_sha256=_digest(body),
        )

    def _dispatch(
        self,
        *,
        authorization: SmokeAuthorization,
        request: BoundVertexRequest,
        token: str,
    ) -> tuple[SmokeDispatchReceipt, SanitizedVertexSmokeResult]:
        if (
            len(token) < 20
            or any(character.isspace() for character in token)
        ):
            raise RuntimeError("access token was not bounded")
        started = monotonic()
        failure_code: str | None = None
        raw_response = bytearray()
        try:
            with self._client.stream(
                "POST",
                request.url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                content=request.body,
            ) as response:
                if response.status_code >= 400:
                    failure_code = f"http-{response.status_code // 100}xx"
                else:
                    for chunk in response.iter_bytes():
                        raw_response.extend(chunk)
                        if len(raw_response) > _MAX_RESPONSE_BYTES:
                            failure_code = "response-too-large"
                            raw_response.clear()
                            break
        except httpx.TimeoutException:
            failure_code = "timeout"
        except httpx.HTTPError:
            failure_code = "transport"
        if failure_code is not None:
            raise VertexSmokeDispatchError(failure_code)
        latency_ms = max(0, int((monotonic() - started) * 1000))
        response_bytes = bytes(raw_response)
        parse_failure = False
        try:
            parsed = cast("object", json.loads(response_bytes))
            input_tokens, output_tokens = self._validate_response(
                capability=request.capability,
                payload=parsed,
            )
        except (json.JSONDecodeError, RuntimeError, TypeError, ValueError):
            parse_failure = True
            input_tokens, output_tokens = 0, 0
        if parse_failure:
            raise VertexSmokeDispatchError("invalid-response")
        incurred_cost = authorization.reservation_microusd
        receipt_payload = {
            "capability": request.capability.value,
            "incurredCostMicrousd": incurred_cost,
            "inputTokens": input_tokens,
            "latencyMs": latency_ms,
            "manifestDigest": authorization.manifest_digest,
            "outputTokens": output_tokens,
            "requestSha256": request.body_sha256,
            "responseSha256": _digest(response_bytes),
            "schemaVersion": 1,
        }
        receipt_sha256 = _digest(receipt_payload)
        receipt = SmokeDispatchReceipt(
            outcome=SmokeOutcome.SUCCEEDED,
            incurred_cost_microusd=incurred_cost,
            receipt_sha256=receipt_sha256,
        )
        result = SanitizedVertexSmokeResult(
            authorization_evidence=authorization.sanitized_evidence(),
            capability=request.capability,
            request_sha256=request.body_sha256,
            response_sha256=cast("str", receipt_payload["responseSha256"]),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            incurred_cost_microusd=incurred_cost,
            receipt_sha256=receipt_sha256,
        )
        return receipt, result

    def _validate_response(
        self,
        *,
        capability: SmokeCapability,
        payload: object,
    ) -> tuple[int, int]:
        if not isinstance(payload, dict):
            raise RuntimeError("Vertex smoke response must be an object")
        value = cast("dict[str, object]", payload)
        if capability is SmokeCapability.GENERATION:
            usage = value.get("usageMetadata")
            candidates = value.get("candidates")
            model_version = value.get("modelVersion")
            if (
                model_version
                != self._manifest.generation_endpoint.model_revision
                or not isinstance(usage, dict)
                or not isinstance(candidates, list)
            ):
                raise RuntimeError("Vertex generation response is incomplete")
            usage_map = cast("dict[str, object]", usage)
            candidate_items = cast("list[object]", candidates)
            input_tokens = _bounded_token_count(
                usage_map.get("promptTokenCount"),
                ceiling=self._manifest.input_token_caps[capability],
            )
            output_tokens = _bounded_token_count(
                usage_map.get("candidatesTokenCount"),
                ceiling=self._manifest.output_token_caps[capability],
            )
            if len(candidate_items) != 1:
                raise RuntimeError("Vertex generation response is ambiguous")
            candidate = candidate_items[0]
            if not isinstance(candidate, dict) or cast(
                "dict[str, object]", candidate
            ).get("finishReason") != "STOP":
                raise RuntimeError("Vertex generation did not finish safely")
            return input_tokens, output_tokens

        predictions = value.get("predictions")
        if not isinstance(predictions, list):
            raise RuntimeError("Vertex embedding response is incomplete")
        prediction_items = cast("list[object]", predictions)
        if len(prediction_items) != 1:
            raise RuntimeError("Vertex embedding response is incomplete")
        prediction = prediction_items[0]
        if not isinstance(prediction, dict):
            raise RuntimeError("Vertex embedding prediction is invalid")
        prediction_map = cast("dict[str, object]", prediction)
        embeddings = prediction_map.get("embeddings")
        if not isinstance(embeddings, dict):
            raise RuntimeError("Vertex embedding payload is invalid")
        embedding_map = cast("dict[str, object]", embeddings)
        values = embedding_map.get("values")
        statistics = embedding_map.get("statistics")
        value_items = cast("list[object]", values) if isinstance(values, list) else []
        statistics_map = (
            cast("dict[str, object]", statistics)
            if isinstance(statistics, dict)
            else {}
        )
        if (
            len(value_items) != 768
            or not statistics_map
            or statistics_map.get("truncated") is not False
            or any(
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not math.isfinite(float(item))
                for item in value_items
            )
        ):
            raise RuntimeError("Vertex embedding dimensions or truncation mismatch")
        input_tokens = _bounded_token_count(
            statistics_map.get("token_count"),
            ceiling=self._manifest.input_token_caps[capability],
        )
        return input_tokens, 0


def _bounded_token_count(value: object, *, ceiling: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        or value > ceiling
    ):
        raise RuntimeError("provider token usage exceeded the sealed cap")
    return value
