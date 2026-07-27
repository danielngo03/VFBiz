from app.modules.assistant.application import RouteDecision
from app.modules.assistant.domain import ActiveTaskState, ConfirmedGlobalEntity

# Ordered, first-match-wins keyword sets. This is deliberately a zero-cost,
# zero-latency classifier rather than an LLM call: TaskIntent is a small
# closed set, and routing spend on every turn is not worth it when a cheap
# rule reaches the same answer (see VFBIZ-0094 checkpoint: cost-efficient
# tiered routing). Upgrading to a learned classifier later does not change
# the SupervisorPort contract.
_FINANCING_KEYWORDS = (
    "vay",
    "trả góp",
    "lãi suất",
    "tài chính",
    "financing",
    "loan",
    "installment",
    "emi",
)
_CHARGING_KEYWORDS = (
    "sạc",
    "trạm sạc",
    "pin",
    "charging",
    "charge",
    "battery",
    "kwh",
)
_VEHICLE_KEYWORDS = (
    "vf3",
    "vf 3",
    "vf5",
    "vf 5",
    "vf6",
    "vf 6",
    "vf7",
    "vf 7",
    "vf8",
    "vf 8",
    "vf9",
    "vf 9",
    "vinfast",
    "xe điện",
    "phiên bản",
    "thông số",
    "variant",
    "specs",
)


class KeywordSupervisor:
    """Deterministic, zero-cost intent routing for the baseline assistant.

    A rule-based classifier is the correct default here, not a placeholder:
    TaskIntent is a small closed set, and every turn otherwise pays for an
    LLM call before any grounded work even starts.
    """

    async def route(
        self,
        *,
        message: str,
        global_entities: tuple[ConfirmedGlobalEntity, ...],
        previous_task: ActiveTaskState | None,
    ) -> RouteDecision:
        normalized = message.casefold()
        if any(keyword in normalized for keyword in _FINANCING_KEYWORDS):
            return RouteDecision(intent="financing_question")
        if any(keyword in normalized for keyword in _CHARGING_KEYWORDS):
            return RouteDecision(intent="charging_question")
        if any(keyword in normalized for keyword in _VEHICLE_KEYWORDS):
            return RouteDecision(intent="vehicle_question")
        if any(entity.kind == "vehicle_model" for entity in global_entities) and (
            previous_task is not None and previous_task.intent == "vehicle_question"
        ):
            return RouteDecision(intent="vehicle_question")
        return RouteDecision(intent="public_knowledge")
