import re
import unicodedata
from typing import cast

from app.modules.assistant.application import RouteDecision
from app.modules.assistant.domain import ActiveTaskState, ConfirmedGlobalEntity, TaskIntent

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
    "sạc pin",
    "sạc xe",
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

_ABUSE_PATTERNS = (
    "ignore previous instructions",
    "bo qua moi huong dan truoc",
    "system prompt",
    "developer message",
)


def _searchable_text(message: str) -> str:
    decomposed = unicodedata.normalize("NFKD", message.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))


def _contains(text: str, keyword: str) -> bool:
    normalized_keyword = _searchable_text(keyword)
    return re.search(rf"(?:^| )({re.escape(normalized_keyword)})(?: |$)", text) is not None


def _contains_message(*, original: str, searchable: str, keyword: str) -> bool:
    # Stripping Vietnamese tone marks makes "sạc" collide with "sắc". Keep
    # this short, ambiguous keyword accent-sensitive; longer charging phrases
    # ("tram sac", "sac pin") remain safe for no-diacritic input.
    if keyword == "sạc":
        return re.search(r"(?:^|\W)sạc(?:\W|$)", original) is not None
    return _contains(searchable, keyword)


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
        original = message.casefold()
        normalized = _searchable_text(message)
        matched: list[TaskIntent] = []
        for intent, keywords in (
            ("financing_question", _FINANCING_KEYWORDS),
            ("charging_question", _CHARGING_KEYWORDS),
            ("vehicle_question", _VEHICLE_KEYWORDS),
        ):
            if any(
                _contains_message(
                    original=original,
                    searchable=normalized,
                    keyword=keyword,
                )
                for keyword in keywords
            ):
                matched.append(cast(TaskIntent, intent))
        matched_intents = tuple(matched)
        abuse_signals = tuple(
            "instruction_override"
            for pattern in _ABUSE_PATTERNS
            if _contains(normalized, pattern)
        )[:1]
        if matched_intents:
            return RouteDecision(
                intent=matched_intents[0],
                confidence=1.0 if len(matched_intents) == 1 else 0.5,
                multi_intent=len(matched_intents) > 1,
                abuse_signals=abuse_signals,
            )
        if any(entity.kind == "vehicle_model" for entity in global_entities) and (
            previous_task is not None and previous_task.intent == "vehicle_question"
        ):
            return RouteDecision(intent="vehicle_question", abuse_signals=abuse_signals)
        return RouteDecision(
            intent="public_knowledge",
            confidence=0.5,
            abuse_signals=abuse_signals,
        )
