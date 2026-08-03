#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast

from app.infrastructure.model_providers.vertex_smoke_authority import (
    CANONICAL_FIXTURE_DIGESTS,
    DataControlsEvidence,
    FileSmokeLedger,
    IamEvidence,
    PricingEvidence,
    SmokeCapability,
    SmokePreflightFailure,
    VertexEndpointIdentity,
    VertexSmokeAuthority,
    VertexSmokeManifest,
)
from app.infrastructure.model_providers.vertex_smoke_runner import (
    SanitizedVertexSmokeResult,
    VertexSmokeDispatchError,
    VertexSmokeRunner,
)

PROJECT_ID = "vinfast-503003"
PRINCIPAL = (
    "vfbiz-vertex-smoke@vinfast-503003.iam.gserviceaccount.com"
)
GENERATION_MODEL = "gemini-2.5-flash"
GENERATION_LOCATION = "asia-southeast1"
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_LOCATION = "global"
PRICING_URL = "https://cloud.google.com/vertex-ai/generative-ai/pricing"


class SmokeRunFailed(RuntimeError):
    def __init__(self, *, code: str, packet_sha256: str) -> None:
        self.code = code
        self.packet_sha256 = packet_sha256
        super().__init__(f"Vertex smoke failed: {code}")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    raw = value if isinstance(value, bytes) else _canonical_bytes(value)
    return sha256(raw).hexdigest()


