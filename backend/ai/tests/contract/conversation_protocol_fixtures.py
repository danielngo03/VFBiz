import json
import time
from collections.abc import Mapping
from typing import cast
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient

from app.bootstrap.conversation_graph import ConversationRuntimeDependencies
from app.main import create_application
from app.platform.cancellation import ExecutionCancellationPort
from app.platform.config import Settings
from app.platform.security.execution_assertion import (
    AllowedPublicKeys,
    ExecutionAssertionVerifier,
    InMemoryAssertionReplayStore,
    SigningKeyResolver,
    canonical_request_hash,
)

PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
PUBLIC_KEY = PRIVATE_KEY.public_key()


class StaticSigningKeyResolver:
    async def resolve(self, _token: str) -> AllowedPublicKeys:
        return PUBLIC_KEY


def application_client(
    cancellation_port: ExecutionCancellationPort | None = None,
    key_resolver: SigningKeyResolver | None = None,
    conversation_dependencies: ConversationRuntimeDependencies | None = None,
) -> AsyncClient:
    application = create_application(
        Settings(environment="test", allowed_hosts=("testserver",), expose_docs=False)
    )
    application.state.execution_assertion_verifier = ExecutionAssertionVerifier(
        key_resolver=key_resolver or StaticSigningKeyResolver(),
        replay_store=InMemoryAssertionReplayStore(),
    )
    if cancellation_port is not None:
        application.state.execution_cancellation_port = cancellation_port
    if conversation_dependencies is not None:
        application.state.conversation_dependencies = conversation_dependencies
    return AsyncClient(
        transport=ASGITransport(app=application, raise_app_exceptions=False),
        base_url="http://testserver",
    )


def turn_body(*, conversation_version: int = 1, fencing_token: int = 7) -> dict[str, object]:
    return {
        "requestId": str(uuid4()),
        "correlationId": str(uuid4()),
        "sessionId": str(uuid4()),
        "turnId": str(uuid4()),
        "conversationVersion": conversation_version,
        "fencingToken": fencing_token,
        "locale": "vi",
        "message": "Thông tin bảo hành nào đã được xác minh?",
        "confirmedEntities": [
            {
                "kind": "vehicle_model",
                "reference": "vf-8",
                "sourceRevision": "a" * 64,
                "classification": "non_sensitive",
                "authority": "vehicle-catalog",
                "authorityDigest": "b" * 64,
                "confirmedAt": "2026-07-27T00:00:00Z",
                "expiresAt": "2026-07-28T00:00:00Z",
            }
        ],
    }


def assertion_claims(
    *,
    body: Mapping[str, object],
    path: str = "/internal/v1/conversation/turns",
    action: str = "turn.execute",
    audience: str = "vfbiz-ai",
    assistant_profile: str = "public_customer",
    authorization: Mapping[str, object] | None = None,
    conversation_version: int | None = None,
    fencing_token: int | None = None,
    issued_at: int | None = None,
    expires_at: int | None = None,
    max_model_tokens: int = 1_000,
    deadline_at: str = "2099-07-25T12:00:00Z",
) -> dict[str, object]:
    now = int(time.time()) if issued_at is None else issued_at
    canonical = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return {
        "iss": "vfbiz-api",
        "aud": audience,
        "iat": now,
        "nbf": now,
        "exp": now + 60 if expires_at is None else expires_at,
        "jti": str(uuid4()),
        "action": action,
        "requestHash": canonical_request_hash(method="POST", path=path, body=canonical),
        "requestId": body["requestId"],
        "correlationId": body["correlationId"],
        "sessionId": body["sessionId"],
        "turnId": body["turnId"],
        "conversationVersion": (
            cast(int, body["conversationVersion"])
            if conversation_version is None
            else conversation_version
        ),
        "fencingToken": (
            cast(int, body["fencingToken"]) if fencing_token is None else fencing_token
        ),
        "assistantProfile": assistant_profile,
        "authorization": authorization
        or {
            "kind": "public_capability",
            "capabilityHash": "a" * 64,
            "allowedTools": ["search_public_knowledge"],
        },
        "locale": "vi",
        "budget": {
            "maxModelTokens": max_model_tokens,
            "maxCostMicros": 10_000,
            "deadlineAt": deadline_at,
        },
        "policyRevision": "policy-r1",
        "graphRevision": "graph-r1",
        "knowledgeRevision": "knowledge-active-r1",
        "activationId": "00000000-0000-4000-8000-000000000010",
        "manifestSha256": "c" * 64,
    }


def sign(claims: Mapping[str, object]) -> str:
    return jwt.encode(
        dict(claims),
        PRIVATE_KEY,
        algorithm="ES256",
        headers={"kid": "test-key", "typ": "vfbiz-ai+jwt"},
    )
