from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, cast

_PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_SECRET_ID = re.compile(r"^[A-Za-z0-9_-]{1,255}$")


class _SecretPayload(Protocol):
    data: bytes


class _SecretResponse(Protocol):
    payload: _SecretPayload


class SecretManagerClient(Protocol):
    def access_secret_version(
        self,
        *,
        request: dict[str, str],
    ) -> _SecretResponse: ...


@dataclass(frozen=True, slots=True)
class LangfuseSecretReferences:
    """Non-secret coordinates used to resolve Langfuse credentials at runtime."""

    project_id: str
    public_key_secret_id: str
    secret_key_secret_id: str
    version: str

    def __post_init__(self) -> None:
        if not _PROJECT_ID.fullmatch(self.project_id):
            raise ValueError("Google Cloud project ID is malformed")
        for secret_id in (
            self.public_key_secret_id,
            self.secret_key_secret_id,
        ):
            if not _SECRET_ID.fullmatch(secret_id):
                raise ValueError("Secret Manager secret ID is malformed")
        if not self.version.isdecimal() or int(self.version) < 1:
            raise ValueError("Secret Manager version must be a positive number")


def load_langfuse_credentials(
    references: LangfuseSecretReferences,
    *,
    client: SecretManagerClient | None = None,
) -> tuple[str, str]:
    """Read both credentials without persisting either value to a local file."""

    if client is None:
        from google.cloud import secretmanager

        resolved_client = cast(
            SecretManagerClient,
            secretmanager.SecretManagerServiceClient(),
        )
    else:
        resolved_client = client
    public_key = _read_secret(
        resolved_client,
        project_id=references.project_id,
        secret_id=references.public_key_secret_id,
        version=references.version,
    )
    secret_key = _read_secret(
        resolved_client,
        project_id=references.project_id,
        secret_id=references.secret_key_secret_id,
        version=references.version,
    )
    if not public_key.startswith("pk-lf-") or not secret_key.startswith("sk-lf-"):
        raise RuntimeError("Secret Manager returned malformed Langfuse credentials")
    return public_key, secret_key


def _read_secret(
    client: SecretManagerClient,
    *,
    project_id: str,
    secret_id: str,
    version: str,
) -> str:
    response = client.access_secret_version(
        request={
            "name": (
                f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
            )
        }
    )
    value = response.payload.data.decode("utf-8").strip()
    if not value:
        raise RuntimeError("Secret Manager returned an empty credential")
    return value
