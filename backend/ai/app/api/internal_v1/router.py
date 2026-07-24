from fastapi import APIRouter

from app.modules.assistant.presentation import answer_router
from app.platform.health import internal_health_router

internal_v1_router = APIRouter(prefix="/internal/v1")
internal_v1_router.include_router(internal_health_router)
internal_v1_router.include_router(answer_router)
