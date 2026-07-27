from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from app.modules.governance.domain.release_manifest import (
    ApprovalEvidence,
    AssistantReleaseCandidate,
    AssistantReleaseManifest,
    AutomatedGateEvidence,
    PriorActivationRollbackTarget,
    PromotionEvidence,
    ReleaseActivationState,
    StaticSafeApprovalEvidence,
    StaticSafeRelease,
    StaticSafeReleaseRollbackTarget,
)


class ReleaseManifestStore(Protocol):
    async def get(self, activation_id: str) -> AssistantReleaseManifest | None: ...

    async def get_candidate(
        self,
        candidate_id: str,
    ) -> AssistantReleaseCandidate | None: ...


class ArtifactDigestReader(Protocol):
    async def sha256(self, artifact_ref: str) -> str | None: ...


class ReleaseEvidenceVerifier(Protocol):
    async def verify_approval(
        self,
        approval: ApprovalEvidence,
        candidate: AssistantReleaseCandidate,
    ) -> bool: ...

    async def verify_automated_gate(
        self,
        evidence: AutomatedGateEvidence,
        candidate: AssistantReleaseCandidate,
    ) -> bool: ...

    async def verify_live_controls(
        self,
        manifest: AssistantReleaseManifest,
    ) -> bool: ...

    async def verify_static_safe_approval(
        self,
        approval: StaticSafeApprovalEvidence,
        release: StaticSafeRelease,
    ) -> bool: ...

    async def verify_promotion(
        self,
        evidence: PromotionEvidence,
        manifest: AssistantReleaseManifest,
    ) -> bool: ...


