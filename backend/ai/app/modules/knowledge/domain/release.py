import hashlib
import json
from datetime import datetime
from typing import Literal, Self
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.knowledge.domain.errors import (
    InvalidKnowledgeTransition,
    KnowledgeAuthorizationRejected,
    SourceApprovalRejected,
)

AssistantProfile = Literal["public_customer", "authenticated_customer"]
KnowledgeCriticality = Literal["critical", "non_critical"]
KnowledgeReleaseStatus = Literal[
    "candidate",
    "evaluated",
    "ready",
    "active",
    "superseded",
    "rejected",
    "tombstoned",
]
BarrierState = Literal["clear", "syncing", "blocked"]
ActorKind = Literal["human", "ingestion_service", "system"]
SourceType = Literal[
    "first-party-content",
    "internal-content",
    "public-dataset",
    "synthetic",
    "customer-derived",
]
KnowledgePurpose = Literal[
    "knowledge",
    "retrieval-evaluation",
    "intent-ood",
    "conversation-quality",
    "tool-evaluation",
    "refusal-safety",
    "red-team",
    "state-resilience",
    "multimodal",
]

_REVISION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$"
_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_DIGEST_PATTERN = r"^[a-f0-9]{64}$"


class KnowledgeScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: str = Field(pattern=_SLUG_PATTERN, max_length=80)
    locale: Literal["vi", "en", "vi-VN", "en-US"]
    assistant_profile: AssistantProfile
    acl_namespace: str = Field(
        pattern=(
            r"^(public_customer|authenticated_customer):"
            r"[a-z0-9]+(?:-[a-z0-9]+)*:(vi|en)(?:-[A-Z]{2})?$"
        ),
        max_length=160,
    )

    @model_validator(mode="after")
    def require_profile_namespace(self) -> Self:
        if not self.acl_namespace.startswith(f"{self.assistant_profile}:"):
            raise ValueError("ACL namespace must match assistant profile")
        return self


