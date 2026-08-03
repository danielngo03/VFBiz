#!/usr/bin/env python3
"""Validate a content-free VFBIZ-0199 GCP activation packet.

The packet is an operator handoff, not an approval generator. It contains
only identities, digests, bounded plan counts and disabled switches. This
validator never reads a PDF/OCR/chunk/vector object and never mutates GCP.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

SCHEMA = "vfbiz-gcp-ingestion-activation/v1"
PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
POSITIVE = re.compile(r"^[1-9][0-9]*$")
SECRET_ID = re.compile(r"^[A-Za-z0-9_-]{1,255}$")
ARTIFACT = re.compile(r"^[a-z0-9][a-z0-9./_-]{1,200}@sha256:[a-f0-9]{64}$")
GCS_URI = re.compile(r"^gs://[a-z0-9][a-z0-9._-]{2,62}/[A-Za-z0-9._/-]{1,900}$")
EVIDENCE_URI = re.compile(r"^(evidence|decision)://[A-Za-z0-9._:/-]{1,255}$")


class ActivationPacketError(ValueError):
    """Raised when a packet is missing authority or contains unsafe content."""


def canonical_digest(payload: dict[str, Any]) -> str:
    """Digest the packet without its self-reported digest field."""

    unsigned = {key: value for key, value in payload.items() if key != "packet_sha256"}
    encoded = json.dumps(
        unsigned,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_packet(payload: object) -> dict[str, str | int]:
    """Validate and return only sanitized packet identity evidence."""

    packet = _mapping(payload, "packet")
    _keys(
        packet,
        {
            "schema_version",
            "work_item",
            "status",
            "project_id",
            "project_number",
            "region",
            "worker_image",
            "rollback_image_sha256",
            "worker_database_secret_id",
            "worker_database_secret_version",
            "reconciler_database_secret_id",
            "reconciler_database_secret_version",
            "synthetic_smoke_manifest",
            "authority",
            "saved_plan",
            "risk_disposition",
            "switches",
            "packet_sha256",
        })
    if (
        packet["schema_version"] != SCHEMA
        or packet["work_item"] != "VFBIZ-0199"
        or packet["status"] != "preflight"
        or not _string_match(packet["project_id"], PROJECT_ID)
        or not _string_match(packet["project_number"], POSITIVE)
        or packet["region"] != "asia-southeast1"
    ):
        raise ActivationPacketError("packet identity or status is invalid")

    worker_image = _string(packet, "worker_image")
    rollback_digest = _string(packet, "rollback_image_sha256")
    if not ARTIFACT.fullmatch(worker_image) or not SHA256.fullmatch(rollback_digest):
        raise ActivationPacketError("worker and rollback image identities are invalid")
    worker_image_digest = worker_image.rsplit("@sha256:", maxsplit=1)[1]
    if worker_image_digest == rollback_digest:
        raise ActivationPacketError("rollback image must differ from active image")

    worker_secret = _string(packet, "worker_database_secret_id")
    reconciler_secret = _string(packet, "reconciler_database_secret_id")
    if (
        not SECRET_ID.fullmatch(worker_secret)
        or not SECRET_ID.fullmatch(reconciler_secret)
        or worker_secret == reconciler_secret
        or not POSITIVE.fullmatch(_string(packet, "worker_database_secret_version"))
        or not POSITIVE.fullmatch(_string(packet, "reconciler_database_secret_version"))
    ):
        raise ActivationPacketError("runtime secret identities must be distinct and numeric")

    _validate_manifest(packet["synthetic_smoke_manifest"])
    authority = _mapping(packet["authority"], "authority")
    _keys(authority, {"sha256", "generation", "storage_uri"})
    if (
        not _string_match(authority["sha256"], SHA256)
        or not _string_match(authority["generation"], POSITIVE)
        or not _string_match(authority["storage_uri"], GCS_URI)
    ):
        raise ActivationPacketError("authority object identity is invalid")

    plan = _mapping(packet["saved_plan"], "saved_plan")
    _keys(plan, {"sha256", "replacement_count", "destruction_count"})
    if (
        not _string_match(plan["sha256"], SHA256)
        or not _bounded_int(plan["replacement_count"], 0, 0)
        or not _bounded_int(plan["destruction_count"], 0, 0)
    ):
        raise ActivationPacketError("saved plan must have zero replacements and destructions")

    risk = _mapping(packet["risk_disposition"], "risk_disposition")
    _keys(risk, {"sha256", "reference"})
    if not _string_match(risk["sha256"], SHA256) or not _string_match(
        risk["reference"], EVIDENCE_URI
    ):
        raise ActivationPacketError("risk disposition evidence is invalid")

    switches = _mapping(packet["switches"], "switches")
    _keys(
        switches,
        {"worker_dispatch_enabled", "reconciler_schedule_enabled", "ocr_output_bucket_enabled"},
    )
    if any(switches[key] is not False for key in switches):
        raise ActivationPacketError("activation packet switches must remain disabled")

    packet_digest = packet.get("packet_sha256")
    if not isinstance(packet_digest, str) or packet_digest != canonical_digest(packet):
        raise ActivationPacketError("packet canonical digest mismatch")
    return {
        "schema_version": SCHEMA,
        "work_item": "VFBIZ-0199",
        "packet_sha256": packet_digest,
        "authority_sha256": cast(str, authority["sha256"]),
        "authority_generation": cast(str, authority["generation"]),
        "saved_plan_sha256": cast(str, plan["sha256"]),
        "risk_disposition_sha256": cast(str, risk["sha256"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.packet.read_text(encoding="utf-8"))
        result = validate_packet(payload)
    except (OSError, json.JSONDecodeError, ActivationPacketError) as error:
        print(f"FAILED-SAFELY: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ActivationPacketError(f"{label} must be an object")
    raw = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in raw):
        raise ActivationPacketError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _keys(value: dict[str, Any], expected: set[str]) -> None:
    if set(value) != expected:
        raise ActivationPacketError("packet contains unknown or missing fields")


def _string(packet: dict[str, Any], key: str) -> str:
    value = packet.get(key)
    if not isinstance(value, str) or not value:
        raise ActivationPacketError(f"{key} must be a non-empty string")
    return value


def _string_match(value: object, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _bounded_int(value: object, minimum: int, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _validate_manifest(value: object) -> None:
    manifest = _mapping(value, "synthetic_smoke_manifest")
    if not manifest:
        raise ActivationPacketError("synthetic smoke manifest cannot be empty")
    if any(
        not _string_match(digest, SHA256) or not _bounded_int(pages, 1, 500)
        for digest, pages in manifest.items()
    ):
        raise ActivationPacketError("synthetic manifest must map SHA-256 to 1..500 pages")


if __name__ == "__main__":
    raise SystemExit(main())
