import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.infrastructure.model_providers.vertex_smoke_authority import (
    CANONICAL_FIXTURES,
    DataControlsEvidence,
    FileSmokeLedger,
    IamEvidence,
    PricingEvidence,
    SmokeCapability,
    SmokeDispatchReceipt,
    SmokeOutcome,
    SmokePreflightFailure,
    SmokePreflightFailureCode,
    SyntheticFixture,
    VertexEndpointIdentity,
    VertexSmokeAuthority,
    VertexSmokeManifest,
    authorize_and_reserve,
    execute_authorized_smoke,
)

NOW = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)
PROJECT = "vinfast-503003"
SEAL_KEY = b"synthetic-smoke-ledger-test-key!" * 2
SEAL_KEY_ID = "test-kms-key-v1"
DAILY_CAP_MICROUSD = 499_999
GENERATION = VertexEndpointIdentity(
    project_id=PROJECT,
    location="asia-southeast1",
    model_revision="gemini-2.5-flash",
)
EMBEDDING = VertexEndpointIdentity(
    project_id=PROJECT,
    location="global",
    model_revision="gemini-embedding-001",
)


def fixture(capability: SmokeCapability) -> SyntheticFixture:
    return CANONICAL_FIXTURES[capability]


def manifest(**overrides: object) -> VertexSmokeManifest:
    values: dict[str, object] = {
        "run_id": "vertex-smoke-20260730-001",
        "created_at": NOW - timedelta(minutes=5),
        "expires_at": NOW + timedelta(hours=1),
        "generation_endpoint": GENERATION,
        "embedding_endpoint": EMBEDDING,
        "fixture_digests": {
            capability: fixture(capability).digest
            for capability in SmokeCapability
        },
        "input_token_caps": {
            SmokeCapability.GENERATION: 512,
            SmokeCapability.EMBEDDING: 128,
        },
        "output_token_caps": {
            SmokeCapability.GENERATION: 128,
            SmokeCapability.EMBEDDING: 0,
        },
        "reservation_microusd": {
            SmokeCapability.GENERATION: 154,
            SmokeCapability.EMBEDDING: 20,
        },
        "max_total_cost_microusd": 500,
        "max_requests_per_capability": 1,
        "pricing": PricingEvidence(
            revision="vertex-pricing-2026-07-30",
            source_url=(
                "https://cloud.google.com/vertex-ai/generative-ai/pricing"
            ),
            observed_at=NOW - timedelta(hours=1),
            input_microusd_per_million_tokens=150_000,
            output_microusd_per_million_tokens=600_000,
        ),
        "data_controls": DataControlsEvidence(
            decision_reference="data-controls-review-20260730",
            decision_sha256="a" * 64,
            retention_policy="standard",
            effective_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=30),
        ),
    }
    values.update(overrides)
    return VertexSmokeManifest(**values)  # type: ignore[arg-type]


def iam(**overrides: object) -> IamEvidence:
    values: dict[str, object] = {
        "principal": "vfbiz-vertex-smoke@vinfast-503003.iam.gserviceaccount.com",
        "observed_at": NOW - timedelta(minutes=1),
        "granted_permissions": frozenset({"aiplatform.endpoints.predict"}),
        "evidence_sha256": "b" * 64,
    }
    values.update(overrides)
    return IamEvidence(**values)  # type: ignore[arg-type]


def ledger(path: Path) -> FileSmokeLedger:
    return FileSmokeLedger(
        path.resolve(),
        seal_key=SEAL_KEY,
        key_id=SEAL_KEY_ID,
        daily_cap_microusd=DAILY_CAP_MICROUSD,
    )


def authority(smoke_ledger: FileSmokeLedger) -> VertexSmokeAuthority:
    return VertexSmokeAuthority(
        expected_project_id=PROJECT,
        expected_principal=(
            "vfbiz-vertex-smoke@vinfast-503003.iam.gserviceaccount.com"
        ),
        expected_ledger_path=smoke_ledger.path,
        expected_ledger_key_id=smoke_ledger.key_id,
        generation_endpoint=GENERATION,
        embedding_endpoint=EMBEDDING,
    )


def assert_failure(
    code: SmokePreflightFailureCode,
    operation: Callable[[], object],
) -> None:
    with pytest.raises(SmokePreflightFailure) as caught:
        operation()
    assert caught.value.code is code


