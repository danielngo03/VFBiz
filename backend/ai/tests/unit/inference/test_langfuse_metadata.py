from __future__ import annotations

from hashlib import sha256

import pytest

from app.infrastructure.observability import (
    LangfuseMetadataExporter,
    LangfuseSecretReferences,
    SanitizedModelObservation,
    load_langfuse_credentials,
)


class _FakeSink:
    def __init__(self) -> None:
        self.observations: list[SanitizedModelObservation] = []
        self.flushed = False
        self.close_called = False

    def emit(self, observation: SanitizedModelObservation) -> None:
        self.observations.append(observation)

    def flush(self) -> None:
        self.flushed = True

    def close(self) -> None:
        self.close_called = True


class _Payload:
    def __init__(self, data: bytes) -> None:
        self.data = data


class _SecretResponse:
    def __init__(self, data: bytes) -> None:
        self.payload = _Payload(data)


class _FakeSecretClient:
    def __init__(self) -> None:
        self.names: list[str] = []

    def access_secret_version(
        self,
        *,
        request: dict[str, str],
    ) -> _SecretResponse:
        name = request["name"]
        self.names.append(name)
        prefix = b"pk-lf-" if "public" in name else b"sk-lf-"
        return _SecretResponse(prefix + b"synthetic")


def _observation() -> SanitizedModelObservation:
    return SanitizedModelObservation(
        capability="generation",
        model_revision="gemini-2.5-flash",
        run_id_sha256=sha256(b"run").hexdigest(),
        manifest_sha256=sha256(b"manifest").hexdigest(),
        receipt_sha256=sha256(b"receipt").hexdigest(),
        outcome="succeeded",
        input_tokens=37,
        output_tokens=7,
        latency_ms=1_698,
        cost_microusd=154,
    )


def test_exporter_accepts_only_content_free_observation() -> None:
    sink = _FakeSink()
    exporter = LangfuseMetadataExporter(
        public_key="pk-lf-synthetic",
        secret_key="sk-lf-synthetic",  # noqa: S106 - inert test credential
        sink=sink,
    )
    exporter.emit(_observation())
    exporter.flush()

    assert sink.flushed is True
    assert sink.observations == [_observation()]
    assert not hasattr(sink.observations[0], "prompt")
    assert not hasattr(sink.observations[0], "response")
    assert not hasattr(sink.observations[0], "vector")


def test_exporter_rejects_unpinned_origin_and_malformed_identity() -> None:
    with pytest.raises(ValueError):
        LangfuseMetadataExporter(
            public_key="pk-lf-synthetic",
            secret_key="sk-lf-synthetic",  # noqa: S106 - inert test credential
            base_url="https://example.invalid",
            sink=_FakeSink(),
        )
    with pytest.raises(ValueError):
        SanitizedModelObservation(
            capability="embedding",
            model_revision="gemini-embedding-001",
            run_id_sha256="not-a-digest",
            manifest_sha256=sha256(b"manifest").hexdigest(),
            receipt_sha256=sha256(b"receipt").hexdigest(),
            outcome="succeeded",
            input_tokens=1,
            output_tokens=0,
            latency_ms=1,
            cost_microusd=1,
        )


def test_secret_references_resolve_without_local_secret_values() -> None:
    client = _FakeSecretClient()
    references = LangfuseSecretReferences(
        project_id="vinfast-503003",
        public_key_secret_id="vfbiz-langfuse-public-key-dev",  # noqa: S106
        secret_key_secret_id="vfbiz-langfuse-secret-key-dev",  # noqa: S106
        version="7",
    )

    credentials = load_langfuse_credentials(references, client=client)

    assert credentials == ("pk-lf-synthetic", "sk-lf-synthetic")
    assert client.names == [
        (
            "projects/vinfast-503003/secrets/"
            "vfbiz-langfuse-public-key-dev/versions/7"
        ),
        (
            "projects/vinfast-503003/secrets/"
            "vfbiz-langfuse-secret-key-dev/versions/7"
        ),
    ]
