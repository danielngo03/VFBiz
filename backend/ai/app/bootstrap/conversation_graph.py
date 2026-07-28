import asyncio
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.release_runtime import (
    ReleaseBoundRuntimeResolver,
    ReleaseCommitLease,
    ReleaseRuntimeUnavailable,
    ResolvedReleaseRuntime,
)
from app.infrastructure.embedding_providers.configuration import (
    build_embedding_runtime,
)
from app.modules.assistant.graph.builder import build_conversation_graph
from app.modules.assistant.graph.runtime import ConversationGraphRuntime
from app.modules.assistant.graph.state import ConversationGraphState
from app.modules.assistant.infrastructure.entity_revalidation import (
    FailClosedEntityRevalidator,
)
from app.modules.assistant.infrastructure.execution_control import (
    PostgresExecutionControlAdapter,
)
from app.modules.assistant.infrastructure.keyword_supervisor import KeywordSupervisor
from app.modules.assistant.infrastructure.knowledge_worker import KnowledgeGroundedWorker
from app.modules.assistant.infrastructure.released_knowledge import (
    ReleasedEvidenceAuthority,
    ReleasedKnowledgeRetriever,
)
from app.modules.assistant.infrastructure.resume_claims import PostgresResumeClaimAdapter
from app.modules.governance.infrastructure import PostgresActiveReleasePointerAdapter
from app.modules.inference.application import InferenceBudget
from app.modules.inference.application.embedding_runtime import EmbeddingRuntime
from app.modules.knowledge.application import KnowledgeRetrievalService
from app.modules.knowledge.domain import KnowledgeScope
from app.modules.knowledge.infrastructure import PostgresRetrievalSnapshotReader
from app.platform.checkpoints.contracts import CheckpointIdentity
from app.platform.checkpoints.execution_fence import PostgresExecutionFenceStore
from app.platform.checkpoints.graph_checkpointer import (
    ConversationCheckpointerRuntime,
    create_conversation_checkpointer_runtime,
)
from app.platform.checkpoints.postgres import PostgresResumeClaimStore
from app.platform.config import Settings


@dataclass
class ConversationRuntimeDependencies:
    """App-wide singletons composed once at lifespan startup."""

    checkpointer_runtime: ConversationCheckpointerRuntime
    fence_store: PostgresExecutionFenceStore
    resume_claims: PostgresResumeClaimAdapter
    release_runtime: ReleaseBoundRuntimeResolver
    embedding_runtime: EmbeddingRuntime | None
    retrieval_store: PostgresRetrievalSnapshotReader

    async def close(self) -> None:
        results = await asyncio.gather(
            self.release_runtime.close(),
            (
                self.embedding_runtime.aclose()
                if self.embedding_runtime is not None
                else _noop()
            ),
            self.checkpointer_runtime.close(),
            return_exceptions=True,
        )
        first_error = next(
            (result for result in results if isinstance(result, BaseException)),
            None,
        )
        if first_error is not None:
            raise first_error


@dataclass(frozen=True, slots=True)
class BoundConversationTurnRuntime:
    graph: ConversationGraphRuntime
    release: ResolvedReleaseRuntime
    release_resolver: ReleaseBoundRuntimeResolver
    assistant_profile: str

    async def start(
        self,
        state: ConversationGraphState,
        *,
        identity: CheckpointIdentity,
    ) -> dict[str, object]:
        return await self.graph.start(state, identity=identity)

    async def assert_release_current(self) -> None:
        await self.release_resolver.assert_current(
            self.release,
            assistant_profile=self.assistant_profile,
        )

    async def issue_commit_lease(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        request_id: UUID,
        conversation_version: int,
        fencing_token: int,
    ) -> ReleaseCommitLease:
        return await self.release_resolver.issue_commit_lease(
            self.release,
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            conversation_version=conversation_version,
            fencing_token=fencing_token,
            assistant_profile=self.assistant_profile,
        )

    async def close(self) -> None:
        await self.release_resolver.release(self.release)


async def _noop() -> None:
    return None


