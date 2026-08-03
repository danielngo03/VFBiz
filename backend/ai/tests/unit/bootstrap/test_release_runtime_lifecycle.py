import asyncio
from collections import OrderedDict
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap import release_runtime as release_module
from app.bootstrap.release_runtime import (
    ReleaseBoundRuntimeResolver,
    ReleaseRuntimeUnavailable,
)
from app.modules.evaluation.application import (
    DeterministicExtractiveGroundingValidator,
    SealedAssistantReleaseEvidenceAuthority,
)
from app.modules.evaluation.infrastructure import (
    PostgresAssistantReleaseEvidenceReader,
)
from app.modules.governance.application import ActiveReleasePointer
from app.modules.inference.application import (
    DeploymentPolicyDescriptor,
    GroundedAnswerPrompt,
    ModelMesh,
    RetentionPolicy,
)
from app.platform.config import Settings

POLICY = DeploymentPolicyDescriptor(
    revision="policy-v1",
    profile="customer-grounded-v1",
    safety_tier="customer-factual-v1",
    residency="vn",
    retention=RetentionPolicy.ZERO_DATA_RETENTION,
    schema_revision="grounded-answer-v2",
    model_release="model-v1",
    provider_project_id="project-v1",
    provider_organization_id=None,
    data_controls_approval_reference="approval-v1",
    data_controls_approval_sha256="a" * 64,
    release_manifest_sha256="b" * 64,
)
PROMPT = GroundedAnswerPrompt(revision="prompt-v1")


class Mesh:
    def __init__(self) -> None:
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


class PointerStore:
    def __init__(
        self,
        pointer: ActiveReleasePointer | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.pointer = pointer
        self.error = error

    async def current(
        self,
        *,
        assistant_profile: str,
        environment: str,
    ) -> ActiveReleasePointer | None:
        assert assistant_profile
        assert environment
        if self.error is not None:
            raise self.error
        return self.pointer


def _resolver() -> ReleaseBoundRuntimeResolver:
    resolver = object.__new__(ReleaseBoundRuntimeResolver)
    resolver._meshes = OrderedDict()  # noqa: SLF001
    resolver._mesh_leases = {}  # noqa: SLF001
    resolver._lock = asyncio.Lock()  # noqa: SLF001
    resolver._settings = Settings()  # noqa: SLF001
    resolver._grounding_validator = (  # noqa: SLF001
        DeterministicExtractiveGroundingValidator()
    )
    return resolver


def test_real_composition_wires_sealed_evaluation_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class CapturingAuthority:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        release_module,
        "PostgresReleaseAuthorityResolver",
        CapturingAuthority,
    )
    sessions = cast(async_sessionmaker[AsyncSession], object())

    ReleaseBoundRuntimeResolver(
        settings=Settings(),
        sessions=sessions,
        pointer_store=PointerStore(),
    )

    authority = captured["evaluation_evidence_authority"]
    assert isinstance(authority, SealedAssistantReleaseEvidenceAuthority)
    assert isinstance(
        authority._reader,  # noqa: SLF001
        PostgresAssistantReleaseEvidenceReader,
    )
    assert captured["required_approval_roles"] == (
        "release-owner",
        "security-owner",
        "data-owner",
    )


@pytest.mark.asyncio
async def test_cache_never_evicts_a_leased_inflight_mesh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meshes: list[Mesh] = []

    def build(*_: object, **__: object) -> ModelMesh:
        mesh = Mesh()
        meshes.append(mesh)
        return cast(ModelMesh, mesh)

    monkeypatch.setattr(release_module, "build_model_mesh", build)
    resolver = _resolver()
    manifests = [SimpleNamespace(activation_envelope_sha256=f"{index:064x}") for index in range(9)]

    for manifest in manifests:
        await resolver._mesh_for(  # noqa: SLF001
            manifest,  # type: ignore[arg-type]
            POLICY,
            PROMPT,
            lease=True,
        )

    assert len(resolver._meshes) == 9  # noqa: SLF001
    assert all(mesh.closed == 0 for mesh in meshes)

    await resolver.release(manifests[0])  # type: ignore[arg-type]

    assert len(resolver._meshes) == 8  # noqa: SLF001
    assert meshes[0].closed == 1
    assert all(mesh.closed == 0 for mesh in meshes[1:])

    for manifest in manifests[1:]:
        await resolver.release(manifest)  # type: ignore[arg-type]
    await resolver.close()
    assert all(mesh.closed == 1 for mesh in meshes)


@pytest.mark.asyncio
async def test_release_is_idempotent_and_does_not_underflow_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mesh = Mesh()

    def build(*_: object, **__: object) -> ModelMesh:
        return cast(ModelMesh, mesh)

    monkeypatch.setattr(
        release_module,
        "build_model_mesh",
        build,
    )
    resolver = _resolver()
    manifest = SimpleNamespace(activation_envelope_sha256="c" * 64)
    await resolver._mesh_for(  # noqa: SLF001
        manifest,  # type: ignore[arg-type]
        POLICY,
        PROMPT,
        lease=True,
    )

    await resolver.release(manifest)  # type: ignore[arg-type]
    await resolver.release(manifest)  # type: ignore[arg-type]

    assert resolver._mesh_leases["c" * 64] == 0  # noqa: SLF001
    await resolver.close()
    assert mesh.closed == 1


@pytest.mark.asyncio
async def test_resolver_fails_closed_without_active_release() -> None:
    resolver = ReleaseBoundRuntimeResolver(
        settings=Settings(),
        sessions=cast(async_sessionmaker[AsyncSession], object()),
        pointer_store=PointerStore(),
    )
    with pytest.raises(ReleaseRuntimeUnavailable, match="NO_ACTIVE_GENERATION_RELEASE"):
        await resolver.resolve(
            assistant_profile="public_customer",
            graph_revision="graph-v1",
            policy_revision="policy-v1",
            knowledge_revision="00000000-0000-4000-8000-000000000101",
            locale="vi",
        )
    await resolver.close()


@pytest.mark.asyncio
async def test_resolver_normalizes_pointer_database_outage() -> None:
    resolver = ReleaseBoundRuntimeResolver(
        settings=Settings(),
        sessions=cast(async_sessionmaker[AsyncSession], object()),
        pointer_store=PointerStore(
            error=OperationalError("SELECT pointer", {}, RuntimeError("offline"))
        ),
    )
    with pytest.raises(
        ReleaseRuntimeUnavailable,
        match="RELEASE_AUTHORITY_UNAVAILABLE",
    ):
        await resolver.resolve(
            assistant_profile="public_customer",
            graph_revision="graph-v1",
            policy_revision="policy-v1",
            knowledge_revision="00000000-0000-4000-8000-000000000101",
            locale="vi",
        )
    await resolver.close()


# pyright: reportPrivateUsage=false
