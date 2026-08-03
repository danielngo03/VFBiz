from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.infrastructure.model_providers.vertex_tuning_rehearsal_authority import (
    FileTuningRehearsalLedger,
    TuningRehearsalManifest,
)


def _manifest(**overrides: object) -> TuningRehearsalManifest:
    values: dict[str, object] = {
        "run_id": "vertex-tuning-rehearsal-20260731-001",
        "dataset_manifest_sha256": "a" * 64,
        "train_sha256": "b" * 64,
        "validation_sha256": "c" * 64,
        "heldout_sha256": "d" * 64,
        "project_id": "vinfast-503003",
        "region": "us-central1",
        "base_model_revision": "gemini-2.0-flash-lite-001",
        "pricing_revision": "vertex-pricing-2026-07-31",
        "training_token_cap": 100_000,
        "epoch_count": 3,
        "baseline_input_token_cap": 100_000,
        "baseline_output_token_cap": 50_000,
        "evaluation_input_token_cap": 100_000,
        "evaluation_output_token_cap": 50_000,
        "input_price_microusd_per_million": 75_000,
        "output_price_microusd_per_million": 300_000,
        "training_price_microusd_per_million": 1_000_000,
        "storage_reservation_microusd": 10_000,
        "reservation_microusd": {
            "baseline": 22_500,
            "training": 300_000,
            "post_tune_evaluation": 22_500,
            "storage": 10_000,
        },
    }
    values.update(overrides)
    return TuningRehearsalManifest(**values)  # type: ignore[arg-type]


def _ledger(tmp_path: Path) -> FileTuningRehearsalLedger:
    return FileTuningRehearsalLedger(
        (tmp_path / "ledger.json").resolve(),
        seal_key=b"k" * 32,
        key_id="test-key",
    )


def test_manifest_rejects_cost_above_usd_five() -> None:
    with pytest.raises(ValueError, match="USD 5"):
        _manifest(
            training_token_cap=1_000_000,
            epoch_count=5,
            storage_reservation_microusd=0,
            reservation_microusd={
                "baseline": 22_500,
                "training": 5_000_000,
                "post_tune_evaluation": 22_500,
                "storage": 0,
            },
        )


def test_training_authorization_is_single_attempt_and_no_retry(tmp_path: Path) -> None:
    manifest = _manifest()
    ledger = _ledger(tmp_path)

    authorization = ledger.authorize_dispatch(manifest, "training")

    assert authorization["operation"] == "training"
    assert authorization["reservationMicrousd"] == 300_000
    with pytest.raises(ValueError, match="replay"):
        ledger.authorize_dispatch(manifest, "training")
    assert ledger.read_sanitized(manifest)["providerSubmissionCount"] == 1


def test_ambiguous_training_remains_consumed(tmp_path: Path) -> None:
    manifest = _manifest()
    ledger = _ledger(tmp_path)
    ledger.authorize_dispatch(manifest, "training")
    ledger.reconcile(
        manifest,
        operation="training",
        outcome="ambiguous",
        receipt_sha256="e" * 64,
        incurred_cost_microusd=None,
    )

    with pytest.raises(ValueError, match="replay"):
        ledger.authorize_dispatch(manifest, "training")
    record = ledger.read_sanitized(manifest)["operations"]["training"]  # type: ignore[index]
    assert record["state"] == "ambiguous"


def test_tampered_ledger_fails_closed(tmp_path: Path) -> None:
    manifest = _manifest()
    ledger = _ledger(tmp_path)
    ledger.authorize_dispatch(manifest, "baseline")
    path = tmp_path / "ledger.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["reservedMicrousd"] = 0
    path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="seal"):
        ledger.read_sanitized(manifest)


def test_deleted_ledger_cannot_be_reinitialized(tmp_path: Path) -> None:
    manifest = _manifest()
    ledger = _ledger(tmp_path)
    ledger.authorize_dispatch(manifest, "storage")
    (tmp_path / "ledger.json").unlink()

    with pytest.raises(ValueError, match="rollback"):
        ledger.read_sanitized(manifest)


def test_valid_sealed_snapshot_rollback_is_rejected(tmp_path: Path) -> None:
    manifest = _manifest()
    ledger = _ledger(tmp_path)
    ledger.authorize_dispatch(manifest, "baseline")
    old_ledger = (tmp_path / "ledger.json").read_bytes()
    ledger.authorize_dispatch(manifest, "training")
    (tmp_path / "ledger.json").write_bytes(old_ledger)

    with pytest.raises(ValueError, match="rollback"):
        ledger.authorize_dispatch(manifest, "training")


def test_underestimated_reservation_is_rejected() -> None:
    with pytest.raises(ValueError, match="worst-case"):
        _manifest(
            reservation_microusd={
                "baseline": 1,
                "training": 1,
                "post_tune_evaluation": 1,
                "storage": 1,
            }
        )


@pytest.mark.parametrize("field", ["training_token_cap", "epoch_count"])
@pytest.mark.parametrize("value", [True, 1.5])
def test_numeric_bounds_reject_bool_and_float(field: str, value: object) -> None:
    with pytest.raises(ValueError, match="bounds"):
        _manifest(**{field: value})
