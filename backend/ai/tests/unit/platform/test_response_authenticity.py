import base64
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.requests import Request
from starlette.responses import StreamingResponse

from app.bootstrap.application import secure_response_middleware
from app.platform.security.response_authenticity import (
    InternalResponseSigner,
    canonical_response_signature_input,
)


def test_signs_body_and_request_binding_with_ed25519() -> None:
    private_key = Ed25519PrivateKey.generate()
    signer = InternalResponseSigner(
        key_id="ai-response-current",
        private_key=private_key,
        ttl_seconds=30,
    )

    headers = signer.sign(
        body=b'{"outcome":"refused"}',
        request_id="request-1",
        correlation_id="correlation-1",
        now=datetime(2026, 7, 27, 12, 0, tzinfo=UTC),
    )

    signature = base64.urlsafe_b64decode(headers.signature + "==")
    private_key.public_key().verify(
        signature,
        canonical_response_signature_input(
            key_id=headers.key_id,
            issued_at=headers.issued_at,
            expires_at=headers.expires_at,
            request_id="request-1",
            correlation_id="correlation-1",
            body_sha256=headers.body_sha256,
        ),
    )


def test_signature_changes_when_body_changes() -> None:
    signer = InternalResponseSigner(
        key_id="ai-response-current",
        private_key=Ed25519PrivateKey.generate(),
        ttl_seconds=30,
    )
    now = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)

    first = signer.sign(
        body=b"first", request_id="request-1", correlation_id="correlation-1", now=now
    )
    second = signer.sign(
        body=b"second", request_id="request-1", correlation_id="correlation-1", now=now
    )

    assert first.body_sha256 != second.body_sha256
    assert first.signature != second.signature


@pytest.mark.asyncio
async def test_private_turn_middleware_attaches_detached_signature_headers() -> None:
    signer = InternalResponseSigner(
        key_id="ai-response-current",
        private_key=Ed25519PrivateKey.generate(),
        ttl_seconds=30,
    )
    application = SimpleNamespace(
        state=SimpleNamespace(internal_response_signer=signer)
    )
    request = Request(
        {
            "app": application,
            "headers": [
                (b"x-correlation-id", b"423e4567-e89b-42d3-a456-426614174000"),
                (b"x-vfbiz-ai-request-id", b"323e4567-e89b-42d3-a456-426614174000"),
            ],
            "method": "POST",
            "path": "/internal/v1/conversation/turns",
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "type": "http",
        }
    )
    request.state.ai_response_request_id = "323e4567-e89b-42d3-a456-426614174000"

    async def call_next(_request: Request) -> StreamingResponse:
        return StreamingResponse(iter([b'{"outcome":"refused"}']), status_code=200)

    response = await secure_response_middleware(request, call_next)

    assert response.headers["x-vfbiz-ai-response-key-id"] == "ai-response-current"
    assert response.headers["x-vfbiz-ai-response-body-sha256"]
    assert response.headers["x-vfbiz-ai-response-signature"]
