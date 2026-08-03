import fcntl
import hmac
import json
import os
import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import TypeVar, cast

_R = TypeVar("_R")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


class SmokeCapability(StrEnum):
    GENERATION = "generation"
    EMBEDDING = "embedding"


class SmokeOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"
    CANCELLED = "cancelled"


class SmokePreflightFailureCode(StrEnum):
    EXPIRED_PACKET = "expired_packet"
    FIXTURE_TAMPERED = "fixture_tampered"
    UNSAFE_FIXTURE = "unsafe_fixture"
    ENDPOINT_MISMATCH = "endpoint_mismatch"
    PRICING_INVALID = "pricing_invalid"
    DATA_CONTROLS_INVALID = "data_controls_invalid"
    PRINCIPAL_INVALID = "principal_invalid"
    PREDICTION_PERMISSION_MISSING = "prediction_permission_missing"
    FORBIDDEN_PERMISSION_GRANTED = "forbidden_permission_granted"
    REPLAY_REJECTED = "replay_rejected"
    COST_BUDGET_EXCEEDED = "cost_budget_exceeded"
    LEDGER_TAMPERED = "ledger_tampered"
    RECONCILIATION_INVALID = "reconciliation_invalid"


class SmokePreflightFailure(RuntimeError):
    def __init__(self, code: SmokePreflightFailureCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True, slots=True)
