from app.modules.inference.application.ports import (
    ClaimSupportDecision,
    GenerationRequest,
    GenerationResult,
)
from app.modules.inference.application.prompt_contract import dynamic_input_sha256


def normalized_evidence_digest(request: GenerationRequest) -> str:
    """Compatibility name for the exact canonical dynamic-input digest."""
    return dynamic_input_sha256(request)


class FailClosedClaimSupportValidator:
    """Boundary default until an approved deterministic/NLI validator is wired."""

    revision = "fail-closed-v1"

    async def validate(
        self,
        request: GenerationRequest,
        result: GenerationResult,
    ) -> ClaimSupportDecision:
        _ = result
        return ClaimSupportDecision(
            supported=False,
            validator_revision=self.revision,
            evidence_digest=normalized_evidence_digest(request),
        )
