import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

_ALLOWED_ARTIFACT_SCHEMES = frozenset(
    {
        "approval",
        "artifact",
        "dataset",
        "drill",
        "evaluation",
        "evaluator",
        "graph",
        "history",
        "knowledge",
        "model",
        "policy",
        "prompt",
        "retriever",
        "safe-release",
        "schema",
        "tools",
        "validator",
    }
)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _validate_artifact_ref(value: str, expected_scheme: str | None = None) -> None:
    scheme, separator, payload = value.partition("://")
    if (
        not value.strip()
        or len(value) > 255
        or any(ord(character) < 32 for character in value)
        or any(character in value for character in ("?", "#", "@", "\\"))
        or not separator
        or not payload.strip("/")
        or scheme not in _ALLOWED_ARTIFACT_SCHEMES
        or (expected_scheme is not None and scheme != expected_scheme)
    ):
        raise ValueError("release artifact reference must use an approved opaque scheme")


@dataclass(frozen=True, slots=True)
class AssistantReleaseArtifacts:
    model_deployment_ref: str
    model_deployment_sha256: str
    prompt_ref: str
    prompt_sha256: str
    output_schema_ref: str
    output_schema_sha256: str
    graph_ref: str
    graph_sha256: str
    policy_ref: str
    policy_sha256: str
    validator_ref: str
    validator_sha256: str
    knowledge_profile_ref: str
    knowledge_profile_sha256: str
    retriever_ref: str
    retriever_sha256: str
    embedding_generation_digest: str
    dataset_release_refs: tuple[str, ...]
    dataset_release_sha256: tuple[str, ...]
    tool_registry_ref: str
    tool_registry_sha256: str
    evaluator_ref: str
    evaluator_sha256: str

    def __post_init__(self) -> None:
        pairs = self.artifact_digests()
        if len(pairs) > 42:
            raise ValueError("release artifact collection exceeds local limit")
        expected = (
            (self.model_deployment_ref, "model"),
            (self.prompt_ref, "prompt"),
            (self.output_schema_ref, "schema"),
            (self.graph_ref, "graph"),
            (self.policy_ref, "policy"),
            (self.validator_ref, "validator"),
            (self.knowledge_profile_ref, "knowledge"),
            (self.retriever_ref, "retriever"),
            (self.tool_registry_ref, "tools"),
            (self.evaluator_ref, "evaluator"),
        ) + tuple((reference, "dataset") for reference in self.dataset_release_refs)
        for reference, scheme in expected:
            _validate_artifact_ref(reference, scheme)
        if len({reference for reference, _ in pairs}) != len(pairs):
            raise ValueError("release artifact references must be globally unique")
        for _, digest in pairs:
            if not _is_sha256(digest):
                raise ValueError("release artifact digests must use SHA-256 hex")
        if not _is_sha256(self.embedding_generation_digest):
            raise ValueError("embedding generation identity must use SHA-256 hex")
        if (
            not self.dataset_release_refs
            or len(self.dataset_release_refs) > 32
            or len(self.dataset_release_refs) != len(self.dataset_release_sha256)
            or len(set(self.dataset_release_refs)) != len(self.dataset_release_refs)
        ):
            raise ValueError("dataset release references and digests must align")

    def artifact_digests(self) -> tuple[tuple[str, str], ...]:
        fixed = (
            (self.model_deployment_ref, self.model_deployment_sha256),
            (self.prompt_ref, self.prompt_sha256),
            (self.output_schema_ref, self.output_schema_sha256),
            (self.graph_ref, self.graph_sha256),
            (self.policy_ref, self.policy_sha256),
            (self.validator_ref, self.validator_sha256),
            (self.knowledge_profile_ref, self.knowledge_profile_sha256),
            (self.retriever_ref, self.retriever_sha256),
            (self.tool_registry_ref, self.tool_registry_sha256),
            (self.evaluator_ref, self.evaluator_sha256),
        )
        return fixed + tuple(
            zip(
                self.dataset_release_refs,
                self.dataset_release_sha256,
                strict=True,
            )
        )


