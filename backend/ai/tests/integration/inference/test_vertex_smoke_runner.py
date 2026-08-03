from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import httpx
import pytest
from google.api_core.exceptions import PreconditionFailed

from app.infrastructure.model_providers import vertex_smoke_runner as runner_module
from app.infrastructure.model_providers.vertex_smoke_authority import (
    CANONICAL_FIXTURE_DIGESTS,
    DataControlsEvidence,
    FileSmokeLedger,
    IamEvidence,
    PricingEvidence,
    SmokeCapability,
    SmokePreflightFailure,
    SmokePreflightFailureCode,
    VertexEndpointIdentity,
    VertexSmokeAuthority,
    VertexSmokeManifest,
)
from app.infrastructure.model_providers.vertex_smoke_runner import (
    DispatchWitness,
    GcsDispatchWitness,
    VertexSmokeDispatchError,
    VertexSmokeRunner,
)
from scripts import run_vertex_synthetic_smoke as smoke_script

_PROJECT = "synthetic-project"
_PRINCIPAL = (
    "vfbiz-vertex-smoke@synthetic-project.iam.gserviceaccount.com"
)
_KEY = b"k" * 32


class _FakeBoundTokenProvider:
    def __init__(
        self,
        *,
        principal: str = _PRINCIPAL,
        callback: Callable[[], str] | None = None,
    ) -> None:
        self._principal = principal
        self._callback = callback or (
            lambda: "synthetic-access-token-value"
        )

    @property
    def principal(self) -> str:
        return self._principal

    def __call__(self) -> str:
        return self._callback()


class _FakeDispatchWitness:
    def __init__(self) -> None:
        self.claimed: set[tuple[str, SmokeCapability]] = set()

    def claim(
        self,
        *,
        manifest: VertexSmokeManifest,
        capability: SmokeCapability,
    ) -> None:
        identity = (manifest.digest, capability)
        if identity in self.claimed:
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.REPLAY_REJECTED
            )
        self.claimed.add(identity)


class _FakeGcsBlob:
    def __init__(self, *, name: str, objects: set[str]) -> None:
        self._name = name
        self._objects = objects

    def upload_from_string(
        self,
        _payload: bytes,
        *,
        content_type: str,
        if_generation_match: int,
    ) -> None:
        assert content_type == "application/json"
        assert if_generation_match == 0
        if self._name in self._objects:
            raise PreconditionFailed("witness exists")
        self._objects.add(self._name)


class _FakeGcsBucket:
    versioning_enabled = True

    def __init__(
        self,
        *,
        objects: set[str],
        retention_period: int = 86_400,
    ) -> None:
        self._objects = objects
        self.retention_period = retention_period
        self.reloaded = False

    def reload(self) -> None:
        self.reloaded = True

    def blob(self, name: str) -> _FakeGcsBlob:
        assert self.reloaded is True
        return _FakeGcsBlob(name=name, objects=self._objects)


class _FakeGcsClient:
    def __init__(
        self,
        *,
        bucket: _FakeGcsBucket,
        credentials: object,
    ) -> None:
        self._bucket = bucket
        self.credentials = credentials

    def bucket(self, _name: str) -> _FakeGcsBucket:
        return self._bucket


def _manifest(now: datetime) -> VertexSmokeManifest:
    pricing = PricingEvidence(
        revision="vertex-pricing-2026-07-31",
        source_url="https://cloud.google.com/vertex-ai/generative-ai/pricing",
        observed_at=now,
        input_microusd_per_million_tokens=150_000,
        output_microusd_per_million_tokens=600_000,
    )
    input_caps = {
        SmokeCapability.GENERATION: 64,
        SmokeCapability.EMBEDDING: 64,
    }
    output_caps = {
        SmokeCapability.GENERATION: 32,
        SmokeCapability.EMBEDDING: 0,
    }
    reservations = {
        SmokeCapability.GENERATION: 29,
        SmokeCapability.EMBEDDING: 10,
    }
    return VertexSmokeManifest(
        run_id=f"vertex-smoke-{now:%Y%m%d}-001",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        generation_endpoint=VertexEndpointIdentity(
            project_id=_PROJECT,
            location="asia-southeast1",
            model_revision="gemini-2.5-flash",
        ),
        embedding_endpoint=VertexEndpointIdentity(
            project_id=_PROJECT,
            location="global",
            model_revision="gemini-embedding-001",
        ),
        fixture_digests=CANONICAL_FIXTURE_DIGESTS,
        input_token_caps=input_caps,
        output_token_caps=output_caps,
        reservation_microusd=reservations,
        max_total_cost_microusd=499_999,
        max_requests_per_capability=1,
        pricing=pricing,
        data_controls=DataControlsEvidence(
            decision_reference="development-synthetic-no-content-v1",
            decision_sha256=sha256(b"synthetic-only").hexdigest(),
            retention_policy="standard",
            effective_at=now,
            expires_at=now + timedelta(hours=1),
        ),
    )


