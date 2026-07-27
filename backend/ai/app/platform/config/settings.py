from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


@dataclass(frozen=True, slots=True)
class OpenAICapabilitySettings:
    api_key: SecretStr | None
    base_url: str
    project_id: str | None
    organization_id: str | None
    retention_policy: str
    approval_reference: str | None
    approval_sha256: str | None


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
    gateway_issuer: str = "vfbiz-api"
    gateway_audience: str = "vfbiz-ai"
    gateway_jwks_url: str = "http://127.0.0.1:8000/api/v1/internal/ai/jwks"
    gateway_jwks_allowed_origins: tuple[str, ...] = ()

    generation_provider: Literal["disabled", "openai", "azure_openai", "self_hosted"] = "disabled"
    embedding_provider: Literal["disabled", "openai", "azure_openai", "self_hosted"] = "disabled"
    generation_model: str = "disabled"
    embedding_model: str = "disabled"
    embedding_dimension: int = Field(default=8, ge=1, le=65_536)
    embedding_max_items_per_request: int = Field(default=64, ge=1, le=2_048)
    embedding_max_input_bytes_per_request: int = Field(default=1_048_576, ge=1_024, le=16_777_216)
    embedding_max_input_tokens_per_request: int = Field(default=128_000, ge=1, le=2_000_000)
    embedding_max_concurrency: int = Field(default=16, ge=1, le=1_024)
    embedding_max_response_bytes: int = Field(default=8_388_608, ge=1_024, le=67_108_864)
    embedding_max_output_elements: int = Field(default=1_048_576, ge=1, le=16_777_216)
    embedding_input_template_revision: str = Field(
        default="identity-v1", min_length=1, max_length=160
    )
    embedding_query_prefix: str = Field(default="", max_length=1_024)
    embedding_document_prefix: str = Field(default="", max_length=1_024)
    embedding_circuit_failure_threshold: int = Field(default=3, ge=1, le=100)
    embedding_circuit_recovery_seconds: float = Field(default=30, ge=1, le=600)
    embedding_input_microusd_per_million_tokens: int = Field(default=0, ge=0)
    embedding_fixed_request_cost_microusd: int = Field(default=0, ge=0)
    self_hosted_embedding_base_url: str = "http://127.0.0.1:8080"
    self_hosted_embedding_api_token: SecretStr | None = None
    self_hosted_embedding_tokenizer_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    self_hosted_embedding_weights_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    self_hosted_embedding_deployment_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    request_timeout_seconds: float = Field(default=30, ge=1, le=120)
    max_input_tokens: int = Field(default=16_000, ge=1, le=1_000_000)
    max_output_tokens: int = Field(default=1_200, ge=1, le=16_384)
    model_policy_profile: str = Field(
        default="customer-grounded-v1",
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*-v[1-9][0-9]*$",
    )
    prompt_revision: str = Field(
        default="customer-grounded-v1",
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*-v[1-9][0-9]*$",
    )
    structured_schema_revision: str = Field(default="grounded-answer-v2", min_length=1)
    model_safety_tier: str = Field(default="customer-factual-v1", min_length=1)
    model_residency: str = Field(default="global", min_length=1)
    max_response_bytes: int = Field(default=262_144, ge=1_024, le=4_194_304)
    max_provider_concurrency: int = Field(default=32, ge=1, le=1_024)
    input_microusd_per_million_tokens: int = Field(default=0, ge=0)
    output_microusd_per_million_tokens: int = Field(default=0, ge=0)
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_project_id: str | None = Field(default=None, max_length=160)
    openai_organization_id: str | None = Field(default=None, max_length=160)
    openai_generation_model_allowlist: tuple[str, ...] = ()
    openai_embedding_model_allowlist: tuple[str, ...] = ()
    openai_retention_policy: Literal[
        "standard",
        "zero_data_retention",
        "modified_abuse_monitoring",
    ] = "standard"
    openai_data_controls_approval_reference: str | None = Field(
        default=None,
        max_length=160,
    )
    openai_data_controls_approval_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    model_release_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    generation_openai_api_key: SecretStr | None = None
    generation_openai_base_url: str | None = None
    generation_openai_project_id: str | None = Field(default=None, max_length=160)
    generation_openai_organization_id: str | None = Field(default=None, max_length=160)
    generation_openai_retention_policy: Literal[
        "standard",
        "zero_data_retention",
        "modified_abuse_monitoring",
    ] | None = None
    generation_openai_approval_reference: str | None = Field(
        default=None, max_length=160
    )
    generation_openai_approval_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    embedding_openai_api_key: SecretStr | None = None
    embedding_openai_base_url: str | None = None
    embedding_openai_project_id: str | None = Field(default=None, max_length=160)
    embedding_openai_organization_id: str | None = Field(default=None, max_length=160)
    embedding_openai_retention_policy: Literal[
        "standard",
        "zero_data_retention",
        "modified_abuse_monitoring",
    ] | None = None
    embedding_openai_approval_reference: str | None = Field(
        default=None, max_length=160
    )
    embedding_openai_approval_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )

    knowledge_ingestion_profile: Literal["disabled", "synthetic_local"] = "disabled"
    knowledge_synthetic_source_root: Path | None = None
    knowledge_artifact_root: Path | None = None
    knowledge_source_map_path: Path | None = None
    knowledge_scanner_revision: str = "deterministic-v1"
    knowledge_policy_revision: str = "policy-v1"
    knowledge_embedding_dimension: int = Field(default=8, ge=1, le=65_536)

    def openai_capability(
        self,
        capability: Literal["generation", "embedding"],
    ) -> OpenAICapabilitySettings:
        dedicated = (
            self.generation_openai_api_key
            if capability == "generation"
            else self.embedding_openai_api_key
        )
        other_enabled = (
            self.embedding_provider == "openai"
            if capability == "generation"
            else self.generation_provider == "openai"
        )
        allow_legacy = not other_enabled
        prefix = "generation" if capability == "generation" else "embedding"
        return OpenAICapabilitySettings(
            api_key=dedicated or (self.openai_api_key if allow_legacy else None),
            base_url=(
                getattr(self, f"{prefix}_openai_base_url")
                or (self.openai_base_url if allow_legacy else "")
            ),
            project_id=(
                getattr(self, f"{prefix}_openai_project_id")
                or (self.openai_project_id if allow_legacy else None)
            ),
            organization_id=(
                getattr(self, f"{prefix}_openai_organization_id")
                or (self.openai_organization_id if allow_legacy else None)
            ),
            retention_policy=(
                getattr(self, f"{prefix}_openai_retention_policy")
                or (self.openai_retention_policy if allow_legacy else "")
            ),
            approval_reference=(
                getattr(self, f"{prefix}_openai_approval_reference")
                or (
                    self.openai_data_controls_approval_reference
                    if allow_legacy
                    else None
                )
            ),
            approval_sha256=(
                getattr(self, f"{prefix}_openai_approval_sha256")
                or (
                    self.openai_data_controls_approval_sha256
                    if allow_legacy
                    else None
                )
            ),
        )

    @model_validator(mode="after")
    def validate_runtime_policy(self) -> Self:
        if self.environment in {"staging", "production"}:
            if self.database_url is None:
                raise ValueError("database_url is required outside local/test")
            if self.redis_url is None:
                raise ValueError("redis_url is required outside local/test")
            if self.expose_docs:
                raise ValueError("expose_docs must be false outside local/test")
            jwks = urlsplit(self.gateway_jwks_url)
            origin = f"{jwks.scheme}://{jwks.netloc}"
            if (
                jwks.scheme != "https"
                or not jwks.hostname
                or jwks.username
                or jwks.password
                or jwks.query
                or jwks.fragment
            ):
                raise ValueError(
                    "gateway_jwks_url must be an HTTPS URL without credentials, query or fragment"
                )
            if origin not in self.gateway_jwks_allowed_origins:
                raise ValueError("gateway_jwks_url origin is not in gateway_jwks_allowed_origins")
        else:
            jwks = urlsplit(self.gateway_jwks_url)
            if jwks.scheme == "http" and jwks.hostname not in {
                "127.0.0.1",
                "localhost",
                "::1",
            }:
                raise ValueError("cleartext gateway_jwks_url is allowed only on loopback")
        if self.generation_provider != "disabled":
            if self.generation_model == "disabled":
                raise ValueError(
                    "generation_model must be pinned for an enabled generation provider"
                )
        if self.embedding_provider != "disabled":
            if self.embedding_model == "disabled":
                raise ValueError("embedding_model must be pinned for an enabled embedding provider")
        if self.embedding_provider == "self_hosted":
            endpoint = urlsplit(self.self_hosted_embedding_base_url)
            is_loopback = endpoint.hostname in {"127.0.0.1", "localhost", "::1"}
            if (
                not endpoint.hostname
                or endpoint.username
                or endpoint.password
                or endpoint.query
                or endpoint.fragment
                or endpoint.path.rstrip("/")
            ):
                raise ValueError(
                    "self_hosted_embedding_base_url must be an origin without "
                    "credentials, query, fragment or path"
                )
            if endpoint.scheme != "https" and not (
                self.environment in {"development", "test"}
                and endpoint.scheme == "http"
                and is_loopback
            ):
                raise ValueError(
                    "self_hosted_embedding_base_url must use HTTPS outside a local/test loopback"
                )
            if any(
                digest is None
                for digest in (
                    self.self_hosted_embedding_tokenizer_sha256,
                    self.self_hosted_embedding_weights_sha256,
                    self.self_hosted_embedding_deployment_sha256,
                )
            ):
                raise ValueError(
                    "self-hosted embedding requires pinned tokenizer, weights "
                    "and deployment SHA-256 fingerprints"
                )
            if self.environment in {"staging", "production"} and (
                self.self_hosted_embedding_api_token is None
                or not self.self_hosted_embedding_api_token.get_secret_value().strip()
            ):
                raise ValueError("self-hosted embedding requires workload service credentials")
        if "openai" in {self.generation_provider, self.embedding_provider}:
            if (
                self.generation_provider == "openai"
                and self.generation_model not in self.openai_generation_model_allowlist
            ):
                raise ValueError("generation_model must be in openai_generation_model_allowlist")
            if (
                self.embedding_provider == "openai"
                and self.embedding_model not in self.openai_embedding_model_allowlist
            ):
                raise ValueError("embedding_model must be in openai_embedding_model_allowlist")
            capabilities = tuple(
                capability
                for capability, provider in (
                    ("generation", self.generation_provider),
                    ("embedding", self.embedding_provider),
                )
                if provider == "openai"
            )
            for capability in capabilities:
                identity = self.openai_capability(capability)  # type: ignore[arg-type]
                if (
                    identity.api_key is None
                    or not identity.api_key.get_secret_value().strip()
                    or identity.project_id is None
                    or not identity.project_id.strip()
                    or identity.approval_reference is None
                    or not identity.approval_reference.strip()
                    or identity.approval_sha256 is None
                ):
                    raise ValueError(
                        f"{capability} OpenAI capability requires independent "
                        "credentials, project and durable approval evidence"
                    )
                endpoint = urlsplit(identity.base_url)
                if (
                    not endpoint.hostname
                    or endpoint.username
                    or endpoint.password
                    or endpoint.query
                    or endpoint.fragment
                ):
                    raise ValueError(
                        f"{capability} OpenAI base URL must not contain "
                        "credentials, query or fragment"
                    )
                if endpoint.scheme != "https":
                    is_local = endpoint.scheme == "http" and endpoint.hostname in {
                        "127.0.0.1",
                        "localhost",
                        "::1",
                    }
                    if self.environment not in {"development", "test"} or not is_local:
                        raise ValueError(
                            f"{capability} OpenAI base URL must use HTTPS "
                            "outside a local/test loopback"
                        )
                if self.environment in {"staging", "production"} and (
                    endpoint.hostname != "api.openai.com"
                    or endpoint.port not in {None, 443}
                    or endpoint.path.rstrip("/") != "/v1"
                ):
                    raise ValueError(
                        f"{capability} OpenAI staging/production endpoint must "
                        "be https://api.openai.com/v1"
                    )
            if self.environment in {"staging", "production"}:
                if self.generation_provider == "openai" and (
                    self.input_microusd_per_million_tokens == 0
                    or self.output_microusd_per_million_tokens == 0
                ):
                    raise ValueError("OpenAI generation token prices must be configured for FinOps")
                if (
                    self.embedding_provider == "openai"
                    and self.embedding_input_microusd_per_million_tokens == 0
                ):
                    raise ValueError("OpenAI embedding token price must be configured for FinOps")
        if self.knowledge_ingestion_profile == "synthetic_local":
            if self.environment not in {"development", "test"}:
                raise ValueError("synthetic_local knowledge ingestion is local/test only")
            if self.database_url is None:
                raise ValueError("database_url is required for knowledge ingestion")
            if any(
                value is None
                for value in (
                    self.knowledge_synthetic_source_root,
                    self.knowledge_artifact_root,
                    self.knowledge_source_map_path,
                )
            ):
                raise ValueError("synthetic source root, artifact root and source map are required")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
