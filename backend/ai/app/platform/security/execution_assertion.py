import asyncio
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Literal, Protocol, cast
from uuid import UUID

import jwt
from fastapi import Header, HTTPException, Request, status
from jwt import PyJWK, PyJWKClient
from jwt.algorithms import AllowedPublicKeys
from jwt.exceptions import PyJWKClientConnectionError
from pydantic import BaseModel, ConfigDict, Field, model_validator
from redis.asyncio import Redis
from starlette.concurrency import run_in_threadpool

from app.platform.config import Settings

ExecutionAction = Literal["turn.execute", "turn.cancel"]
AssistantProfile = Literal["public_customer", "authenticated_customer"]
PublicReadOnlyTool = Literal["search_public_knowledge"]
ReadOnlyTool = Literal[
    "search_public_knowledge",
    "get_vehicle_profile",
    "get_customer_garage",
    "list_charging_stations",
]

_ALLOWED_ALGORITHMS = frozenset({"EdDSA", "ES256"})
_ASSERTION_TYPE = "vfbiz-ai+jwt"
_MAX_ASSERTION_TTL_SECONDS = 60
_CLOCK_SKEW_SECONDS = 5
_MAX_ASSERTION_HEADER_BYTES = 8_192
_MAX_TURN_REQUEST_BYTES = 65_536
_MAX_SAFE_INTEGER = 9_007_199_254_740_991

Scope = Annotated[str, Field(min_length=1, max_length=160)]


class TurnBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_model_tokens: int = Field(alias="maxModelTokens", strict=True, ge=1, le=32_000)
    max_cost_micros: int = Field(alias="maxCostMicros", strict=True, ge=1, le=10_000_000)
    deadline_at: datetime = Field(alias="deadlineAt")

    @model_validator(mode="after")
    def validate_deadline(self) -> "TurnBudget":
        if self.deadline_at.tzinfo is None:
            raise ValueError("deadlineAt must include a timezone")
        if self.deadline_at <= datetime.now(UTC):
            raise ValueError("deadlineAt must be in the future")
        return self


class PublicCapabilityAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["public_capability"]
    capability_hash: str = Field(alias="capabilityHash", pattern=r"^[a-f0-9]{64}$")
    allowed_tools: tuple[PublicReadOnlyTool, ...] = Field(alias="allowedTools", max_length=1)


class AuthenticatedCustomerAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["authenticated_customer"]
    subject_ref: str = Field(alias="subjectRef", pattern=r"^[a-f0-9]{64}$")
    scopes: tuple[Scope, ...] = Field(max_length=32)
    allowed_tools: tuple[ReadOnlyTool, ...] = Field(alias="allowedTools", max_length=5)


class AIExecutionAssertionClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    issuer: Literal["vfbiz-api"] = Field(alias="iss")
    audience: Literal["vfbiz-ai"] = Field(alias="aud")
    issued_at: int = Field(alias="iat", strict=True, ge=1, le=_MAX_SAFE_INTEGER)
    not_before: int = Field(alias="nbf", strict=True, ge=1, le=_MAX_SAFE_INTEGER)
    expires_at: int = Field(alias="exp", strict=True, ge=1, le=_MAX_SAFE_INTEGER)
    jti: UUID
    action: ExecutionAction
    request_hash: str = Field(alias="requestHash", pattern=r"^[a-f0-9]{64}$")
    request_id: UUID = Field(alias="requestId")
    correlation_id: UUID = Field(alias="correlationId")
    session_id: UUID = Field(alias="sessionId")
    turn_id: UUID = Field(alias="turnId")
    conversation_version: int = Field(
        alias="conversationVersion", strict=True, ge=1, le=_MAX_SAFE_INTEGER
    )
    fencing_token: int = Field(alias="fencingToken", strict=True, ge=1, le=_MAX_SAFE_INTEGER)
    assistant_profile: AssistantProfile = Field(alias="assistantProfile")
    authorization_context_digest: str = Field(
        alias="authorizationContextDigest", pattern=r"^[a-f0-9]{64}$"
    )
    authorization: PublicCapabilityAuthorization | AuthenticatedCustomerAuthorization = Field(
        discriminator="kind"
    )
    locale: Literal["vi", "en"]
    budget: TurnBudget
    policy_revision: str = Field(alias="policyRevision", min_length=1, max_length=160)
    graph_revision: str = Field(alias="graphRevision", min_length=1, max_length=160)
    knowledge_revision: str = Field(alias="knowledgeRevision", min_length=1, max_length=160)
    activation_id: UUID = Field(alias="activationId")
    manifest_sha256: str = Field(alias="manifestSha256", pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_trust_invariants(self) -> "AIExecutionAssertionClaims":
        if self.expires_at - self.issued_at > _MAX_ASSERTION_TTL_SECONDS:
            raise ValueError("assertion TTL exceeds policy")
        if self.not_before > self.expires_at:
            raise ValueError("nbf must not be after exp")
        if (
            self.assistant_profile == "public_customer"
            and self.authorization.kind != "public_capability"
        ):
            raise ValueError("public profile requires public capability")
        if (
            self.assistant_profile == "authenticated_customer"
            and self.authorization.kind != "authenticated_customer"
        ):
            raise ValueError("authenticated profile requires customer authorization")
        if len(set(self.authorization.allowed_tools)) != len(self.authorization.allowed_tools):
            raise ValueError("allowedTools must not contain duplicates")
        if isinstance(self.authorization, AuthenticatedCustomerAuthorization) and len(
            set(self.authorization.scopes)
        ) != len(self.authorization.scopes):
            raise ValueError("scopes must not contain duplicates")
        return self


class ExecutionContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    claims: AIExecutionAssertionClaims


class SigningKeyResolver(Protocol):
    async def resolve(self, token: str) -> AllowedPublicKeys | PyJWK | str | bytes: ...


class AssertionReplayStore(Protocol):
    async def consume(self, jti: str, expires_at: int) -> bool: ...


class JwksSigningKeyResolver:
    def __init__(self, jwks_url: str) -> None:
        self._client = PyJWKClient(
            jwks_url,
            cache_keys=True,
            lifespan=300,
            timeout=2,
        )

    async def resolve(self, token: str) -> AllowedPublicKeys | PyJWK | str | bytes:
        key = await run_in_threadpool(self._client.get_signing_key_from_jwt, token)
        return key.key


class InMemoryAssertionReplayStore:
    def __init__(self) -> None:
        self._entries: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def consume(self, jti: str, expires_at: int) -> bool:
        now = int(time.time())
        async with self._lock:
            self._entries = {key: expiry for key, expiry in self._entries.items() if expiry > now}
            if jti in self._entries:
                return False
            self._entries[jti] = expires_at
            return True


class RedisAssertionReplayStore:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def consume(self, jti: str, expires_at: int) -> bool:
        ttl = max(1, expires_at - int(time.time()) + _CLOCK_SKEW_SECONDS)
        key = f"vfbiz:ai:assertion:jti:{jti}"
        accepted = await self._client.set(key, "1", ex=ttl, nx=True)
        return bool(accepted)


class ExecutionAssertionVerifier:
    def __init__(
        self,
        *,
        key_resolver: SigningKeyResolver,
        replay_store: AssertionReplayStore,
    ) -> None:
        self._key_resolver = key_resolver
        self._replay_store = replay_store

    async def verify(
        self,
        *,
        token: str,
        method: str,
        path: str,
        body: bytes,
        expected_action: ExecutionAction,
    ) -> ExecutionContext:
        try:
            header = cast(Mapping[str, object], jwt.get_unverified_header(token))
            algorithm = header.get("alg")
            if algorithm not in _ALLOWED_ALGORITHMS:
                raise ValueError("unapproved signing algorithm")
            if header.get("typ") != _ASSERTION_TYPE:
                raise ValueError("invalid assertion type")
            if not isinstance(header.get("kid"), str) or not header["kid"]:
                raise ValueError("approved key id is required")
        except Exception as error:
            raise assertion_error(
                status.HTTP_401_UNAUTHORIZED,
                "ASSERTION_INVALID",
                "The AI execution assertion could not be verified.",
            ) from error
        try:
            signing_key = await self._key_resolver.resolve(token)
        except (PyJWKClientConnectionError, TimeoutError, OSError) as error:
            raise assertion_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "ASSERTION_INVALID",
                "The approved assertion key service is unavailable.",
            ) from error
        except Exception as error:
            raise assertion_error(
                status.HTTP_401_UNAUTHORIZED,
                "ASSERTION_INVALID",
                "The assertion key id is not approved.",
            ) from error
        try:
            decoded = cast(
                dict[str, object],
                jwt.decode(
                    token,
                    signing_key,
                    algorithms=[cast(str, algorithm)],
                    audience="vfbiz-ai",
                    issuer="vfbiz-api",
                    leeway=_CLOCK_SKEW_SECONDS,
                    options={
                        "require": [
                            "iss",
                            "aud",
                            "iat",
                            "nbf",
                            "exp",
                            "jti",
                            "action",
                            "requestHash",
                        ]
                    },
                ),
            )
            claims = AIExecutionAssertionClaims.model_validate(decoded)
        except Exception as error:
            raise assertion_error(
                status.HTTP_401_UNAUTHORIZED,
                "ASSERTION_INVALID",
                "The AI execution assertion could not be verified.",
            ) from error

        expected_hash = canonical_request_hash(method=method, path=path, body=body)
        if claims.action != expected_action or not hmac.compare_digest(
            claims.request_hash,
            expected_hash,
        ):
            raise assertion_error(
                status.HTTP_403_FORBIDDEN,
                "ASSERTION_MISMATCH",
                "The assertion is not valid for this operation.",
            )

        try:
            accepted = await self._replay_store.consume(str(claims.jti), claims.expires_at)
        except Exception as error:
            raise assertion_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "ASSERTION_INVALID",
                "Assertion replay protection is unavailable.",
            ) from error
        if not accepted:
            raise assertion_error(
                status.HTTP_401_UNAUTHORIZED,
                "ASSERTION_REPLAYED",
                "The AI execution assertion has already been consumed.",
            )
        return ExecutionContext(claims=claims)