def _runner(
    tmp_path: Path,
    *,
    handler: Callable[[httpx.Request], httpx.Response],
    token_provider: _FakeBoundTokenProvider | None = None,
    witness: DispatchWitness | None = None,
) -> tuple[VertexSmokeRunner, VertexSmokeManifest, IamEvidence]:
    now = datetime(2026, 7, 31, 2, tzinfo=UTC)
    manifest = _manifest(now)
    ledger_path = (tmp_path / "ledger.json").resolve()
    ledger = FileSmokeLedger(
        ledger_path,
        seal_key=_KEY,
        key_id="test-key-v1",
        daily_cap_microusd=499_999,
    )
    authority = VertexSmokeAuthority(
        expected_project_id=_PROJECT,
        expected_principal=_PRINCIPAL,
        expected_ledger_path=ledger_path,
        expected_ledger_key_id="test-key-v1",
        generation_endpoint=manifest.generation_endpoint,
        embedding_endpoint=manifest.embedding_endpoint,
    )
    iam = IamEvidence(
        principal=_PRINCIPAL,
        observed_at=now,
        granted_permissions=frozenset({"aiplatform.endpoints.predict"}),
        evidence_sha256=sha256(b"iam").hexdigest(),
    )
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    runner = VertexSmokeRunner(
        authority=authority,
        ledger=ledger,
        manifest=manifest,
        principal=_PRINCIPAL,
        witness_bucket="synthetic-evidence",
    )
    runner._client.close()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    runner._client = client  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    runner._token_provider = (  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        token_provider or _FakeBoundTokenProvider()
    )
    runner._witness = (  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        witness or _FakeDispatchWitness()
    )
    return runner, manifest, iam


def test_generation_request_is_derived_and_sanitized(tmp_path: Path) -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["body"] = json.loads(request.content)
        observed["authorization"] = request.headers["Authorization"]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "four"}]},
                        "finishReason": "STOP",
                    }
                ],
                "modelVersion": "gemini-2.5-flash",
                "usageMetadata": {
                    "promptTokenCount": 30,
                    "candidatesTokenCount": 2,
                },
            },
        )

    runner, manifest, iam = _runner(tmp_path, handler=handler)
    result = runner.run(
        capability=SmokeCapability.GENERATION,
        iam=iam,
        now=manifest.created_at,
    )

    assert result is not None
    assert observed["url"] == (
        "https://asia-southeast1-aiplatform.googleapis.com/v1/"
        "projects/synthetic-project/locations/asia-southeast1/"
        "publishers/google/models/gemini-2.5-flash:generateContent"
    )
    body = observed["body"]
    assert isinstance(body, dict)
    assert body["generationConfig"] == {
        "candidateCount": 1,
        "maxOutputTokens": 32,
        "temperature": 0,
    }
    assert "synthetic" in json.dumps(body).lower()
    assert observed["authorization"] == "Bearer synthetic-access-token-value"
    serialized = json.dumps(result.as_dict())
    assert "four" not in serialized
    assert "synthetic-access-token-value" not in serialized


