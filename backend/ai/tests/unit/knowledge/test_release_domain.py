from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.modules.knowledge.domain import (
    ApprovedKnowledgeSource,
    InvalidKnowledgeTransition,
    KnowledgeActor,
    KnowledgeAuthorizationRejected,
    KnowledgeRelease,
    KnowledgeScope,
    SourceApprovalRejected,
    source_set_digest,
)

NOW = datetime(2026, 7, 25, tzinfo=UTC)
INDEX_GENERATION_ID = UUID("00000000-0000-4000-8000-000000000111")


def scope(*, profile: str = "public_customer") -> KnowledgeScope:
    return KnowledgeScope(
        domain="warranty",
        locale="vi-VN",
        assistant_profile=profile,
        acl_namespace=f"{profile}:warranty:vi-VN",
    )  # type: ignore[arg-type]


def source(
    *,
    classification: str = "public",
    purposes: tuple[str, ...] = ("knowledge",),
    rights_approved: bool = True,
    deletion_fenced: bool = False,
) -> ApprovedKnowledgeSource:
    return ApprovedKnowledgeSource(
        source_id="warranty-policy",
        source_type="internal-content",
        locator_ref="gs://approved-knowledge/warranty-policy/v1.pdf",
        owner_role="content-owner",
        custodian_role="knowledge-steward",
        version="v1",
        source_revision="revision-1",
        checksum_sha256="a" * 64,
        registry_document_hash="b" * 64,
        approved_purposes=purposes,
        acl_namespaces=("public_customer:warranty:vi-VN",),
        classification=classification,
        rights_approved=rights_approved,
        rights_license_id="LicenseRef-Internal-1",
        rights_commercial_use="permitted" if rights_approved else "prohibited",
        rights_derivatives="permitted" if rights_approved else "prohibited",
        rights_redistribution="prohibited",
        rights_access_conditions="Approved customer-support retrieval only",
        rights_evidence_urls=("urn:vfbiz:evidence:rights-1",),
        rights_legal_review="approved" if rights_approved else "rejected",
        retention_policy_id="policy-365d",
        retention_duration_days=365,
        deletion_method="crypto-erase",
        approval_evidence_hashes=("c" * 64,),
        review_date=NOW + timedelta(days=30),
        deletion_fenced=deletion_fenced,
    )  # type: ignore[arg-type]


def candidate(*, proposer: str = "maker-01") -> KnowledgeRelease:
    sources = (source(),)
    return KnowledgeRelease(
        scope=scope(),
        criticality="critical",
        sources=sources,
        source_set_hash=source_set_digest(sources),
        transform_revision="transform-v1",
        chunking_revision="chunk-v1",
        index_generation_id=INDEX_GENERATION_ID,
        embedding_revision="embed-v1",
        embedding_dimension=1536,
        retriever_revision="retriever-v1",
        policy_revision="policy-v1",
        index_checksum="d" * 64,
        proposer_ref=proposer,
        effective_at=NOW,
        freshness_expires_at=NOW + timedelta(days=30),
        barrier_generation=3,
        version=1,
    )


def approver(*, actor_ref: str = "checker-01") -> KnowledgeActor:
    return KnowledgeActor(
        actor_ref=actor_ref,
        kind="human",
        capability="knowledge.release.approve",
        entitlement_revision="entitlement-v2",
        mfa_verified=True,
    )


def evaluated() -> KnowledgeRelease:
    return candidate().record_evaluation(
        run_ref="evaluation-run-01",
        suite_revision="golden-v1",
        evidence_hashes=("e" * 64,),
    )


def test_approved_source_must_match_purpose_rights_acl_and_public_classification() -> None:
    source().assert_eligible(scope(), at=NOW)

    with pytest.raises(SourceApprovalRejected, match="knowledge"):
        source(purposes=("red-team",)).assert_eligible(scope(), at=NOW)
    with pytest.raises(SourceApprovalRejected, match="rights"):
        source(rights_approved=False).assert_eligible(scope(), at=NOW)
    with pytest.raises(SourceApprovalRejected, match="rights"):
        source(deletion_fenced=True).assert_eligible(scope(), at=NOW)
    with pytest.raises(SourceApprovalRejected, match="public"):
        source(classification="internal").assert_eligible(scope(), at=NOW)


def test_release_requires_exact_source_set_hash() -> None:
    with pytest.raises(ValueError, match="source set hash"):
        KnowledgeRelease.model_validate(candidate().model_dump() | {"source_set_hash": "f" * 64})


def test_source_digest_pins_full_rights_and_governance_projection() -> None:
    approved = source()
    changed_rights = approved.model_copy(update={"rights_redistribution": "permitted"})
    changed_owner = approved.model_copy(update={"owner_role": "different-owner"})

    assert changed_rights.digest() != approved.digest()
    assert changed_owner.digest() != approved.digest()


def test_release_manifest_hash_detects_pinned_input_tampering() -> None:
    release = candidate()
    with pytest.raises(ValueError, match="manifest hash"):
        KnowledgeRelease.model_validate(
            release.model_dump()
            | {"embedding_revision": "embed-v2", "manifest_hash": release.manifest_hash}
        )


def test_release_manifest_pins_embedding_index_generation() -> None:
    release = candidate()

    with pytest.raises(ValueError, match="manifest hash"):
        KnowledgeRelease.model_validate(
            release.model_dump()
            | {
                "index_generation_id": UUID("00000000-0000-4000-8000-000000000112"),
                "manifest_hash": release.manifest_hash,
            }
        )


def test_evaluation_and_maker_checker_approval_are_bounded() -> None:
    release = evaluated()
    approved = release.approve(
        actor=approver(),
        source_set_hash=release.source_set_hash,
        evidence_hash="f" * 64,
    )

    assert approved.status == "ready"
    assert approved.approver_ref == "checker-01"
    assert approved.version == 3

    with pytest.raises(KnowledgeAuthorizationRejected, match="own release"):
        release.approve(
            actor=approver(actor_ref="maker-01"),
            source_set_hash=release.source_set_hash,
            evidence_hash="f" * 64,
        )


def test_ingestion_service_cannot_approve_and_snapshot_drift_fails_closed() -> None:
    release = evaluated()
    service = approver().model_copy(update={"kind": "ingestion_service", "mfa_verified": False})

    with pytest.raises(KnowledgeAuthorizationRejected, match="human authority"):
        release.approve(
            actor=service,
            source_set_hash=release.source_set_hash,
            evidence_hash="f" * 64,
        )
    with pytest.raises(SourceApprovalRejected, match="changed"):
        release.approve(
            actor=approver(),
            source_set_hash="0" * 64,
            evidence_hash="f" * 64,
        )


def test_invalid_transition_and_active_tombstone_are_rejected() -> None:
    with pytest.raises(InvalidKnowledgeTransition, match="candidate"):
        evaluated().record_evaluation(
            run_ref="run-2",
            suite_revision="suite-2",
            evidence_hashes=("a" * 64,),
        )

    active = (
        evaluated()
        .approve(
            actor=approver(),
            source_set_hash=evaluated().source_set_hash,
            evidence_hash="f" * 64,
        )
        .model_copy(update={"status": "active"})
    )
    with pytest.raises(InvalidKnowledgeTransition, match="fenced"):
        active.tombstone()