class ApprovedKnowledgeSource(BaseModel):
    """Immutable read model projected from an approved Source Register v2 entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(pattern=_SLUG_PATTERN, max_length=160)
    source_type: SourceType
    locator_ref: str = Field(min_length=1, max_length=255)
    owner_role: str = Field(pattern=_REVISION_PATTERN)
    custodian_role: str = Field(pattern=_REVISION_PATTERN)
    version: str = Field(pattern=_REVISION_PATTERN)
    source_revision: str = Field(pattern=_REVISION_PATTERN)
    checksum_sha256: str = Field(pattern=_DIGEST_PATTERN)
    registry_document_hash: str = Field(pattern=_DIGEST_PATTERN)
    approved_purposes: tuple[KnowledgePurpose, ...] = Field(min_length=1, max_length=16)
    acl_namespaces: tuple[str, ...] = Field(min_length=1, max_length=32)
    classification: Literal["public", "internal", "confidential", "restricted"]
    rights_approved: bool
    rights_license_id: str | None = Field(default=None, max_length=160)
    rights_commercial_use: Literal["unknown", "permitted", "prohibited"]
    rights_derivatives: Literal["unknown", "permitted", "prohibited"]
    rights_redistribution: Literal["unknown", "permitted", "prohibited"]
    rights_access_conditions: str = Field(max_length=2_000)
    rights_evidence_urls: tuple[str, ...] = Field(max_length=32)
    rights_legal_review: Literal["not-reviewed", "pending", "approved", "rejected"]
    retention_policy_id: str = Field(pattern=_REVISION_PATTERN)
    retention_duration_days: int = Field(strict=True, ge=1, le=36_500)
    deletion_method: str = Field(min_length=1, max_length=160)
    approval_evidence_hashes: tuple[str, ...] = Field(min_length=1, max_length=32)
    review_date: datetime
    deletion_fenced: bool = False

    @model_validator(mode="after")
    def validate_approval_shape(self) -> Self:
        if self.review_date.tzinfo is None:
            raise ValueError("source review_date must include a timezone")
        if any(
            len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value)
            for value in self.approval_evidence_hashes
        ):
            raise ValueError("approval evidence must contain SHA-256 digests")
        if len(set(self.approved_purposes)) != len(self.approved_purposes):
            raise ValueError("approved purposes must be unique")
        if len(set(self.acl_namespaces)) != len(self.acl_namespaces):
            raise ValueError("ACL namespaces must be unique")
        if "@" in self.locator_ref or "?" in self.locator_ref or "#" in self.locator_ref:
            raise ValueError("locator_ref must not contain credentials, query, or fragment")
        for evidence_url in self.rights_evidence_urls:
            parsed = urlsplit(evidence_url)
            if parsed.scheme not in {"https", "urn"} or parsed.username or parsed.password:
                raise ValueError("rights evidence URL must be an approved credential-free URI")
        expected_rights = (
            self.rights_commercial_use == "permitted"
            and self.rights_derivatives == "permitted"
            and self.rights_legal_review == "approved"
        )
        if self.rights_approved != expected_rights:
            raise ValueError("rights_approved must match the pinned rights decision")
        return self

    def assert_eligible(self, scope: KnowledgeScope, *, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("eligibility time must include a timezone")
        if "knowledge" not in self.approved_purposes:
            raise SourceApprovalRejected("source is not approved for knowledge")
        if not self.rights_approved or self.deletion_fenced:
            raise SourceApprovalRejected("source rights are unavailable")
        if scope.acl_namespace not in self.acl_namespaces:
            raise SourceApprovalRejected("source ACL does not match release scope")
        if scope.assistant_profile == "public_customer" and self.classification != "public":
            raise SourceApprovalRejected("public release requires public classification")
        if self.review_date < at:
            raise SourceApprovalRejected("source governance review is expired")

    def digest(self) -> str:
        payload = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class KnowledgeActor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_ref: str = Field(pattern=_REVISION_PATTERN)
    kind: ActorKind
    capability: str = Field(pattern=r"^knowledge\.[a-z-]+\.[a-z-]+$")
    entitlement_revision: str = Field(pattern=_REVISION_PATTERN)
    mfa_verified: bool

    def assert_human_authority(self, required_capability: str) -> None:
        if self.kind != "human" or self.capability != required_capability or not self.mfa_verified:
            raise KnowledgeAuthorizationRejected("current human authority is required")

    def assert_evaluation_authority(self) -> None:
        if self.capability != "knowledge.release.evaluate":
            raise KnowledgeAuthorizationRejected("evaluation capability is required")
        if self.kind == "human" and not self.mfa_verified:
            raise KnowledgeAuthorizationRejected("human evaluator requires current MFA")
        if self.kind not in {"human", "system"}:
            raise KnowledgeAuthorizationRejected("ingestion worker cannot record evaluation")


class KnowledgeRelease(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    release_id: UUID = Field(default_factory=uuid4)
    scope: KnowledgeScope
    status: KnowledgeReleaseStatus = "candidate"
    criticality: KnowledgeCriticality
    sources: tuple[ApprovedKnowledgeSource, ...] = Field(min_length=1, max_length=64)
    source_set_hash: str = Field(pattern=_DIGEST_PATTERN)
    manifest_hash: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    transform_revision: str = Field(pattern=_REVISION_PATTERN)
    chunking_revision: str = Field(pattern=_REVISION_PATTERN)
    index_generation_id: UUID
    embedding_revision: str = Field(pattern=_REVISION_PATTERN)
    embedding_dimension: int = Field(strict=True, ge=1, le=65_536)
    retriever_revision: str = Field(pattern=_REVISION_PATTERN)
    policy_revision: str = Field(pattern=_REVISION_PATTERN)
    index_checksum: str = Field(pattern=_DIGEST_PATTERN)
    evaluation_run_ref: str | None = Field(default=None, pattern=_REVISION_PATTERN)
    evaluation_suite_revision: str | None = Field(default=None, pattern=_REVISION_PATTERN)
    evaluation_evidence_hashes: tuple[str, ...] = Field(default=(), max_length=64)
    proposer_ref: str = Field(pattern=_REVISION_PATTERN)
    approver_ref: str | None = Field(default=None, pattern=_REVISION_PATTERN)
    approval_source_set_hash: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    approval_evidence_hash: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    effective_at: datetime
    freshness_expires_at: datetime
    supersedes_release_id: UUID | None = None
    rollback_of_release_id: UUID | None = None
    barrier_generation: int = Field(strict=True, ge=0)
    version: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.effective_at.tzinfo is None or self.freshness_expires_at.tzinfo is None:
            raise ValueError("release timestamps must include a timezone")
        if self.freshness_expires_at <= self.effective_at:
            raise ValueError("freshness expiry must follow effective time")
        source_ids = [source.source_id for source in self.sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("release sources must be unique")
        for source in self.sources:
            try:
                source.assert_eligible(self.scope, at=self.effective_at)
            except SourceApprovalRejected as error:
                raise ValueError(
                    "release source is not eligible for the exact scope and revision"
                ) from error
        if self.source_set_hash != source_set_digest(self.sources):
            raise ValueError("source set hash does not match pinned sources")
        expected_manifest_hash = knowledge_manifest_digest(self)
        if self.manifest_hash is None:
            object.__setattr__(self, "manifest_hash", expected_manifest_hash)
        elif self.manifest_hash != expected_manifest_hash:
            raise ValueError("manifest hash does not match pinned release inputs")
        if self.status in {"evaluated", "ready", "active", "superseded"}:
            if not self.evaluation_run_ref or not self.evaluation_evidence_hashes:
                raise ValueError("evaluated release requires evaluation evidence")
        if self.status in {"ready", "active", "superseded"}:
            if (
                not self.approver_ref
                or not self.approval_evidence_hash
                or self.approval_source_set_hash != self.source_set_hash
            ):
                raise ValueError("ready release requires source-bound approval")
        return self

    def record_evaluation(
        self,
        *,
        run_ref: str,
        suite_revision: str,
        evidence_hashes: tuple[str, ...],
    ) -> Self:
        if self.status != "candidate":
            raise InvalidKnowledgeTransition("only a candidate can be evaluated")
        if not evidence_hashes:
            raise InvalidKnowledgeTransition("evaluation evidence is required")
        for evidence_hash in evidence_hashes:
            _require_digest(evidence_hash, "evaluation evidence")
        return self.model_copy(
            update={
                "status": "evaluated",
                "evaluation_run_ref": run_ref,
                "evaluation_suite_revision": suite_revision,
                "evaluation_evidence_hashes": evidence_hashes,
                "version": self.version + 1,
            }
        )

    def approve(
        self,
        *,
        actor: KnowledgeActor,
        source_set_hash: str,
        evidence_hash: str,
    ) -> Self:
        if self.status != "evaluated":
            raise InvalidKnowledgeTransition("only an evaluated release can be approved")
        actor.assert_human_authority("knowledge.release.approve")
        if actor.actor_ref == self.proposer_ref:
            raise KnowledgeAuthorizationRejected("proposer cannot approve own release")
        if source_set_hash != self.source_set_hash:
            raise SourceApprovalRejected("source snapshot changed after evaluation")
        _require_digest(evidence_hash, "approval evidence")
        return self.model_copy(
            update={
                "status": "ready",
                "approver_ref": actor.actor_ref,
                "approval_source_set_hash": source_set_hash,
                "approval_evidence_hash": evidence_hash,
                "version": self.version + 1,
            }
        )

    def tombstone(self) -> Self:
        if self.status == "active":
            raise InvalidKnowledgeTransition("active release must be fenced before tombstone")
        if self.status == "tombstoned":
            return self
        return self.model_copy(update={"status": "tombstoned", "version": self.version + 1})


class RevisionBarrier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: KnowledgeScope
    state: BarrierState
    generation: int = Field(strict=True, ge=0)
    candidate_release_id: UUID | None = None
    deadline_at: datetime | None = None
    pointer_version: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if self.state == "syncing" and (
            self.candidate_release_id is None or self.deadline_at is None
        ):
            raise ValueError("syncing barrier requires candidate and deadline")
        if self.deadline_at is not None and self.deadline_at.tzinfo is None:
            raise ValueError("barrier deadline must include a timezone")
        return self


def source_set_digest(sources: tuple[ApprovedKnowledgeSource, ...]) -> str:
    payload = sorted((source.source_id, source.digest()) for source in sources)
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def knowledge_manifest_digest(release: KnowledgeRelease) -> str:
    payload = {
        "scope": release.scope.model_dump(mode="json"),
        "criticality": release.criticality,
        "source_set_hash": release.source_set_hash,
        "transform_revision": release.transform_revision,
        "chunking_revision": release.chunking_revision,
        "index_generation_id": str(release.index_generation_id),
        "embedding_revision": release.embedding_revision,
        "embedding_dimension": release.embedding_dimension,
        "retriever_revision": release.retriever_revision,
        "policy_revision": release.policy_revision,
        "index_checksum": release.index_checksum,
        "effective_at": release.effective_at.isoformat(),
        "freshness_expires_at": release.freshness_expires_at.isoformat(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _require_digest(value: str, name: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
