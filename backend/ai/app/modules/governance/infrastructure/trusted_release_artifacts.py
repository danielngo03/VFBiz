import asyncio
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.governance.domain import SemanticClassifierReleaseBinding

from app.modules.governance.domain.release_manifest import (
    ApprovalEvidence,
    AssistantReleaseCandidate,
    AssistantReleaseManifest,
    AutomatedGateEvidence,
    PromotionEvidence,
    StaticSafeApprovalEvidence,
    StaticSafeRelease,
)

_OPAQUE_REFERENCE = re.compile(
    r"^(?:approval|artifact|classifier|dataset|drill|evaluation|evaluator|graph|history|"
    r"knowledge|model|policy|prompt|retriever|safe-release|schema|tools|"
    r"validator)://[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$"
)
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class ReleaseArtifactErrorCode(StrEnum):
    INVALID_REFERENCE = "INVALID_ARTIFACT_REFERENCE"
    LOOKUP_TIMEOUT = "ARTIFACT_LOOKUP_TIMEOUT"
    LOOKUP_FAILED = "ARTIFACT_LOOKUP_FAILED"
    EVIDENCE_TIMEOUT = "EVIDENCE_VERIFICATION_TIMEOUT"
    EVIDENCE_FAILED = "EVIDENCE_VERIFICATION_FAILED"


class ReleaseArtifactInfrastructureError(RuntimeError):
    def __init__(
        self,
        code: ReleaseArtifactErrorCode,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.retryable = retryable


class TrustedArtifactRegistry(Protocol):
    """Read a digest from an internal registry; implementations must not fetch URLs."""

    async def read_sha256(self, artifact_ref: str) -> str | None: ...


class TrustedEvidenceRegistry(Protocol):
    async def verify(self, request: "EvidenceAuthenticityRequest") -> bool: ...


class EvidenceKind(StrEnum):
    APPROVAL = "approval"
    AUTOMATED_GATE = "automated_gate"
    STATIC_SAFE_APPROVAL = "static_safe_approval"
    PROMOTION = "promotion"
    LIVE_CONTROL = "live_control"
    CLASSIFIER_EVALUATION = "classifier_evaluation"
    CLASSIFIER_APPROVAL = "classifier_approval"


@dataclass(frozen=True, slots=True)
class EvidenceAuthenticityRequest:
    kind: EvidenceKind
    evidence_ref: str
    evidence_sha256: str
    target_sha256: str
    assistant_profile: str
    environment: str
    authority_role: str | None = None
    approver_subject: str | None = None

    def __post_init__(self) -> None:
        if not _OPAQUE_REFERENCE.fullmatch(self.evidence_ref):
            raise ValueError("evidence reference must be an approved opaque reference")
        if not _SHA256.fullmatch(self.evidence_sha256) or not _SHA256.fullmatch(self.target_sha256):
            raise ValueError("evidence authenticity request requires SHA-256 digests")


class BoundedOpaqueArtifactDigestReader:
    """Bounded, cancellable adapter over a trusted internal artifact registry."""

    def __init__(
        self,
        *,
        registry: TrustedArtifactRegistry,
        timeout_seconds: float,
        max_concurrency: int,
    ) -> None:
        if timeout_seconds <= 0 or max_concurrency <= 0:
            raise ValueError("artifact reader limits must be positive")
        self._registry = registry
        self._timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def sha256(self, artifact_ref: str) -> str | None:
        if not _OPAQUE_REFERENCE.fullmatch(artifact_ref):
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.INVALID_REFERENCE,
                retryable=False,
            )
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._semaphore:
                    digest = await self._registry.read_sha256(artifact_ref)
        except TimeoutError as error:
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.LOOKUP_TIMEOUT,
                retryable=True,
            ) from error
        except asyncio.CancelledError:
            raise
        except ReleaseArtifactInfrastructureError:
            raise
        except Exception as error:
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.LOOKUP_FAILED,
                retryable=True,
            ) from error
        if digest is not None and not _SHA256.fullmatch(digest):
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.LOOKUP_FAILED,
                retryable=False,
            )
        return digest


