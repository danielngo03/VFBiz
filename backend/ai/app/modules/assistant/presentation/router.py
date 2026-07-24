from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.modules.assistant.application import AnswerService
from app.modules.assistant.dependencies import get_answer_service
from app.modules.assistant.domain import AnswerRequest, AssistantProfile
from app.modules.assistant.presentation.schemas import AnswerRequestSchema, AnswerResponseSchema
from app.platform.security import GatewayContext, require_gateway_context

answer_router = APIRouter(prefix="/answers", tags=["assistant"])


@answer_router.post("", response_model=AnswerResponseSchema)
async def answer(
    request: AnswerRequestSchema,
    gateway: Annotated[GatewayContext, Depends(require_gateway_context)],
    service: Annotated[AnswerService, Depends(get_answer_service)],
) -> AnswerResponseSchema:
    requested_profile = AssistantProfile(request.profile)
    authorized_profile = AssistantProfile(gateway.assistant_profile)
    try:
        result = await service.answer(
            AnswerRequest(
                question=request.question,
                profile=requested_profile,
                subject=gateway.subject,
            ),
            authorized_profile=authorized_profile,
        )
    except PermissionError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ASSISTANT_PROFILE_FORBIDDEN",
                "message": "The requested assistant profile is not authorized.",
            },
        ) from error
    return AnswerResponseSchema.from_result(result)