@dataclass(frozen=True, slots=True)
class AssistantReleaseCandidate:
    candidate_id: str
    assistant_profile: str
    environment: str
    requested_by_subject: str
    gate_policy_revision: str
    gate_policy_sha256: str
    artifacts: AssistantReleaseArtifacts

    def __post_init__(self) -> None:
        if any(
            not value.strip() or len(value) > 160
            for value in (
                self.candidate_id,
                self.assistant_profile,
                self.environment,
                self.requested_by_subject,
                self.gate_policy_revision,
            )
        ):
            raise ValueError("release candidate identity must be non-empty and bounded")
        if self.environment not in {"development", "test", "staging", "production"}:
            raise ValueError("release environment is not supported")
        if not _is_sha256(self.gate_policy_sha256):
            raise ValueError("release gate policy must use SHA-256 hex")

    @property
    def content_sha256(self) -> str:
        payload = {
            "artifacts": {
                "embeddingGenerationDigest": self.artifacts.embedding_generation_digest,
                "modelDeployment": {
                    "ref": self.artifacts.model_deployment_ref,
                    "sha256": self.artifacts.model_deployment_sha256,
                },
                "prompt": {
                    "ref": self.artifacts.prompt_ref,
                    "sha256": self.artifacts.prompt_sha256,
                },
                "outputSchema": {
                    "ref": self.artifacts.output_schema_ref,
                    "sha256": self.artifacts.output_schema_sha256,
                },
                "graph": {
                    "ref": self.artifacts.graph_ref,
                    "sha256": self.artifacts.graph_sha256,
                },
                "policy": {
                    "ref": self.artifacts.policy_ref,
                    "sha256": self.artifacts.policy_sha256,
                },
                "validator": {
                    "ref": self.artifacts.validator_ref,
                    "sha256": self.artifacts.validator_sha256,
                },
                "knowledgeProfile": {
                    "ref": self.artifacts.knowledge_profile_ref,
                    "sha256": self.artifacts.knowledge_profile_sha256,
                },
                "retriever": {
                    "ref": self.artifacts.retriever_ref,
                    "sha256": self.artifacts.retriever_sha256,
                },
                "datasets": [
                    {"ref": reference, "sha256": digest}
                    for reference, digest in zip(
                        self.artifacts.dataset_release_refs,
                        self.artifacts.dataset_release_sha256,
                        strict=True,
                    )
                ],
                "toolRegistry": {
                    "ref": self.artifacts.tool_registry_ref,
                    "sha256": self.artifacts.tool_registry_sha256,
                },
                "evaluator": {
                    "ref": self.artifacts.evaluator_ref,
                    "sha256": self.artifacts.evaluator_sha256,
                },
            },
            "assistantProfile": self.assistant_profile,
            "candidateId": self.candidate_id,
            "environment": self.environment,
            "gatePolicyRevision": self.gate_policy_revision,
            "gatePolicySha256": self.gate_policy_sha256,
            "requestedBySubject": self.requested_by_subject,
        }
        canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        return sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovalEvidence:
    approval_id: str
    authority_role: str
    approver_subject: str
    approved_at: datetime
    evidence_ref: str
    evidence_sha256: str
    target_candidate_sha256: str
    assistant_profile: str
    environment: str

    def __post_init__(self) -> None:
        if any(
            not value.strip() or len(value) > 160
            for value in (
                self.approval_id,
                self.authority_role,
                self.approver_subject,
                self.assistant_profile,
                self.environment,
            )
        ):
            raise ValueError("approval identity must be non-empty and bounded")
        _validate_artifact_ref(self.evidence_ref)
        if self.approved_at.tzinfo is None:
            raise ValueError("approval timestamp must include a timezone")
        if not _is_sha256(self.evidence_sha256) or not _is_sha256(self.target_candidate_sha256):
            raise ValueError("approval evidence must use SHA-256 hex")


@dataclass(frozen=True, slots=True)
class AutomatedGateEvidence:
    evidence_ref: str
    evidence_sha256: str
    target_candidate_sha256: str
    assistant_profile: str
    environment: str
    gate_policy_revision: str
    gate_policy_sha256: str

    def __post_init__(self) -> None:
        _validate_artifact_ref(self.evidence_ref)
        if any(
            not value.strip() or len(value) > 160
            for value in (
                self.assistant_profile,
                self.environment,
                self.gate_policy_revision,
            )
        ):
            raise ValueError("automated gate identity must be bounded")
        if any(
            not _is_sha256(value)
            for value in (
                self.evidence_sha256,
                self.target_candidate_sha256,
                self.gate_policy_sha256,
            )
        ):
            raise ValueError("automated gate evidence must use SHA-256 hex")


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    evidence_ref: str
    evidence_sha256: str
    target_activation_core_sha256: str

    def __post_init__(self) -> None:
        _validate_artifact_ref(self.evidence_ref, "approval")
        if not _is_sha256(self.evidence_sha256) or not _is_sha256(
            self.target_activation_core_sha256
        ):
            raise ValueError("promotion evidence must use SHA-256 hex")


