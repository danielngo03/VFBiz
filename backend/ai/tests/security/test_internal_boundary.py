import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_application
from app.platform.config import Settings


def client() -> AsyncClient:
    application = create_application(
        Settings(environment="test", allowed_hosts=("testserver",), expose_docs=False)
    )
    return AsyncClient(
        transport=ASGITransport(app=application, raise_app_exceptions=False),
        base_url="http://testserver",
    )


@pytest.mark.asyncio
async def test_liveness_is_the_only_unauthenticated_health_route() -> None:
    async with client() as http:
        response = await http.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_internal_routes_fail_closed_without_gateway_assertion() -> None:
    async with client() as http:
        response = await http.get("/internal/v1/health/ready")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "GATEWAY_ASSERTION_REQUIRED"


@pytest.mark.asyncio
async def test_internal_routes_reject_malformed_assertion_without_provider_call() -> None:
    async with client() as http:
        response = await http.get(
            "/internal/v1/health/ready",
            headers={"authorization": "Bearer malformed"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_GATEWAY_ASSERTION"


@pytest.mark.asyncio
async def test_sensitive_response_headers_are_always_present() -> None:
    async with client() as http:
        response = await http.get("/health/live")

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
