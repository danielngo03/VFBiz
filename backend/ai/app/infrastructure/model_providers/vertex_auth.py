"""Keyless Vertex authentication through application default credentials."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

import google.auth
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request

_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

AccessTokenProvider = Callable[[], Awaitable[str]]


class VertexAuthenticationError(RuntimeError):
    """ADC/workload-identity authentication was unavailable or malformed."""


class ApplicationDefaultVertexTokenProvider:
    """Refresh a short-lived ADC token without accepting user-managed keys.

    The provider deliberately performs no work until its callable is awaited.
    Local development therefore remains fail-closed unless ADC is explicitly
    available, while Cloud Run can use its attached workload identity.
    """

    def __init__(self, *, scopes: tuple[str, ...] = (_CLOUD_PLATFORM_SCOPE,)) -> None:
        if not scopes or any(not scope.strip() for scope in scopes):
            raise ValueError("Vertex ADC scopes must be non-empty")
        self._scopes = scopes
        self._credentials: Credentials | None = None
        self._lock = asyncio.Lock()

    async def __call__(self) -> str:
        async with self._lock:
            return await asyncio.to_thread(self._refresh)

    def _refresh(self) -> str:
        try:
            credentials = self._credentials
            if credentials is None:
                credentials, _ = cast(
                    tuple[Credentials, str | None],
                    google.auth.default(  # pyright: ignore[reportUnknownMemberType]
                        scopes=list(self._scopes)
                    ),
                )
                self._credentials = credentials
            credentials.refresh(  # pyright: ignore[reportUnknownMemberType]
                Request()
            )
            token = cast("str | None", credentials.token)
        except Exception as error:  # provider SDK errors are intentionally opaque
            raise VertexAuthenticationError("Vertex ADC refresh failed") from error
        if (
            not isinstance(token, str)
            or not token.strip()
            or len(token) > 8192
            or any(character.isspace() for character in token)
        ):
            raise VertexAuthenticationError("Vertex ADC returned an invalid token")
        return token
