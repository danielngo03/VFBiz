from __future__ import annotations

import json
from base64 import b64encode
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

import requests
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


@dataclass(frozen=True, slots=True)
class SanitizedModelObservation:
    """Content-free provider observation safe for external development telemetry."""

    capability: Literal["generation", "embedding"]
    model_revision: str
    run_id_sha256: str
    manifest_sha256: str
    receipt_sha256: str
    outcome: Literal["succeeded", "failed", "ambiguous", "cancelled"]
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_microusd: int

    def __post_init__(self) -> None:
        if not self.model_revision.strip() or len(self.model_revision) > 160:
            raise ValueError("model revision must be non-empty and bounded")
        for digest in (
            self.run_id_sha256,
            self.manifest_sha256,
            self.receipt_sha256,
        ):
            if not _is_sha256(digest):
                raise ValueError("observation identities must use SHA-256")
        for value in (
            self.input_tokens,
            self.output_tokens,
            self.latency_ms,
            self.cost_microusd,
        ):
            if value < 0:
                raise ValueError(
                    "observation measurements must be non-negative"
                )


class _ObservationSink(Protocol):
    def emit(self, observation: SanitizedModelObservation) -> None: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


class _TrackingExporter(SpanExporter):
    def __init__(self, delegate: SpanExporter) -> None:
        self._delegate = delegate
        self.last_result: SpanExportResult | None = None

    def export(
        self,
        spans: Sequence[ReadableSpan],
    ) -> SpanExportResult:
        self.last_result = self._delegate.export(spans)
        return self.last_result

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._delegate.force_flush(timeout_millis)

    def shutdown(self) -> None:
        self._delegate.shutdown()


class _OtelLangfuseSink:
    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        base_url: str,
    ) -> None:
        auth = b64encode(f"{public_key}:{secret_key}".encode()).decode()
        session = requests.Session()
        session.trust_env = False
        self._session = session
        delegate = OTLPSpanExporter(
            endpoint=f"{base_url}/api/public/otel/v1/traces",
            headers={
                "Authorization": f"Basic {auth}",
                "x-langfuse-ingestion-version": "4",
            },
            timeout=10,
            session=session,
        )
        self._exporter = _TrackingExporter(delegate)
        self._provider = TracerProvider(
            resource=Resource.create(
                {
                    "deployment.environment": "development",
                    "service.name": "vfbiz-ai",
                }
            )
        )
        self._provider.add_span_processor(SimpleSpanProcessor(self._exporter))
        self._tracer = self._provider.get_tracer(
            "vfbiz.ai.observability",
            "1",
        )

    def emit(self, observation: SanitizedModelObservation) -> None:
        with self._tracer.start_as_current_span(
            f"vertex-{observation.capability}-synthetic-smoke"
        ) as span:
            span.set_attribute(
                "langfuse.trace.name",
                "vertex-synthetic-smoke",
            )
            span.set_attribute("langfuse.environment", "development")
            span.set_attribute(
                "langfuse.observation.type",
                observation.capability,
            )
            span.set_attribute(
                "langfuse.observation.model.name",
                observation.model_revision,
            )
            span.set_attribute(
                "langfuse.observation.usage_details",
                json.dumps(
                    {
                        "input": observation.input_tokens,
                        "output": observation.output_tokens,
                        "total": observation.input_tokens
                        + observation.output_tokens,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
            span.set_attribute(
                "langfuse.observation.cost_details",
                json.dumps(
                    {"total": observation.cost_microusd / 1_000_000},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
            metadata = {
                "authority_class": "development-synthetic-observation",
                "content_exported": "false",
                "latency_ms": str(observation.latency_ms),
                "manifest_sha256": observation.manifest_sha256,
                "outcome": observation.outcome,
                "receipt_sha256": observation.receipt_sha256,
                "run_id_sha256": observation.run_id_sha256,
            }
            for key, value in metadata.items():
                span.set_attribute(
                    f"langfuse.observation.metadata.{key}",
                    value,
                )
        if self._exporter.last_result is not SpanExportResult.SUCCESS:
            raise RuntimeError("Langfuse OTLP export failed")

    def flush(self) -> None:
        if not self._provider.force_flush(timeout_millis=10_000):
            raise RuntimeError("Langfuse OTLP flush failed")

    def close(self) -> None:
        self._provider.shutdown()
        self._session.close()


class LangfuseMetadataExporter:
    """Emit content-free observations; raw model I/O is not accepted."""

    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        base_url: str = "https://jp.cloud.langfuse.com",
        environment: Literal["development"] = "development",
        sink: _ObservationSink | None = None,
    ) -> None:
        if (
            not public_key.startswith("pk-lf-")
            or not secret_key.startswith("sk-lf-")
        ):
            raise ValueError("Langfuse credentials are malformed")
        if base_url != "https://jp.cloud.langfuse.com":
            raise ValueError(
                "Langfuse development egress must use the pinned JP origin"
            )
        if environment != "development":
            raise ValueError("Langfuse metadata exporter is development-only")
        self._owns_sink = sink is None
        self._sink: _ObservationSink = sink or _OtelLangfuseSink(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
        )

    def emit(self, observation: SanitizedModelObservation) -> None:
        self._sink.emit(observation)

    def flush(self) -> None:
        self._sink.flush()

    def close(self) -> None:
        if self._owns_sink:
            self._sink.close()
