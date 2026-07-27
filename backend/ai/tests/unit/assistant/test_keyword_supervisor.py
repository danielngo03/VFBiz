from datetime import UTC, datetime

import pytest

from app.modules.assistant.domain import ActiveTaskState, ConfirmedGlobalEntity
from app.modules.assistant.infrastructure.keyword_supervisor import KeywordSupervisor


def entity(kind: str = "vehicle_model") -> ConfirmedGlobalEntity:
    return ConfirmedGlobalEntity(
        kind=kind,  # type: ignore[arg-type]
        reference="vf-8",
        source_revision="a" * 64,
        confirmed_at=datetime.now(UTC),
        confidence=0.9,
    )


@pytest.mark.asyncio
async def test_routes_financing_keywords_regardless_of_case() -> None:
    supervisor = KeywordSupervisor()

    decision = await supervisor.route(
        message="Tôi muốn hỏi về LÃI SUẤT trả góp",
        global_entities=(),
        previous_task=None,
    )

    assert decision.intent == "financing_question"


@pytest.mark.asyncio
async def test_routes_charging_keywords() -> None:
    supervisor = KeywordSupervisor()

    decision = await supervisor.route(
        message="Trạm sạc gần nhất ở đâu?",
        global_entities=(),
        previous_task=None,
    )

    assert decision.intent == "charging_question"


@pytest.mark.asyncio
async def test_routes_vehicle_keywords() -> None:
    supervisor = KeywordSupervisor()

    decision = await supervisor.route(
        message="VF 8 có thông số gì đặc biệt?",
        global_entities=(),
        previous_task=None,
    )

    assert decision.intent == "vehicle_question"


@pytest.mark.asyncio
async def test_financing_keyword_wins_over_vehicle_keyword() -> None:
    supervisor = KeywordSupervisor()

    decision = await supervisor.route(
        message="VF 8 trả góp lãi suất bao nhiêu?",
        global_entities=(),
        previous_task=None,
    )

    assert decision.intent == "financing_question"


@pytest.mark.asyncio
async def test_defaults_to_public_knowledge_without_any_keyword() -> None:
    supervisor = KeywordSupervisor()

    decision = await supervisor.route(
        message="Chính sách bảo hành hiện tại là gì?",
        global_entities=(),
        previous_task=None,
    )

    assert decision.intent == "public_knowledge"


@pytest.mark.asyncio
async def test_follow_up_without_keywords_stays_on_the_active_vehicle_task() -> None:
    supervisor = KeywordSupervisor()

    decision = await supervisor.route(
        message="còn màu sắc thì sao?",
        global_entities=(entity(),),
        previous_task=ActiveTaskState(
            intent="vehicle_question", required_arguments=(), retry_count=0
        ),
    )

    assert decision.intent == "vehicle_question"


@pytest.mark.asyncio
async def test_follow_up_without_keywords_or_prior_vehicle_task_falls_back() -> None:
    supervisor = KeywordSupervisor()

    decision = await supervisor.route(
        message="còn màu sắc thì sao?",
        global_entities=(entity(),),
        previous_task=None,
    )

    assert decision.intent == "public_knowledge"