class BoundedReleaseEvidenceVerifier:
    """Authenticates evidence without trusting mutable environment flags."""

    def __init__(
        self,
        *,
        registry: TrustedEvidenceRegistry,
        timeout_seconds: float,
        max_concurrency: int,
    ) -> None:
        if timeout_seconds <= 0 or max_concurrency <= 0:
            raise ValueError("evidence verifier limits must be positive")
        self._registry = registry
        self._timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def verify_approval(
        self,
        approval: ApprovalEvidence,
        candidate: AssistantReleaseCandidate,
    ) -> bool:
        return await self._verify(
            EvidenceAuthenticityRequest(
                kind=EvidenceKind.APPROVAL,
                evidence_ref=approval.evidence_ref,
                evidence_sha256=approval.evidence_sha256,
                target_sha256=candidate.content_sha256,
                assistant_profile=candidate.assistant_profile,
                environment=candidate.environment,
                authority_role=approval.authority_role,
                approver_subject=approval.approver_subject,
            )
        )

    async def verify_automated_gate(
        self,
        evidence: AutomatedGateEvidence,
        candidate: AssistantReleaseCandidate,
    ) -> bool:
        return await self._verify(
            EvidenceAuthenticityRequest(
                kind=EvidenceKind.AUTOMATED_GATE,
                evidence_ref=evidence.evidence_ref,
                evidence_sha256=evidence.evidence_sha256,
                target_sha256=candidate.content_sha256,
                assistant_profile=candidate.assistant_profile,
                environment=candidate.environment,
            )
        )

    async def verify_live_controls(
        self,
        manifest: AssistantReleaseManifest,
    ) -> bool:
        requests = (
            EvidenceAuthenticityRequest(
                kind=EvidenceKind.LIVE_CONTROL,
                evidence_ref=manifest.kill_switch_registry_ref,
                evidence_sha256=manifest.kill_switch_registry_sha256,
                target_sha256=manifest.candidate.content_sha256,
                assistant_profile=manifest.candidate.assistant_profile,
                environment=manifest.candidate.environment,
            ),
            EvidenceAuthenticityRequest(
                kind=EvidenceKind.LIVE_CONTROL,
                evidence_ref=manifest.rollback_drill_evidence_ref,
                evidence_sha256=manifest.rollback_drill_evidence_sha256,
                target_sha256=manifest.candidate.content_sha256,
                assistant_profile=manifest.candidate.assistant_profile,
                environment=manifest.candidate.environment,
            ),
        )
        results = await asyncio.gather(*(self._verify(request) for request in requests))
        return all(results)

    async def verify_static_safe_approval(
        self,
        approval: StaticSafeApprovalEvidence,
        release: StaticSafeRelease,
    ) -> bool:
        return await self._verify(
            EvidenceAuthenticityRequest(
                kind=EvidenceKind.STATIC_SAFE_APPROVAL,
                evidence_ref=approval.evidence_ref,
                evidence_sha256=approval.evidence_sha256,
                target_sha256=release.safe_release_core_sha256,
                assistant_profile=release.assistant_profile,
                environment=release.environment,
                authority_role=approval.authority_role,
                approver_subject=approval.approver_subject,
            )
        )

    async def verify_promotion(
        self,
        evidence: PromotionEvidence,
        manifest: AssistantReleaseManifest,
    ) -> bool:
        return await self._verify(
            EvidenceAuthenticityRequest(
                kind=EvidenceKind.PROMOTION,
                evidence_ref=evidence.evidence_ref,
                evidence_sha256=evidence.evidence_sha256,
                target_sha256=evidence.target_activation_core_sha256,
                assistant_profile=manifest.candidate.assistant_profile,
                environment=manifest.candidate.environment,
            )
        )

    async def _verify(self, request: EvidenceAuthenticityRequest) -> bool:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._semaphore:
                    return await self._registry.verify(request)
        except TimeoutError as error:
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.EVIDENCE_TIMEOUT,
                retryable=True,
            ) from error
        except asyncio.CancelledError:
            raise
        except ReleaseArtifactInfrastructureError:
            raise
        except Exception as error:
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.EVIDENCE_FAILED,
                retryable=True,
            ) from error


class BoundedSemanticClassifierEvidenceVerifier:
    """Authenticates classifier evidence without weakening release evidence types."""

    def __init__(
        self,
        *,
        registry: TrustedEvidenceRegistry,
        timeout_seconds: float,
        max_concurrency: int,
    ) -> None:
        if timeout_seconds <= 0 or max_concurrency <= 0:
            raise ValueError("classifier evidence verifier limits must be positive")
        self._registry = registry
        self._timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def verify_evaluation(
        self,
        binding: "SemanticClassifierReleaseBinding",
    ) -> bool:
        document = binding.to_document()
        return await self._verify(
            EvidenceAuthenticityRequest(
                kind=EvidenceKind.CLASSIFIER_EVALUATION,
                evidence_ref=binding.evaluation_evidence_ref,
                evidence_sha256=binding.evaluation_evidence_sha256,
                target_sha256=str(document["classification_stack_sha256"]),
                assistant_profile=binding.assistant_profile,
                environment=binding.environment,
            )
        )

    async def verify_approval(
        self,
        binding: "SemanticClassifierReleaseBinding",
    ) -> bool:
        document = binding.to_document()
        return await self._verify(
            EvidenceAuthenticityRequest(
                kind=EvidenceKind.CLASSIFIER_APPROVAL,
                evidence_ref=binding.approval_evidence_ref,
                evidence_sha256=binding.approval_evidence_sha256,
                target_sha256=str(document["binding_core_sha256"]),
                assistant_profile=binding.assistant_profile,
                environment=binding.environment,
            )
        )

    async def _verify(self, request: EvidenceAuthenticityRequest) -> bool:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._semaphore:
                    return await self._registry.verify(request)
        except TimeoutError as error:
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.EVIDENCE_TIMEOUT,
                retryable=True,
            ) from error
        except asyncio.CancelledError:
            raise
        except ReleaseArtifactInfrastructureError:
            raise
        except Exception as error:
            raise ReleaseArtifactInfrastructureError(
                ReleaseArtifactErrorCode.EVIDENCE_FAILED,
                retryable=True,
            ) from error
