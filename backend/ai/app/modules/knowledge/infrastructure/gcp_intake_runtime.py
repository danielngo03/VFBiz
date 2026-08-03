from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.modules.knowledge.application.cloud_ingestion_ports import (
    DocumentAiOperationReceipt,
    DocumentAiOutputReader,
)
from app.modules.knowledge.application.cloud_ingestion_reconciliation import (
    DocumentAiReconciliationService,
)
from app.modules.knowledge.application.cloud_ingestion_worker import CloudIngestionWorker
from app.modules.knowledge.application.cloud_materialization import (
    DocumentAiCandidateMaterializationWorker,
    DocumentAiCandidateSummary,
)
from app.modules.knowledge.infrastructure.gcp_cloud_ingestion import (
    GcpCloudObjectStager,
    GcpCloudObjectVerifier,
    GcpDocumentAiBatchProcessor,
    GcpDocumentAiOutputReader,
    GcpMetadataAccessTokenSource,
    GcpPubSubDeadLetterPublisher,
    GcpPubSubPushEnvelopeDecoder,
)
from app.modules.knowledge.infrastructure.postgres_cloud_ingestion import (
    PostgresDocumentAiReconciliationRepository,
    PostgresDocumentAiSubmissionLedger,
)
from app.platform.config import Settings


@dataclass(frozen=True, slots=True)
class GcpIntakeRuntime:
    worker: CloudIngestionWorker
    output_reader: DocumentAiOutputReader
    reconciler: DocumentAiReconciliationService
    candidate_materialization_worker: DocumentAiCandidateMaterializationWorker | None
    reconcile_batch_size: int
    http_client: httpx.Client
    database_engine: Engine

    async def materialize_candidate(
        self,
        receipt: DocumentAiOperationReceipt,
        *,
        deletion_generation: int = 0,
        fencing_token: int | None = None,
    ) -> DocumentAiCandidateSummary:
        """Run the explicit post-reconciliation candidate boundary.

        The intake HTTP worker never calls this method. A separately deployed,
        bounded reconciliation/materialization job must inject the scanner,
        chunker, embedder and candidate sink. Keeping the dependency optional
        makes an accidental candidate write impossible in the intake service.
        """
        if self.candidate_materialization_worker is None:
            raise RuntimeError("GCP_CANDIDATE_MATERIALIZATION_DISABLED")
        return await self.candidate_materialization_worker.run(
            receipt,
            deletion_generation=deletion_generation,
            fencing_token=fencing_token,
        )

    def close(self) -> None:
        self.http_client.close()
        self.database_engine.dispose()


