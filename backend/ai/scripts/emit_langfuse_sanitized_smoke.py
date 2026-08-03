from __future__ import annotations

import argparse
import hmac
import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Literal, cast

from app.infrastructure.observability import (
    LangfuseMetadataExporter,
    LangfuseSecretReferences,
    SanitizedModelObservation,
    load_langfuse_credentials,
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _load_verified_packet(packet_path: Path, seal_key_path: Path) -> dict[str, object]:
    decoded: object = json.loads(packet_path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError("operator packet shape is invalid")
    packet = cast("dict[str, object]", decoded)
    key_id = packet.get("keyId")
    payload = packet.get("payload")
    seal = packet.get("seal")
    if (
        packet.get("schemaVersion") != 1
        or not isinstance(key_id, str)
        or not isinstance(payload, dict)
        or not isinstance(seal, str)
    ):
        raise RuntimeError("operator packet shape is invalid")
    typed_payload = cast("dict[str, object]", payload)
    key = seal_key_path.read_bytes()
    expected = hmac.new(
        key,
        _canonical_bytes(
            {
                "keyId": key_id,
                "payload": typed_payload,
                "schemaVersion": 1,
            }
        ),
        digestmod=sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, seal):
        raise RuntimeError("operator packet seal is invalid")
    if (
        typed_payload.get("outcome") != "succeeded"
        or typed_payload.get("publicChatEnabled") is not False
        or typed_payload.get("releaseEligible") is not False
        or typed_payload.get("trainingEligible") is not False
    ):
        raise RuntimeError("operator packet is not an eligible synthetic receipt")
    return typed_payload


def execute(args: argparse.Namespace) -> str:
    payload = _load_verified_packet(args.packet, args.seal_key)
    manifest_digest = payload.get("manifestDigest")
    run_id = payload.get("runId")
    raw_results = payload.get("results")
    if (
        not isinstance(manifest_digest, str)
        or not isinstance(run_id, str)
        or not isinstance(raw_results, list)
    ):
        raise RuntimeError("operator packet identity is invalid")
    results = cast("list[object]", raw_results)
    public_key, secret_key = _load_credentials()
    exporter = LangfuseMetadataExporter(
        public_key=public_key,
        secret_key=secret_key,
        base_url=os.environ.get(
            "LANGFUSE_BASE_URL",
            "https://jp.cloud.langfuse.com",
        ),
    )
    try:
        for raw_result in results:
            if not isinstance(raw_result, dict):
                raise RuntimeError("operator result is invalid")
            result = cast("dict[str, object]", raw_result)
            raw_capability = result.get("capability")
            raw_authorization = result.get("authorization")
            if (
                raw_capability not in {"generation", "embedding"}
                or not isinstance(raw_authorization, dict)
            ):
                raise RuntimeError("operator result authority is invalid")
            capability = cast(
                'Literal["generation", "embedding"]',
                raw_capability,
            )
            authorization = cast("dict[str, object]", raw_authorization)
            raw_endpoint = authorization.get("endpoint")
            if not isinstance(raw_endpoint, dict):
                raise RuntimeError("operator endpoint is invalid")
            endpoint = cast("dict[str, object]", raw_endpoint)
            model_revision = endpoint.get("modelRevision")
            receipt_sha256 = result.get("receiptSha256")
            measurements = (
                result.get("inputTokens"),
                result.get("outputTokens"),
                result.get("latencyMs"),
                result.get("incurredCostMicrousd"),
            )
            if (
                not isinstance(model_revision, str)
                or not isinstance(receipt_sha256, str)
                or any(not isinstance(value, int) for value in measurements)
            ):
                raise RuntimeError("operator measurements are invalid")
            exporter.emit(
                SanitizedModelObservation(
                    capability=capability,
                    model_revision=model_revision,
                    run_id_sha256=sha256(run_id.encode()).hexdigest(),
                    manifest_sha256=manifest_digest,
                    receipt_sha256=receipt_sha256,
                    outcome="succeeded",
                    input_tokens=cast("int", measurements[0]),
                    output_tokens=cast("int", measurements[1]),
                    latency_ms=cast("int", measurements[2]),
                    cost_microusd=cast("int", measurements[3]),
                )
            )
        exporter.flush()
    finally:
        exporter.close()
    return sha256(
        _canonical_bytes(
            {
                "manifestDigest": manifest_digest,
                "observationCount": len(results),
                "runIdSha256": sha256(run_id.encode()).hexdigest(),
            }
        )
    ).hexdigest()


def _load_credentials() -> tuple[str, str]:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    public_key_secret_id = os.environ.get(
        "LANGFUSE_PUBLIC_KEY_SECRET_ID",
        "",
    )
    secret_key_secret_id = os.environ.get(
        "LANGFUSE_SECRET_KEY_SECRET_ID",
        "",
    )
    version = os.environ.get("LANGFUSE_SECRET_VERSION", "")
    if not version.isdecimal() or int(version) < 1:
        raise RuntimeError("LANGFUSE_SECRET_VERSION must pin a positive version")
    return load_langfuse_credentials(
        LangfuseSecretReferences(
            project_id=project_id,
            public_key_secret_id=public_key_secret_id,
            secret_key_secret_id=secret_key_secret_id,
            version=version,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit content-free Vertex smoke metadata to Langfuse."
    )
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--seal-key", type=Path, required=True)
    args = parser.parse_args()
    receipt = execute(args)
    print(
        json.dumps(
            {
                "contentExported": False,
                "observationCount": 2,
                "receiptSha256": receipt,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