def _load_or_create_seal_key(directory: Path) -> tuple[bytes, str]:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    key_path = directory / ".vertex-smoke-seal-key"
    try:
        descriptor = os.open(
            key_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        mode = key_path.stat().st_mode & 0o777
        key = key_path.read_bytes()
        if mode != 0o600 or len(key) != 32:
            raise RuntimeError(
                "existing smoke seal key is invalid"
            ) from None
    else:
        key = secrets.token_bytes(32)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(key)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(key_path, 0o600)
    return key, f"local-dev-{sha256(key).hexdigest()[:16]}"


def _manifest(
    *,
    now: datetime,
    data_control_sha256: str,
) -> VertexSmokeManifest:
    return VertexSmokeManifest(
        run_id=f"vertex-smoke-{now:%Y%m%d}-001",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        generation_endpoint=VertexEndpointIdentity(
            project_id=PROJECT_ID,
            location=GENERATION_LOCATION,
            model_revision=GENERATION_MODEL,
        ),
        embedding_endpoint=VertexEndpointIdentity(
            project_id=PROJECT_ID,
            location=EMBEDDING_LOCATION,
            model_revision=EMBEDDING_MODEL,
        ),
        fixture_digests=CANONICAL_FIXTURE_DIGESTS,
        input_token_caps={
            SmokeCapability.GENERATION: 512,
            SmokeCapability.EMBEDDING: 128,
        },
        output_token_caps={
            SmokeCapability.GENERATION: 128,
            SmokeCapability.EMBEDDING: 0,
        },
        reservation_microusd={
            SmokeCapability.GENERATION: 154,
            SmokeCapability.EMBEDDING: 20,
        },
        max_total_cost_microusd=500,
        max_requests_per_capability=1,
        pricing=PricingEvidence(
            revision="google-vertex-pricing-observed-2026-07-31",
            source_url=PRICING_URL,
            observed_at=now,
            input_microusd_per_million_tokens=150_000,
            output_microusd_per_million_tokens=600_000,
        ),
        data_controls=DataControlsEvidence(
            decision_reference=(
                "user-authorized-development-synthetic-no-content-smoke"
            ),
            decision_sha256=data_control_sha256,
            retention_policy="standard",
            effective_at=now,
            expires_at=now + timedelta(hours=1),
        ),
    )


def _write_packet(
    *,
    output: Path,
    payload: dict[str, object],
    seal_key: bytes,
    key_id: str,
) -> str:
    seal = hmac.new(
        seal_key,
        _canonical_bytes(
            {
                "keyId": key_id,
                "payload": payload,
                "schemaVersion": 1,
            }
        ),
        digestmod=sha256,
    ).hexdigest()
    packet = {
        "keyId": key_id,
        "payload": payload,
        "schemaVersion": 1,
        "seal": seal,
    }
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(output.parent, 0o700)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_bytes(packet))
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        os.chmod(output, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()
    return _sha256(packet)


def execute(args: argparse.Namespace) -> str:
    now = datetime.now(UTC).replace(microsecond=0)
    ledger_directory = args.ledger_dir.resolve()
    output = args.output.resolve()
    seal_key, key_id = _load_or_create_seal_key(ledger_directory)
    manifest = _manifest(
        now=now,
        data_control_sha256=args.data_control_sha256,
    )
    ledger_path = ledger_directory / "ledger.json"
    ledger = FileSmokeLedger(
        ledger_path,
        seal_key=seal_key,
        key_id=key_id,
        daily_cap_microusd=499_999,
    )
    authority = VertexSmokeAuthority(
        expected_project_id=PROJECT_ID,
        expected_principal=PRINCIPAL,
        expected_ledger_path=ledger_path,
        expected_ledger_key_id=key_id,
        generation_endpoint=manifest.generation_endpoint,
        embedding_endpoint=manifest.embedding_endpoint,
    )
    iam = IamEvidence(
        principal=PRINCIPAL,
        observed_at=now,
        granted_permissions=frozenset(
            {"aiplatform.endpoints.predict"}
        ),
        evidence_sha256=args.iam_evidence_sha256,
    )
    results: list[SanitizedVertexSmokeResult] = []
    runner = VertexSmokeRunner(
        authority=authority,
        ledger=ledger,
        manifest=manifest,
        principal=PRINCIPAL,
        witness_bucket=f"{PROJECT_ID}-evidence-dev",
    )
    failure: dict[str, object] | None = None
    try:
        for capability in SmokeCapability:
            result = runner.run(
                capability=capability,
                iam=iam,
                now=now,
            )
            if result is None:
                raise RuntimeError("smoke was cancelled")
            results.append(result)
    except SmokePreflightFailure as error:
        failure = {
            "class": "preflight",
            "code": error.code.value,
        }
    except VertexSmokeDispatchError as error:
        failure = {
            "class": "provider-dispatch",
            "code": error.code,
        }
    except Exception:
        failure = {
            "class": "runtime",
            "code": "sanitized-runtime-failure",
        }
    finally:
        runner.close()
    try:
        ledger_snapshot: dict[str, object] = ledger.read_sanitized(manifest)
    except Exception:
        ledger_snapshot = {
            "available": False,
            "reason": "ledger-unavailable",
            "schemaVersion": 1,
        }
    raw_reservations = ledger_snapshot.get("reservations", {})
    reservations: list[dict[str, object]] = []
    if isinstance(raw_reservations, dict):
        typed_reservations = cast(
            "dict[object, object]",
            raw_reservations,
        )
        reservations = [
            cast("dict[str, object]", record)
            for record in typed_reservations.values()
            if isinstance(record, dict)
        ]
    states = {
        str(record.get("state"))
        for record in reservations
    }
    provider_attempt_count = sum(
        1
        for record in reservations
        if record.get("state") in {"ambiguous", "succeeded"}
    )
    overall_outcome = (
        "succeeded"
        if failure is None and len(results) == len(SmokeCapability)
        else "ambiguous"
        if "ambiguous" in states or "dispatching" in states
        else "failed"
    )
    payload: dict[str, object] = {
        "authorityClass": manifest.authority_class,
        "environment": manifest.environment,
        "failure": failure,
        "humanApprovalClaimed": False,
        "manifestDigest": manifest.digest,
        "outcome": overall_outcome,
        "providerAttemptCount": provider_attempt_count,
        "providerSuccessCount": len(results),
        "publicChatEnabled": False,
        "releaseEligible": False,
        "results": [result.as_dict() for result in results],
        "runId": manifest.run_id,
        "schemaVersion": 1,
        "trainingEligible": False,
        "ledger": ledger_snapshot,
    }
    packet_sha256 = _write_packet(
        output=output,
        payload=payload,
        seal_key=seal_key,
        key_id=key_id,
    )
    if failure is not None:
        raise SmokeRunFailed(
            code=str(failure["code"]),
            packet_sha256=packet_sha256,
        ) from None
    return packet_sha256


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run exactly two content-free Vertex smoke requests."
    )
    parser.add_argument("--ledger-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--iam-evidence-sha256",
        required=True,
        choices=None,
    )
    parser.add_argument(
        "--data-control-sha256",
        required=True,
        choices=None,
    )
    args = parser.parse_args()
    for field in ("iam_evidence_sha256", "data_control_sha256"):
        value = cast("str", getattr(args, field))
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            parser.error(f"{field} must be lowercase SHA-256")
    try:
        packet_digest = execute(args)
    except SmokeRunFailed as error:
        print(
            json.dumps(
                {
                    "failureCode": error.code,
                    "packetSha256": error.packet_sha256,
                    "providerResult": "failed-or-ambiguous",
                    "rawContentPersisted": False,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "packetSha256": packet_digest,
                "providerRequests": 2,
                "rawContentPersisted": False,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