def test_authorize_reserves_once_and_emits_only_sanitized_evidence(
    tmp_path: Path,
) -> None:
    smoke_manifest = manifest()
    smoke_ledger = ledger(tmp_path / "private" / "ledger.json")
    authorization = authorize_and_reserve(
        authority=authority(smoke_ledger),
        ledger=smoke_ledger,
        manifest=smoke_manifest,
        capability=SmokeCapability.GENERATION,
        fixture=fixture(SmokeCapability.GENERATION),
        iam=iam(),
        now=NOW,
    )

    evidence = authorization.sanitized_evidence()
    rendered = json.dumps(evidence, sort_keys=True)
    assert evidence["manifestDigest"] == smoke_manifest.digest
    assert evidence["reservationMicrousd"] == 154
    assert evidence["iamEvidenceSha256"] == "b" * 64
    assert "synthetic test value" not in rendered
    assert "gserviceaccount.com" not in rendered
    assert (tmp_path / "private").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "private" / "ledger.json").stat().st_mode & 0o777 == 0o600

    assert_failure(
        SmokePreflightFailureCode.REPLAY_REJECTED,
        lambda: authorize_and_reserve(
            authority=authority(smoke_ledger),
            ledger=smoke_ledger,
            manifest=smoke_manifest,
            capability=SmokeCapability.GENERATION,
            fixture=fixture(SmokeCapability.GENERATION),
            iam=iam(),
            now=NOW,
        ),
    )


def test_dispatch_checks_cancellation_before_token_and_provider(
    tmp_path: Path,
) -> None:
    smoke_manifest = manifest()
    smoke_ledger = ledger(tmp_path / "ledger.json")
    authorization = authorize_and_reserve(
        authority=authority(smoke_ledger),
        ledger=smoke_ledger,
        manifest=smoke_manifest,
        capability=SmokeCapability.GENERATION,
        fixture=fixture(SmokeCapability.GENERATION),
        iam=iam(),
        now=NOW,
    )
    acquired = False
    dispatched = False

    def acquire_token() -> str:
        nonlocal acquired
        acquired = True
        return "not-a-real-token"

    def dispatch(_token: str) -> SmokeDispatchReceipt:
        nonlocal dispatched
        dispatched = True
        return SmokeDispatchReceipt(
            outcome=SmokeOutcome.SUCCEEDED,
            incurred_cost_microusd=1,
            receipt_sha256="f" * 64,
        )

    assert (
        execute_authorized_smoke(
            authorization=authorization,
            ledger=smoke_ledger,
            manifest=smoke_manifest,
            is_cancelled=lambda: True,
            acquire_token=acquire_token,
            dispatch=dispatch,
        )
        is None
    )
    assert not acquired
    assert not dispatched
    reservations = smoke_ledger.read_sanitized(smoke_manifest)["reservations"]
    assert isinstance(reservations, dict)
    assert reservations["generation"]["state"] == "cancelled"


def test_dispatch_failure_is_reconciled_as_ambiguous(
    tmp_path: Path,
) -> None:
    smoke_manifest = manifest()
    smoke_ledger = ledger(tmp_path / "ledger.json")
    authorization = authorize_and_reserve(
        authority=authority(smoke_ledger),
        ledger=smoke_ledger,
        manifest=smoke_manifest,
        capability=SmokeCapability.GENERATION,
        fixture=fixture(SmokeCapability.GENERATION),
        iam=iam(),
        now=NOW,
    )

    def fail_dispatch(_token: str) -> SmokeDispatchReceipt:
        raise TimeoutError("synthetic timeout")

    with pytest.raises(TimeoutError, match="synthetic timeout"):
        execute_authorized_smoke(
            authorization=authorization,
            ledger=smoke_ledger,
            manifest=smoke_manifest,
            is_cancelled=lambda: False,
            acquire_token=lambda: "not-a-real-token",
            dispatch=fail_dispatch,
        )
    reservations = smoke_ledger.read_sanitized(smoke_manifest)["reservations"]
    assert isinstance(reservations, dict)
    assert reservations["generation"]["state"] == "ambiguous"