@dataclass(frozen=True, slots=True)
class PriorActivationRollbackTarget:
    activation_id: str
    activation_envelope_sha256: str
    candidate_id: str
    candidate_sha256: str
    assistant_profile: str
    environment: str
    eligible_history_event_ref: str
    eligible_history_event_sha256: str

    def __post_init__(self) -> None:
        if any(
            not value.strip() or len(value) > 160
            for value in (
                self.activation_id,
                self.candidate_id,
                self.assistant_profile,
                self.environment,
            )
        ):
            raise ValueError("prior activation rollback identity must be bounded")
        _validate_artifact_ref(self.eligible_history_event_ref, "history")
        for digest in (
            self.activation_envelope_sha256,
            self.candidate_sha256,
            self.eligible_history_event_sha256,
        ):
            if not _is_sha256(digest):
                raise ValueError("prior activation rollback must use SHA-256 hex")


@dataclass(frozen=True, slots=True)
class StaticSafeReleaseRollbackTarget:
    safe_release_id: str
    safe_release_ref: str
    safe_release_core_sha256: str
    approval_set_sha256: str
    safe_release_envelope_sha256: str
    assistant_profile: str
    environment: str

    def __post_init__(self) -> None:
        if any(
            not value.strip() or len(value) > 160
            for value in (
                self.safe_release_id,
                self.assistant_profile,
                self.environment,
            )
        ):
            raise ValueError("static-safe rollback identity must be bounded")
        _validate_artifact_ref(self.safe_release_ref, "safe-release")
        for digest in (
            self.safe_release_core_sha256,
            self.approval_set_sha256,
            self.safe_release_envelope_sha256,
        ):
            if not _is_sha256(digest):
                raise ValueError("static-safe rollback must use SHA-256 hex")


ReleaseRollbackTarget = PriorActivationRollbackTarget | StaticSafeReleaseRollbackTarget


@dataclass(frozen=True, slots=True)
class StaticSafeApprovalEvidence:
    approval_id: str
    authority_role: str
    approver_subject: str
    approved_at: datetime
    evidence_ref: str
    evidence_sha256: str
    target_safe_release_core_sha256: str

    def __post_init__(self) -> None:
        if any(
            not value.strip() or len(value) > 160
            for value in (
                self.approval_id,
                self.authority_role,
                self.approver_subject,
            )
        ):
            raise ValueError("static-safe approval identity must be bounded")
        if self.approved_at.tzinfo is None:
            raise ValueError("static-safe approval timestamp must include timezone")
        _validate_artifact_ref(self.evidence_ref, "approval")
        if not _is_sha256(self.evidence_sha256) or not _is_sha256(
            self.target_safe_release_core_sha256
        ):
            raise ValueError("static-safe approval evidence must use SHA-256 hex")


@dataclass(frozen=True, slots=True)
class StaticSafeRelease:
    safe_release_id: str
    safe_release_ref: str
    safe_release_core_sha256: str
    approval_set_sha256: str
    safe_release_envelope_sha256: str
    template_ref: str
    template_sha256: str
    response_policy_ref: str
    response_policy_sha256: str
    assistant_profile: str
    environment: str
    effective_at: datetime
    expires_at: datetime
    approvals: tuple[StaticSafeApprovalEvidence, ...]

    def __post_init__(self) -> None:
        target = StaticSafeReleaseRollbackTarget(
            safe_release_id=self.safe_release_id,
            safe_release_ref=self.safe_release_ref,
            safe_release_core_sha256=self.safe_release_core_sha256,
            approval_set_sha256=self.approval_set_sha256,
            safe_release_envelope_sha256=self.safe_release_envelope_sha256,
            assistant_profile=self.assistant_profile,
            environment=self.environment,
        )
        del target
        _validate_artifact_ref(self.template_ref, "prompt")
        _validate_artifact_ref(self.response_policy_ref, "policy")
        if not _is_sha256(self.template_sha256) or not _is_sha256(self.response_policy_sha256):
            raise ValueError("static-safe artifacts must use SHA-256 hex")
        if self.effective_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("static-safe effective window must include timezone")
        if self.expires_at <= self.effective_at:
            raise ValueError("static-safe expiry must be after effective time")
        if not 2 <= len(self.approvals) <= 8:
            raise ValueError("static-safe release requires bounded dual approval")
        if len({item.approval_id for item in self.approvals}) != len(self.approvals):
            raise ValueError("static-safe approval IDs must be unique")
        if len({item.approver_subject for item in self.approvals}) != len(self.approvals):
            raise ValueError("static-safe approvers must be distinct")
        if any(
            item.target_safe_release_core_sha256 != self.safe_release_core_sha256
            or item.approved_at > self.effective_at
            for item in self.approvals
        ):
            raise ValueError("static-safe approval binding is invalid")

    def rollback_target(self) -> StaticSafeReleaseRollbackTarget:
        return StaticSafeReleaseRollbackTarget(
            safe_release_id=self.safe_release_id,
            safe_release_ref=self.safe_release_ref,
            safe_release_core_sha256=self.safe_release_core_sha256,
            approval_set_sha256=self.approval_set_sha256,
            safe_release_envelope_sha256=self.safe_release_envelope_sha256,
            assistant_profile=self.assistant_profile,
            environment=self.environment,
        )


