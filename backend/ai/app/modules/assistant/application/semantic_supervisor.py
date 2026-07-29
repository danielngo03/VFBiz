import re
from dataclasses import dataclass, replace
from typing import Protocol

from app.modules.assistant.application.ports import RouteDecision, SupervisorPort
from app.modules.assistant.domain import ActiveTaskState, ConfirmedGlobalEntity

_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")


@dataclass(frozen=True, slots=True)
class SemanticClassifierBinding:
    artifact_sha256: str
    classifier_revision: str
    evaluation_evidence_sha256: str
    output_schema_revision: str
    threshold_policy_revision: str
    threshold_policy_sha256: str
    semantic_acceptance_confidence: float
    semantic_activation_below: float

    def __post_init__(self) -> None:
        digests = (
            self.artifact_sha256,
            self.evaluation_evidence_sha256,
            self.threshold_policy_sha256,
        )
        if any(not _DIGEST.fullmatch(digest) for digest in digests):
            raise ValueError("classifier binding digest must be SHA-256")
        revisions = (
            self.classifier_revision,
            self.output_schema_revision,
            self.threshold_policy_revision,
        )
        if any(not _REVISION.fullmatch(revision) for revision in revisions):
            raise ValueError("classifier binding revision is invalid")
        if not (
            0.0 < self.semantic_acceptance_confidence <= 1.0
            and 0.0 < self.semantic_activation_below <= 1.0
            and self.semantic_acceptance_confidence >= self.semantic_activation_below
        ):
            raise ValueError("semantic routing thresholds are invalid")


@dataclass(frozen=True, slots=True)
class SemanticRoutePrediction:
    decision: RouteDecision
    binding: SemanticClassifierBinding


class SemanticRouteClassifierPort(Protocol):
    @property
    def binding(self) -> SemanticClassifierBinding: ...

    async def classify(
        self,
        *,
        message: str,
        global_entities: tuple[ConfirmedGlobalEntity, ...],
        previous_task: ActiveTaskState | None,
    ) -> SemanticRoutePrediction: ...


class GovernedSemanticSupervisor:
    def __init__(
        self,
        *,
        deterministic: SupervisorPort,
        classifier: SemanticRouteClassifierPort,
        binding: SemanticClassifierBinding,
    ) -> None:
        if classifier.binding != binding:
            raise ValueError("classifier release binding mismatch")
        self._deterministic = deterministic
        self._classifier = classifier
        self._binding = binding
        self._acceptance_confidence = binding.semantic_acceptance_confidence
        self._activation_below = binding.semantic_activation_below

    async def route(
        self,
        *,
        message: str,
        global_entities: tuple[ConfirmedGlobalEntity, ...],
        previous_task: ActiveTaskState | None,
    ) -> RouteDecision:
        deterministic = await self._deterministic.route(
            message=message,
            global_entities=global_entities,
            previous_task=previous_task,
        )
        if deterministic.abuse_signals or (
            deterministic.confidence >= self._activation_below and not deterministic.multi_intent
        ):
            return deterministic

        try:
            prediction = await self._classifier.classify(
                message=message,
                global_entities=global_entities,
                previous_task=previous_task,
            )
        except TimeoutError:
            return replace(
                deterministic,
                fallback_reason="classifier_unavailable",
                routing_source="deterministic",
            )
        except Exception:
            return replace(
                deterministic,
                fallback_reason="classifier_unavailable",
                routing_source="deterministic",
            )

        semantic = prediction.decision
        if (
            prediction.binding != self._binding
            or semantic.routing_source != "semantic"
            or semantic.fallback_reason is not None
        ):
            return replace(
                deterministic,
                fallback_reason="classifier_invalid",
                routing_source="deterministic",
            )
        combined_abuse = tuple(
            dict.fromkeys((*deterministic.abuse_signals, *semantic.abuse_signals))
        )
        if semantic.confidence < self._acceptance_confidence:
            return RouteDecision(
                intent="unknown",
                confidence=semantic.confidence,
                required_arguments=("primary_intent",),
                missing_slots=("primary_intent",),
                abuse_signals=combined_abuse,
                routing_source="semantic",
            )
        return replace(semantic, abuse_signals=combined_abuse)