async def build_conversation_runtime_dependencies(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
) -> ConversationRuntimeDependencies:
    if settings.database_url is None:
        raise ValueError("database_url is required to compose the conversation graph")
    checkpointer_runtime: ConversationCheckpointerRuntime | None = None
    embedding_runtime: EmbeddingRuntime | None = None
    try:
        embedding_runtime = build_embedding_runtime(settings)
        checkpointer_runtime = await create_conversation_checkpointer_runtime(
            settings.database_url
        )
        pointer_store = PostgresActiveReleasePointerAdapter(sessions)
        return ConversationRuntimeDependencies(
            checkpointer_runtime=checkpointer_runtime,
            fence_store=PostgresExecutionFenceStore(sessions),
            resume_claims=PostgresResumeClaimAdapter(PostgresResumeClaimStore(sessions)),
            release_runtime=ReleaseBoundRuntimeResolver(
                settings=settings,
                sessions=sessions,
                pointer_store=pointer_store,
            ),
            embedding_runtime=embedding_runtime,
            retrieval_store=PostgresRetrievalSnapshotReader(sessions),
        )
    except BaseException:
        await asyncio.gather(
            (
                embedding_runtime.aclose()
                if embedding_runtime is not None
                else _noop()
            ),
            (
                checkpointer_runtime.close()
                if checkpointer_runtime is not None
                else _noop()
            ),
            return_exceptions=True,
        )
        raise


async def build_turn_runtime(
    dependencies: ConversationRuntimeDependencies,
    *,
    session_id: UUID,
    turn_id: UUID,
    subject: str,
    assistant_profile: str,
    locale: str,
    graph_revision: str,
    policy_revision: str,
    knowledge_revision: str,
    expected_activation_id: UUID,
    expected_manifest_sha256: str,
    budget: InferenceBudget,
    correlation_id: str,
) -> BoundConversationTurnRuntime:
    """Compose one turn's graph. Per-turn, not a singleton: `GraphControlState`
    carries no session/turn/subject identity, so `ExecutionControlPort` and
    `TaskWorkerPort` must close over it here instead (see the VFBIZ-0094
    checkpoint for why). `StateGraph.compile()` is in-memory, not I/O, so
    building a fresh graph per turn is not a performance concern.
    """
    execution_control = PostgresExecutionControlAdapter(
        session_id=session_id,
        turn_id=turn_id,
        store=dependencies.fence_store,
    )
    release = await dependencies.release_runtime.resolve(
        assistant_profile=assistant_profile,
        graph_revision=graph_revision,
        policy_revision=policy_revision,
        knowledge_revision=knowledge_revision,
        locale=locale,
    )
    try:
        if (
            release.activation_id != str(expected_activation_id)
            or release.candidate_sha256 != expected_manifest_sha256
        ):
            raise ReleaseRuntimeUnavailable("SIGNED_RELEASE_BINDING_MISMATCH")
        if dependencies.embedding_runtime is None:
            raise ReleaseRuntimeUnavailable("EMBEDDING_RUNTIME_DISABLED")
        try:
            expected_knowledge_release = UUID(knowledge_revision)
        except ValueError as error:
            raise ReleaseRuntimeUnavailable(
                "SIGNED_KNOWLEDGE_REVISION_INVALID"
            ) from error
        scope = KnowledgeScope.model_validate(
            {
                "domain": "customer-support",
                "locale": locale,
                "assistant_profile": assistant_profile,
                "acl_namespace": f"{assistant_profile}:customer-support:{locale}",
            }
        )
        released_retriever = ReleasedKnowledgeRetriever(
            service=KnowledgeRetrievalService(
                dependencies.retrieval_store,
                dependencies.retrieval_store,
                dependencies.embedding_runtime,
            ),
            scope=scope,
            expected_release_id=expected_knowledge_release,
        )
        worker = KnowledgeGroundedWorker(
            retriever=released_retriever,
            model_mesh=release.model_mesh,
            policy=release.policy,
            budget=budget,
            prompt_revision=release.prompt.revision,
            prompt_content_sha256=release.prompt.content_sha256,
            correlation_id=correlation_id,
        )
        graph = build_conversation_graph(
            supervisor=KeywordSupervisor(),
            worker=worker,
            execution_control=execution_control,
            evidence_authority=ReleasedEvidenceAuthority(
                retriever=released_retriever,
                snapshots=dependencies.retrieval_store,
            ),
            checkpointer=dependencies.checkpointer_runtime.saver,
        )
        return BoundConversationTurnRuntime(
            graph=ConversationGraphRuntime(
                graph,
                resume_claims=dependencies.resume_claims,
                entity_revalidator=FailClosedEntityRevalidator(),
            ),
            release=release,
            release_resolver=dependencies.release_runtime,
            assistant_profile=assistant_profile,
        )
    except BaseException:
        await dependencies.release_runtime.release(release)
        raise
