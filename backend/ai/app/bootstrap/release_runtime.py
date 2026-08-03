import asyncio
import json
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.embedding_providers.configuration import (
    EmbeddingConfigurationError,
    embedding_generation_for_settings,
)
from app.infrastructure.model_providers.configuration import (
    InferenceConfigurationError,
    build_model_mesh,
    model_deployment_sha256_for_settings,
)
from app.modules.evaluation.application import (
    DeterministicExtractiveGroundingValidator,
    SealedAssistantReleaseEvidenceAuthority,
)
from app.modules.evaluation.infrastructure import (
    PostgresAssistantReleaseEvidenceReader,
)
from app.modules.governance.application import ActiveReleasePointerStore
from app.modules.governance.domain.release_manifest import AssistantReleaseManifest
from app.modules.governance.infrastructure import (
    BoundedOpaqueArtifactDigestReader,
    BoundedReleaseEvidenceVerifier,
    JsonSchemaReleaseAuthorityValidator,
    PostgresReleaseAuthorityResolver,
    PostgresTrustedReleaseRegistry,
    ReleaseArtifactInfrastructureError,
    ReleasePersistenceError,
)
from app.modules.inference.application import (
    DeploymentPolicyDescriptor,
    GroundedAnswerPrompt,
    ModelMesh,
    RetentionPolicy,
)
from app.platform.config import Settings

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_RELEASE_SCHEMA = _REPOSITORY_ROOT / "contracts/ai/ai-release-manifest.schema.json"
# A runtime release must bind product release authority, security authority and
# data-controls authority.  Provider-level data-control metadata alone is not a
# substitute for an independent data-owner decision.
_REQUIRED_APPROVAL_ROLES = ("release-owner", "security-owner", "data-owner")


class ReleaseRuntimeUnavailable(RuntimeError):
    """No verified, runtime-compatible assistant release is available."""


@dataclass(frozen=True, slots=True)
class ResolvedReleaseRuntime:
    activation_id: str
    candidate_sha256: str
    activation_envelope_sha256: str
    pointer_revision: int
    policy: DeploymentPolicyDescriptor
    prompt: GroundedAnswerPrompt
    model_mesh: ModelMesh
    knowledge_profile_sha256: str
    retriever_sha256: str
    embedding_generation_digest: str
    validator_sha256: str
    graph_revision: str
    policy_revision: str
    knowledge_revision: str
    locale: str


@dataclass(frozen=True, slots=True)
class ReleaseCommitLease:
    lease_id: UUID
    issued_at: datetime
    expires_at: datetime


