from typing import Annotated, Literal, cast

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from app.platform.config import Settings

AssistantProfile = Literal["public_customer", "authenticated_customer", "employee"]


class GatewayContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    subject: str
    issuer: str
    audience: tuple[str, ...]
    scopes: frozenset[str]
    assistant_profile: AssistantProfile


_bearer = HTTPBearer(auto_error=False)


async def require_gateway_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> GatewayContext:
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SECURITY_CONFIGURATION_UNAVAILABLE",
                "message": "Gateway verification is not configured.",
            },
        )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "GATEWAY_ASSERTION_REQUIRED",
                "message": "A signed gateway assertion is required.",
            },
        )
    if credentials.scheme != "Bearer" or credentials.credentials.count(".") != 2:
        raise invalid_assertion()

    try:
        jwks_client = PyJWKClient(settings.gateway_jwks_url, cache_keys=True, lifespan=300)
        signing_key = await run_in_threadpool(
            jwks_client.get_signing_key_from_jwt,
            credentials.credentials,
        )
        claims = cast(
            dict[str, object],
            jwt.decode(
                credentials.credentials,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=settings.gateway_audience,
                issuer=settings.gateway_issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "profile"]},
            ),
        )
        profile = claims["profile"]
        if not isinstance(profile, str) or profile not in {
            "public_customer",
            "authenticated_customer",
            "employee",
        }:
            raise ValueError("unapproved assistant profile")
        audience_claim = claims["aud"]
        audience = (
            tuple(str(item) for item in cast(list[object], audience_claim))
            if isinstance(audience_claim, list)
            else (str(audience_claim),)
        )
        context = GatewayContext(
            subject=str(claims["sub"]),
            issuer=str(claims["iss"]),
            audience=audience,
            scopes=frozenset(str(claims.get("scope", "")).split()),
            assistant_profile=cast(AssistantProfile, profile),
        )
        request.state.gateway_context = context
        return context
    except Exception as error:
        raise invalid_assertion() from error


def invalid_assertion() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "INVALID_GATEWAY_ASSERTION",
            "message": "The gateway assertion could not be verified.",
        },
    )
