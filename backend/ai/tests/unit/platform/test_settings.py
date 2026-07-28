import pytest
from pydantic import ValidationError

from app.platform.config.settings import Settings


def test_development_settings_are_typed() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
        redis_url="redis://localhost:6379/2",
    )

    assert settings.environment == "development"
    assert settings.generation_provider == "disabled"
    assert settings.embedding_provider == "disabled"
    assert settings.internal_api_prefix == "/internal/v1"


def test_staging_requires_database_and_redis() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None, environment="staging", expose_docs=False)


def test_enabled_generation_provider_requires_pinned_model() -> None:
    with pytest.raises(ValidationError, match="generation_model"):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
            redis_url="redis://localhost:6379/2",
            generation_provider="openai",
        )


def test_documentation_cannot_be_exposed_in_production() -> None:
    with pytest.raises(ValidationError, match="expose_docs"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
            redis_url="redis://localhost:6379/2",
            expose_docs=True,
        )


def test_staging_requires_https_allowlisted_jwks_origin() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            _env_file=None,
            environment="staging",
            database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
            redis_url="redis://localhost:6379/2",
            expose_docs=False,
        )

    with pytest.raises(ValidationError, match="allowed_origins"):
        Settings(
            _env_file=None,
            environment="staging",
            database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
            redis_url="redis://localhost:6379/2",
            expose_docs=False,
            gateway_jwks_url="https://api.internal.example/.well-known/jwks.json",
        )

    settings = Settings(
        _env_file=None,
        environment="staging",
        database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
        redis_url="redis://localhost:6379/2",
        expose_docs=False,
        gateway_jwks_url="https://api.internal.example/.well-known/jwks.json",
        gateway_jwks_allowed_origins=("https://api.internal.example",),
        response_signing_key_id="ai-response-current",
        response_signing_private_key_file="/run/secrets/ai-response-private.pem",
    )
    assert settings.gateway_jwks_url.startswith("https://")
