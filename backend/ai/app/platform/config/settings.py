from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VFBIZ_AI_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    service_name: str = Field(default="VFBiz AI Platform", min_length=1, max_length=80)
    internal_api_prefix: Literal["/internal/v1"] = "/internal/v1"
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    expose_docs: bool = True

    database_url: str | None = None
    redis_url: RedisDsn | None = None
    gateway_issuer: str = "http://127.0.0.1:8000"
    gateway_audience: str = "vfbiz-ai-internal"
    gateway_jwks_url: str = "http://127.0.0.1:8000/.well-known/jwks.json"

    provider: Literal["disabled", "openai", "azure_openai", "self_hosted"] = "disabled"
    chat_model: str = "disabled"
    embedding_model: str = "disabled"
    request_timeout_seconds: float = Field(default=30, ge=1, le=120)
    max_output_tokens: int = Field(default=1_200, ge=1, le=16_384)

    @model_validator(mode="after")
    def validate_runtime_policy(self) -> Self:
        if self.environment in {"staging", "production"}:
            if self.database_url is None:
                raise ValueError("database_url is required outside local/test")
            if self.redis_url is None:
                raise ValueError("redis_url is required outside local/test")
            if self.expose_docs:
                raise ValueError("expose_docs must be false outside local/test")
        if self.provider != "disabled":
            if self.chat_model == "disabled":
                raise ValueError("chat_model must be pinned for an enabled provider")
            if self.embedding_model == "disabled":
                raise ValueError("embedding_model must be pinned for an enabled provider")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
