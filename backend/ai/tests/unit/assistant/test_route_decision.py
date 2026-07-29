import pytest

from app.modules.assistant.application import RouteDecision


def test_route_decision_rejects_an_unregistered_worker_intent() -> None:
    with pytest.raises(ValueError, match="intent is not registered"):
        RouteDecision(intent="delete_customer_account")  # type: ignore[arg-type]


def test_route_decision_allows_missing_slots_that_are_required() -> None:
    decision = RouteDecision(
        intent="vehicle_question",
        required_arguments=("vehicle_variant",),
        missing_slots=("vehicle_variant",),
    )

    assert decision.missing_slots == ("vehicle_variant",)


def test_route_decision_rejects_duplicate_or_unrequired_missing_slots() -> None:
    with pytest.raises(ValueError, match="route slots must be unique"):
        RouteDecision(
            intent="vehicle_question",
            required_arguments=("vehicle_variant", "vehicle_variant"),
        )

    with pytest.raises(ValueError, match="missing slots must be required"):
        RouteDecision(
            intent="vehicle_question",
            required_arguments=("vehicle_variant",),
            missing_slots=("market",),
        )


def test_route_decision_rejects_unknown_or_duplicate_abuse_signals() -> None:
    with pytest.raises(ValueError, match="abuse signal is not registered"):
        RouteDecision(
            intent="unknown",
            abuse_signals=("model_invented_denial",),
        )

    with pytest.raises(ValueError, match="abuse signals must be unique"):
        RouteDecision(
            intent="unknown",
            abuse_signals=("instruction_override", "instruction_override"),
        )
