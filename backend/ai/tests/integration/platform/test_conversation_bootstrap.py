import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, text, update

from app.bootstrap.conversation_graph import (
    ConversationRuntimeDependencies,
    build_conversation_runtime_dependencies,
    build_turn_runtime,
)
from app.bootstrap.release_runtime import (
    ReleaseCommitLease,
    ReleaseRuntimeUnavailable,
    ResolvedReleaseRuntime,
)
from app.modules.assistant.domain import GraphControlState, GraphOutcome
from app.modules.assistant.graph.state import ConversationGraphState
from app.modules.inference.application import (
    Citation,
    DeploymentPolicyDescriptor,
    GenerationOutcome,
    GenerationRequest,
    GenerationResult,
    GroundedAnswerPrompt,
    InferenceBudget,
    InferenceUsage,
    RetentionPolicy,
)
from app.modules.knowledge.domain import CandidateChunkMaterialization
from app.modules.knowledge.infrastructure.models import (
    EmbeddingIndexGenerationRecord,
    KnowledgeChunk,
    KnowledgeReleaseRecord,
    KnowledgeReleaseSource,
    KnowledgeRevisionPointer,
    KnowledgeSource,
)
from app.modules.knowledge.infrastructure.postgres_materialization import (
    materialization_checksum,
)
from app.platform.checkpoints import CheckpointIdentity
from app.platform.config import Settings

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)


@dataclass(frozen=True)
class IntegrationEmbedder:
    revision: str = "synthetic-embed-1536-v1"
    dimension: int = 1536

    async def embed_query(self, query: str) -> tuple[float, ...]:
        assert query == "VinFast approved active evidence"
        return (1.0, *([0.0] * 1535))

    async def aclose(self) -> None:
        return None


class ExtractiveModelMesh:
    async def generate(self, request: GenerationRequest) -> GenerationResult:
        evidence = request.evidence[0]
        return GenerationResult(
            outcome=GenerationOutcome.ANSWERED,
            answer=evidence.excerpt,
            citations=(
                Citation(
                    evidence_id=evidence.evidence_id,
                    source_uri=evidence.source_uri,
                    source_revision=evidence.source_revision,
                    title=evidence.title,
                    freshness=evidence.freshness,
                ),
            ),
            usage=InferenceUsage(
                input_tokens=12,
                output_tokens=4,
                cached_input_tokens=0,
                reasoning_tokens=0,
            ),
            estimated_cost_microusd=25,
            deployment_id="integration-deployment",
            provider_id="integration-provider",
            deployment_policy=request.required_policy,
            model_revision="integration-model-v1",
            prompt_revision=request.expected_prompt_revision,
            prompt_content_sha256=request.expected_prompt_content_sha256,
            evidence_digest="0" * 64,
            correlation_id=request.correlation_id,
            provider_request_id="integration-request-1",
        )


class FixedReleaseRuntime:
    def __init__(self, release: ResolvedReleaseRuntime) -> None:
        self.release = release

    async def resolve(self, **_: object) -> ResolvedReleaseRuntime:
        return self.release

    async def assert_current(self, *_: object, **__: object) -> None:
        return None

    async def release(self, _: ResolvedReleaseRuntime) -> None:
        return None

    async def close(self) -> None:
        return None

    async def issue_commit_lease(
        self, *_: object, **__: object
    ) -> ReleaseCommitLease:
        now = datetime.now(UTC)
        return ReleaseCommitLease(uuid4(), now, now + timedelta(seconds=15))


