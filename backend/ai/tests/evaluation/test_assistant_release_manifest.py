from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.governance.application.release_resolver import (
    ArtifactDigestReader,
    ReleaseEvidenceVerifier,
    ReleaseManifestResolutionError,
    ReleaseManifestResolver,
    ReleaseManifestStore,
)
from app.modules.governance.domain.release_manifest import (
    ApprovalEvidence,
    AssistantReleaseArtifacts,
    AssistantReleaseCandidate,
    AssistantReleaseManifest,
    AutomatedGateEvidence,
    PromotionEvidence,
    ReleaseActivationState,
    StaticSafeApprovalEvidence,
    StaticSafeRelease,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)


def digest(character: str) -> str:
    return character * 64


def candidate(candidate_id: str = "candidate-2", character: str = "a") -> AssistantReleaseCandidate:
    return AssistantReleaseCandidate(
        candidate_id=candidate_id,
        assistant_profile="customer-assistant",
        environment="staging",
        requested_by_subject="subject-proposer",
        gate_policy_revision="release-gate-v2",
        gate_policy_sha256=digest("e"),
        artifacts=AssistantReleaseArtifacts(
            model_deployment_ref=f"model://customer/{candidate_id}",
            model_deployment_sha256=digest(character),
            prompt_ref=f"prompt://customer/{candidate_id}",
            prompt_sha256=digest("b"),
            output_schema_ref="schema://grounded-answer/v2",
            output_schema_sha256=digest("c"),
            graph_ref="graph://customer-assistant/v2",
            graph_sha256=digest("d"),
            policy_ref="policy://customer-factual/v3",
            policy_sha256=digest("e"),
            validator_ref="validator://claim-support/v2",
            validator_sha256=digest("f"),
            knowledge_profile_ref="knowledge://public-customer/v4",
            knowledge_profile_sha256=digest("1"),
            retriever_ref="retriever://hybrid/v4",
            retriever_sha256=digest("2"),
            embedding_generation_digest=digest("3"),
            dataset_release_refs=("dataset://gold/v2",),
            dataset_release_sha256=(digest("4"),),
            tool_registry_ref="tools://customer-read-only/v2",
            tool_registry_sha256=digest("6"),
            evaluator_ref="evaluator://assistant-release/v2",
            evaluator_sha256=digest("7"),
        ),
    )


def manifest() -> AssistantReleaseManifest:
    item = candidate()
    safe_core = digest("0")
    static_safe = StaticSafeRelease(
        safe_release_id="static-safe-1",
        safe_release_ref="safe-release://customer/static-safe-1",
        safe_release_core_sha256=safe_core,
        approval_set_sha256=digest("1"),
        safe_release_envelope_sha256=digest("2"),
        template_ref="prompt://customer/static-safe-1",
        template_sha256=digest("3"),
        response_policy_ref="policy://customer/static-safe-1",
        response_policy_sha256=digest("4"),
        assistant_profile=item.assistant_profile,
        environment=item.environment,
        effective_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=8),
        approvals=tuple(
            StaticSafeApprovalEvidence(
                approval_id=f"safe-approval-{role}",
                authority_role=role,
                approver_subject=f"safe-subject-{role}",
                approved_at=NOW - timedelta(days=2),
                evidence_ref=f"approval://static-safe/{role}",
                evidence_sha256=digest(character),
                target_safe_release_core_sha256=safe_core,
            )
            for role, character in (("security-owner", "5"), ("release-owner", "6"))
        ),
    )
    activation_core = digest("7")
    return AssistantReleaseManifest(
        activation_id="activation-2",
        candidate=item,
        state=ReleaseActivationState.ACTIVE,
        automated_gate=AutomatedGateEvidence(
            evidence_ref="evaluation://assistant-release/2",
            evidence_sha256=digest("8"),
            target_candidate_sha256=item.content_sha256,
            assistant_profile=item.assistant_profile,
            environment=item.environment,
            gate_policy_revision=item.gate_policy_revision,
            gate_policy_sha256=item.gate_policy_sha256,
        ),
        approvals=tuple(
            ApprovalEvidence(
                approval_id=f"approval-{role}",
                authority_role=role,
                approver_subject=f"subject-{role}",
                approved_at=NOW - timedelta(hours=1),
                evidence_ref=f"approval://{role}/2",
                evidence_sha256=digest(character),
                target_candidate_sha256=item.content_sha256,
                assistant_profile=item.assistant_profile,
                environment=item.environment,
            )
            for role, character in (("security-owner", "9"), ("release-owner", "a"))
        ),
        effective_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(days=7),
        kill_switch_registry_ref="tools://kill-switches/v2",
        kill_switch_registry_sha256=digest("5"),
        rollback_drill_evidence_ref="drill://rollback/2",
        rollback_drill_evidence_sha256=digest("6"),
        activation_core_sha256=activation_core,
        activation_envelope_sha256=digest("8"),
        promotion_evidence=PromotionEvidence(
            evidence_ref="approval://promotion/2",
            evidence_sha256=digest("9"),
            target_activation_core_sha256=activation_core,
        ),
        rollback_target=static_safe.rollback_target(),
        static_safe_release=static_safe,
    )


