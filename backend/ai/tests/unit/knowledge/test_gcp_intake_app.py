from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import httpx
from fastapi.testclient import TestClient

from app.modules.knowledge.presentation.gcp_intake import (
    create_gcp_intake_application,
)
from app.platform.config import Settings


class _StubWorker:
    def dispatch(self, body: bytes) -> object:
        assert body == b"pointer-only"
        return {
            "status": "accepted",
            "message_id": "message-1",
            "receipt_id": "receipt.0199",
            "operation_name": (
                "projects/vinfast-503003/locations/asia-southeast1/operations/op-0199"
            ),
            "dead_letter_message_id": None,
        }


def _post(
    client: TestClient,
    url: str,
    *,
    content: bytes | None = None,
) -> httpx.Response:
    return cast(
        httpx.Response,
        client.post(url, content=content),  # pyright: ignore[reportUnknownMemberType]
    )


def test_worker_endpoint_is_disabled_without_gcp_profile() -> None:
    app = create_gcp_intake_application(Settings(environment="test", expose_docs=False))

    with TestClient(app) as client:
        response = _post(
            client,
            "/internal/v1/knowledge/gcp-intake/pubsub",
            content=b"pointer-only",
        )

    assert response.status_code == 503
    assert response.json() == {"code": "GCP_INTAKE_DISABLED", "retryable": True}


def test_worker_endpoint_accepts_bounded_pointer_delivery() -> None:
    app = create_gcp_intake_application(Settings(environment="test", expose_docs=False))

    with TestClient(app) as client:
        app.state.gcp_intake_runtime = SimpleNamespace(worker=_StubWorker())
        response = _post(
            client,
            "/internal/v1/knowledge/gcp-intake/pubsub",
            content=b"pointer-only",
        )

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert "text" not in response.text.lower()


def test_worker_endpoint_rejects_oversized_body_before_dispatch() -> None:
    app = create_gcp_intake_application(Settings(environment="test", expose_docs=False))

    with TestClient(app) as client:
        app.state.gcp_intake_runtime = SimpleNamespace(worker=_StubWorker())
        response = _post(
            client,
            "/internal/v1/knowledge/gcp-intake/pubsub",
            content=b"x" * 32_769,
        )

    assert response.status_code == 413
    assert response.json()["code"] == "PUBSUB_ENVELOPE_TOO_LARGE"


def test_reconciliation_is_not_exposed_by_the_pubsub_service() -> None:
    app = create_gcp_intake_application(Settings(environment="test", expose_docs=False))

    with TestClient(app) as client:
        response = _post(client, "/internal/v1/knowledge/gcp-intake/reconcile")

    assert response.status_code == 404