class SyntheticFixture:
    fixture_id: str
    payload: Mapping[str, object]
    allowed_use: str = "evaluation-smoke-only"
    human_adjudicated: bool = False
    golden_eligible: bool = False
    training_eligible: bool = False
    release_eligible: bool = False

    def __post_init__(self) -> None:
        if (
            not self.fixture_id.strip()
            or len(self.fixture_id) > 128
            or len(_canonical_bytes(self.payload)) > 16_384
            or self.allowed_use != "evaluation-smoke-only"
            or self.human_adjudicated
            or self.golden_eligible
            or self.training_eligible
            or self.release_eligible
        ):
            raise ValueError(
                "synthetic fixture must be bounded and evaluation-only"
            )

    @property
    def digest(self) -> str:
        return _sha256(
            {
                "allowedUse": self.allowed_use,
                "fixtureId": self.fixture_id,
                "goldenEligible": self.golden_eligible,
                "humanAdjudicated": self.human_adjudicated,
                "payload": self.payload,
                "releaseEligible": self.release_eligible,
                "schemaVersion": 1,
                "trainingEligible": self.training_eligible,
            }
        )

    @property
    def scan_text(self) -> str:
        rendered = json.dumps(
            self.payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return unicodedata.normalize("NFKC", rendered).translate(
            {
                0x200B: None,
                0x200C: None,
                0x200D: None,
                0x2060: None,
                0xFEFF: None,
            }
        )


@dataclass(frozen=True, slots=True)
class VertexEndpointIdentity:
    project_id: str
    location: str
    model_revision: str

    def __post_init__(self) -> None:
        for value in (self.project_id, self.location, self.model_revision):
            if not value.strip() or len(value) > 160:
                raise ValueError("Vertex endpoint identity must be bounded")

    def as_dict(self) -> dict[str, str]:
        return {
            "location": self.location,
            "modelRevision": self.model_revision,
            "projectId": self.project_id,
        }


@dataclass(frozen=True, slots=True)
class PricingEvidence:
    revision: str
    source_url: str
    observed_at: datetime
    input_microusd_per_million_tokens: int
    output_microusd_per_million_tokens: int

    def __post_init__(self) -> None:
        if (
            not self.revision.strip()
            or len(self.revision) > 160
            or not self.source_url.startswith("https://cloud.google.com/")
            or self.observed_at.tzinfo is None
            or min(
                self.input_microusd_per_million_tokens,
                self.output_microusd_per_million_tokens,
            )
            < 1
        ):
            raise ValueError("pricing evidence must be positive and pinned")

    def as_dict(self) -> dict[str, object]:
        return {
            "inputMicrousdPerMillionTokens": (
                self.input_microusd_per_million_tokens
            ),
            "observedAt": self.observed_at.astimezone(UTC).isoformat(),
            "outputMicrousdPerMillionTokens": (
                self.output_microusd_per_million_tokens
            ),
            "revision": self.revision,
            "sourceUrl": self.source_url,
        }


@dataclass(frozen=True, slots=True)
class DataControlsEvidence:
    decision_reference: str
    decision_sha256: str
    retention_policy: str
    effective_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if (
            not self.decision_reference.strip()
            or len(self.decision_reference) > 160
            or not _is_sha256(self.decision_sha256)
            or self.retention_policy
            not in {"standard", "zero_data_retention", "modified_abuse_monitoring"}
            or self.effective_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or self.expires_at <= self.effective_at
        ):
            raise ValueError("data-control evidence must be immutable and bounded")

    def as_dict(self) -> dict[str, str]:
        return {
            "decisionReference": self.decision_reference,
            "decisionSha256": self.decision_sha256,
            "effectiveAt": self.effective_at.astimezone(UTC).isoformat(),
            "expiresAt": self.expires_at.astimezone(UTC).isoformat(),
            "retentionPolicy": self.retention_policy,
        }


@dataclass(frozen=True, slots=True)
class IamEvidence:
    principal: str
    observed_at: datetime
    granted_permissions: frozenset[str]
    evidence_sha256: str

    def __post_init__(self) -> None:
        if (
            not self.principal.endswith(".gserviceaccount.com")
            or len(self.principal) > 254
            or self.observed_at.tzinfo is None
            or not _is_sha256(self.evidence_sha256)
            or any(
                not permission.startswith("aiplatform.")
                or len(permission) > 160
                for permission in self.granted_permissions
            )
        ):
            raise ValueError("IAM evidence must be bounded service-account evidence")


@dataclass(frozen=True, slots=True)
class VertexSmokeManifest:
    run_id: str
    created_at: datetime
    expires_at: datetime
    generation_endpoint: VertexEndpointIdentity
    embedding_endpoint: VertexEndpointIdentity
    fixture_digests: Mapping[SmokeCapability, str]
    input_token_caps: Mapping[SmokeCapability, int]
    output_token_caps: Mapping[SmokeCapability, int]
    reservation_microusd: Mapping[SmokeCapability, int]
    max_total_cost_microusd: int
    max_requests_per_capability: int
    pricing: PricingEvidence
    data_controls: DataControlsEvidence
    authority_class: str = "synthetic-evaluation-smoke-only"
    environment: str = "development"
    training_eligible: bool = False
    release_eligible: bool = False
    public_serving_eligible: bool = False

    def __post_init__(self) -> None:
        if (
            not self.run_id.strip()
            or len(self.run_id) > 128
            or any(
                not (character.isalnum() or character in "-_.:")
                for character in self.run_id
            )
            or self.created_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or self.expires_at <= self.created_at
            or self.expires_at - self.created_at
            > timedelta(hours=4)
            or self.authority_class != "synthetic-evaluation-smoke-only"
            or self.environment != "development"
            or self.training_eligible
            or self.release_eligible
            or self.public_serving_eligible
            or self.max_requests_per_capability != 1
            or not 1 <= self.max_total_cost_microusd <= 499_999
        ):
            raise ValueError("smoke manifest violates synthetic-only limits")
        if set(self.fixture_digests) != set(SmokeCapability) or set(
            self.reservation_microusd
        ) != set(SmokeCapability) or set(self.input_token_caps) != set(
            SmokeCapability
        ) or set(self.output_token_caps) != set(SmokeCapability):
            raise ValueError("smoke manifest must bind both capabilities")
        if any(
            not _is_sha256(digest) for digest in self.fixture_digests.values()
        ):
            raise ValueError("fixture identities must use SHA-256")
        expected_reservations = {
            capability: self._cost_ceiling(capability)
            for capability in SmokeCapability
        }
        if self.reservation_microusd != expected_reservations or (
            sum(expected_reservations.values()) > self.max_total_cost_microusd
        ):
            raise ValueError("smoke reservations exceed the run budget")

    def _cost_ceiling(self, capability: SmokeCapability) -> int:
        input_tokens = self.input_token_caps[capability]
        output_tokens = self.output_token_caps[capability]
        if (
            not 1 <= input_tokens <= 2_048
            or not 0 <= output_tokens <= 512
            or (
                capability is SmokeCapability.GENERATION
                and output_tokens < 1
            )
            or (
                capability is SmokeCapability.EMBEDDING
                and output_tokens != 0
            )
        ):
            raise ValueError("smoke token limits must be bounded")
        numerator = (
            input_tokens * self.pricing.input_microusd_per_million_tokens
            + output_tokens
            * self.pricing.output_microusd_per_million_tokens
        )
        return max(1, (numerator + 999_999) // 1_000_000)

    @property
    def digest(self) -> str:
        return _sha256(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "authorityClass": self.authority_class,
            "createdAt": self.created_at.astimezone(UTC).isoformat(),
            "dataControls": self.data_controls.as_dict(),
            "embeddingEndpoint": self.embedding_endpoint.as_dict(),
            "environment": self.environment,
            "expiresAt": self.expires_at.astimezone(UTC).isoformat(),
            "fixtureDigests": {
                key.value: value
                for key, value in sorted(
                    self.fixture_digests.items(),
                    key=lambda item: item[0].value,
                )
            },
            "generationEndpoint": self.generation_endpoint.as_dict(),
            "inputTokenCaps": {
                key.value: value
                for key, value in sorted(
                    self.input_token_caps.items(),
                    key=lambda item: item[0].value,
                )
            },
            "maxRequestsPerCapability": self.max_requests_per_capability,
            "maxTotalCostMicrousd": self.max_total_cost_microusd,
            "pricing": self.pricing.as_dict(),
            "publicServingEligible": self.public_serving_eligible,
            "releaseEligible": self.release_eligible,
            "reservationMicrousd": {
                key.value: value
                for key, value in sorted(
                    self.reservation_microusd.items(),
                    key=lambda item: item[0].value,
                )
            },
            "outputTokenCaps": {
                key.value: value
                for key, value in sorted(
                    self.output_token_caps.items(),
                    key=lambda item: item[0].value,
                )
            },
            "runId": self.run_id,
            "schemaVersion": 1,
            "trainingEligible": self.training_eligible,
        }


@dataclass(frozen=True, slots=True)
class SmokeAuthorization:
    run_id: str
    manifest_digest: str
    capability: SmokeCapability
    fixture_digest: str
    endpoint: VertexEndpointIdentity
    principal: str
    reservation_microusd: int
    ledger_sequence: int
    iam_evidence_sha256: str
    authorization_seal: str

    def sanitized_evidence(self) -> dict[str, object]:
        return {
            "capability": self.capability.value,
            "endpoint": self.endpoint.as_dict(),
            "fixtureDigest": self.fixture_digest,
            "iamEvidenceSha256": self.iam_evidence_sha256,
            "ledgerSequence": self.ledger_sequence,
            "manifestDigest": self.manifest_digest,
            "principalSha256": sha256(
                self.principal.encode("utf-8")
            ).hexdigest(),
            "reservationMicrousd": self.reservation_microusd,
            "runId": self.run_id,
        }


@dataclass(frozen=True, slots=True)
class SmokeDispatchReceipt:
    outcome: SmokeOutcome
    incurred_cost_microusd: int
    receipt_sha256: str

    def __post_init__(self) -> None:
        if (
            self.outcome
            not in {SmokeOutcome.SUCCEEDED, SmokeOutcome.FAILED}
            or self.incurred_cost_microusd < 0
            or not _is_sha256(self.receipt_sha256)
        ):
            raise ValueError("provider receipt must be bounded and terminal")


_UNSAFE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\b(?:sk|pk)_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?<!\d)(?:\+?84|0)\d{9,10}(?!\d)"),
    re.compile(r"\b(?:vinfast|vivi|vf\s*[3-9e])\b", re.IGNORECASE),
    re.compile(r"\bgolden(?:[\s_-]*(?:case|dataset|suite))?\b", re.IGNORECASE),
    re.compile(r"\b(?:secret|password|credential|token)\b", re.IGNORECASE),
    re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"),
    re.compile(r"(?<!\d)(?:\+?\s*84|0)(?:[\s.-]*\d){9,10}(?!\d)"),
    re.compile(r"https?://", re.IGNORECASE),
)

