"""Fail-closed authority for one synthetic Vertex tuning rehearsal."""

from __future__ import annotations

import fcntl
import hmac
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal, cast

_OPERATIONS = ("baseline", "training", "post_tune_evaluation", "storage")
_TERMINAL_STATES = frozenset({"succeeded", "failed", "ambiguous", "cancelled"})


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _object_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("ledger object is invalid")
    mapping = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in mapping):
        raise ValueError("ledger object is invalid")
    return cast(dict[str, object], mapping)


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("ledger integer is invalid")
    return value


def _bounded_integer(value: object, *, minimum: int, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _priced_tokens(token_cap: int, price_microusd_per_million: int) -> int:
    return (token_cap * price_microusd_per_million + 999_999) // 1_000_000


@dataclass(frozen=True, slots=True)
class TuningRehearsalManifest:
    """Exact bounded inputs and prices required before any provider dispatch."""

    run_id: str
    dataset_manifest_sha256: str
    train_sha256: str
    validation_sha256: str
    heldout_sha256: str
    project_id: str
    region: Literal["us-central1"]
    base_model_revision: str
    pricing_revision: str
    training_token_cap: int
    epoch_count: int
    baseline_input_token_cap: int
    baseline_output_token_cap: int
    evaluation_input_token_cap: int
    evaluation_output_token_cap: int
    input_price_microusd_per_million: int
    output_price_microusd_per_million: int
    training_price_microusd_per_million: int
    storage_reservation_microusd: int
    reservation_microusd: Mapping[str, int]
    max_total_cost_microusd: int = 5_000_000
    provider_submission_limit: int = 1
    automatic_retry_limit: int = 0

    def __post_init__(self) -> None:
        digests = (
            self.dataset_manifest_sha256,
            self.train_sha256,
            self.validation_sha256,
            self.heldout_sha256,
        )
        if not self.run_id.strip() or any(not _is_sha256(value) for value in digests):
            raise ValueError("run and dataset identities must be pinned")
        if self.region != "us-central1" or not self.project_id.strip():
            raise ValueError("project and reviewed tuning region must be pinned")
        if not self.base_model_revision.strip() or not self.pricing_revision.strip():
            raise ValueError("model and price revisions must be pinned")
        bounded_values = (
            (self.training_token_cap, 1, 5_000_000),
            (self.epoch_count, 1, 5),
            (self.baseline_input_token_cap, 1, 5_000_000),
            (self.baseline_output_token_cap, 1, 5_000_000),
            (self.evaluation_input_token_cap, 1, 5_000_000),
            (self.evaluation_output_token_cap, 1, 5_000_000),
            (self.input_price_microusd_per_million, 1, 100_000_000),
            (self.output_price_microusd_per_million, 1, 100_000_000),
            (self.training_price_microusd_per_million, 1, 100_000_000),
            (self.storage_reservation_microusd, 0, 5_000_000),
        )
        if any(
            not _bounded_integer(value, minimum=minimum, maximum=maximum)
            for value, minimum, maximum in bounded_values
        ):
            raise ValueError("training token and epoch bounds are invalid")
        if set(self.reservation_microusd) != set(_OPERATIONS):
            raise ValueError("every rehearsal cost category must be reserved")
        if any(
            not _bounded_integer(value, minimum=0, maximum=5_000_000)
            for value in self.reservation_microusd.values()
        ):
            raise ValueError("cost reservations must be non-negative integers")
        expected_reservations = {
            "baseline": _priced_tokens(
                self.baseline_input_token_cap,
                self.input_price_microusd_per_million,
            )
            + _priced_tokens(
                self.baseline_output_token_cap,
                self.output_price_microusd_per_million,
            ),
            "training": _priced_tokens(
                self.training_token_cap * self.epoch_count,
                self.training_price_microusd_per_million,
            ),
            "post_tune_evaluation": _priced_tokens(
                self.evaluation_input_token_cap,
                self.input_price_microusd_per_million,
            )
            + _priced_tokens(
                self.evaluation_output_token_cap,
                self.output_price_microusd_per_million,
            ),
            "storage": self.storage_reservation_microusd,
        }
        if dict(self.reservation_microusd) != expected_reservations:
            raise ValueError("cost reservations must equal pinned worst-case prices")
        if (
            not 1 <= self.max_total_cost_microusd <= 5_000_000
            or sum(self.reservation_microusd.values()) > self.max_total_cost_microusd
        ):
            raise ValueError("rehearsal reservations exceed the USD 5 hard cap")
        if self.provider_submission_limit != 1 or self.automatic_retry_limit != 0:
            raise ValueError("only one provider submission with no retry is allowed")

    @property
    def digest(self) -> str:
        return sha256(_canonical_bytes(self.as_dict())).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "automaticRetryLimit": self.automatic_retry_limit,
            "baselineInputTokenCap": self.baseline_input_token_cap,
            "baselineOutputTokenCap": self.baseline_output_token_cap,
            "baseModelRevision": self.base_model_revision,
            "datasetManifestSha256": self.dataset_manifest_sha256,
            "epochCount": self.epoch_count,
            "evaluationInputTokenCap": self.evaluation_input_token_cap,
            "evaluationOutputTokenCap": self.evaluation_output_token_cap,
            "heldoutSha256": self.heldout_sha256,
            "maxTotalCostMicrousd": self.max_total_cost_microusd,
            "pricingRevision": self.pricing_revision,
            "inputPriceMicrousdPerMillion": self.input_price_microusd_per_million,
            "outputPriceMicrousdPerMillion": self.output_price_microusd_per_million,
            "trainingPriceMicrousdPerMillion": self.training_price_microusd_per_million,
            "projectId": self.project_id,
            "providerSubmissionLimit": self.provider_submission_limit,
            "region": self.region,
            "reservationMicrousd": dict(sorted(self.reservation_microusd.items())),
            "runId": self.run_id,
            "schemaVersion": 1,
            "storageReservationMicrousd": self.storage_reservation_microusd,
            "trainingTokenCap": self.training_token_cap,
            "trainSha256": self.train_sha256,
            "validationSha256": self.validation_sha256,
        }


