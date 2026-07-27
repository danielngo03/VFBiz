from fastapi import APIRouter

from app.api.internal_v1.conversation_router import conversation_router
from app.platform.health import internal_health_router

internal_v1_router = APIRouter(prefix="/internal/v1")
internal_v1_router.include_router(internal_health_router)
internal_v1_router.include_router(conversation_router)