def test_same_authorization_cannot_dispatch_twice(tmp_path: Path) -> None:
    smoke_manifest = manifest()
    smoke_ledger = ledger(tmp_path / "ledger.json")
    authorization = authorize_and_reserve(
        authority=authority(smoke_ledger),
        ledger=smoke_ledger,
        manifest=smoke_manifest,
        capability=SmokeCapability.GENERATION,
        fixture=fixture(SmokeCapability.GENERATION),
        iam=iam(),
        now=NOW,
    )
    token_calls = 0
    dispatch_calls = 0

    def acquire_token() -> str:
        nonlocal token_calls
        token_calls += 1
        return "not-a-real-token"

    def dispatch(_token: str) -> SmokeDispatchReceipt:
        nonlocal dispatch_calls
        dispatch_calls += 1
        return SmokeDispatchReceipt(
            outcome=SmokeOutcome.SUCCEEDED,
            incurred_cost_microusd=1,
            receipt_sha256="f" * 64,
        )

    assert (
        execute_authorized_smoke(
            authorization=authorization,
            ledger=smoke_ledger,
            manifest=smoke_manifest,
            is_cancelled=lambda: False,
            acquire_token=acquire_token,
            dispatch=dispatch,
        )
        is not None
    )
    assert_failure(
        SmokePreflightFailureCode.REPLAY_REJECTED,
        lambda: execute_authorized_smoke(
            authorization=authorization,
            ledger=smoke_ledger,
            manifest=smoke_manifest,
            is_cancelled=lambda: False,
            acquire_token=acquire_token,
            dispatch=dispatch,
        ),
    )
    assert token_calls == 1
    assert dispatch_calls == 1


def test_dispatch_rejects_fabricated_authorization(
    tmp_path: Path,
) -> None:
    smoke_manifest = manifest()
    smoke_ledger = ledger(tmp_path / "ledger.json")
    authorization = authorize_and_reserve(
        authority=authority(smoke_ledger),
        ledger=smoke_ledger,
        manifest=smoke_manifest,
        capability=SmokeCapability.GENERATION,
        fixture=fixture(SmokeCapability.GENERATION),
        iam=iam(),
        now=NOW,
    )
    fabricated = replace(
        authorization,
        fixture_digest="0" * 64,
        principal="foreign@other-project.iam.gserviceaccount.com",
    )
    dispatched = False

    def dispatch(_token: str) -> SmokeDispatchReceipt:
        nonlocal dispatched
        dispatched = True
        return SmokeDispatchReceipt(
            outcome=SmokeOutcome.SUCCEEDED,
            incurred_cost_microusd=1,
            receipt_sha256="f" * 64,
        )

    assert_failure(
        SmokePreflightFailureCode.RECONCILIATION_INVALID,
        lambda: execute_authorized_smoke(
            authorization=fabricated,
            ledger=smoke_ledger,
            manifest=smoke_manifest,
            is_cancelled=lambda: False,
            acquire_token=lambda: "not-a-real-token",
            dispatch=dispatch,
        ),
    )
    assert not dispatched


def test_token_acquisition_failure_is_reconciled_as_failed(
    tmp_path: Path,
) -> None:
    smoke_manifest = manifest()
    smoke_ledger = ledger(tmp_path / "ledger.json")
    authorization = authorize_and_reserve(
        authority=authority(smoke_ledger),
        ledger=smoke_ledger,
        manifest=smoke_manifest,
        capability=SmokeCapability.GENERATION,
        fixture=fixture(SmokeCapability.GENERATION),
        iam=iam(),
        now=NOW,
    )

    def fail_token() -> str:
        raise RuntimeError("synthetic auth failure")

    with pytest.raises(RuntimeError, match="synthetic auth failure"):
        execute_authorized_smoke(
            authorization=authorization,
            ledger=smoke_ledger,
            manifest=smoke_manifest,
            is_cancelled=lambda: False,
            acquire_token=fail_token,
            dispatch=lambda _token: SmokeDispatchReceipt(
                outcome=SmokeOutcome.SUCCEEDED,
                incurred_cost_microusd=1,
                receipt_sha256="f" * 64,
            ),
        )
    reservations = smoke_ledger.read_sanitized(smoke_manifest)["reservations"]
    assert isinstance(reservations, dict)
    assert reservations["generation"]["state"] == "failed"


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "contact test@example.com",
        "Bearer abcdefghijklmnopqrstuvwxyz",
        "-----BEGIN PRIVATE KEY-----",
        "VinFast policy",
        "https://example.com/source",
        "0901234567",
        "090 123 4567",
        "Vin\u200bFast policy",
        "ABCDEFGHJKLMNPR12",
        "Golden dataset",
        "client secret",
    ],
)
def test_preflight_rejects_pii_secrets_and_business_content(
    tmp_path: Path,
    unsafe_text: str,
) -> None:
    unsafe = SyntheticFixture("unsafe-v1", {"text": unsafe_text})
    smoke_ledger = ledger(tmp_path / "ledger.json")
    smoke_manifest = manifest(
        fixture_digests={
            SmokeCapability.GENERATION: unsafe.digest,
            SmokeCapability.EMBEDDING: fixture(
                SmokeCapability.EMBEDDING
            ).digest,
        }
    )
    assert_failure(
        SmokePreflightFailureCode.UNSAFE_FIXTURE,
        lambda: authorize_and_reserve(
            authority=authority(smoke_ledger),
            ledger=smoke_ledger,
            manifest=smoke_manifest,
            capability=SmokeCapability.GENERATION,
            fixture=unsafe,
            iam=iam(),
            now=NOW,
        ),
    )