CANONICAL_FIXTURES = {
    SmokeCapability.GENERATION: SyntheticFixture(
        fixture_id="vertex-generation-fixture-v1",
        payload={
            "evidence": [
                {
                    "content": "The synthetic test value is four.",
                    "evidenceId": "synthetic-1",
                }
            ],
            "question": "What is the synthetic test value?",
        },
    ),
    SmokeCapability.EMBEDDING: SyntheticFixture(
        fixture_id="vertex-embedding-fixture-v1",
        payload={
            "purpose": "retrieval_query",
            "text": "synthetic retrieval test value",
        },
    ),
}
CANONICAL_FIXTURE_DIGESTS = {
    capability: fixture.digest
    for capability, fixture in CANONICAL_FIXTURES.items()
}

REQUIRED_PREDICTION_PERMISSION = "aiplatform.endpoints.predict"


class VertexSmokeAuthority:
    def __init__(
        self,
        *,
        expected_project_id: str,
        expected_principal: str,
        expected_ledger_path: Path,
        expected_ledger_key_id: str,
        generation_endpoint: VertexEndpointIdentity,
        embedding_endpoint: VertexEndpointIdentity,
    ) -> None:
        if (
            generation_endpoint.project_id != expected_project_id
            or embedding_endpoint.project_id != expected_project_id
            or not expected_principal.endswith(
                f"@{expected_project_id}.iam.gserviceaccount.com"
            )
            or not expected_ledger_path.is_absolute()
            or not expected_ledger_key_id.strip()
        ):
            raise ValueError("authority policy must be exact and project-bound")
        self._project_id = expected_project_id
        self._expected_principal = expected_principal
        self._expected_ledger_path = expected_ledger_path
        self._expected_ledger_key_id = expected_ledger_key_id
        self._generation_endpoint = generation_endpoint
        self._embedding_endpoint = embedding_endpoint

    def validate_ledger(self, ledger: "FileSmokeLedger") -> None:
        if (
            ledger.path != self._expected_ledger_path
            or ledger.key_id != self._expected_ledger_key_id
        ):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.LEDGER_TAMPERED
            )

    def preflight(
        self,
        *,
        manifest: VertexSmokeManifest,
        capability: SmokeCapability,
        fixture: SyntheticFixture,
        iam: IamEvidence,
        now: datetime,
    ) -> None:
        if now.tzinfo is None:
            raise ValueError("preflight clock must include a timezone")
        if now < manifest.created_at or now >= manifest.expires_at:
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.EXPIRED_PACKET
            )
        if manifest.run_id != (
            f"vertex-smoke-{manifest.created_at.astimezone(UTC):%Y%m%d}-001"
        ):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.REPLAY_REJECTED
            )
        if any(pattern.search(fixture.scan_text) for pattern in _UNSAFE_PATTERNS):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.UNSAFE_FIXTURE
            )
        if fixture.digest != manifest.fixture_digests[capability]:
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.FIXTURE_TAMPERED
            )
        if (
            fixture.digest != CANONICAL_FIXTURE_DIGESTS[capability]
            or manifest.fixture_digests[capability]
            != CANONICAL_FIXTURE_DIGESTS[capability]
        ):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.FIXTURE_TAMPERED
            )
        expected_endpoint = (
            self._generation_endpoint
            if capability is SmokeCapability.GENERATION
            else self._embedding_endpoint
        )
        actual_endpoint = (
            manifest.generation_endpoint
            if capability is SmokeCapability.GENERATION
            else manifest.embedding_endpoint
        )
        if (
            actual_endpoint != expected_endpoint
            or actual_endpoint.project_id != self._project_id
        ):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.ENDPOINT_MISMATCH
            )
        if (
            manifest.pricing.observed_at > now
            or now - manifest.pricing.observed_at
            > timedelta(days=7)
        ):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.PRICING_INVALID
            )
        controls = manifest.data_controls
        if (
            now < controls.effective_at
            or now >= controls.expires_at
            or controls.decision_reference.startswith("placeholder")
        ):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.DATA_CONTROLS_INVALID
            )
        if (
            iam.principal != self._expected_principal
            or now - iam.observed_at
            > timedelta(minutes=15)
            or iam.observed_at > now
        ):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.PRINCIPAL_INVALID
            )
        if not iam.granted_permissions:
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.PREDICTION_PERMISSION_MISSING
            )
        if iam.granted_permissions != frozenset(
            {REQUIRED_PREDICTION_PERMISSION}
        ):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.FORBIDDEN_PERMISSION_GRANTED
            )