class FileTuningRehearsalLedger:
    """Atomic HMAC-sealed ledger consumed before token acquisition."""

    def __init__(self, path: Path, *, seal_key: bytes, key_id: str) -> None:
        if not path.is_absolute() or len(seal_key) < 32 or not key_id.strip():
            raise ValueError("absolute ledger path, seal key and key ID are required")
        self._path = path
        self._lock_path = path.with_suffix(path.suffix + ".lock")
        self._anchor_path = path.with_suffix(path.suffix + ".anchor")
        self._seal_key = bytes(seal_key)
        self._key_id = key_id

    def authorize_dispatch(
        self,
        manifest: TuningRehearsalManifest,
        operation: Literal["baseline", "training", "post_tune_evaluation", "storage"],
    ) -> dict[str, object]:
        if operation not in _OPERATIONS:
            raise ValueError("unknown rehearsal operation")
        with self._locked():
            state = self._read_or_initialize(manifest)
            self._validate(state, manifest)
            operations = _object_mapping(state["operations"])
            if operation in operations:
                raise ValueError("replay rejected")
            if operation == "training" and _integer(state["providerSubmissionCount"]) >= 1:
                raise ValueError("provider submission limit reached")
            reservation = manifest.reservation_microusd[operation]
            reserved = _integer(state["reservedMicrousd"])
            if reserved + reservation > manifest.max_total_cost_microusd:
                raise ValueError("cost budget exceeded")
            sequence = _integer(state["sequence"]) + 1
            authorization = {
                "manifestDigest": manifest.digest,
                "operation": operation,
                "reservationMicrousd": reservation,
                "runId": manifest.run_id,
                "sequence": sequence,
            }
            operations[operation] = {
                **authorization,
                "state": "dispatching",
            }
            state["operations"] = operations
            state["reservedMicrousd"] = reserved + reservation
            state["sequence"] = sequence
            if operation == "training":
                state["providerSubmissionCount"] = _integer(state["providerSubmissionCount"]) + 1
            state["seal"] = self._seal(state)
            self._write_atomic(state)
            return {
                **authorization,
                "authorizationSeal": hmac.new(
                    self._seal_key,
                    _canonical_bytes(authorization),
                    sha256,
                ).hexdigest(),
                "keyId": self._key_id,
            }

    def reconcile(
        self,
        manifest: TuningRehearsalManifest,
        *,
        operation: Literal["baseline", "training", "post_tune_evaluation", "storage"],
        outcome: Literal["succeeded", "failed", "ambiguous", "cancelled"],
        receipt_sha256: str,
        incurred_cost_microusd: int | None,
    ) -> None:
        if outcome not in _TERMINAL_STATES or not _is_sha256(receipt_sha256):
            raise ValueError("reconciliation evidence is invalid")
        if outcome == "ambiguous":
            if incurred_cost_microusd is not None:
                raise ValueError("ambiguous cost must remain reserved")
        elif incurred_cost_microusd is None or incurred_cost_microusd < 0:
            raise ValueError("terminal cost is required")
        with self._locked():
            state = self._read_or_initialize(manifest)
            self._validate(state, manifest)
            operations = _object_mapping(state["operations"])
            record = _object_mapping(operations.get(operation, {}))
            if record.get("state") != "dispatching":
                raise ValueError("operation is not dispatching")
            reservation = _integer(record["reservationMicrousd"])
            if incurred_cost_microusd is not None and incurred_cost_microusd > reservation:
                raise ValueError("incurred cost exceeds reservation")
            record.update(
                {
                    "incurredCostMicrousd": incurred_cost_microusd,
                    "receiptSha256": receipt_sha256,
                    "state": outcome,
                }
            )
            operations[operation] = record
            state["operations"] = operations
            state["seal"] = self._seal(state)
            self._write_atomic(state)

    def read_sanitized(self, manifest: TuningRehearsalManifest) -> dict[str, object]:
        with self._locked():
            state = self._read_or_initialize(manifest)
            self._validate(state, manifest)
            result = dict(state)
            result.pop("seal", None)
            return result

    def _read_or_initialize(self, manifest: TuningRehearsalManifest) -> dict[str, object]:
        if not self._path.exists():
            if self._anchor_path.exists():
                raise ValueError("ledger deletion or rollback detected")
            return {
                "keyId": self._key_id,
                "manifestDigest": manifest.digest,
                "operations": {},
                "providerSubmissionCount": 0,
                "reservedMicrousd": 0,
                "runId": manifest.run_id,
                "schemaVersion": 1,
                "sequence": 0,
            }
        try:
            raw: object = json.loads(self._path.read_text(encoding="utf-8"))
            state = _object_mapping(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("ledger is unreadable") from error
        if not hmac.compare_digest(
            str(state.get("seal", "")),
            self._seal(state),
        ):
            raise ValueError("ledger seal mismatch")
        self._verify_anchor(state)
        return state

    def _validate(self, state: Mapping[str, object], manifest: TuningRehearsalManifest) -> None:
        if (
            state.get("manifestDigest") != manifest.digest
            or state.get("runId") != manifest.run_id
            or state.get("keyId") != self._key_id
        ):
            raise ValueError("ledger identity mismatch")

    def _seal(self, state: Mapping[str, object]) -> str:
        unsigned = dict(state)
        unsigned.pop("seal", None)
        return hmac.new(self._seal_key, _canonical_bytes(unsigned), sha256).hexdigest()

    def _write_atomic(self, state: Mapping[str, object]) -> None:
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + f".{os.getpid()}.tmp")
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(_canonical_bytes(state))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
            os.chmod(self._path, 0o600)
            self._write_anchor(state)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _anchor(self, state: Mapping[str, object]) -> dict[str, object]:
        payload: dict[str, object] = {
            "keyId": self._key_id,
            "ledgerSha256": sha256(_canonical_bytes(state)).hexdigest(),
            "manifestDigest": state["manifestDigest"],
            "runId": state["runId"],
            "schemaVersion": 1,
            "sequence": state["sequence"],
        }
        payload["seal"] = hmac.new(
            self._seal_key,
            _canonical_bytes(payload),
            sha256,
        ).hexdigest()
        return payload

    def _verify_anchor(self, state: Mapping[str, object]) -> None:
        if not self._anchor_path.exists():
            raise ValueError("ledger anchor is missing")
        try:
            raw: object = json.loads(self._anchor_path.read_text(encoding="utf-8"))
            observed = _object_mapping(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("ledger anchor is unreadable") from error
        if observed != self._anchor(state):
            raise ValueError("ledger rollback or anchor mismatch detected")

    def _write_anchor(self, state: Mapping[str, object]) -> None:
        anchor = self._anchor(state)
        temporary = self._anchor_path.with_suffix(self._anchor_path.suffix + f".{os.getpid()}.tmp")
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(_canonical_bytes(anchor))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._anchor_path)
            os.chmod(self._anchor_path, 0o600)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _locked(self):  # type: ignore[no-untyped-def]
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
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
