import pytest

from app.modules.governance.infrastructure import BoundedOpaqueArtifactDigestReader


class FixedArtifactRegistry:
    async def read_sha256(self, artifact_ref: str) -> str | None:
        assert artifact_ref == "classifier://vivi/router/v1"
        return "a" * 64


@pytest.mark.asyncio
async def test_classifier_reference_is_a_supported_opaque_artifact() -> None:
    reader = BoundedOpaqueArtifactDigestReader(
        registry=FixedArtifactRegistry(),
        timeout_seconds=1,
        max_concurrency=1,
    )

    observed = await reader.sha256("classifier://vivi/router/v1")

    assert observed == "a" * 64
