import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_CONTEXT = "VFBIZ-AI-RESPONSE-V1"


@dataclass(frozen=True, slots=True)
class SignedResponseHeaders:
    key_id: str
    issued_at: str
    expires_at: str
    body_sha256: str
    signature: str

    def as_http_headers(self) -> dict[str, str]:
        return {
            "x-vfbiz-ai-response-key-id": self.key_id,
            "x-vfbiz-ai-response-issued-at": self.issued_at,
            "x-vfbiz-ai-response-expires-at": self.expires_at,
            "x-vfbiz-ai-response-body-sha256": self.body_sha256,
            "x-vfbiz-ai-response-signature": self.signature,
        }


class InternalResponseSigner:
    def __init__(
        self,
        *,
        key_id: str,
        private_key: Ed25519PrivateKey,
        ttl_seconds: int,
    ) -> None:
        self._key_id = key_id
        self._private_key = private_key
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_pem_file(
        cls,
        *,
        key_id: str,
        private_key_file: Path,
        ttl_seconds: int,
    ) -> "InternalResponseSigner":
        key = serialization.load_pem_private_key(private_key_file.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("internal AI response signing key must be Ed25519")
        return cls(key_id=key_id, private_key=key, ttl_seconds=ttl_seconds)

    def sign(
        self,
        *,
        body: bytes,
        request_id: str,
        correlation_id: str,
        now: datetime | None = None,
    ) -> SignedResponseHeaders:
        issued = (now or datetime.now(UTC)).astimezone(UTC)
        expires = issued + timedelta(seconds=self._ttl_seconds)
        issued_text = _timestamp(issued)
        expires_text = _timestamp(expires)
        body_sha256 = hashlib.sha256(body).hexdigest()
        signing_input = canonical_response_signature_input(
            key_id=self._key_id,
            issued_at=issued_text,
            expires_at=expires_text,
            request_id=request_id,
            correlation_id=correlation_id,
            body_sha256=body_sha256,
        )
        signature = base64.urlsafe_b64encode(self._private_key.sign(signing_input)).rstrip(b"=")
        return SignedResponseHeaders(
            key_id=self._key_id,
            issued_at=issued_text,
            expires_at=expires_text,
            body_sha256=body_sha256,
            signature=signature.decode("ascii"),
        )


def canonical_response_signature_input(
    *,
    key_id: str,
    issued_at: str,
    expires_at: str,
    request_id: str,
    correlation_id: str,
    body_sha256: str,
) -> bytes:
    return (
        f"{_CONTEXT}\n{key_id}\n{issued_at}\n{expires_at}\n"
        f"{request_id}\n{correlation_id}\n{body_sha256}"
    ).encode()


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
