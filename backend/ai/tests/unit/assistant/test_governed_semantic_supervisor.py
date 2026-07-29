from dataclasses import replace

import pytest

from app.modules.assistant.application import (
    GovernedSemanticSupervisor,
    RouteDecision,
    SemanticClassifierBinding,
    SemanticRoutePrediction,
)
from app.modules.assistant.infrastructure.keyword_supervisor import KeywordSupervisor

_BINDING = SemanticClassifierBinding(
    artifact_sha256="a" * 64,
    classifier_revision="vivi-router-v1",
    evaluation_evidence_sha256="b" * 64,
    output_schema_revision="route-decision-v1",
    threshold_policy_revision="semantic-routing-policy-v1",
    threshold_policy_sha256="c" * 64,
    semantic_acceptance_confidence=0.8,
    semantic_activation_below=0.8,
)


class FixedClassifier:
    def __init__(
        self,
        prediction: SemanticRoutePrediction | Exception,
        *,
        binding: SemanticClassifierBinding = _BINDING,
    ) -> None:
        self.binding = binding
        self._prediction = prediction
        self.calls = 0

    async def classify(self, **_kwargs: object) -> SemanticRoutePrediction:
        self.calls += 1
        if isinstance(self._prediction, Exception):
            raise self._prediction
        return self._prediction


@pytest.mark.asyncio
async def test_exact_deterministic_route_avoids_semantic_cost() -> None:
    classifier = FixedClassifier(
        SemanticRoutePrediction(
            decision=RouteDecision(intent="public_knowledge", confidence=0.99),
            binding=_BINDING,
        )
    )
    supervisor = GovernedSemanticSupervisor(
        deterministic=KeywordSupervisor(),
        classifier=classifier,
        binding=_BINDING,
    )

    decision = await supervisor.route(
        message="VF 8 có thông số gì?",
        global_entities=(),
        previous_task=None,
    )

    assert decision.intent == "vehicle_question"
    assert decision.routing_source == "deterministic"
    assert classifier.calls == 0


@pytest.mark.asyncio
async def test_semantic_route_handles_implicit_intent_with_release_binding() -> None:
    classifier = FixedClassifier(
        SemanticRoutePrediction(
            decision=RouteDecision(
                intent="financing_question",
                confidence=0.93,
                routing_source="semantic",
            ),
            binding=_BINDING,
        )
    )
    supervisor = GovernedSemanticSupervisor(
        deterministic=KeywordSupervisor(),
        classifier=classifier,
        binding=_BINDING,
    )

    decision = await supervisor.route(
        message="Mỗi tháng tôi cần chuẩn bị khoảng bao nhiêu?",
        global_entities=(),
        previous_task=None,
    )

    assert decision.intent == "financing_question"
    assert decision.routing_source == "semantic"
    assert classifier.calls == 1


@pytest.mark.asyncio
async def test_low_confidence_semantic_result_requires_clarification() -> None:
    classifier = FixedClassifier(
        SemanticRoutePrediction(
            decision=RouteDecision(
                intent="vehicle_question",
                confidence=0.61,
                routing_source="semantic",
            ),
            binding=_BINDING,
        )
    )
    supervisor = GovernedSemanticSupervisor(
        deterministic=KeywordSupervisor(),
        classifier=classifier,
        binding=_BINDING,
    )

    decision = await supervisor.route(
        message="Tôi muốn biết thêm",
        global_entities=(),
        previous_task=None,
    )

    assert decision.intent == "unknown"
    assert decision.required_arguments == ("primary_intent",)
    assert decision.missing_slots == ("primary_intent",)
    assert decision.routing_source == "semantic"


@pytest.mark.asyncio
async def test_classifier_failure_falls_back_without_losing_deterministic_safety() -> None:
    classifier = FixedClassifier(TimeoutError("classifier deadline"))
    supervisor = GovernedSemanticSupervisor(
        deterministic=KeywordSupervisor(),
        classifier=classifier,
        binding=_BINDING,
    )

    decision = await supervisor.route(
        message="Chính sách hiện tại là gì?",
        global_entities=(),
        previous_task=None,
    )

    assert decision.intent == "public_knowledge"
    assert decision.fallback_reason == "classifier_unavailable"
    assert decision.routing_source == "deterministic"


def test_classifier_binding_mismatch_fails_before_any_customer_turn() -> None:
    classifier = FixedClassifier(
        SemanticRoutePrediction(
            decision=RouteDecision(intent="public_knowledge"),
            binding=_BINDING,
        ),
        binding=replace(_BINDING, artifact_sha256="c" * 64),
    )

    with pytest.raises(ValueError, match="classifier release binding mismatch"):
        GovernedSemanticSupervisor(
            deterministic=KeywordSupervisor(),
            classifier=classifier,
            binding=_BINDING,
        )


def test_classifier_threshold_policy_is_part_of_the_release_binding() -> None:
    classifier = FixedClassifier(
        SemanticRoutePrediction(
            decision=RouteDecision(intent="public_knowledge"),
            binding=_BINDING,
        ),
        binding=replace(
            _BINDING,
            threshold_policy_sha256="d" * 64,
            semantic_acceptance_confidence=0.9,
        ),
    )

    with pytest.raises(ValueError, match="classifier release binding mismatch"):
        GovernedSemanticSupervisor(
            deterministic=KeywordSupervisor(),
            classifier=classifier,
            binding=_BINDING,
        )


def test_classifier_binding_rejects_an_invalid_threshold_policy() -> None:
    with pytest.raises(ValueError, match="semantic routing thresholds are invalid"):
        replace(
            _BINDING,
            semantic_acceptance_confidence=0.5,
            semantic_activation_below=0.8,
        )