async def require_execution_context(
    request: Request,
    assertion: Annotated[str | None, Header(alias="X-VFBiz-AI-Assertion")] = None,
) -> ExecutionContext:
    if (
        assertion is None
        or assertion.count(".") != 2
        or not 64 <= len(assertion.encode()) <= _MAX_ASSERTION_HEADER_BYTES
    ):
        raise assertion_error(
            status.HTTP_401_UNAUTHORIZED,
            "ASSERTION_INVALID",
            "A compact signed AI execution assertion is required.",
        )
    expected_action = action_for_request(request.method, request.url.path)
    if request.url.query:
        raise assertion_error(
            status.HTTP_403_FORBIDDEN,
            "ASSERTION_MISMATCH",
            "Query parameters are forbidden on signed AI operations.",
        )
    verifier = execution_assertion_verifier(request)
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_TURN_REQUEST_BYTES:
                raise request_too_large()
        except ValueError as error:
            raise assertion_error(
                status.HTTP_400_BAD_REQUEST,
                "ASSERTION_MISMATCH",
                "Content-Length must be a valid integer.",
            ) from error
    body = await request.body()
    if len(body) > _MAX_TURN_REQUEST_BYTES:
        raise request_too_large()
    context = await verifier.verify(
        token=assertion,
        method=request.method,
        path=request.url.path,
        body=body,
        expected_action=expected_action,
    )
    request.state.execution_context = context
    return context


def action_for_request(method: str, path: str) -> ExecutionAction:
    if method.upper() != "POST":
        raise assertion_error(
            status.HTTP_403_FORBIDDEN,
            "ASSERTION_MISMATCH",
            "The assertion action does not support this HTTP method.",
        )
    if path == "/internal/v1/conversation/turns":
        return "turn.execute"
    if path.startswith("/internal/v1/conversation/turns/") and path.endswith("/cancel"):
        return "turn.cancel"
    raise assertion_error(
        status.HTTP_403_FORBIDDEN,
        "ASSERTION_MISMATCH",
        "The assertion is not valid for this path.",
    )


