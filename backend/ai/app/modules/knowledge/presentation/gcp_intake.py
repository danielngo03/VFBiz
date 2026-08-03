from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.modules.knowledge.application.cloud_ingestion_worker import (
    CloudIngestionDispatchResult,
)
from app.modules.knowledge.application.ingestion_ports import (
    PermanentIngestionFailure,
    TransientIngestionFailure,
)
from app.modules.knowledge.infrastructure.gcp_intake_runtime import (
    GcpIntakeRuntime,
    build_gcp_intake_runtime,
)
from app.platform.config import Settings

_MAX_ENVELOPE_BYTES = 32_768


def create_gcp_intake_application(settings: Settings | None = None) -> FastAPI:
    configuration = settings or Settings()
    application = FastAPI(
        title="VFBiz GCP Knowledge Intake Worker",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_lifespan,
    )
    application.state.settings = configuration
    application.state.gcp_intake_runtime = None

    @application.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    @application.post(
        "/internal/v1/knowledge/gcp-intake/pubsub",
        response_model=CloudIngestionDispatchResult,
        status_code=202,
    )
    async def receive_pubsub(  # pyright: ignore[reportUnusedFunction]
        request: Request,
    ) -> CloudIngestionDispatchResult:
        runtime = cast(GcpIntakeRuntime | None, request.app.state.gcp_intake_runtime)
        if runtime is None:
            raise HTTPException(status_code=503, detail="GCP_INTAKE_DISABLED")
        body = await _read_bounded_body(request)
        try:
            return await run_in_threadpool(runtime.worker.dispatch, body)
        except PermanentIngestionFailure as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except TransientIngestionFailure as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except (httpx.HTTPError, OSError) as error:
            raise HTTPException(status_code=503, detail="GCP_PROVIDER_UNAVAILABLE") from error

    @application.exception_handler(HTTPException)
    async def http_error(  # pyright: ignore[reportUnusedFunction]
        _request: Request, error: Exception
    ) -> JSONResponse:
        exception = cast(HTTPException, error)
        return JSONResponse(
            status_code=exception.status_code,
            content={
                "code": str(exception.detail),
                "retryable": exception.status_code == 503,
            },
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    return application


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncGenerator[None]:
    settings = cast(Settings, application.state.settings)
    runtime: GcpIntakeRuntime | None = None
    if settings.knowledge_ingestion_profile == "gcp":
        runtime = build_gcp_intake_runtime(settings)
    application.state.gcp_intake_runtime = runtime
    try:
        yield
    finally:
        if runtime is not None:
            await run_in_threadpool(runtime.close)


async def _read_bounded_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_ENVELOPE_BYTES:
                raise HTTPException(status_code=413, detail="PUBSUB_ENVELOPE_TOO_LARGE")
        except ValueError as error:
            raise HTTPException(status_code=400, detail="CONTENT_LENGTH_INVALID") from error
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > _MAX_ENVELOPE_BYTES:
            raise HTTPException(status_code=413, detail="PUBSUB_ENVELOPE_TOO_LARGE")
        chunks.append(chunk)
    return b"".join(chunks)


app = create_gcp_intake_application()

__all__ = ["app", "create_gcp_intake_application"]