def test_embedding_request_is_exact_and_vector_is_not_retained(
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {
                        "embeddings": {
                            "statistics": {
                                "token_count": 5,
                                "truncated": False,
                            },
                            "values": [0.01] * 768,
                        }
                    }
                ]
            },
        )

    runner, manifest, iam = _runner(tmp_path, handler=handler)
    result = runner.run(
        capability=SmokeCapability.EMBEDDING,
        iam=iam,
        now=manifest.created_at,
    )

    assert result is not None
    assert observed["url"] == (
        "https://aiplatform.googleapis.com/v1/projects/synthetic-project/"
        "locations/global/publishers/google/models/"
        "gemini-embedding-001:predict"
    )
    assert observed["body"] == {
        "instances": [
            {
                "content": "synthetic retrieval test value",
                "task_type": "RETRIEVAL_QUERY",
            }
        ],
        "parameters": {
            "autoTruncate": False,
            "outputDimensionality": 768,
        },
    }
    assert "0.01" not in json.dumps(result.as_dict())


def test_replay_is_rejected_before_second_token_or_request(
    tmp_path: Path,
) -> None:
    requests = 0
    token_calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "STOP"}],
                "modelVersion": "gemini-2.5-flash",
                "usageMetadata": {
                    "promptTokenCount": 20,
                    "candidatesTokenCount": 1,
                },
            },
        )

    def token_provider() -> str:
        nonlocal token_calls
        token_calls += 1
        return "synthetic-access-token-value"

    runner, manifest, iam = _runner(
        tmp_path,
        handler=handler,
        token_provider=_FakeBoundTokenProvider(callback=token_provider),
    )
    runner.run(
        capability=SmokeCapability.GENERATION,
        iam=iam,
        now=manifest.created_at,
    )
    with pytest.raises(SmokePreflightFailure):
        runner.run(
            capability=SmokeCapability.GENERATION,
            iam=iam,
            now=manifest.created_at,
        )
    assert requests == 1
    assert token_calls == 1


def test_timeout_is_terminal_ambiguous_and_not_retried(
    tmp_path: Path,
) -> None:
    requests = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        raise httpx.ReadTimeout("synthetic timeout")

    runner, manifest, iam = _runner(tmp_path, handler=handler)
    with pytest.raises(VertexSmokeDispatchError) as caught:
        runner.run(
            capability=SmokeCapability.GENERATION,
            iam=iam,
            now=manifest.created_at,
        )
    assert caught.value.code == "timeout"
    assert caught.value.__context__ is None
    with pytest.raises(SmokePreflightFailure):
        runner.run(
            capability=SmokeCapability.GENERATION,
            iam=iam,
            now=manifest.created_at,
        )
    assert requests == 1


def test_wrong_endpoint_manifest_is_rejected_before_token(
    tmp_path: Path,
) -> None:
    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        pytest.fail("request must not be sent")

    runner, manifest, iam = _runner(
        tmp_path,
        handler=unexpected_request,
    )
    object.__setattr__(
        manifest,
        "generation_endpoint",
        VertexEndpointIdentity(
            project_id=_PROJECT,
            location="us-central1",
            model_revision="gemini-2.5-flash",
        ),
    )
    with pytest.raises(SmokePreflightFailure):
        runner.run(
            capability=SmokeCapability.GENERATION,
            iam=iam,
            now=manifest.created_at,
        )


def test_cancellation_happens_before_token_and_request(tmp_path: Path) -> None:
    token_called = False

    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        pytest.fail("request must not be sent")

    def token_provider() -> str:
        nonlocal token_called
        token_called = True
        return "synthetic-access-token-value"

    runner, manifest, iam = _runner(
        tmp_path,
        handler=unexpected_request,
        token_provider=_FakeBoundTokenProvider(callback=token_provider),
    )
    result = runner.run(
        capability=SmokeCapability.GENERATION,
        iam=iam,
        now=manifest.created_at,
        is_cancelled=lambda: True,
    )
    assert result is None
    assert token_called is False


def test_cancellation_after_token_happens_before_request(tmp_path: Path) -> None:
    token_called = False

    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        pytest.fail("request must not be sent")

    def token_provider() -> str:
        nonlocal token_called
        token_called = True
        return "synthetic-access-token-value"

    runner, manifest, iam = _runner(
        tmp_path,
        handler=unexpected_request,
        token_provider=_FakeBoundTokenProvider(callback=token_provider),
    )
    result = runner.run(
        capability=SmokeCapability.GENERATION,
        iam=iam,
        now=manifest.created_at,
        is_cancelled=lambda: token_called,
    )
    assert result is None
    assert token_called is True