def canonical_request_hash(*, method: str, path: str, body: bytes) -> str:
    try:
        parsed = json.loads(
            body or b"{}",
            object_pairs_hook=_unique_object,
            parse_int=_parse_safe_integer,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except (ValueError, UnicodeDecodeError) as error:
        raise assertion_error(
            status.HTTP_400_BAD_REQUEST,
            "ASSERTION_MISMATCH",
            "The request body is not canonical JSON.",
        ) from error
    canonical_body = json.dumps(
        parsed,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    material = method.upper().encode() + b"\n" + path.encode() + b"\n" + canonical_body
    return hashlib.sha256(material).hexdigest()


def build_execution_assertion_verifier(
    settings: Settings,
) -> tuple[ExecutionAssertionVerifier | None, Redis | None]:
    """Construct the verifier once for the process lifespan.

    Returns `(None, None)` when replay protection cannot be configured (no
    Redis URL outside development/test) so the caller can fail closed at
    request time via `execution_assertion_verifier` instead of raising here
    and aborting an otherwise-healthy process (other routes, e.g. health
    checks, must still start).
    """
    redis_client: Redis | None = None
    replay_store: AssertionReplayStore | None = None
    if settings.redis_url is not None:
        redis_client = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            str(settings.redis_url),
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            retry_on_timeout=False,
        )
        replay_store = RedisAssertionReplayStore(redis_client)
    elif settings.environment in {"development", "test"}:
        replay_store = InMemoryAssertionReplayStore()
    if replay_store is None:
        return None, None
    verifier = ExecutionAssertionVerifier(
        key_resolver=JwksSigningKeyResolver(settings.gateway_jwks_url),
        replay_store=replay_store,
    )
    return verifier, redis_client


def execution_assertion_verifier(request: Request) -> ExecutionAssertionVerifier:
    configured = getattr(request.app.state, "execution_assertion_verifier", None)
    if isinstance(configured, ExecutionAssertionVerifier):
        return configured
    raise assertion_error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "ASSERTION_INVALID",
        "Assertion verification is not configured.",
    )


def assert_request_matches_claims(
    *,
    context: ExecutionContext,
    request_id: UUID,
    correlation_id: UUID,
    session_id: UUID,
    turn_id: UUID,
    conversation_version: int,
    fencing_token: int,
    locale: Literal["vi", "en"] | None = None,
    authorization_context_digest: str | None = None,
) -> None:
    claims = context.claims
    received = (
        request_id,
        correlation_id,
        session_id,
        turn_id,
        conversation_version,
        fencing_token,
    )
    expected = (
        claims.request_id,
        claims.correlation_id,
        claims.session_id,
        claims.turn_id,
        claims.conversation_version,
        claims.fencing_token,
    )
    if received != expected:
        raise assertion_error(
            status.HTTP_403_FORBIDDEN,
            "ASSERTION_MISMATCH",
            "Request identity, version or fencing fields do not match the assertion.",
        )
    if locale is not None and locale != claims.locale:
        raise assertion_error(
            status.HTTP_403_FORBIDDEN,
            "ASSERTION_MISMATCH",
            "Request locale does not match the signed assertion.",
        )
    if authorization_context_digest is not None and not hmac.compare_digest(
        authorization_context_digest,
        claims.authorization_context_digest,
    ):
        raise assertion_error(
            status.HTTP_403_FORBIDDEN,
            "ASSERTION_MISMATCH",
            "Authorization context does not match the signed assertion.",
        )


def assertion_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def request_too_large() -> HTTPException:
    return assertion_error(
        status.HTTP_413_CONTENT_TOO_LARGE,
        "REQUEST_TOO_LARGE",
        "The AI turn request exceeds the internal size limit.",
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_safe_integer(value: str) -> int:
    parsed = int(value)
    if abs(parsed) > _MAX_SAFE_INTEGER:
        raise ValueError("JSON integer exceeds the cross-runtime safe range")
    return parsed


def _reject_float(_value: str) -> object:
    raise ValueError("floating-point JSON numbers are forbidden")
