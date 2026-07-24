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
    assert settings.provider == "disabled"
    assert settings.internal_api_prefix == "/internal/v1"


def test_staging_requires_database_and_redis() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None, environment="staging", expose_docs=False)


def test_enabled_provider_requires_pinned_models() -> None:
    with pytest.raises(ValidationError, match="chat_model"):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://vfbiz:vfbiz@localhost:5432/vfbiz_ai",
            redis_url="redis://localhost:6379/2",
            provider="openai",
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
