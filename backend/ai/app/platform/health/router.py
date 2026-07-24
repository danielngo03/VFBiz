from typing import Annotated

from fastapi import APIRouter, Depends

from app.platform.security import GatewayContext, require_gateway_context

public_health_router = APIRouter(prefix="/health", tags=["health"])
internal_health_router = APIRouter(prefix="/health", tags=["health"])


@public_health_router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@internal_health_router.get("/ready")
async def readiness(
    _context: Annotated[GatewayContext, Depends(require_gateway_context)],
) -> dict[str, str]:
    # Resource-specific readiness indicators are added when adapters are enabled.
    return {"status": "ready"}
