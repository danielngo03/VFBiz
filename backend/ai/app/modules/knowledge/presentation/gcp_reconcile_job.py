from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol

import httpx

from app.modules.knowledge.application.ingestion_ports import (
    PermanentIngestionFailure,
    TransientIngestionFailure,
)
from app.modules.knowledge.infrastructure.gcp_intake_runtime import (
    GcpIntakeRuntime,
    build_gcp_intake_runtime,
)
from app.platform.config import Settings


class RuntimeBuilder(Protocol):
    def __call__(self, settings: Settings) -> GcpIntakeRuntime: ...


def run_reconciliation_job(
    *,
    settings: Settings | None = None,
    runtime_builder: RuntimeBuilder = build_gcp_intake_runtime,
    emit: Callable[[str], None] = print,
) -> int:
    """Run one bounded content-free reconciliation batch for Cloud Run Jobs."""

    runtime: GcpIntakeRuntime | None = None
    try:
        runtime = runtime_builder(settings or Settings())
        outcome = runtime.reconciler.reconcile_pending(
            limit=runtime.reconcile_batch_size,
        )
        emit(outcome.model_dump_json())
        return 0
    except PermanentIngestionFailure as error:
        emit(_failure_payload(error.code, retryable=False))
        return 2
    except TransientIngestionFailure as error:
        emit(_failure_payload(error.code, retryable=True))
        return 1
    except (httpx.HTTPError, OSError):
        emit(_failure_payload("GCP_PROVIDER_UNAVAILABLE", retryable=True))
        return 1
    except Exception:
        emit(_failure_payload("RECONCILIATION_JOB_UNEXPECTED", retryable=True))
        return 1
    finally:
        if runtime is not None:
            runtime.close()


def _failure_payload(code: str, *, retryable: bool) -> str:
    return json.dumps(
        {
            "schema_revision": "document-ai-reconciliation-job-v1",
            "status": "failed",
            "failure_code": code,
            "retryable": retryable,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def main() -> int:
    return run_reconciliation_job()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_reconciliation_job"]
