from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from app.modules.knowledge.application.cloud_ingestion_ports import (
    DocumentAiOperationReceipt,
)
from app.modules.knowledge.application.cloud_ingestion_reconciliation import (
    DocumentAiReconciliationBatchOutcome,
)
from app.modules.knowledge.application.cloud_materialization import (
    DocumentAiCandidateMaterializationWorker,
)
from app.modules.knowledge.application.ingestion_ports import (
    TransientIngestionFailure,
)
from app.modules.knowledge.infrastructure.gcp_intake_runtime import GcpIntakeRuntime
from app.modules.knowledge.presentation.gcp_reconcile_job import run_reconciliation_job
from app.platform.config import Settings


def _runtime_with_candidate_worker(
    worker: DocumentAiCandidateMaterializationWorker | None,
) -> GcpIntakeRuntime:
    return cast(
        GcpIntakeRuntime,
        SimpleNamespace(candidate_materialization_worker=worker),
    )


def _gcp_runtime_settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
        knowledge_ingestion_profile="gcp",
        knowledge_gcp_project_id="vinfast-503003",
        knowledge_gcp_location="asia-southeast1",
        knowledge_gcp_document_processor_id="processor-1",
        knowledge_gcp_document_processor_revision="pretrained-ocr-v2.1.1-2025-01-31",
        knowledge_gcp_input_buckets=("vinfast-503003-intake-dev",),
        knowledge_gcp_staging_bucket="vinfast-503003-derived-dev",
        knowledge_gcp_output_bucket="vinfast-503003-ocr-output-dev",
        knowledge_gcp_pubsub_subscription="worker-sub",
        knowledge_gcp_pubsub_dead_letter_topic="dead-letter",
        knowledge_gcp_synthetic_smoke_manifest={"a" * 64: 1},
    )


def test_runtime_composition_keeps_staging_and_output_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.knowledge.infrastructure.gcp_intake_runtime as runtime_module

    class _FakeHttpClient:
        def close(self) -> None:
            return None

    class _FakeEngine:
        def dispose(self) -> None:
            return None

    captured: dict[str, dict[str, object]] = {}

    def capture(name: str) -> object:
        def factory(*args: object, **kwargs: object) -> object:
            if args:
                kwargs["_positional"] = args
            captured[name] = kwargs
            return object()

        return factory

    monkeypatch.setattr(runtime_module.httpx, "Client", lambda **_kwargs: _FakeHttpClient())
    monkeypatch.setattr(runtime_module, "create_engine", lambda *_args, **_kwargs: _FakeEngine())
    monkeypatch.setattr(runtime_module, "sessionmaker", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runtime_module, "GcpMetadataAccessTokenSource", capture("token"))
    monkeypatch.setattr(runtime_module, "PostgresDocumentAiSubmissionLedger", capture("ledger"))
    monkeypatch.setattr(runtime_module, "GcpDocumentAiBatchProcessor", capture("processor"))
    monkeypatch.setattr(runtime_module, "GcpDocumentAiOutputReader", capture("reader"))
    monkeypatch.setattr(
        runtime_module,
        "PostgresDocumentAiReconciliationRepository",
        capture("repository"),
    )
    monkeypatch.setattr(runtime_module, "DocumentAiReconciliationService", capture("reconciler"))
    monkeypatch.setattr(runtime_module, "GcpPubSubPushEnvelopeDecoder", capture("decoder"))
    monkeypatch.setattr(runtime_module, "GcpCloudObjectVerifier", capture("verifier"))
    monkeypatch.setattr(runtime_module, "GcpCloudObjectStager", capture("stager"))
    monkeypatch.setattr(runtime_module, "GcpPubSubDeadLetterPublisher", capture("dead_letters"))
    monkeypatch.setattr(runtime_module, "CloudIngestionWorker", capture("worker"))

    runtime = runtime_module.build_gcp_intake_runtime(_gcp_runtime_settings())
    runtime.close()

    assert captured["processor"]["output_bucket"] == "vinfast-503003-ocr-output-dev"
    assert captured["processor"]["allowed_input_buckets"] == (
        "vinfast-503003-intake-dev",
        "vinfast-503003-derived-dev",
    )
    assert captured["reader"]["output_bucket"] == "vinfast-503003-ocr-output-dev"
    assert captured["stager"]["destination_bucket"] == "vinfast-503003-derived-dev"
    assert captured["worker"]["output_bucket"] == "vinfast-503003-ocr-output-dev"


@pytest.mark.asyncio
async def test_runtime_candidate_boundary_is_optional_and_forwarded() -> None:
    receipt = cast(DocumentAiOperationReceipt, object())
    calls: list[tuple[object, int, int | None]] = []

    class _CandidateWorker:
        async def run(
            self,
            received: DocumentAiOperationReceipt,
            *,
            deletion_generation: int,
            fencing_token: int | None,
        ) -> object:
            calls.append((received, deletion_generation, fencing_token))
            return object()

    runtime = _runtime_with_candidate_worker(
        cast(DocumentAiCandidateMaterializationWorker, _CandidateWorker())
    )
    result = await GcpIntakeRuntime.materialize_candidate(
        runtime,
        receipt,
        deletion_generation=4,
        fencing_token=9,
    )

    assert result is not None
    assert calls == [(receipt, 4, 9)]

    disabled = _runtime_with_candidate_worker(None)
    with pytest.raises(RuntimeError, match="GCP_CANDIDATE_MATERIALIZATION_DISABLED"):
        await GcpIntakeRuntime.materialize_candidate(disabled, receipt)


class _Reconciler:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def reconcile_pending(self, *, limit: int) -> DocumentAiReconciliationBatchOutcome:
        assert limit == 1
        if self._fail:
            raise TransientIngestionFailure("DOCUMENT_AI_OUTPUT_UNAVAILABLE")
        return DocumentAiReconciliationBatchOutcome(
            processed_count=0,
            outcomes=(),
        )


class _Runtime:
    def __init__(self, *, fail: bool = False) -> None:
        self.reconciler = _Reconciler(fail=fail)
        self.reconcile_batch_size = 1
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_reconciliation_job_emits_only_content_free_outcome_and_closes() -> None:
    runtime = _Runtime()
    emitted: list[str] = []

    result = run_reconciliation_job(
        settings=Settings(environment="test"),
        runtime_builder=lambda _settings: cast(GcpIntakeRuntime, runtime),
        emit=emitted.append,
    )

    assert result == 0
    assert runtime.closed
    assert emitted == [
        '{"schema_revision":"document-ai-reconciliation-batch-v1",'
        '"processed_count":0,"outcomes":[]}'
    ]
    assert "text" not in emitted[0].lower()


def test_reconciliation_job_sanitizes_retryable_failure_and_closes() -> None:
    runtime = _Runtime(fail=True)
    emitted: list[str] = []

    result = run_reconciliation_job(
        settings=Settings(environment="test"),
        runtime_builder=lambda _settings: cast(GcpIntakeRuntime, runtime),
        emit=emitted.append,
    )

    assert result == 1
    assert runtime.closed
    assert emitted == [
        '{"failure_code":"DOCUMENT_AI_OUTPUT_UNAVAILABLE",'
        '"retryable":true,"schema_revision":"document-ai-reconciliation-job-v1",'
        '"status":"failed"}'
    ]
    assert "provider" not in emitted[0].lower()