def build_gcp_intake_runtime(
    settings: Settings,
    *,
    candidate_materialization_worker: DocumentAiCandidateMaterializationWorker | None = None,
) -> GcpIntakeRuntime:
    project_id = _required(settings.knowledge_gcp_project_id, "GCP project")
    location = _required(settings.knowledge_gcp_location, "GCP location")
    processor_id = _required(settings.knowledge_gcp_document_processor_id, "Document AI processor")
    processor_revision = _required(
        settings.knowledge_gcp_document_processor_revision,
        "Document AI processor revision",
    )
    staging_bucket = _required(settings.knowledge_gcp_staging_bucket, "staging bucket")
    output_bucket = _required(settings.knowledge_gcp_output_bucket, "output bucket")
    subscription = _subscription_name(
        project_id,
        _required(settings.knowledge_gcp_pubsub_subscription, "Pub/Sub subscription"),
    )
    dead_letter_topic = _topic_id(
        project_id,
        _required(settings.knowledge_gcp_pubsub_dead_letter_topic, "dead-letter topic"),
    )
    database_url = _required(settings.database_url, "database URL")
    database_engine = create_engine(_sync_database_url(database_url), pool_pre_ping=True)
    sessions = sessionmaker(database_engine, class_=Session, expire_on_commit=False)
    http_client = httpx.Client(trust_env=False)
    token_source = GcpMetadataAccessTokenSource(client=http_client)
    ledger = PostgresDocumentAiSubmissionLedger(
        sessions,
        clock=lambda: datetime.now(UTC),
        max_pages_per_day=settings.knowledge_gcp_daily_page_budget,
    )
    processor = GcpDocumentAiBatchProcessor(
        project_id=project_id,
        location=location,
        processor_id=processor_id,
        processor_revision=processor_revision,
        allowed_input_buckets=(*settings.knowledge_gcp_input_buckets, staging_bucket),
        output_bucket=output_bucket,
        access_token=token_source,
        client=http_client,
        ledger=ledger,
        clock=lambda: datetime.now(UTC),
        max_pages_per_batch=settings.knowledge_gcp_max_pages_per_batch,
        max_source_bytes=settings.knowledge_gcp_max_source_bytes,
    )
    output_reader = GcpDocumentAiOutputReader(
        output_bucket=output_bucket,
        access_token=token_source,
        client=http_client,
        max_output_objects=settings.knowledge_gcp_max_output_objects,
        max_output_object_bytes=settings.knowledge_gcp_max_output_object_bytes,
        max_output_total_bytes=settings.knowledge_gcp_max_output_total_bytes,
        max_extracted_text_bytes=settings.knowledge_gcp_max_extracted_text_bytes,
        min_page_confidence=settings.knowledge_gcp_min_page_confidence,
        min_page_text_characters=settings.knowledge_gcp_min_page_text_characters,
        deadline_seconds=settings.knowledge_gcp_reconciliation_deadline_seconds,
    )
    reconciliation_repository = PostgresDocumentAiReconciliationRepository(
        sessions,
        clock=lambda: datetime.now(UTC),
    )
    reconciler = DocumentAiReconciliationService(
        processor=processor,
        output_reader=output_reader,
        repository=reconciliation_repository,
    )
    worker = CloudIngestionWorker(
        decoder=GcpPubSubPushEnvelopeDecoder(expected_subscription=subscription),
        object_verifier=GcpCloudObjectVerifier(
            allowed_buckets=settings.knowledge_gcp_input_buckets,
            approved_smoke_documents=settings.knowledge_gcp_synthetic_smoke_manifest,
            access_token=token_source,
            client=http_client,
            max_source_bytes=settings.knowledge_gcp_max_source_bytes,
        ),
        object_stager=GcpCloudObjectStager(
            destination_bucket=staging_bucket,
            access_token=token_source,
            client=http_client,
        ),
        processor=processor,
        dead_letters=GcpPubSubDeadLetterPublisher(
            project_id=project_id,
            topic_id=dead_letter_topic,
            access_token=token_source,
            client=http_client,
        ),
        output_bucket=output_bucket,
        processor_revision=processor_revision,
        clock=lambda: datetime.now(UTC),
    )
    return GcpIntakeRuntime(
        worker=worker,
        output_reader=output_reader,
        reconciler=reconciler,
        candidate_materialization_worker=candidate_materialization_worker,
        reconcile_batch_size=settings.knowledge_gcp_reconcile_batch_size,
        http_client=http_client,
        database_engine=database_engine,
    )


def _required(value: str | None, label: str) -> str:
    if value is None or not value.strip():
        raise ValueError(f"{label} is required")
    return value


def _subscription_name(project_id: str, value: str) -> str:
    if value.startswith("projects/"):
        expected_prefix = f"projects/{project_id}/subscriptions/"
        if not value.startswith(expected_prefix):
            raise ValueError("Pub/Sub subscription belongs to another project")
        return value
    return f"projects/{project_id}/subscriptions/{value}"


def _topic_id(project_id: str, value: str) -> str:
    if value.startswith("projects/"):
        prefix = f"projects/{project_id}/topics/"
        if not value.startswith(prefix):
            raise ValueError("dead-letter topic belongs to another project")
        return value.removeprefix(prefix)
    return value


def _sync_database_url(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