def test_preflight_rejects_fixture_tamper_before_ledger_write(
    tmp_path: Path,
) -> None:
    ledger_path = (tmp_path / "ledger.json").resolve()
    smoke_ledger = ledger(ledger_path)
    assert_failure(
        SmokePreflightFailureCode.FIXTURE_TAMPERED,
        lambda: authorize_and_reserve(
            authority=authority(smoke_ledger),
            ledger=smoke_ledger,
            manifest=manifest(),
            capability=SmokeCapability.GENERATION,
            fixture=SyntheticFixture("changed", {"value": 7}),
            iam=iam(),
            now=NOW,
        ),
    )
    assert not ledger_path.exists()


@pytest.mark.parametrize(
    ("iam_evidence", "code"),
    [
        (
            iam(granted_permissions=frozenset[str]()),
            SmokePreflightFailureCode.PREDICTION_PERMISSION_MISSING,
        ),
        (
            iam(
                granted_permissions=frozenset(
                    {
                        "aiplatform.endpoints.predict",
                        "aiplatform.batchPredictionJobs.create",
                    }
                )
            ),
            SmokePreflightFailureCode.FORBIDDEN_PERMISSION_GRANTED,
        ),
        (
            iam(
                principal=(
                    "vfbiz-ai-dev-worker@vinfast-503003.iam.gserviceaccount.com"
                )
            ),
            SmokePreflightFailureCode.PRINCIPAL_INVALID,
        ),
        (
            iam(
                principal=(
                    "vfbiz-vertex-smoke@other-project.iam.gserviceaccount.com"
                )
            ),
            SmokePreflightFailureCode.PRINCIPAL_INVALID,
        ),
        (
            iam(observed_at=NOW - timedelta(hours=1)),
            SmokePreflightFailureCode.PRINCIPAL_INVALID,
        ),
    ],
)
def test_preflight_enforces_prediction_only_fresh_service_identity(
    tmp_path: Path,
    iam_evidence: IamEvidence,
    code: SmokePreflightFailureCode,
) -> None:
    smoke_ledger = ledger(tmp_path / "ledger.json")
    assert_failure(
        code,
        lambda: authorize_and_reserve(
            authority=authority(smoke_ledger),
            ledger=smoke_ledger,
            manifest=manifest(),
            capability=SmokeCapability.GENERATION,
            fixture=fixture(SmokeCapability.GENERATION),
            iam=iam_evidence,
            now=NOW,
        ),
    )