def test_provider_usage_over_sealed_cap_is_rejected(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "STOP"}],
                "modelVersion": "gemini-2.5-flash",
                "usageMetadata": {
                    "promptTokenCount": 65,
                    "candidatesTokenCount": 1,
                },
            },
        )

    runner, manifest, iam = _runner(tmp_path, handler=handler)
    with pytest.raises(VertexSmokeDispatchError) as caught:
        runner.run(
            capability=SmokeCapability.GENERATION,
            iam=iam,
            now=manifest.created_at,
        )
    assert caught.value.code == "invalid-response"
    assert caught.value.__context__ is None


def test_response_byte_cap_is_terminal_and_not_retried(
    tmp_path: Path,
) -> None:
    request_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, content=b"x" * 262_145)

    runner, manifest, iam = _runner(tmp_path, handler=handler)
    with pytest.raises(VertexSmokeDispatchError) as caught:
        runner.run(
            capability=SmokeCapability.GENERATION,
            iam=iam,
            now=manifest.created_at,
        )
    assert caught.value.code == "response-too-large"
    assert caught.value.__context__ is None
    with pytest.raises(SmokePreflightFailure):
        runner.run(
            capability=SmokeCapability.GENERATION,
            iam=iam,
            now=manifest.created_at,
        )
    assert request_count == 1


def test_token_provider_principal_mismatch_is_rejected_before_reservation(
    tmp_path: Path,
) -> None:
    token_called = False

    def token_provider() -> str:
        nonlocal token_called
        token_called = True
        return "synthetic-access-token-value"

    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        pytest.fail("request must not be sent")

    runner, manifest, iam = _runner(
        tmp_path,
        handler=unexpected_request,
        token_provider=_FakeBoundTokenProvider(
            principal=(
                "other-smoke@synthetic-project.iam.gserviceaccount.com"
            ),
            callback=token_provider,
        ),
    )
    with pytest.raises(SmokePreflightFailure):
        runner.run(
            capability=SmokeCapability.GENERATION,
            iam=iam,
            now=manifest.created_at,
        )
    assert token_called is False


def test_http_failure_does_not_retain_request_or_token(
    tmp_path: Path,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b"provider error")

    runner, manifest, iam = _runner(tmp_path, handler=handler)
    with pytest.raises(VertexSmokeDispatchError) as caught:
        runner.run(
            capability=SmokeCapability.GENERATION,
            iam=iam,
            now=manifest.created_at,
        )
    rendered = repr(caught.value)
    assert caught.value.code == "http-4xx"
    assert caught.value.__context__ is None
    assert "synthetic-access-token-value" not in rendered
    assert "synthetic test value" not in rendered


def test_external_witness_blocks_replay_after_ledger_and_anchor_loss(
    tmp_path: Path,
) -> None:
    witness = _FakeDispatchWitness()
    requests = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "STOP"}],
                "modelVersion": "gemini-2.5-flash",
                "usageMetadata": {
                    "promptTokenCount": 20,
                    "candidatesTokenCount": 1,
                },
            },
        )

    runner, manifest, iam = _runner(
        tmp_path,
        handler=handler,
        witness=witness,
    )
    runner.run(
        capability=SmokeCapability.GENERATION,
        iam=iam,
        now=manifest.created_at,
    )
    (tmp_path / "ledger.json").unlink()
    (tmp_path / "ledger.json.anchor").unlink()
    second_runner, second_manifest, second_iam = _runner(
        tmp_path,
        handler=handler,
        witness=witness,
    )
    with pytest.raises(SmokePreflightFailure):
        second_runner.run(
            capability=SmokeCapability.GENERATION,
            iam=second_iam,
            now=second_manifest.created_at,
        )
    assert requests == 1


