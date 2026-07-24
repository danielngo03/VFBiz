from collections.abc import Awaitable, Callable, Mapping
from typing import cast
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from app.api.internal_v1 import internal_v1_router
from app.platform.config import Settings
from app.platform.health import public_health_router


def create_application(settings: Settings | None = None) -> FastAPI:
    configuration = settings or Settings()
    application = FastAPI(
        title="VFBiz AI Platform",
        version="0.1.0",
        description="Private AI capabilities for the VFBiz API Platform.",
        docs_url="/docs" if configuration.expose_docs else None,
        redoc_url="/redoc" if configuration.expose_docs else None,
        openapi_url="/openapi.json" if configuration.expose_docs else None,
    )
    application.state.settings = configuration
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(configuration.allowed_hosts),
    )
    application.middleware("http")(secure_response_middleware)
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(Exception, unexpected_exception_handler)
    application.include_router(public_health_router)
    application.include_router(internal_v1_router)
    return application


async def secure_response_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    candidate = request.headers.get("x-correlation-id", "")
    try:
        correlation_id = str(UUID(candidate, version=4))
    except ValueError:
        correlation_id = str(uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["cache-control"] = "no-store"
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["referrer-policy"] = "no-referrer"
    response.headers["x-correlation-id"] = correlation_id
    return response


async def http_exception_handler(request: Request, exception: Exception) -> JSONResponse:
    http_exception = cast(HTTPException, exception)
    detail: Mapping[str, object]
    if isinstance(http_exception.detail, dict):
        detail = cast(Mapping[str, object], http_exception.detail)
    else:
        detail = {}
    code = str(detail.get("code", "REQUEST_REJECTED"))
    message = str(detail.get("message", "The request was rejected."))
    return problem_response(request, http_exception.status_code, code, message)


async def validation_exception_handler(request: Request, exception: Exception) -> JSONResponse:
    _ = cast(RequestValidationError, exception)
    return problem_response(request, 422, "VALIDATION_FAILED", "Request validation failed.")


async def unexpected_exception_handler(request: Request, _exception: Exception) -> JSONResponse:
    return problem_response(
        request,
        500,
        "INTERNAL_ERROR",
        "The service could not complete the request.",
    )


def problem_response(request: Request, status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://vfbiz.vn/problems/{code.lower().replace('_', '-')}",
            "title": "Request Failed",
            "status": status_code,
            "detail": detail,
            "instance": request.url.path,
            "code": code,
            "correlationId": getattr(request.state, "correlation_id", str(uuid4())),
        },
    )