def test_preflight_rejects_wrong_endpoint_stale_pricing_and_controls(
    tmp_path: Path,
) -> None:
    cases = (
        (
            manifest(
                generation_endpoint=replace(
                    GENERATION,
                    location="global",
                )
            ),
            SmokePreflightFailureCode.ENDPOINT_MISMATCH,
        ),
        (
            manifest(
                pricing=replace(
                    cast_pricing(manifest().pricing),
                    observed_at=NOW - timedelta(days=8),
                )
            ),
            SmokePreflightFailureCode.PRICING_INVALID,
        ),
        (
            manifest(
                data_controls=replace(
                    cast_controls(manifest().data_controls),
                    expires_at=NOW,
                )
            ),
            SmokePreflightFailureCode.DATA_CONTROLS_INVALID,
        ),
    )
    for index, (smoke_manifest, code) in enumerate(cases):
        smoke_ledger = ledger(tmp_path / f"ledger-{index}.json")
        assert_failure(
            code,
            lambda current=smoke_manifest, current_ledger=smoke_ledger: authorize_and_reserve(
                authority=authority(current_ledger),
                ledger=current_ledger,
                manifest=current,
                capability=SmokeCapability.GENERATION,
                fixture=fixture(SmokeCapability.GENERATION),
                iam=iam(),
                now=NOW,
            ),
        )


def cast_pricing(value: PricingEvidence) -> PricingEvidence:
    return value


def cast_controls(value: DataControlsEvidence) -> DataControlsEvidence:
    return value


def test_ledger_reservations_are_concurrency_safe(tmp_path: Path) -> None:
    smoke_manifest = manifest()
    smoke_ledger = ledger(tmp_path / "ledger.json")

    def reserve() -> object:
        try:
            return smoke_ledger.reserve(
                smoke_manifest,
                SmokeCapability.GENERATION,
            )
        except SmokePreflightFailure as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(reserve), executor.submit(reserve))
        results = tuple(future.result() for future in futures)
    assert sorted(str(result) for result in results) == [
        "1",
        SmokePreflightFailureCode.REPLAY_REJECTED.value,
    ]


def test_ledger_reconciles_terminal_and_ambiguous_outcomes(
    tmp_path: Path,
) -> None:
    smoke_manifest = manifest()
    smoke_ledger = ledger(tmp_path / "ledger.json")
    generation_authorization = authorize_and_reserve(
        authority=authority(smoke_ledger),
        ledger=smoke_ledger,
        manifest=smoke_manifest,
        capability=SmokeCapability.GENERATION,
        fixture=fixture(SmokeCapability.GENERATION),
        iam=iam(),
        now=NOW,
    )
    embedding_authorization = authorize_and_reserve(
        authority=authority(smoke_ledger),
        ledger=smoke_ledger,
        manifest=smoke_manifest,
        capability=SmokeCapability.EMBEDDING,
        fixture=fixture(SmokeCapability.EMBEDDING),
        iam=iam(),
        now=NOW,
    )
    smoke_ledger.begin_dispatch(smoke_manifest, generation_authorization)
    smoke_ledger.begin_dispatch(smoke_manifest, embedding_authorization)
    smoke_ledger.reconcile(
        smoke_manifest,
        SmokeCapability.GENERATION,
        outcome=SmokeOutcome.SUCCEEDED,
        incurred_cost_microusd=70,
        receipt_sha256="c" * 64,
    )
    smoke_ledger.reconcile(
        smoke_manifest,
        SmokeCapability.EMBEDDING,
        outcome=SmokeOutcome.AMBIGUOUS,
        incurred_cost_microusd=None,
        receipt_sha256="d" * 64,
    )
    state = smoke_ledger.read_sanitized(smoke_manifest)
    reservations = state["reservations"]
    assert isinstance(reservations, dict)
    assert reservations["generation"]["state"] == "succeeded"
    assert reservations["embedding"]["state"] == "ambiguous"
    assert_failure(
        SmokePreflightFailureCode.RECONCILIATION_INVALID,
        lambda: smoke_ledger.reconcile(
            smoke_manifest,
            SmokeCapability.GENERATION,
            outcome=SmokeOutcome.FAILED,
            incurred_cost_microusd=0,
            receipt_sha256="e" * 64,
        ),
    )


def test_ledger_rejects_tamper_and_manifest_rebinding(tmp_path: Path) -> None:
    smoke_manifest = manifest()
    ledger_path = (tmp_path / "ledger.json").resolve()
    smoke_ledger = ledger(ledger_path)
    smoke_ledger.reserve(smoke_manifest, SmokeCapability.GENERATION)
    state = json.loads(ledger_path.read_text(encoding="utf-8"))
    del state["reservations"]["generation"]
    ledger_path.write_text(json.dumps(state), encoding="utf-8")
    assert_failure(
        SmokePreflightFailureCode.LEDGER_TAMPERED,
        lambda: smoke_ledger.reserve(
            smoke_manifest,
            SmokeCapability.EMBEDDING,
        ),
    )