class ReleaseActivationState(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class AssistantReleaseManifest:
    """Resolved activation record around an immutable release candidate."""

    activation_id: str
    candidate: AssistantReleaseCandidate
    state: ReleaseActivationState
    automated_gate: AutomatedGateEvidence
    approvals: tuple[ApprovalEvidence, ...]
    effective_at: datetime
    expires_at: datetime
    kill_switch_registry_ref: str
    kill_switch_registry_sha256: str
    rollback_drill_evidence_ref: str
    rollback_drill_evidence_sha256: str
    activation_core_sha256: str
    activation_envelope_sha256: str
    promotion_evidence: PromotionEvidence
    rollback_target: ReleaseRollbackTarget
    static_safe_release: StaticSafeRelease | None = None

    def __post_init__(self) -> None:
        if not self.activation_id.strip() or len(self.activation_id) > 160:
            raise ValueError("release activation identity must be bounded")
        if self.effective_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("release effective window must include timezone")
        if self.expires_at <= self.effective_at:
            raise ValueError("release expiry must be after effective time")
        if not self.approvals or len(self.approvals) > 8:
            raise ValueError("release approvals must be non-empty and bounded")
        if not _is_sha256(self.activation_core_sha256) or not _is_sha256(
            self.activation_envelope_sha256
        ):
            raise ValueError("activation authority must use SHA-256 hex")
        if self.promotion_evidence.target_activation_core_sha256 != self.activation_core_sha256:
            raise ValueError("promotion evidence must bind the activation core")
        if isinstance(self.rollback_target, PriorActivationRollbackTarget):
            if (
                self.rollback_target.candidate_id == self.candidate.candidate_id
                or self.rollback_target.assistant_profile != self.candidate.assistant_profile
                or self.rollback_target.environment != self.candidate.environment
            ):
                raise ValueError("prior activation rollback binding is invalid")
        elif (
            self.static_safe_release is None
            or self.rollback_target != self.static_safe_release.rollback_target()
            or self.rollback_target.assistant_profile != self.candidate.assistant_profile
            or self.rollback_target.environment != self.candidate.environment
            or self.static_safe_release.effective_at > self.effective_at
            or self.static_safe_release.expires_at < self.expires_at
        ):
            raise ValueError("static-safe rollback binding is invalid")
        for reference in (
            self.kill_switch_registry_ref,
            self.rollback_drill_evidence_ref,
        ):
            _validate_artifact_ref(reference)
        for digest in (
            self.kill_switch_registry_sha256,
            self.rollback_drill_evidence_sha256,
        ):
            if not _is_sha256(digest):
                raise ValueError("activation controls must use SHA-256 hex")

    @property
    def content_sha256(self) -> str:
        """Compatibility alias: approvals always target the immutable candidate."""
        return self.candidate.content_sha256


@dataclass(frozen=True, slots=True)
class AIReleaseCandidate:
    """Legacy evaluation input retained until callers migrate to the manifest."""

    release_id: str
    owner_ref: str
    model_revision: str
    prompt_revision: str
    embedding_revision: str
    retriever_revision: str
    dataset_revisions: tuple[str, ...]
    tool_registry_revision: str
    rollback_ref: str
    kill_switch_available: bool
    citation_correctness: float
    acl_leakage_count: int
    pii_leakage_count: int