@pytest.mark.asyncio
async def test_composed_turn_runtime_rejects_missing_release_authority() -> None:
    settings = Settings()
    assert settings.database_url is not None
    assert settings.generation_provider == "disabled"
    from app.platform.database.session import create_engine, create_session_factory

    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    dependencies = await build_conversation_runtime_dependencies(settings, sessions)
    try:
        session_id, turn_id = uuid4(), uuid4()
        with pytest.raises(
            ReleaseRuntimeUnavailable,
            match="NO_ACTIVE_GENERATION_RELEASE",
        ):
            await build_turn_runtime(
                dependencies,
                session_id=session_id,
                turn_id=turn_id,
                subject="customer-1",
                assistant_profile="public_customer",
                locale="vi",
                graph_revision="graph-r1",
                policy_revision="policy-r1",
                knowledge_revision=str(uuid4()),
                expected_activation_id=uuid4(),
                expected_manifest_sha256="d" * 64,
                budget=InferenceBudget(
                    max_input_tokens=1_000,
                    max_output_tokens=500,
                    max_cost_microusd=10_000,
                ),
                correlation_id="corr-1",
            )
    finally:
        await dependencies.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_db_backed_turn_returns_only_active_revision_citation() -> None:
    """Exercise graph → pgvector snapshot → grounding with deterministic adapters.

    External provider credentials are deliberately excluded. This proves the
    production composition boundary and database authority without pretending
    that a synthetic fixture is Content/Legal approval for staging.
    """

    settings = Settings()
    assert settings.database_url is not None
    from app.platform.database.session import create_engine, create_session_factory

    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    async with sessions() as session, session.begin():
        for statement in (
            """
                DELETE FROM ai_knowledge_revision_pointer
                WHERE domain = 'customer-support'
                  AND locale = 'vi'
                  AND assistant_profile = 'public_customer'
                  AND acl_namespace =
                      'public_customer:customer-support:vi'
            """,
            """
                DELETE FROM ai_knowledge_chunk
                WHERE release_id IN (
                  SELECT id FROM ai_knowledge_release
                  WHERE domain = 'customer-support'
                    AND locale = 'vi'
                    AND assistant_profile = 'public_customer'
                    AND acl_namespace =
                        'public_customer:customer-support:vi'
                )
            """,
            """
                DELETE FROM ai_knowledge_release_source
                WHERE release_id IN (
                  SELECT id FROM ai_knowledge_release
                  WHERE domain = 'customer-support'
                    AND locale = 'vi'
                    AND assistant_profile = 'public_customer'
                    AND acl_namespace =
                        'public_customer:customer-support:vi'
                )
            """,
            """
                DELETE FROM ai_knowledge_release
                WHERE domain = 'customer-support'
                  AND locale = 'vi'
                  AND assistant_profile = 'public_customer'
                  AND acl_namespace =
                      'public_customer:customer-support:vi'
            """,
            """
                DELETE FROM ai_knowledge_source
                WHERE canonical_source_id LIKE 'integration-%'
            """,
        ):
            await session.execute(text(statement))
    base = await build_conversation_runtime_dependencies(settings, sessions)
    source_id, release_id, generation_id, chunk_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    now = datetime.now(UTC)
    acl_namespace = "public_customer:customer-support:vi"
    materialized = CandidateChunkMaterialization(
        chunk_id=chunk_id,
        chunk_key="approved-active",
        content_checksum="a" * 64,
        redacted_text="VinFast approved active evidence",
        embedding=(1.0, *([0.0] * 1535)),
    )
    policy = DeploymentPolicyDescriptor(
        revision="integration-policy-v1",
        profile="customer-grounded-v1",
        safety_tier="customer-factual-v1",
        residency="vn",
        retention=RetentionPolicy.ZERO_DATA_RETENTION,
        schema_revision="grounded-answer-v2",
        model_release="integration-model-v1",
        provider_project_id="integration-project",
        provider_organization_id=None,
        data_controls_approval_reference="integration-only",
        data_controls_approval_sha256="b" * 64,
        release_manifest_sha256="c" * 64,
    )
    prompt = GroundedAnswerPrompt(revision="integration-prompt-v1")
    release = ResolvedReleaseRuntime(
        activation_id=str(uuid4()),
        candidate_sha256="d" * 64,
        activation_envelope_sha256="e" * 64,
        pointer_revision=1,
        policy=policy,
        prompt=prompt,
        model_mesh=cast("object", ExtractiveModelMesh()),  # type: ignore[arg-type]
        knowledge_profile_sha256="f" * 64,
        retriever_sha256="1" * 64,
        embedding_generation_digest="2" * 64,
        validator_sha256="3" * 64,
        graph_revision="graph-r1",
        policy_revision="policy-r1",
        knowledge_revision=str(release_id),
        locale="vi",
    )
    dependencies = ConversationRuntimeDependencies(
        checkpointer_runtime=base.checkpointer_runtime,
        fence_store=base.fence_store,
        resume_claims=base.resume_claims,
        release_runtime=cast("object", FixedReleaseRuntime(release)),  # type: ignore[arg-type]
        embedding_runtime=cast("object", IntegrationEmbedder()),  # type: ignore[arg-type]
        retrieval_store=base.retrieval_store,
    )
    try:
        async with sessions() as session, session.begin():
            session.add(
                EmbeddingIndexGenerationRecord(
                    id=generation_id,
                    generation_key=f"integration:{generation_id}",
                    embedding_revision="synthetic-embed-1536-v1",
                    embedding_dimension=1536,
                    distance_metric="cosine",
                    normalization="l2",
                    instruction_digest="4" * 64,
                    tokenizer_digest="5" * 64,
                    lifecycle="ready",
                )
            )
            session.add(
                KnowledgeSource(
                    id=source_id,
                    uri="urn:vfbiz:synthetic:approved-source",
                    title="Approved integration source",
                    classification="public",
                    checksum="6" * 64,
                    source_revision="source-r1",
                    status="approved",
                    effective_at=now - timedelta(minutes=1),
                    canonical_source_id=f"integration-{source_id.hex}",
                    deletion_fenced=False,
                )
            )
            await session.flush()
            session.add(
                KnowledgeReleaseRecord(
                    id=release_id,
                    domain="customer-support",
                    locale="vi",
                    assistant_profile="public_customer",
                    acl_namespace=acl_namespace,
                    status="candidate",
                    criticality="non_critical",
                    source_set_hash="7" * 64,
                    manifest_hash="8" * 64,
                    transform_revision="transform-r1",
                    chunking_revision="chunk-r1",
                    index_generation_id=generation_id,
                    embedding_revision="synthetic-embed-1536-v1",
                    embedding_dimension=1536,
                    retriever_revision="hybrid-v1",
                    policy_revision="policy-r1",
                    index_checksum="9" * 64,
                    materialization_checksum=materialization_checksum((materialized,)),
                    materialized_chunk_count=1,
                    proposer_ref="integration-maker",
                    approver_ref="integration-checker",
                    effective_at=now - timedelta(minutes=1),
                    freshness_expires_at=now + timedelta(hours=1),
                    barrier_generation=1,
                    version=1,
                )
            )
            await session.flush()
            session.add(
                KnowledgeReleaseSource(
                    release_id=release_id,
                    source_id=source_id,
                    source_revision="source-r1",
                    checksum_sha256="6" * 64,
                    registry_document_hash="a" * 64,
                    source_snapshot_hash="b" * 64,
                    snapshot={"source_id": str(source_id)},
                )
            )
            await session.flush()
            session.add(
                KnowledgeChunk(
                    id=chunk_id,
                    release_id=release_id,
                    source_id=source_id,
                    chunk_revision="approved-active",
                    index_generation_id=generation_id,
                    embedding_revision="synthetic-embed-1536-v1",
                    embedding_dimension=1536,
                    acl_namespace=acl_namespace,
                    citation_uri="https://example.test/vinfast/approved",
                    citation_title="Approved integration source",
                    content_checksum="a" * 64,
                    redacted_text="VinFast approved active evidence",
                    acl={"namespaces": [acl_namespace]},
                    attributes={"synthetic": True},
                    embedding=[1.0, *([0.0] * 1535)],
                )
            )
        async with sessions() as session, session.begin():
            await session.execute(
                update(KnowledgeReleaseRecord)
                .where(KnowledgeReleaseRecord.id == release_id)
                .values(status="active")
            )
            session.add(
                KnowledgeRevisionPointer(
                    domain="customer-support",
                    locale="vi",
                    assistant_profile="public_customer",
                    acl_namespace=acl_namespace,
                    active_release_id=release_id,
                    candidate_release_id=None,
                    barrier_state="clear",
                    barrier_generation=1,
                    version=1,
                )
            )

        session_id, turn_id = uuid4(), uuid4()
        registered_fence = await dependencies.fence_store.advance_fencing_token(
            session_id=session_id,
            turn_id=turn_id,
            fencing_token=1,
        )
        assert registered_fence.fencing_token == 1
        assert registered_fence.cancelled is False
        runtime = await build_turn_runtime(
            dependencies,
            session_id=session_id,
            turn_id=turn_id,
            subject="integration-customer",
            assistant_profile="public_customer",
            locale="vi",
            graph_revision="graph-r1",
            policy_revision="policy-r1",
            knowledge_revision=str(release_id),
            expected_activation_id=UUID(release.activation_id),
            expected_manifest_sha256=release.candidate_sha256,
            budget=InferenceBudget(
                max_input_tokens=1_000,
                max_output_tokens=200,
                max_cost_microusd=1_000,
            ),
            correlation_id="integration-grounded-turn",
        )
        control = GraphControlState(
            graph_version="graph-r1",
            policy_revision="policy-r1",
            knowledge_revision=str(release_id),
            assistant_profile="public_customer",
            authorization_context_hash="c" * 64,
            conversation_version=1,
            fencing_token=1,
            deadline_at=now + timedelta(seconds=10),
        )
        state: ConversationGraphState = {
            "message": "VinFast approved active evidence",
            "final_answer": "",
            "citations": (),
            "global_entities": (),
            "active_task": None,
            "control": control,
            "evidence": (),
            "outcome": None,
            "worker_attempts": 0,
            "route_history": (),
            "cost_microusd": 0,
            "model_tokens": 0,
        }
        result = await runtime.start(
            state,
            identity=CheckpointIdentity(
                session_id=session_id,
                turn_id=turn_id,
                graph_version="graph-r1",
            ),
        )

        assert result["outcome"] == GraphOutcome(
            kind="completed",
            code="ANSWERED",
        )
        citations = cast(tuple[Citation, ...], result["citations"])
        assert len(citations) == 1
        assert citations[0].source_revision == "source-r1"
        assert citations[0].source_uri == "https://example.test/vinfast/approved"
    finally:
        async with sessions() as session, session.begin():
            await session.execute(
                delete(KnowledgeRevisionPointer).where(
                    KnowledgeRevisionPointer.active_release_id == release_id
                )
            )
            await session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.id == chunk_id)
            )
            await session.execute(
                delete(KnowledgeReleaseSource).where(
                    KnowledgeReleaseSource.release_id == release_id
                )
            )
            await session.execute(
                delete(KnowledgeReleaseRecord).where(
                    KnowledgeReleaseRecord.id == release_id
                )
            )
            await session.execute(
                delete(KnowledgeSource).where(KnowledgeSource.id == source_id)
            )
            await session.execute(
                update(EmbeddingIndexGenerationRecord)
                .where(EmbeddingIndexGenerationRecord.id == generation_id)
                .values(lifecycle="tombstoned")
            )
        await dependencies.close()
        await base.release_runtime.close()
        await engine.dispose()