class FileSmokeLedger:
    """Sidecar-locked, atomic local admission ledger for one synthetic run."""

    def __init__(
        self,
        path: Path,
        *,
        seal_key: bytes,
        key_id: str,
        daily_cap_microusd: int,
    ) -> None:
        if not path.is_absolute():
            raise ValueError("ledger path must be absolute")
        if len(seal_key) < 32:
            raise ValueError("ledger seal key must contain at least 32 bytes")
        if (
            not key_id.strip()
            or len(key_id) > 128
            or not 1 <= daily_cap_microusd <= 499_999
        ):
            raise ValueError("ledger policy must be bounded and fail closed")
        self._path = path
        self._lock_path = path.with_suffix(path.suffix + ".lock")
        self._anchor_path = path.with_suffix(path.suffix + ".anchor")
        self._seal_key = bytes(seal_key)
        self._key_id = key_id
        self._daily_cap_microusd = daily_cap_microusd

    @property
    def path(self) -> Path:
        return self._path

    @property
    def key_id(self) -> str:
        return self._key_id

    def reserve(
        self,
        manifest: VertexSmokeManifest,
        capability: SmokeCapability,
    ) -> int:
        def operation(state: dict[str, object]) -> tuple[dict[str, object], int]:
            self._validate_identity(state, manifest)
            reservations = _object_mapping(state["reservations"])
            if capability.value in reservations:
                raise SmokePreflightFailure(
                    SmokePreflightFailureCode.REPLAY_REJECTED
                )
            reserved_total = _nonnegative_int(state["reservedMicrousd"])
            reservation = manifest.reservation_microusd[capability]
            if (
                reserved_total + reservation > manifest.max_total_cost_microusd
                or reserved_total + reservation > self._daily_cap_microusd
            ):
                raise SmokePreflightFailure(
                    SmokePreflightFailureCode.COST_BUDGET_EXCEEDED
                )
            sequence = _nonnegative_int(state["sequence"]) + 1
            reservations[capability.value] = {
                "reservationMicrousd": reservation,
                "sequence": sequence,
                "state": "reserved",
            }
            state["reservedMicrousd"] = reserved_total + reservation
            state["sequence"] = sequence
            state["reservations"] = reservations
            return state, sequence

        return self._mutate(manifest, operation)

    def reconcile(
        self,
        manifest: VertexSmokeManifest,
        capability: SmokeCapability,
        *,
        outcome: SmokeOutcome,
        incurred_cost_microusd: int | None,
        receipt_sha256: str,
    ) -> None:
        if not _is_sha256(receipt_sha256):
            raise ValueError("receipt identity must use SHA-256")
        if outcome is SmokeOutcome.AMBIGUOUS:
            if incurred_cost_microusd is not None:
                raise SmokePreflightFailure(
                    SmokePreflightFailureCode.RECONCILIATION_INVALID
                )
        elif incurred_cost_microusd is None or incurred_cost_microusd < 0:
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.RECONCILIATION_INVALID
            )

        def operation(state: dict[str, object]) -> tuple[dict[str, object], None]:
            self._validate_identity(state, manifest)
            reservations = _object_mapping(state["reservations"])
            record = _object_mapping(reservations.get(capability.value))
            if record.get("state") != "dispatching":
                raise SmokePreflightFailure(
                    SmokePreflightFailureCode.RECONCILIATION_INVALID
                )
            reservation = _nonnegative_int(record["reservationMicrousd"])
            if (
                incurred_cost_microusd is not None
                and incurred_cost_microusd > reservation
            ):
                raise SmokePreflightFailure(
                    SmokePreflightFailureCode.COST_BUDGET_EXCEEDED
                )
            record.update(
                {
                    "incurredCostMicrousd": incurred_cost_microusd,
                    "receiptSha256": receipt_sha256,
                    "state": outcome.value,
                }
            )
            reservations[capability.value] = record
            state["reservations"] = reservations
            return state, None

        self._mutate(manifest, operation)

    def _issue_authorization_seal(
        self,
        authorization: Mapping[str, object],
    ) -> str:
        return hmac.new(
            self._seal_key,
            _canonical_bytes(
                {
                    "authorization": authorization,
                    "keyId": self._key_id,
                    "schemaVersion": 1,
                }
            ),
            digestmod=sha256,
        ).hexdigest()

    def verify_authorization(self, authorization: SmokeAuthorization) -> None:
        expected = self._issue_authorization_seal(
            _authorization_seal_payload(authorization)
        )
        if not hmac.compare_digest(authorization.authorization_seal, expected):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.RECONCILIATION_INVALID
            )

    def begin_dispatch(
        self,
        manifest: VertexSmokeManifest,
        authorization: SmokeAuthorization,
    ) -> None:
        """Atomically consume one sealed reservation before token acquisition."""
        self.verify_authorization(authorization)

        def operation(state: dict[str, object]) -> tuple[dict[str, object], None]:
            self._validate_identity(state, manifest)
            reservations = _object_mapping(state["reservations"])
            record = _object_mapping(
                reservations.get(authorization.capability.value)
            )
            if (
                record.get("state") != "reserved"
                or _nonnegative_int(record.get("sequence"))
                != authorization.ledger_sequence
                or _nonnegative_int(record.get("reservationMicrousd"))
                != authorization.reservation_microusd
            ):
                raise SmokePreflightFailure(
                    SmokePreflightFailureCode.REPLAY_REJECTED
                )
            record["dispatchAuthorizationSha256"] = _sha256(
                _authorization_seal_payload(authorization)
            )
            record["state"] = "dispatching"
            reservations[authorization.capability.value] = record
            state["reservations"] = reservations
            return state, None

        self._mutate(manifest, operation)

    def read_sanitized(self, manifest: VertexSmokeManifest) -> dict[str, object]:
        with self._locked():
            state = self._read_or_initialize(manifest)
            self._validate_identity(state, manifest)
            sanitized = dict(state)
            sanitized.pop("seal", None)
            return json.loads(_canonical_bytes(sanitized))

    def _mutate(
        self,
        manifest: VertexSmokeManifest,
        operation: Callable[
            [dict[str, object]],
            tuple[dict[str, object], _R],
        ],
    ) -> _R:
        with self._locked():
            state = self._read_or_initialize(manifest)
            updated, result = operation(state)
            updated["seal"] = self._seal(updated)
            self._write_atomic(updated)
            return result

    def _locked(self):  # type: ignore[no-untyped-def]
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self._path.parent, 0o700)
        handle = self._lock_path.open("a+", encoding="utf-8")
        os.chmod(self._lock_path, 0o600)

        class _Lock:
            def __enter__(_self):  # type: ignore[no-untyped-def]
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                return handle

            def __exit__(_self, *_args: object) -> None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()

        return _Lock()

    def _read_or_initialize(
        self,
        manifest: VertexSmokeManifest,
    ) -> dict[str, object]:
        if not self._path.exists():
            if self._anchor_path.exists():
                raise SmokePreflightFailure(
                    SmokePreflightFailureCode.LEDGER_TAMPERED
                )
            return {
                "manifestDigest": manifest.digest,
                "dailyCapMicrousd": self._daily_cap_microusd,
                "keyId": self._key_id,
                "ledgerDate": manifest.created_at.astimezone(UTC).date().isoformat(),
                "reservations": {},
                "reservedMicrousd": 0,
                "runId": manifest.run_id,
                "schemaVersion": 1,
                "sequence": 0,
            }
        try:
            raw: object = json.loads(self._path.read_bytes())
            state = _object_mapping(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.LEDGER_TAMPERED
            ) from error
        self._verify_seal(state)
        return state

    def _seal(self, state: Mapping[str, object]) -> str:
        unsigned = dict(state)
        unsigned.pop("seal", None)
        return hmac.new(
            self._seal_key,
            _canonical_bytes(unsigned),
            digestmod=sha256,
        ).hexdigest()

    def _verify_seal(self, state: Mapping[str, object]) -> None:
        observed = state.get("seal")
        expected = self._seal(state)
        if (
            not isinstance(observed, str)
            or not hmac.compare_digest(observed, expected)
        ):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.LEDGER_TAMPERED
            )

    def _validate_identity(
        self,
        state: Mapping[str, object],
        manifest: VertexSmokeManifest,
    ) -> None:
        if (
            state.get("schemaVersion") != 1
            or state.get("runId") != manifest.run_id
            or state.get("manifestDigest") != manifest.digest
            or state.get("ledgerDate")
            != manifest.created_at.astimezone(UTC).date().isoformat()
            or state.get("keyId") != self._key_id
            or state.get("dailyCapMicrousd") != self._daily_cap_microusd
        ):
            raise SmokePreflightFailure(
                SmokePreflightFailureCode.LEDGER_TAMPERED
            )

    def _write_atomic(self, state: Mapping[str, object]) -> None:
        self._ensure_anchor(state)
        temporary = self._path.with_suffix(
            f"{self._path.suffix}.{os.getpid()}.tmp"
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(_canonical_bytes(state))
                handle.write(b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
            os.chmod(self._path, 0o600)
        finally:
            temporary.unlink(missing_ok=True)

    def _ensure_anchor(self, state: Mapping[str, object]) -> None:
        anchor = {
            "dailyCapMicrousd": state["dailyCapMicrousd"],
            "keyId": state["keyId"],
            "ledgerDate": state["ledgerDate"],
            "manifestDigest": state["manifestDigest"],
            "runId": state["runId"],
            "schemaVersion": 1,
        }
        anchor["seal"] = self._seal(anchor)
        if self._anchor_path.exists():
            try:
                observed = _object_mapping(
                    json.loads(self._anchor_path.read_bytes())
                )
            except (
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                TypeError,
            ) as error:
                raise SmokePreflightFailure(
                    SmokePreflightFailureCode.LEDGER_TAMPERED
                ) from error
            if observed != anchor:
                raise SmokePreflightFailure(
                    SmokePreflightFailureCode.LEDGER_TAMPERED
                )
            return
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(self._anchor_path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_bytes(anchor))
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(self._anchor_path, 0o600)


def authorize_and_reserve(
    *,
    authority: VertexSmokeAuthority,
    ledger: FileSmokeLedger,
    manifest: VertexSmokeManifest,
    capability: SmokeCapability,
    fixture: SyntheticFixture,
    iam: IamEvidence,
    now: datetime,
) -> SmokeAuthorization:
    authority.validate_ledger(ledger)
    authority.preflight(
        manifest=manifest,
        capability=capability,
        fixture=fixture,
        iam=iam,
        now=now,
    )
    sequence = ledger.reserve(manifest, capability)
    endpoint = (
        manifest.generation_endpoint
        if capability is SmokeCapability.GENERATION
        else manifest.embedding_endpoint
    )
    authorization_payload: dict[str, object] = {
        "capability": capability.value,
        "endpoint": endpoint.as_dict(),
        "fixtureDigest": fixture.digest,
        "iamEvidenceSha256": iam.evidence_sha256,
        "ledgerSequence": sequence,
        "manifestDigest": manifest.digest,
        "principal": iam.principal,
        "reservationMicrousd": manifest.reservation_microusd[capability],
        "runId": manifest.run_id,
    }
    return SmokeAuthorization(
        run_id=manifest.run_id,
        manifest_digest=manifest.digest,
        capability=capability,
        fixture_digest=fixture.digest,
        endpoint=endpoint,
        principal=iam.principal,
        reservation_microusd=manifest.reservation_microusd[capability],
        ledger_sequence=sequence,
        iam_evidence_sha256=iam.evidence_sha256,
        authorization_seal=ledger._issue_authorization_seal(  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
            authorization_payload
        ),
    )


def execute_authorized_smoke[T](
    *,
    authorization: SmokeAuthorization,
    ledger: FileSmokeLedger,
    manifest: VertexSmokeManifest,
    is_cancelled: Callable[[], bool],
    acquire_token: Callable[[], T],
    dispatch: Callable[[T], SmokeDispatchReceipt],
) -> SmokeDispatchReceipt | None:
    """Execute one reserved attempt with cancellation checks around auth."""
    if (
        authorization.run_id != manifest.run_id
        or authorization.manifest_digest != manifest.digest
        or authorization.reservation_microusd
        != manifest.reservation_microusd[authorization.capability]
    ):
        raise SmokePreflightFailure(
            SmokePreflightFailureCode.RECONCILIATION_INVALID
        )
    ledger.begin_dispatch(manifest, authorization)
    cancellation_receipt = _sha256(
        {
            "capability": authorization.capability.value,
            "manifestDigest": authorization.manifest_digest,
            "outcome": SmokeOutcome.CANCELLED.value,
        }
    )
    if is_cancelled():
        ledger.reconcile(
            manifest,
            authorization.capability,
            outcome=SmokeOutcome.CANCELLED,
            incurred_cost_microusd=0,
            receipt_sha256=cancellation_receipt,
        )
        return None
    try:
        token = acquire_token()
    except Exception:
        ledger.reconcile(
            manifest,
            authorization.capability,
            outcome=SmokeOutcome.FAILED,
            incurred_cost_microusd=0,
            receipt_sha256=_sha256(
                {
                    "capability": authorization.capability.value,
                    "manifestDigest": authorization.manifest_digest,
                    "outcome": "token-acquisition-failed",
                }
            ),
        )
        raise
    if is_cancelled():
        ledger.reconcile(
            manifest,
            authorization.capability,
            outcome=SmokeOutcome.CANCELLED,
            incurred_cost_microusd=0,
            receipt_sha256=cancellation_receipt,
        )
        return None
    try:
        receipt = dispatch(token)
    except Exception:
        ledger.reconcile(
            manifest,
            authorization.capability,
            outcome=SmokeOutcome.AMBIGUOUS,
            incurred_cost_microusd=None,
            receipt_sha256=_sha256(
                {
                    "capability": authorization.capability.value,
                    "manifestDigest": authorization.manifest_digest,
                    "outcome": SmokeOutcome.AMBIGUOUS.value,
                }
            ),
        )
        raise
    ledger.reconcile(
        manifest,
        authorization.capability,
        outcome=receipt.outcome,
        incurred_cost_microusd=receipt.incurred_cost_microusd,
        receipt_sha256=receipt.receipt_sha256,
    )
    return receipt


def _authorization_seal_payload(
    authorization: SmokeAuthorization,
) -> dict[str, object]:
    return {
        "capability": authorization.capability.value,
        "endpoint": authorization.endpoint.as_dict(),
        "fixtureDigest": authorization.fixture_digest,
        "iamEvidenceSha256": authorization.iam_evidence_sha256,
        "ledgerSequence": authorization.ledger_sequence,
        "manifestDigest": authorization.manifest_digest,
        "principal": authorization.principal,
        "reservationMicrousd": authorization.reservation_microusd,
        "runId": authorization.run_id,
    }


def _object_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SmokePreflightFailure(
            SmokePreflightFailureCode.LEDGER_TAMPERED
        )
    raw = cast("dict[object, object]", value)
    if not all(isinstance(key, str) for key in raw):
        raise SmokePreflightFailure(
            SmokePreflightFailureCode.LEDGER_TAMPERED
        )
    return cast("dict[str, object]", raw)


def _nonnegative_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SmokePreflightFailure(
            SmokePreflightFailureCode.LEDGER_TAMPERED
        )
    return value