def test_gcs_witness_blocks_replay_after_local_dual_loss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    objects: set[str] = set()
    bucket = _FakeGcsBucket(objects=objects)
    credentials = object()

    def fake_credentials(_principal: str) -> object:
        return credentials

    def fake_client(
        *,
        project: str,
        credentials: object,
    ) -> _FakeGcsClient:
        assert project == _PROJECT
        return _FakeGcsClient(
            bucket=bucket,
            credentials=credentials,
        )

    monkeypatch.setattr(
        runner_module,
        "_impersonated_credentials",
        fake_credentials,
    )
    monkeypatch.setattr(
        runner_module.storage,
        "Client",
        fake_client,
    )

    requests = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            json={
                "candidates": [{"finishReason": "STOP"}],
                "modelVersion": "gemini-2.5-flash",
                "usageMetadata": {
                    "promptTokenCount": 20,
                    "candidatesTokenCount": 1,
                },
            },
        )

    witness = GcsDispatchWitness(
        project_id=_PROJECT,
        bucket_name="synthetic-evidence",
        principal=_PRINCIPAL,
    )
    runner, manifest, iam = _runner(
        tmp_path,
        handler=handler,
        witness=witness,
    )
    runner.run(
        capability=SmokeCapability.GENERATION,
        iam=iam,
        now=manifest.created_at,
    )
    (tmp_path / "ledger.json").unlink()
    (tmp_path / "ledger.json.anchor").unlink()
    second_runner, second_manifest, second_iam = _runner(
        tmp_path,
        handler=handler,
        witness=GcsDispatchWitness(
            project_id=_PROJECT,
            bucket_name="synthetic-evidence",
            principal=_PRINCIPAL,
        ),
    )
    with pytest.raises(SmokePreflightFailure) as caught:
        second_runner.run(
            capability=SmokeCapability.GENERATION,
            iam=second_iam,
            now=second_manifest.created_at,
        )
    assert caught.value.code is SmokePreflightFailureCode.REPLAY_REJECTED
    assert requests == 1


def test_gcs_witness_fails_closed_without_manifest_window_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bucket = _FakeGcsBucket(objects=set(), retention_period=3_599)

    def fake_credentials(_principal: str) -> object:
        return object()

    def fake_client(
        *,
        project: str,
        credentials: object,
    ) -> _FakeGcsClient:
        assert project == _PROJECT
        return _FakeGcsClient(
            bucket=bucket,
            credentials=credentials,
        )

    monkeypatch.setattr(
        runner_module,
        "_impersonated_credentials",
        fake_credentials,
    )
    monkeypatch.setattr(
        runner_module.storage,
        "Client",
        fake_client,
    )
    now = datetime(2026, 7, 31, 2, tzinfo=UTC)
    with pytest.raises(SmokePreflightFailure) as caught:
        GcsDispatchWitness(
            project_id=_PROJECT,
            bucket_name="synthetic-evidence",
            principal=_PRINCIPAL,
        ).claim(
            manifest=_manifest(now),
            capability=SmokeCapability.GENERATION,
        )
    assert caught.value.code is SmokePreflightFailureCode.LEDGER_TAMPERED


def test_script_seals_sanitized_packet_on_dispatch_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingRunner:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def run(self, **_kwargs: object) -> None:
            raise VertexSmokeDispatchError("timeout")

        def close(self) -> None:
            pass

    monkeypatch.setattr(smoke_script, "VertexSmokeRunner", _FailingRunner)
    output = tmp_path / "operator-packet.json"
    args = argparse.Namespace(
        ledger_dir=tmp_path / "ledger",
        output=output,
        iam_evidence_sha256=sha256(b"iam").hexdigest(),
        data_control_sha256=sha256(b"controls").hexdigest(),
    )
    with pytest.raises(smoke_script.SmokeRunFailed) as caught:
        smoke_script.execute(args)
    packet = json.loads(output.read_text(encoding="utf-8"))
    assert caught.value.code == "timeout"
    assert packet["payload"]["failure"] == {
        "class": "provider-dispatch",
        "code": "timeout",
    }
    assert packet["payload"]["outcome"] == "failed"
    assert packet["payload"]["providerAttemptCount"] == 0
    assert packet["payload"]["providerSuccessCount"] == 0