class MemoryStore(ReleaseManifestStore):
    def __init__(self, item: AssistantReleaseManifest) -> None:
        self.item = item
        self.candidates = {
            item.candidate.candidate_id: item.candidate,
            "candidate-1": candidate("candidate-1", "0"),
        }

    async def get(self, activation_id: str) -> AssistantReleaseManifest | None:
        return self.item if activation_id == self.item.activation_id else None

    async def get_candidate(self, candidate_id: str) -> AssistantReleaseCandidate | None:
        return self.candidates.get(candidate_id)


class MemoryDigestReader(ArtifactDigestReader):
    def __init__(self, item: AssistantReleaseManifest) -> None:
        self.values = dict(item.candidate.artifacts.artifact_digests())
        self.values[item.automated_gate.evidence_ref] = item.automated_gate.evidence_sha256
        self.values[item.kill_switch_registry_ref] = item.kill_switch_registry_sha256
        self.values[item.rollback_drill_evidence_ref] = item.rollback_drill_evidence_sha256
        self.values[item.promotion_evidence.evidence_ref] = item.promotion_evidence.evidence_sha256
        if item.static_safe_release is not None:
            safe = item.static_safe_release
            self.values[safe.safe_release_ref] = safe.safe_release_envelope_sha256
            self.values[safe.template_ref] = safe.template_sha256
            self.values[safe.response_policy_ref] = safe.response_policy_sha256
            self.values.update(
                {approval.evidence_ref: approval.evidence_sha256 for approval in safe.approvals}
            )
        self.values.update(
            {approval.evidence_ref: approval.evidence_sha256 for approval in item.approvals}
        )

    async def sha256(self, artifact_ref: str) -> str | None:
        return self.values.get(artifact_ref)


class AcceptingVerifier(ReleaseEvidenceVerifier):
    async def verify_approval(
        self, approval: ApprovalEvidence, candidate: AssistantReleaseCandidate
    ) -> bool:
        return True

    async def verify_automated_gate(
        self, evidence: AutomatedGateEvidence, candidate: AssistantReleaseCandidate
    ) -> bool:
        return True

    async def verify_live_controls(self, manifest: AssistantReleaseManifest) -> bool:
        return True

    async def verify_static_safe_approval(
        self,
        approval: StaticSafeApprovalEvidence,
        release: StaticSafeRelease,
    ) -> bool:
        return True

    async def verify_promotion(
        self,
        evidence: PromotionEvidence,
        manifest: AssistantReleaseManifest,
    ) -> bool:
        return True


def resolver(item: AssistantReleaseManifest) -> ReleaseManifestResolver:
    return ReleaseManifestResolver(
        store=MemoryStore(item),
        digest_reader=MemoryDigestReader(item),
        evidence_verifier=AcceptingVerifier(),
        required_approval_roles=("security-owner", "release-owner"),
        clock=lambda: NOW,
    )


