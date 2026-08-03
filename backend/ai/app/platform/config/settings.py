import re
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


@dataclass(frozen=True, slots=True)
class VertexCapabilitySettings:
    project_id: str | None
    location: str | None
    model_allowlist: tuple[str, ...]
    retention_policy: str
    approval_reference: str | None
    approval_sha256: str | None
    pricing_revision: str | None


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
    evaluation_runner_database_url: str | None = None
    evaluation_sealer_database_url: str | None = None
    evaluation_definition_reader_database_url: str | None = None
    redis_url: RedisDsn | None = None
    gateway_issuer: str = "vfbiz-api"
    gateway_audience: str = "vfbiz-ai"
    gateway_jwks_url: str = "http://127.0.0.1:8000/api/v1/internal/ai/jwks"
    gateway_jwks_allowed_origins: tuple[str, ...] = ()
    response_signing_key_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$"
    )
    response_signing_private_key_file: Path | None = None
    response_signing_ttl_seconds: int = Field(default=30, ge=5, le=60)

    semantic_classifier_provider: Literal["disabled", "http"] = "disabled"
    semantic_classifier_endpoint: str | None = None
    semantic_classifier_allowed_origins: tuple[str, ...] = ()
    semantic_classifier_api_token: SecretStr | None = None
    semantic_classifier_artifact_ref: str | None = Field(
        default=None,
        pattern=r"^classifier://[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$",
    )
    semantic_classifier_artifact_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    semantic_classifier_timeout_seconds: float = Field(default=2, gt=0, le=10)
    semantic_classifier_max_request_bytes: int = Field(default=32_768, ge=1_024, le=262_144)
    semantic_classifier_max_response_bytes: int = Field(default=16_384, ge=1_024, le=262_144)
    semantic_classifier_max_concurrency: int = Field(default=16, ge=1, le=256)

    generation_provider: Literal[
        "disabled", "openai", "azure_openai", "self_hosted", "vertex"
    ] = "disabled"
    embedding_provider: Literal[
        "disabled", "openai", "azure_openai", "self_hosted", "vertex"
    ] = "disabled"
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
    vertex_project_id: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$"
    )
    vertex_location: str | None = Field(default=None, max_length=64)
    vertex_generation_model_allowlist: tuple[str, ...] = ()
    vertex_embedding_model_allowlist: tuple[str, ...] = ()
    vertex_retention_policy: Literal[
        "standard", "zero_data_retention", "modified_abuse_monitoring"
    ] = "standard"
    vertex_data_controls_approval_reference: str | None = Field(
        default=None, max_length=160
    )
    vertex_data_controls_approval_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    vertex_pricing_revision: str | None = Field(default=None, max_length=160)
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
    generation_openai_retention_policy: (
        Literal[
            "standard",
            "zero_data_retention",
            "modified_abuse_monitoring",
        ]
        | None
    ) = None
    generation_openai_approval_reference: str | None = Field(default=None, max_length=160)
    generation_openai_approval_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    embedding_openai_api_key: SecretStr | None = None
    embedding_openai_base_url: str | None = None
    embedding_openai_project_id: str | None = Field(default=None, max_length=160)
    embedding_openai_organization_id: str | None = Field(default=None, max_length=160)
    embedding_openai_retention_policy: (
        Literal[
            "standard",
            "zero_data_retention",
            "modified_abuse_monitoring",
        ]
        | None
    ) = None
    embedding_openai_approval_reference: str | None = Field(default=None, max_length=160)
    embedding_openai_approval_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    knowledge_ingestion_profile: Literal["disabled", "synthetic_local", "gcp"] = "disabled"
    knowledge_synthetic_source_root: Path | None = None
    knowledge_artifact_root: Path | None = None
    knowledge_source_map_path: Path | None = None
    knowledge_scanner_revision: str = "deterministic-v1"
    knowledge_policy_revision: str = "policy-v1"
    knowledge_embedding_dimension: int = Field(default=8, ge=1, le=65_536)
    knowledge_gcp_project_id: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$"
    )
    knowledge_gcp_location: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{1,30}[0-9]$")
    knowledge_gcp_document_processor_id: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9._-]{0,159}$"
    )
    knowledge_gcp_document_processor_revision: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$"
    )
    knowledge_gcp_input_buckets: tuple[str, ...] = ()
    knowledge_gcp_output_bucket: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9._-]{2,62}$"
    )
    knowledge_gcp_staging_bucket: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9._-]{2,62}$"
    )
    knowledge_gcp_pubsub_subscription: str | None = Field(
        default=None, min_length=1, max_length=512
    )
    knowledge_gcp_pubsub_dead_letter_topic: str | None = Field(
        default=None, min_length=1, max_length=255
    )
    knowledge_gcp_max_pages_per_batch: int = Field(default=500, ge=1, le=500)
    knowledge_gcp_daily_page_budget: int = Field(default=500, ge=1, le=50_000)
    knowledge_gcp_synthetic_smoke_manifest: dict[str, int] = Field(default_factory=dict)
    knowledge_gcp_reconcile_batch_size: int = Field(default=1, ge=1, le=5)
    knowledge_gcp_max_source_bytes: int = Field(default=104_857_600, ge=1, le=1_073_741_824)
    knowledge_gcp_max_output_objects: int = Field(default=20, ge=1, le=20)
    knowledge_gcp_max_output_object_bytes: int = Field(
        default=16_777_216, ge=1, le=67_108_864
    )
    knowledge_gcp_max_output_total_bytes: int = Field(
        default=134_217_728, ge=1, le=268_435_456
    )
    knowledge_gcp_max_extracted_text_bytes: int = Field(
        default=33_554_432, ge=1, le=67_108_864
    )
    knowledge_gcp_min_page_confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    knowledge_gcp_min_page_text_characters: int = Field(default=20, ge=1, le=10_000)
    knowledge_gcp_reconciliation_deadline_seconds: float = Field(
        default=180,
        ge=30,
        le=210,
    )

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
                or (self.openai_data_controls_approval_reference if allow_legacy else None)
            ),
            approval_sha256=(
                getattr(self, f"{prefix}_openai_approval_sha256")
                or (self.openai_data_controls_approval_sha256 if allow_legacy else None)
            ),
        )

    def vertex_capability(
        self,
        capability: Literal["generation", "embedding"],
    ) -> VertexCapabilitySettings:
        allowlist = (
            self.vertex_generation_model_allowlist
            if capability == "generation"
            else self.vertex_embedding_model_allowlist
        )
        return VertexCapabilitySettings(
            project_id=self.vertex_project_id,
            location=self.vertex_location,
            model_allowlist=allowlist,
            retention_policy=self.vertex_retention_policy,
            approval_reference=self.vertex_data_controls_approval_reference,
            approval_sha256=self.vertex_data_controls_approval_sha256,
            pricing_revision=self.vertex_pricing_revision,
        )

    @model_validator(mode="after")
    def validate_runtime_policy(self) -> Self:
        evaluation_database_urls = (
            self.evaluation_runner_database_url,
            self.evaluation_sealer_database_url,
            self.evaluation_definition_reader_database_url,
        )
        configured_evaluation_urls = tuple(
            value for value in evaluation_database_urls if value is not None
        )
        if configured_evaluation_urls and len(configured_evaluation_urls) != 3:
            raise ValueError(
                "evaluation database roles require runner, sealer, "
                "and definition-reader URLs"
            )
        if len(configured_evaluation_urls) == 3:
            usernames = tuple(
                urlsplit(value).username for value in configured_evaluation_urls
            )
            if None in usernames or len(set(usernames)) != 3:
                raise ValueError(
                    "evaluation database URLs require three distinct login roles"
                )
        if self.semantic_classifier_provider == "http":
            if (
                self.semantic_classifier_endpoint is None
                or self.semantic_classifier_artifact_ref is None
                or self.semantic_classifier_artifact_sha256 is None
            ):
                raise ValueError(
                    "semantic classifier requires endpoint and pinned artifact identity"
                )
            classifier_url = urlsplit(self.semantic_classifier_endpoint)
            classifier_origin = f"{classifier_url.scheme}://{classifier_url.netloc}"
            if (
                classifier_url.scheme not in {"http", "https"}
                or not classifier_url.hostname
                or classifier_url.username
                or classifier_url.password
                or classifier_url.query
                or classifier_url.fragment
            ):
                raise ValueError(
                    "semantic classifier endpoint must be an absolute URL "
                    "without credentials, query or fragment"
                )
            classifier_is_loopback = classifier_url.hostname in {
                "localhost",
                "127.0.0.1",
                "::1",
            }
            if self.environment not in {"development", "test"} and classifier_url.scheme != "https":
                raise ValueError("semantic classifier endpoint must use HTTPS outside local/test")
            if (
                not classifier_is_loopback
                and classifier_origin not in self.semantic_classifier_allowed_origins
            ):
                raise ValueError("semantic classifier origin is not explicitly allowed")
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
            if (
                self.response_signing_key_id is None
                or self.response_signing_private_key_file is None
            ):
                raise ValueError(
                    "internal response signing key id and private key file are required "
                    "outside local/test"
                )
        else:
            jwks = urlsplit(self.gateway_jwks_url)
            if jwks.scheme == "http" and jwks.hostname not in {
                "127.0.0.1",
                "localhost",
                "::1",
            }:
                raise ValueError("cleartext gateway_jwks_url is allowed only on loopback")
        response_signing_values = (
            self.response_signing_key_id,
            self.response_signing_private_key_file,
        )
        if any(value is not None for value in response_signing_values) and not all(
            value is not None for value in response_signing_values
        ):
            raise ValueError(
                "response signing key id and private key file must be configured together"
            )
        if self.response_signing_private_key_file is not None and not (
            self.response_signing_private_key_file.is_absolute()
        ):
            raise ValueError("response signing private key file must be an absolute path")
        if self.generation_provider != "disabled":
            if self.generation_model == "disabled":
                raise ValueError(
                    "generation_model must be pinned for an enabled generation provider"
                )
        if self.embedding_provider != "disabled":
            if self.embedding_model == "disabled":
                raise ValueError("embedding_model must be pinned for an enabled embedding provider")
        if "vertex" in {self.generation_provider, self.embedding_provider}:
            if self.vertex_project_id is None or self.vertex_location is None:
                raise ValueError("Vertex requires a pinned project and location")
            if self.vertex_location != "global" and not re.fullmatch(
                r"^[a-z][a-z0-9-]{1,30}[0-9]$", self.vertex_location
            ):
                raise ValueError("Vertex location must be a region or global")
            if (
                self.generation_provider == "vertex"
                and self.model_residency != self.vertex_location
            ):
                raise ValueError(
                    "Vertex generation model_residency must match vertex_location"
                )
            if self.vertex_data_controls_approval_reference is None or not (
                self.vertex_data_controls_approval_reference.strip()
            ):
                raise ValueError("Vertex requires data-control approval evidence")
            if self.vertex_data_controls_approval_sha256 is None:
                raise ValueError("Vertex requires data-control approval digest")
            if self.vertex_pricing_revision is None or not self.vertex_pricing_revision.strip():
                raise ValueError("Vertex requires a pinned pricing revision")
            for capability, provider, model, allowlist in (
                (
                    "generation",
                    self.generation_provider,
                    self.generation_model,
                    self.vertex_generation_model_allowlist,
                ),
                (
                    "embedding",
                    self.embedding_provider,
                    self.embedding_model,
                    self.vertex_embedding_model_allowlist,
                ),
            ):
                if provider == "vertex" and model not in allowlist:
                    raise ValueError(
                        f"{capability}_model must be in vertex_{capability}_model_allowlist"
                    )
            if self.generation_provider == "vertex" and (
                self.input_microusd_per_million_tokens <= 0
                or self.output_microusd_per_million_tokens <= 0
            ):
                raise ValueError("Vertex generation token prices must be configured")
            if self.embedding_provider == "vertex" and (
                self.embedding_input_microusd_per_million_tokens <= 0
            ):
                raise ValueError("Vertex embedding token price must be configured")
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
        if self.knowledge_ingestion_profile == "gcp":
            if self.environment not in {"development", "staging"}:
                raise ValueError("GCP knowledge ingestion is limited to development/staging")
            required = (
                self.knowledge_gcp_project_id,
                self.knowledge_gcp_location,
                self.knowledge_gcp_document_processor_id,
                self.knowledge_gcp_document_processor_revision,
                self.knowledge_gcp_output_bucket,
                self.knowledge_gcp_staging_bucket,
                self.knowledge_gcp_pubsub_subscription,
                self.knowledge_gcp_pubsub_dead_letter_topic,
            )
            if any(value is None or not str(value).strip() for value in required):
                raise ValueError("GCP knowledge ingestion requires pinned cloud resources")
            if not self.knowledge_gcp_input_buckets:
                raise ValueError("GCP knowledge ingestion requires allowlisted input buckets")
            if len(set(self.knowledge_gcp_input_buckets)) != len(self.knowledge_gcp_input_buckets):
                raise ValueError("GCP knowledge input buckets must be unique")
            if any(
                not re.fullmatch(r"^[a-z0-9][a-z0-9._-]{2,62}$", bucket)
                for bucket in self.knowledge_gcp_input_buckets
            ):
                raise ValueError("GCP knowledge input bucket identifier is invalid")
            if self.knowledge_gcp_staging_bucket == self.knowledge_gcp_output_bucket:
                raise ValueError("GCP knowledge staging and output buckets must be distinct")
            if self.knowledge_gcp_staging_bucket in self.knowledge_gcp_input_buckets:
                raise ValueError("GCP knowledge staging bucket must not be an input bucket")
            if self.knowledge_gcp_output_bucket in self.knowledge_gcp_input_buckets:
                raise ValueError("GCP knowledge output bucket must not be an input bucket")
            if self.database_url is None:
                raise ValueError("database_url is required for GCP knowledge ingestion")
            if not self.knowledge_gcp_synthetic_smoke_manifest or any(
                not re.fullmatch(r"[a-f0-9]{64}", digest) or page_count < 1 or page_count > 500
                for digest, page_count in self.knowledge_gcp_synthetic_smoke_manifest.items()
            ):
                raise ValueError(
                    "GCP knowledge ingestion requires a reviewed synthetic smoke manifest"
                )
            if (
                self.knowledge_gcp_max_output_total_bytes
                < self.knowledge_gcp_max_output_object_bytes
            ):
                raise ValueError(
                    "GCP Document AI total output limit must cover one output object"
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