class ReleaseManifestResolutionError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ReleaseManifestResolver:
    def __init__(
        self,
        *,
        store: ReleaseManifestStore,
        digest_reader: ArtifactDigestReader,
        evidence_verifier: ReleaseEvidenceVerifier,
        required_approval_roles: tuple[str, ...],
        clock: Callable[[], datetime],
    ) -> None:
        if not required_approval_roles or len(set(required_approval_roles)) != len(
            required_approval_roles
        ):
            raise ValueError("required approval roles must be non-empty and unique")
        self._store = store
        self._digest_reader = digest_reader
        self._evidence_verifier = evidence_verifier
        self._required_approval_roles = frozenset(required_approval_roles)
        self._clock = clock

    async def resolve(
        self,
        *,
        activation_id: str,
        expected_candidate_sha256: str,
        assistant_profile: str,
        environment: str,
    ) -> AssistantReleaseManifest:
        item = await self._store.get(activation_id)
        if item is None:
            raise ReleaseManifestResolutionError("RELEASE_NOT_FOUND")
        candidate = item.candidate
        if candidate.content_sha256 != expected_candidate_sha256:
            raise ReleaseManifestResolutionError("CANDIDATE_DIGEST_MISMATCH")
        if candidate.assistant_profile != assistant_profile:
            raise ReleaseManifestResolutionError("ASSISTANT_PROFILE_MISMATCH")
        if candidate.environment != environment:
            raise ReleaseManifestResolutionError("ENVIRONMENT_MISMATCH")
        if item.state is ReleaseActivationState.REVOKED:
            raise ReleaseManifestResolutionError("RELEASE_REVOKED")
        if item.state is not ReleaseActivationState.ACTIVE:
            raise ReleaseManifestResolutionError("RELEASE_NOT_ACTIVE")
        now = self._clock()
        if now < item.effective_at:
            raise ReleaseManifestResolutionError("RELEASE_NOT_EFFECTIVE")
        if now >= item.expires_at:
            raise ReleaseManifestResolutionError("RELEASE_EXPIRED")
        await self._verify_candidate_artifacts(candidate)
        await self._verify_gate(item)
        await self._verify_approvals(item, now)
        await self._verify_promotion(item)
        await self._verify_rollback(item)
        await self._verify_live_controls(item)
        return item

    async def _verify_candidate_artifacts(
        self,
        candidate: AssistantReleaseCandidate,
    ) -> None:
        for reference, expected_digest in candidate.artifacts.artifact_digests():
            if await self._digest_reader.sha256(reference) != expected_digest:
                raise ReleaseManifestResolutionError("ARTIFACT_DIGEST_MISMATCH")

    async def _verify_gate(self, item: AssistantReleaseManifest) -> None:
        candidate = item.candidate
        gate = item.automated_gate
        if (
            gate.target_candidate_sha256 != candidate.content_sha256
            or gate.assistant_profile != candidate.assistant_profile
            or gate.environment != candidate.environment
            or gate.gate_policy_revision != candidate.gate_policy_revision
            or gate.gate_policy_sha256 != candidate.gate_policy_sha256
            or await self._digest_reader.sha256(gate.evidence_ref) != gate.evidence_sha256
            or not await self._evidence_verifier.verify_automated_gate(
                gate,
                candidate,
            )
        ):
            raise ReleaseManifestResolutionError("AUTOMATED_GATE_INVALID")

    async def _verify_approvals(
        self,
        item: AssistantReleaseManifest,
        now: datetime,
    ) -> None:
        candidate = item.candidate
        roles = {approval.authority_role for approval in item.approvals}
        subjects = {approval.approver_subject for approval in item.approvals}
        if (
            not self._required_approval_roles.issubset(roles)
            or len(subjects) != len(item.approvals)
            or candidate.requested_by_subject in subjects
        ):
            raise ReleaseManifestResolutionError("APPROVAL_AUTHORITY_INVALID")
        for approval in item.approvals:
            if (
                approval.target_candidate_sha256 != candidate.content_sha256
                or approval.assistant_profile != candidate.assistant_profile
                or approval.environment != candidate.environment
                or approval.approved_at > now
                or approval.approved_at > item.effective_at
                or await self._digest_reader.sha256(approval.evidence_ref)
                != approval.evidence_sha256
                or not await self._evidence_verifier.verify_approval(
                    approval,
                    candidate,
                )
            ):
                raise ReleaseManifestResolutionError("APPROVAL_EVIDENCE_INVALID")

    async def _verify_rollback(self, item: AssistantReleaseManifest) -> None:
        target = item.rollback_target
        if isinstance(target, PriorActivationRollbackTarget):
            rollback_manifest = await self._store.get(target.activation_id)
            rollback = rollback_manifest.candidate if rollback_manifest is not None else None
            if (
                rollback is None
                or rollback.content_sha256 != target.candidate_sha256
                or rollback.assistant_profile != item.candidate.assistant_profile
                or rollback.environment != item.candidate.environment
                or rollback_manifest is None
                or rollback_manifest.activation_envelope_sha256 != target.activation_envelope_sha256
                or rollback_manifest.state is not ReleaseActivationState.SUPERSEDED
            ):
                raise ReleaseManifestResolutionError("ROLLBACK_CANDIDATE_INVALID")
            await self._verify_prior_activation_readiness(rollback_manifest)
            return
        await self._verify_static_safe_rollback(item, target)

    async def _verify_prior_activation_readiness(
        self,
        rollback: AssistantReleaseManifest,
    ) -> None:
        now = self._clock()
        if now < rollback.effective_at or now >= rollback.expires_at:
            raise ReleaseManifestResolutionError("ROLLBACK_NOT_READY")
        await self._verify_candidate_artifacts(rollback.candidate)
        await self._verify_gate(rollback)
        await self._verify_approvals(rollback, now)
        await self._verify_promotion(rollback)
        await self._verify_live_controls(rollback)
        static_safe = rollback.static_safe_release
        if static_safe is None:
            raise ReleaseManifestResolutionError("STATIC_SAFE_RELEASE_INVALID")
        await self._verify_static_safe_release(rollback, static_safe)

    async def _verify_promotion(self, item: AssistantReleaseManifest) -> None:
        evidence = item.promotion_evidence
        if (
            evidence.target_activation_core_sha256 != item.activation_core_sha256
            or await self._digest_reader.sha256(evidence.evidence_ref) != evidence.evidence_sha256
            or not await self._evidence_verifier.verify_promotion(
                evidence,
                item,
            )
        ):
            raise ReleaseManifestResolutionError("PROMOTION_EVIDENCE_INVALID")

    async def _verify_static_safe_rollback(
        self,
        item: AssistantReleaseManifest,
        target: StaticSafeReleaseRollbackTarget,
    ) -> None:
        release = item.static_safe_release
        if release is None or target != release.rollback_target():
            raise ReleaseManifestResolutionError("STATIC_SAFE_RELEASE_INVALID")
        await self._verify_static_safe_release(item, release)

    async def _verify_static_safe_release(
        self,
        item: AssistantReleaseManifest,
        release: StaticSafeRelease,
    ) -> None:
        if (
            release.assistant_profile != item.candidate.assistant_profile
            or release.environment != item.candidate.environment
            or release.effective_at > item.effective_at
            or release.expires_at < item.expires_at
            or await self._digest_reader.sha256(release.safe_release_ref)
            != release.safe_release_envelope_sha256
            or await self._digest_reader.sha256(release.template_ref) != release.template_sha256
            or await self._digest_reader.sha256(release.response_policy_ref)
            != release.response_policy_sha256
        ):
            raise ReleaseManifestResolutionError("STATIC_SAFE_RELEASE_INVALID")
        roles = {approval.authority_role for approval in release.approvals}
        if not self._required_approval_roles.issubset(roles):
            raise ReleaseManifestResolutionError("STATIC_SAFE_APPROVAL_INVALID")
        for approval in release.approvals:
            if (
                await self._digest_reader.sha256(approval.evidence_ref) != approval.evidence_sha256
                or not await self._evidence_verifier.verify_static_safe_approval(
                    approval,
                    release,
                )
            ):
                raise ReleaseManifestResolutionError("STATIC_SAFE_APPROVAL_INVALID")

    async def _verify_live_controls(self, item: AssistantReleaseManifest) -> None:
        controls = (
            (
                item.kill_switch_registry_ref,
                item.kill_switch_registry_sha256,
            ),
            (
                item.rollback_drill_evidence_ref,
                item.rollback_drill_evidence_sha256,
            ),
        )
        for reference, expected in controls:
            if await self._digest_reader.sha256(reference) != expected:
                raise ReleaseManifestResolutionError("LIVE_CONTROL_INVALID")
        if not await self._evidence_verifier.verify_live_controls(item):
            raise ReleaseManifestResolutionError("LIVE_CONTROL_INVALID")