class ReleaseBoundRuntimeResolver:
    """Resolve authority on every turn and cache only immutable transports.

    The cache never replaces release resolution. Every call rechecks the
    pointer, approvals, artifacts, live controls and trust-receipt freshness
    before returning a previously built Model Mesh.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        sessions: async_sessionmaker[AsyncSession],
        pointer_store: ActiveReleasePointerStore,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._pointer_store = pointer_store
        registry = PostgresTrustedReleaseRegistry(sessions)
        schema = json.loads(_RELEASE_SCHEMA.read_text(encoding="utf-8"))
        self._authority = PostgresReleaseAuthorityResolver(
            sessions=sessions,
            digest_reader=BoundedOpaqueArtifactDigestReader(
                registry=registry,
                timeout_seconds=2,
                max_concurrency=16,
            ),
            evidence_verifier=BoundedReleaseEvidenceVerifier(
                registry=registry,
                timeout_seconds=2,
                max_concurrency=16,
            ),
            evaluation_evidence_authority=SealedAssistantReleaseEvidenceAuthority(
                PostgresAssistantReleaseEvidenceReader(sessions)
            ),
            schema_validator=JsonSchemaReleaseAuthorityValidator(schema),
            required_approval_roles=_REQUIRED_APPROVAL_ROLES,
            clock=lambda: datetime.now(UTC),
            trust_freshness_fence=registry,
        )
        self._meshes: OrderedDict[str, ModelMesh] = OrderedDict()
        self._mesh_leases: dict[str, int] = {}
        self._grounding_validator = DeterministicExtractiveGroundingValidator()
        self._lock = asyncio.Lock()

    @property
    def environment(self) -> str:
        return self._settings.environment

    async def issue_commit_lease(
        self,
        release: ResolvedReleaseRuntime,
        *,
        session_id: UUID,
        turn_id: UUID,
        request_id: UUID,
        conversation_version: int,
        fencing_token: int,
        assistant_profile: str,
    ) -> ReleaseCommitLease:
        """Bind a short final-commit window to the current release pointer."""
        proposed_lease_id = uuid4()
        async with self._sessions() as session, session.begin():
            row = (
                await session.execute(
                    text(
                        """
                        WITH lease_clock AS (
                          SELECT clock_timestamp() AS issued_at
                        ),
                        current_pointer AS (
                          SELECT activation_record_id, revision
                          FROM ai_assistant_release_pointer
                          WHERE assistant_profile = :assistant_profile
                            AND environment = :environment
                          FOR SHARE
                        ),
                        deleted_expired AS (
                          DELETE FROM ai_assistant_release_commit_lease
                          WHERE id IN (
                            SELECT id
                            FROM ai_assistant_release_commit_lease
                            WHERE expires_at <= clock_timestamp()
                            ORDER BY expires_at
                            LIMIT 1000
                            FOR UPDATE SKIP LOCKED
                          )
                          RETURNING id
                        ),
                        inserted AS (
                        INSERT INTO ai_assistant_release_commit_lease (
                          id, assistant_profile, environment,
                          activation_record_id, candidate_sha256,
                          activation_envelope_sha256, pointer_revision,
                          session_id, turn_id, request_id,
                          conversation_version, fencing_token,
                          issued_at, expires_at
                        )
                        SELECT
                          :lease_id, :assistant_profile, :environment,
                          :activation_id, :candidate_sha256,
                          :activation_envelope_sha256, :pointer_revision,
                          :session_id, :turn_id, :request_id,
                          :conversation_version, :fencing_token,
                          lease_clock.issued_at,
                          lease_clock.issued_at + interval '15 seconds'
                        FROM current_pointer
                        CROSS JOIN lease_clock
                        WHERE activation_record_id = :activation_id
                          AND revision = :pointer_revision
                        ON CONFLICT (
                          session_id, turn_id, fencing_token
                        ) DO NOTHING
                        RETURNING id, issued_at, expires_at
                        )
                        SELECT id, issued_at, expires_at
                        FROM inserted
                        UNION ALL
                        SELECT lease.id, lease.issued_at, lease.expires_at
                        FROM ai_assistant_release_commit_lease lease
                        JOIN current_pointer pointer
                          ON pointer.activation_record_id =
                             lease.activation_record_id
                         AND pointer.revision = lease.pointer_revision
                        WHERE lease.session_id = :session_id
                          AND lease.turn_id = :turn_id
                          AND lease.fencing_token = :fencing_token
                          AND lease.request_id = :request_id
                          AND lease.conversation_version =
                              :conversation_version
                          AND lease.assistant_profile = :assistant_profile
                          AND lease.environment = :environment
                          AND lease.activation_record_id = :activation_id
                          AND lease.candidate_sha256 = :candidate_sha256
                          AND lease.activation_envelope_sha256 =
                              :activation_envelope_sha256
                          AND lease.expires_at > clock_timestamp()
                        LIMIT 1
                        """
                    ),
                    {
                        "lease_id": proposed_lease_id,
                        "assistant_profile": assistant_profile,
                        "environment": self._settings.environment,
                        "activation_id": UUID(release.activation_id),
                        "candidate_sha256": release.candidate_sha256,
                        "activation_envelope_sha256": (
                            release.activation_envelope_sha256
                        ),
                        "pointer_revision": release.pointer_revision,
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "request_id": request_id,
                        "conversation_version": conversation_version,
                        "fencing_token": fencing_token,
                    },
                )
            ).one_or_none()
        if row is None:
            raise ReleaseRuntimeUnavailable("RELEASE_CHANGED_BEFORE_COMMIT_LEASE")
        lease_id, issued_at, expires_at = row
        if (
            not isinstance(lease_id, UUID)
            or not isinstance(issued_at, datetime)
            or not isinstance(expires_at, datetime)
            or expires_at > issued_at + timedelta(seconds=15)
        ):
            raise ReleaseRuntimeUnavailable("INVALID_COMMIT_LEASE")
        return ReleaseCommitLease(
            lease_id=lease_id,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    async def resolve(
        self,
        *,
        assistant_profile: str,
        graph_revision: str,
        policy_revision: str,
        knowledge_revision: str,
        locale: str,
    ) -> ResolvedReleaseRuntime:
        try:
            return await self._resolve(
                assistant_profile=assistant_profile,
                graph_revision=graph_revision,
                policy_revision=policy_revision,
                knowledge_revision=knowledge_revision,
                locale=locale,
                lease_mesh=True,
            )
        except ReleaseRuntimeUnavailable:
            raise
        except (
            EmbeddingConfigurationError,
            InferenceConfigurationError,
            ReleaseArtifactInfrastructureError,
            ReleasePersistenceError,
            SQLAlchemyError,
        ) as error:
            raise ReleaseRuntimeUnavailable(
                "RELEASE_AUTHORITY_UNAVAILABLE"
            ) from error

    async def _resolve(
        self,
        *,
        assistant_profile: str,
        graph_revision: str,
        policy_revision: str,
        knowledge_revision: str,
        locale: str,
        lease_mesh: bool,
    ) -> ResolvedReleaseRuntime:
        pointer = await self._pointer_store.current(
            assistant_profile=assistant_profile,
            environment=self._settings.environment,
        )
        if (
            pointer is None
            or pointer.target_kind != "activation"
            or pointer.activation_id is None
            or pointer.candidate_sha256 is None
        ):
            raise ReleaseRuntimeUnavailable("NO_ACTIVE_GENERATION_RELEASE")
        manifest = await self._authority.resolve(
            activation_id=pointer.activation_id,
            expected_candidate_sha256=pointer.candidate_sha256,
            assistant_profile=assistant_profile,
            environment=self._settings.environment,
        )
        self._assert_pointer_binding(pointer.envelope_sha256, manifest)
        prompt = GroundedAnswerPrompt(revision=self._settings.prompt_revision)
        policy = self._policy(manifest)
        self._assert_runtime_binding(
            manifest,
            prompt,
            policy,
            assistant_profile=assistant_profile,
            graph_revision=graph_revision,
            policy_revision=policy_revision,
            knowledge_revision=knowledge_revision,
            locale=locale,
        )
        mesh = await self._mesh_for(
            manifest,
            policy,
            prompt,
            lease=lease_mesh,
        )
        artifacts = manifest.candidate.artifacts
        return ResolvedReleaseRuntime(
            activation_id=manifest.activation_id,
            candidate_sha256=manifest.candidate.content_sha256,
            activation_envelope_sha256=manifest.activation_envelope_sha256,
            pointer_revision=pointer.pointer_revision,
            policy=policy,
            prompt=prompt,
            model_mesh=mesh,
            knowledge_profile_sha256=artifacts.knowledge_profile_sha256,
            retriever_sha256=artifacts.retriever_sha256,
            embedding_generation_digest=artifacts.embedding_generation_digest,
            validator_sha256=artifacts.validator_sha256,
            graph_revision=graph_revision,
            policy_revision=policy_revision,
            knowledge_revision=knowledge_revision,
            locale=locale,
        )

    async def assert_current(
        self,
        release: ResolvedReleaseRuntime,
        *,
        assistant_profile: str,
    ) -> None:
        current = await self._resolve(
            assistant_profile=assistant_profile,
            graph_revision=release.graph_revision,
            policy_revision=release.policy_revision,
            knowledge_revision=release.knowledge_revision,
            locale=release.locale,
            lease_mesh=False,
        )
        if (
            current.activation_id != release.activation_id
            or current.candidate_sha256 != release.candidate_sha256
            or current.activation_envelope_sha256
            != release.activation_envelope_sha256
            or current.pointer_revision != release.pointer_revision
        ):
            raise ReleaseRuntimeUnavailable("RELEASE_CHANGED_DURING_TURN")

    async def close(self) -> None:
        async with self._lock:
            meshes = tuple(self._meshes.values())
            self._meshes.clear()
            self._mesh_leases.clear()
        await asyncio.gather(*(mesh.aclose() for mesh in meshes))

    async def release(self, release: ResolvedReleaseRuntime) -> None:
        """Release one turn lease and retire only an inactive cached mesh."""
        cache_key = release.activation_envelope_sha256
        retired: ModelMesh | None = None
        async with self._lock:
            leases = self._mesh_leases.get(cache_key, 0)
            if leases > 0:
                self._mesh_leases[cache_key] = leases - 1
            if len(self._meshes) > 8:
                retired = self._retire_oldest_inactive()
        if retired is not None:
            await retired.aclose()

    @staticmethod
    def _assert_pointer_binding(
        expected_envelope_sha256: str,
        manifest: AssistantReleaseManifest,
    ) -> None:
        if manifest.activation_envelope_sha256 != expected_envelope_sha256:
            raise ReleaseRuntimeUnavailable("RELEASE_POINTER_ENVELOPE_MISMATCH")

    def _assert_runtime_binding(
        self,
        manifest: AssistantReleaseManifest,
        prompt: GroundedAnswerPrompt,
        policy: DeploymentPolicyDescriptor,
        *,
        assistant_profile: str,
        graph_revision: str,
        policy_revision: str,
        knowledge_revision: str,
        locale: str,
    ) -> None:
        artifacts = manifest.candidate.artifacts
        if policy_revision != manifest.candidate.gate_policy_revision:
            raise ReleaseRuntimeUnavailable("SIGNED_POLICY_REVISION_MISMATCH")
        if prompt.content_sha256 != artifacts.prompt_sha256:
            raise ReleaseRuntimeUnavailable("PROMPT_ARTIFACT_MISMATCH")
        generation = embedding_generation_for_settings(self._settings)
        if generation is None:
            raise ReleaseRuntimeUnavailable("EMBEDDING_RUNTIME_DISABLED")
        if generation.digest != artifacts.embedding_generation_digest:
            raise ReleaseRuntimeUnavailable("EMBEDDING_GENERATION_MISMATCH")
        if self._settings.generation_provider == "disabled":
            raise ReleaseRuntimeUnavailable("GENERATION_RUNTIME_DISABLED")
        if (
            model_deployment_sha256_for_settings(self._settings)
            != artifacts.model_deployment_sha256
        ):
            raise ReleaseRuntimeUnavailable("MODEL_DEPLOYMENT_MISMATCH")
        if self._grounding_validator.artifact_sha256 != artifacts.validator_sha256:
            raise ReleaseRuntimeUnavailable("GROUNDING_VALIDATOR_MISMATCH")
        expected_artifacts = {
            "graph": runtime_binding_sha256(
                {
                    "schemaVersion": 2,
                    "graphRevision": graph_revision,
                    "sourceTreeSha256": graph_runtime_source_sha256(),
                }
            ),
            "output_schema": runtime_binding_sha256(prompt.output_schema),
            "policy": runtime_binding_sha256(
                {
                    "schemaVersion": 1,
                    "revision": policy.revision,
                    "profile": policy.profile,
                    "safetyTier": policy.safety_tier,
                    "residency": policy.residency,
                    "retention": policy.retention.value,
                    "schemaRevision": policy.schema_revision,
                    "modelRelease": policy.model_release,
                    "providerProjectId": policy.provider_project_id,
                    "providerOrganizationId": policy.provider_organization_id,
                    "dataControlsApprovalReference": (
                        policy.data_controls_approval_reference
                    ),
                    "dataControlsApprovalSha256": (
                        policy.data_controls_approval_sha256
                    ),
                }
            ),
            "knowledge_profile": knowledge_runtime_profile_sha256(
                assistant_profile=assistant_profile,
                locale=locale,
                knowledge_revision=knowledge_revision,
            ),
            "retriever": retriever_runtime_sha256(),
            "tool_registry": runtime_binding_sha256(
                {"schemaVersion": 1, "tools": []}
            ),
        }
        observed_artifacts = {
            "graph": artifacts.graph_sha256,
            "output_schema": artifacts.output_schema_sha256,
            "policy": artifacts.policy_sha256,
            "knowledge_profile": artifacts.knowledge_profile_sha256,
            "retriever": artifacts.retriever_sha256,
            "tool_registry": artifacts.tool_registry_sha256,
        }
        mismatches = tuple(
            name
            for name, expected in expected_artifacts.items()
            if observed_artifacts[name] != expected
        )
        if mismatches:
            raise ReleaseRuntimeUnavailable(
                f"RUNTIME_ARTIFACT_MISMATCH:{','.join(mismatches)}"
            )

    def _policy(
        self,
        manifest: AssistantReleaseManifest,
    ) -> DeploymentPolicyDescriptor:
        settings = self._settings
        if settings.generation_provider == "vertex":
            identity = settings.vertex_capability("generation")
            project_id = identity.project_id
            organization_id = None
            retention = identity.retention_policy
            approval_reference = identity.approval_reference
            approval_sha256 = identity.approval_sha256
        else:
            identity = settings.openai_capability("generation")
            project_id = identity.project_id
            organization_id = identity.organization_id
            retention = identity.retention_policy
            approval_reference = identity.approval_reference
            approval_sha256 = identity.approval_sha256
        if (
            project_id is None
            or approval_reference is None
            or approval_sha256 is None
        ):
            raise ReleaseRuntimeUnavailable("PROVIDER_APPROVAL_UNAVAILABLE")
        return DeploymentPolicyDescriptor(
            revision=manifest.candidate.gate_policy_revision,
            profile=settings.model_policy_profile,
            safety_tier=settings.model_safety_tier,
            residency=settings.model_residency,
            retention=RetentionPolicy(retention),
            schema_revision=settings.structured_schema_revision,
            model_release=settings.generation_model,
            provider_project_id=project_id,
            provider_organization_id=organization_id,
            data_controls_approval_reference=approval_reference,
            data_controls_approval_sha256=approval_sha256,
            release_manifest_sha256=manifest.activation_envelope_sha256,
        )

    async def _mesh_for(
        self,
        manifest: AssistantReleaseManifest,
        policy: DeploymentPolicyDescriptor,
        prompt: GroundedAnswerPrompt,
        *,
        lease: bool,
    ) -> ModelMesh:
        cache_key = manifest.activation_envelope_sha256
        evicted: ModelMesh | None = None
        async with self._lock:
            existing = self._meshes.get(cache_key)
            if existing is not None:
                self._meshes.move_to_end(cache_key)
                if lease:
                    self._mesh_leases[cache_key] = (
                        self._mesh_leases.get(cache_key, 0) + 1
                    )
                return existing
            mesh = build_model_mesh(
                self._settings,
                policy=policy,
                prompt=prompt,
                claim_support_validator=self._grounding_validator,
            )
            self._meshes[cache_key] = mesh
            self._mesh_leases[cache_key] = 1 if lease else 0
            if len(self._meshes) > 8:
                evicted = self._retire_oldest_inactive(
                    excluded_key=cache_key if lease else None
                )
        if evicted is not None:
            await evicted.aclose()
        return mesh

    def _retire_oldest_inactive(
        self,
        *,
        excluded_key: str | None = None,
    ) -> ModelMesh | None:
        for key, mesh in tuple(self._meshes.items()):
            if key == excluded_key or self._mesh_leases.get(key, 0) > 0:
                continue
            self._meshes.pop(key)
            self._mesh_leases.pop(key, None)
            return mesh
        return None


def runtime_binding_sha256(payload: dict[str, object]) -> str:
    """Canonical helper used by release tooling and deterministic tests."""
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode()).hexdigest()


def knowledge_runtime_profile_sha256(
    *,
    assistant_profile: str,
    locale: str,
    knowledge_revision: str,
) -> str:
    return runtime_binding_sha256(
        {
            "schemaVersion": 1,
            "domain": "customer-support",
            "assistantProfile": assistant_profile,
            "locale": locale,
            "aclNamespace": (
                f"{assistant_profile}:customer-support:{locale}"
            ),
            "knowledgeRevision": knowledge_revision,
        }
    )


def retriever_runtime_sha256() -> str:
    return runtime_binding_sha256(
        {
            "schemaVersion": 2,
            "sourceTreeSha256": retriever_runtime_source_sha256(),
            "strategy": "hybrid-pgvector-lexical",
            "maxCandidates": 200,
            "maxResults": 8,
            "lexicalWeight": 0.35,
            "minimumScore": 0.05,
            "reranker": None,
        }
    )


def graph_runtime_source_sha256() -> str:
    return _source_files_sha256(
        (
            "app/modules/assistant/graph/builder.py",
            "app/modules/assistant/graph/nodes.py",
            "app/modules/assistant/graph/runtime.py",
            "app/modules/assistant/graph/state.py",
            "app/modules/assistant/infrastructure/knowledge_worker.py",
            "app/modules/assistant/infrastructure/released_knowledge.py",
        )
    )


def retriever_runtime_source_sha256() -> str:
    return _source_files_sha256(
        (
            "app/modules/knowledge/application/retrieval_service.py",
            "app/modules/knowledge/domain/retrieval.py",
            "app/modules/knowledge/infrastructure/postgres_retrieval.py",
        )
    )


def _source_files_sha256(relative_paths: tuple[str, ...]) -> str:
    """Attest the exact reviewed runtime source bytes shipped in this build."""
    digest = sha256()
    for relative_path in sorted(relative_paths):
        path = _REPOSITORY_ROOT / "backend/ai" / relative_path
        content = path.read_bytes()
        digest.update(relative_path.encode())
        digest.update(b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()
