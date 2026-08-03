import asyncio
import json
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.modules.assistant.application import RouteDecision
from app.modules.assistant.application.semantic_supervisor import (
    SemanticClassifierBinding,
    SemanticRoutePrediction,
)
from app.modules.assistant.domain import ActiveTaskState, ConfirmedGlobalEntity


class _SemanticClassifierResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    abuseSignals: tuple[
        Literal[
            "abusive_language",
            "instruction_override",
            "prompt_exfiltration",
            "tool_injection",
        ],
        ...,
    ] = Field(max_length=16)
    bindingEnvelopeSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confidence: float = Field(ge=0, le=1)
    intent: Literal[
        "public_knowledge",
        "vehicle_question",
        "financing_question",
        "charging_question",
        "unknown",
    ]
    missingSlots: tuple[str, ...] = Field(max_length=16)
    multiIntent: bool
    outOfDomain: bool
    requiredSlots: tuple[str, ...] = Field(max_length=16)


@dataclass(frozen=True, slots=True)
class SemanticClassifierHttpDeployment:
    endpoint: str
    artifact_ref: str
    artifact_sha256: str
    api_token: str | None
    timeout_seconds: float
    max_request_bytes: int
    max_response_bytes: int
    max_concurrency: int


class HttpSemanticRouteClassifier:
    """Provider-neutral strict-schema adapter for an approved classifier service."""

    def __init__(
        self,
        *,
        deployment: SemanticClassifierHttpDeployment,
        binding: SemanticClassifierBinding,
        client: httpx.AsyncClient,
    ) -> None:
        if (
            deployment.artifact_ref != binding.classifier_artifact_ref
            or deployment.artifact_sha256 != binding.artifact_sha256
        ):
            raise ValueError("classifier deployment does not match release binding")
        self._deployment = deployment
        self._binding = binding
        self._client = client
        self._semaphore = asyncio.Semaphore(deployment.max_concurrency)

    @property
    def binding(self) -> SemanticClassifierBinding:
        return self._binding

    async def classify(
        self,
        *,
        message: str,
        global_entities: tuple[ConfirmedGlobalEntity, ...],
        previous_task: ActiveTaskState | None,
    ) -> SemanticRoutePrediction:
        payload = {
            "bindingEnvelopeSha256": self._binding.binding_envelope_sha256,
            "classifierArtifact": {
                "ref": self._binding.classifier_artifact_ref,
                "sha256": self._binding.artifact_sha256,
                "revision": self._binding.classifier_revision,
            },
            "globalEntities": [
                {"kind": entity.kind, "reference": entity.reference}
                for entity in global_entities
            ],
            "message": message,
            "previousTask": (
                None
                if previous_task is None
                else {
                    "intent": previous_task.intent,
                    "requiredSlots": list(previous_task.required_arguments),
                }
            ),
            "routingPolicyRevision": self._binding.threshold_policy_revision,
            "schemaRevision": self._binding.output_schema_revision,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        if len(encoded) > self._deployment.max_request_bytes:
            raise ValueError("classifier request exceeds its release budget")
        headers = {
            "content-type": "application/json",
            "x-vfbiz-binding-sha256": self._binding.binding_envelope_sha256,
        }
        if self._deployment.api_token is not None:
            headers["authorization"] = f"Bearer {self._deployment.api_token}"
        request = self._client.build_request(
            "POST",
            self._deployment.endpoint,
            content=encoded,
            headers=headers,
        )
        response: httpx.Response | None = None
        async with asyncio.timeout(self._deployment.timeout_seconds):
            try:
                async with self._semaphore:
                    response = await self._client.send(
                        request,
                        stream=True,
                        follow_redirects=False,
                    )
                    response.raise_for_status()
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if (
                            len(content) + len(chunk)
                            > self._deployment.max_response_bytes
                        ):
                            raise ValueError(
                                "classifier response exceeds its release budget"
                            )
                        content.extend(chunk)
            finally:
                if response is not None:
                    await response.aclose()
        document = _SemanticClassifierResponse.model_validate_json(content)
        if document.bindingEnvelopeSha256 != self._binding.binding_envelope_sha256:
            raise ValueError("classifier response binding mismatch")
        decision = RouteDecision(
            intent=document.intent,
            confidence=document.confidence,
            required_arguments=document.requiredSlots,
            missing_slots=document.missingSlots,
            multi_intent=document.multiIntent,
            out_of_domain=document.outOfDomain,
            abuse_signals=document.abuseSignals,
            routing_source="semantic",
        )
        return SemanticRoutePrediction(decision=decision, binding=self._binding)