async def resolve(item: AssistantReleaseManifest) -> AssistantReleaseManifest:
    return await resolver(item).resolve(
        activation_id=item.activation_id,
        expected_candidate_sha256=item.candidate.content_sha256,
        assistant_profile="customer-assistant",
        environment="staging",
    )


@pytest.mark.asyncio
async def test_resolver_accepts_bound_release_and_mutable_state_is_not_candidate_identity() -> None:
    item = manifest()
    original_digest = item.candidate.content_sha256

    assert await resolve(item) == item
    revoked = replace(item, state=ReleaseActivationState.REVOKED)
    assert revoked.candidate.content_sha256 == original_digest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ({"state": ReleaseActivationState.REVOKED}, "RELEASE_REVOKED"),
        ({"effective_at": NOW + timedelta(minutes=1)}, "RELEASE_NOT_EFFECTIVE"),
        ({"expires_at": NOW - timedelta(seconds=1)}, "RELEASE_EXPIRED"),
    ],
)
async def test_resolver_fails_closed_on_activation_state(
    mutation: dict[str, object], code: str
) -> None:
    item = replace(manifest(), **mutation)
    with pytest.raises(ReleaseManifestResolutionError) as captured:
        await resolve(item)
    assert captured.value.code == code


@pytest.mark.asyncio
async def test_resolver_rejects_replayed_approval_or_gate() -> None:
    item = manifest()
    wrong = digest("0")
    for changed, expected in (
        (
            replace(
                item,
                approvals=(replace(item.approvals[0], target_candidate_sha256=wrong),)
                + item.approvals[1:],
            ),
            "APPROVAL_EVIDENCE_INVALID",
        ),
        (
            replace(
                item,
                automated_gate=replace(item.automated_gate, target_candidate_sha256=wrong),
            ),
            "AUTOMATED_GATE_INVALID",
        ),
    ):
        with pytest.raises(ReleaseManifestResolutionError) as captured:
            await resolve(changed)
        assert captured.value.code == expected


@pytest.mark.asyncio
async def test_resolver_checks_profile_before_artifact_io() -> None:
    item = manifest()
    with pytest.raises(ReleaseManifestResolutionError) as captured:
        await resolver(item).resolve(
            activation_id=item.activation_id,
            expected_candidate_sha256=item.candidate.content_sha256,
            assistant_profile="employee-assistant",
            environment="staging",
        )
    assert captured.value.code == "ASSISTANT_PROFILE_MISMATCH"


@pytest.mark.asyncio
async def test_resolver_loads_and_verifies_real_rollback_candidate() -> None:
    item = manifest()
    assert item.static_safe_release is not None
    digest_reader = MemoryDigestReader(item)
    digest_reader.values[item.static_safe_release.safe_release_ref] = digest("f")
    release_resolver = ReleaseManifestResolver(
        store=MemoryStore(item),
        digest_reader=digest_reader,
        evidence_verifier=AcceptingVerifier(),
        required_approval_roles=("security-owner", "release-owner"),
        clock=lambda: NOW,
    )
    with pytest.raises(ReleaseManifestResolutionError) as captured:
        await release_resolver.resolve(
            activation_id=item.activation_id,
            expected_candidate_sha256=item.candidate.content_sha256,
            assistant_profile=item.candidate.assistant_profile,
            environment=item.candidate.environment,
        )
    assert captured.value.code == "STATIC_SAFE_RELEASE_INVALID"


def test_release_rejects_arbitrary_network_artifact_reference() -> None:
    with pytest.raises(ValueError, match="approved opaque scheme"):
        replace(candidate().artifacts, prompt_ref="https://attacker.example/prompt")


def test_candidate_digest_binds_each_artifact_to_its_semantic_role() -> None:
    item = candidate()
    with pytest.raises(ValueError, match="approved opaque scheme"):
        replace(
            item.artifacts,
            prompt_ref=item.artifacts.policy_ref,
            prompt_sha256=item.artifacts.policy_sha256,
            policy_ref=item.artifacts.prompt_ref,
            policy_sha256=item.artifacts.prompt_sha256,
        )