def test_ledger_loss_does_not_reopen_admission(tmp_path: Path) -> None:
    smoke_manifest = manifest()
    ledger_path = (tmp_path / "ledger.json").resolve()
    smoke_ledger = ledger(ledger_path)
    smoke_ledger.reserve(smoke_manifest, SmokeCapability.GENERATION)
    ledger_path.unlink()
    assert_failure(
        SmokePreflightFailureCode.LEDGER_TAMPERED,
        lambda: smoke_ledger.reserve(
            smoke_manifest,
            SmokeCapability.GENERATION,
        ),
    )


def test_authority_rejects_new_ledger_namespace_and_new_run(
    tmp_path: Path,
) -> None:
    trusted_ledger = ledger(tmp_path / "trusted.json")
    other_ledger = ledger(tmp_path / "other.json")
    assert_failure(
        SmokePreflightFailureCode.LEDGER_TAMPERED,
        lambda: authorize_and_reserve(
            authority=authority(trusted_ledger),
            ledger=other_ledger,
            manifest=manifest(),
            capability=SmokeCapability.GENERATION,
            fixture=fixture(SmokeCapability.GENERATION),
            iam=iam(),
            now=NOW,
        ),
    )
    next_run = manifest(run_id="vertex-smoke-20260730-002")
    assert_failure(
        SmokePreflightFailureCode.REPLAY_REJECTED,
        lambda: authorize_and_reserve(
            authority=authority(trusted_ledger),
            ledger=trusted_ledger,
            manifest=next_run,
            capability=SmokeCapability.GENERATION,
            fixture=fixture(SmokeCapability.GENERATION),
            iam=iam(),
            now=NOW,
        ),
    )


def test_manifest_derives_reservations_from_pricing_and_token_caps() -> None:
    smoke_manifest = manifest()
    assert smoke_manifest.reservation_microusd == {
        SmokeCapability.GENERATION: 154,
        SmokeCapability.EMBEDDING: 20,
    }
    with pytest.raises(ValueError, match="reservations"):
        manifest(
            reservation_microusd={
                SmokeCapability.GENERATION: 153,
                SmokeCapability.EMBEDDING: 20,
            }
        )


def test_arbitrary_neutral_fixture_cannot_be_self_authorized(
    tmp_path: Path,
) -> None:
    arbitrary = SyntheticFixture("arbitrary", {"value": 8})
    smoke_manifest = manifest(
        fixture_digests={
            SmokeCapability.GENERATION: arbitrary.digest,
            SmokeCapability.EMBEDDING: fixture(
                SmokeCapability.EMBEDDING
            ).digest,
        }
    )
    smoke_ledger = ledger(tmp_path / "ledger.json")
    assert_failure(
        SmokePreflightFailureCode.FIXTURE_TAMPERED,
        lambda: authorize_and_reserve(
            authority=authority(smoke_ledger),
            ledger=smoke_ledger,
            manifest=smoke_manifest,
            capability=SmokeCapability.GENERATION,
            fixture=arbitrary,
            iam=iam(),
            now=NOW,
        ),
        )


def test_manifest_and_ledger_reject_half_dollar_or_higher_caps(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="synthetic-only limits"):
        manifest(max_total_cost_microusd=500_000)
    with pytest.raises(ValueError, match="ledger policy"):
        FileSmokeLedger(
            (tmp_path / "ledger.json").resolve(),
            seal_key=SEAL_KEY,
            key_id=SEAL_KEY_ID,
            daily_cap_microusd=500_000,
        )


def test_manifest_is_content_addressed_and_rejects_eligibility_drift() -> None:
    first = manifest()
    second = manifest()
    assert first.digest == second.digest
    assert len(first.digest) == 64
    with pytest.raises(ValueError, match="synthetic-only"):
        manifest(training_eligible=True)
    with pytest.raises(ValueError, match="synthetic fixture"):
        SyntheticFixture(
            "not-rehearsal",
            {"value": 4},
            human_adjudicated=True,
        )
    with pytest.raises(ValueError, match="synthetic-only"):
        manifest(run_id="operator@example.com")
