#!/usr/bin/env python3
"""Fetch one approved immutable artifact into a content-addressed quarantine.

This command deliberately does not parse, decompress, scan, approve, or release
the downloaded payload. Network egress should still run inside the platform
fetch worker's allowlisted network boundary in production.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
import socket
import ssl
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlsplit, urlunsplit

from validate_source_entry import contract_errors, gate_errors, load_entry

ALLOWED_MEDIA_TYPES = {
    "application/json",
    "application/x-ndjson",
    "application/vnd.apache.parquet",
    "text/csv",
}
DEFAULT_MAX_BYTES = 256 * 1024 * 1024


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a validated address while TLS-verifying the approved hostname."""

    def __init__(
        self,
        hostname: str,
        port: int,
        pinned_address: str,
        timeout: float,
    ) -> None:
        super().__init__(hostname, port=port, timeout=timeout, context=ssl.create_default_context())
        self.pinned_address = pinned_address

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self.pinned_address, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def validate_exact_locator(entry: dict[str, Any]) -> str:
    locator = str(entry["locator"])
    allowed_origin = str(entry["allowed_origin"])
    target = urlsplit(locator)
    origin = urlsplit(allowed_origin)
    if target.scheme != "https" or origin.scheme != "https":
        raise ValueError("locator and allowed origin must use HTTPS")
    if target.username or target.password or origin.username or origin.password:
        raise ValueError("credentials are forbidden in source URLs")
    if target.fragment or origin.query or origin.fragment or origin.path not in {"", "/"}:
        raise ValueError(
            "source origin must be a bare origin and locator cannot contain a fragment"
        )
    if not target.hostname or not origin.hostname or target.hostname != origin.hostname:
        raise ValueError("locator host does not match the approved origin")
    if target.port != origin.port:
        raise ValueError("locator port does not match the approved origin")
    hostname = target.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise ValueError("local hostnames are forbidden")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("non-public IP literals are forbidden")
    return locator


def normalized_media_type(raw_value: str | None) -> str:
    value = (raw_value or "").split(";", 1)[0].strip().lower()
    if value not in ALLOWED_MEDIA_TYPES:
        raise ValueError(f"unsupported media type: {value or 'missing'}")
    return value


def validate_public_dns(hostname: str, port: int) -> frozenset[str]:
    try:
        addresses = {
            item[4][0] for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as error:
        raise ValueError(f"source DNS resolution failed: {error}") from error
    if not addresses:
        raise ValueError("source DNS resolution returned no addresses")
    for raw_address in addresses:
        address = ipaddress.ip_address(raw_address)
        if not address.is_global:
            raise ValueError(f"source DNS resolved to a non-public address: {raw_address}")
    return frozenset(addresses)


def copy_bounded(source: BinaryIO, destination: BinaryIO, max_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    while chunk := source.read(1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"artifact exceeds byte limit: {max_bytes}")
        digest.update(chunk)
        destination.write(chunk)
    return digest.hexdigest(), total


def tree_hash(payload_digest: str, payload_bytes: int) -> str:
    canonical = f"payload\0{payload_digest}\0{payload_bytes}\n".encode()
    return hashlib.sha256(canonical).hexdigest()


def fetch(
    entry: dict[str, Any],
    fetch_id: str,
    quarantine_root: Path,
    max_bytes: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    locator = validate_exact_locator(entry)
    parsed_locator = urlsplit(locator)
    hostname = parsed_locator.hostname
    if hostname is None:
        raise ValueError("source hostname is missing")
    port = parsed_locator.port or 443
    pinned_address = sorted(validate_public_dns(hostname, port))[0]
    request_target = urlunsplit(("", "", parsed_locator.path or "/", parsed_locator.query, ""))
    connection = PinnedHTTPSConnection(hostname, port, pinned_address, timeout_seconds)
    requested_at = utc_now()
    quarantine_root.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        connection.request(
            "GET",
            request_target,
            headers={
                "Accept": ", ".join(sorted(ALLOWED_MEDIA_TYPES)),
                "Host": parsed_locator.netloc,
                "User-Agent": "VFBiz-Dataset-Fetch/1",
            },
        )
        with connection.getresponse() as response:
            if response.status != 200:
                raise ValueError(f"source returned forbidden HTTP status: {response.status}")
            media_type = normalized_media_type(response.getheader("Content-Type"))
            declared_size = response.getheader("Content-Length")
            if declared_size is not None and int(declared_size) > max_bytes:
                raise ValueError(f"declared artifact size exceeds byte limit: {max_bytes}")
            file_descriptor, raw_path = tempfile.mkstemp(prefix="vfbiz-fetch-", dir=quarantine_root)
            temporary_path = Path(raw_path)
            with os.fdopen(file_descriptor, "wb") as output:
                observed_sha256, byte_count = copy_bounded(response, output, max_bytes)
                output.flush()
                os.fsync(output.fileno())
        content_address = f"sha256/{observed_sha256[:2]}/{observed_sha256}"
        upstream_checksum = entry.get("upstream_checksum_sha256")
        if upstream_checksum and observed_sha256 != upstream_checksum:
            raise ValueError("observed checksum does not match the pinned upstream checksum")
        artifact_directory = quarantine_root / "sha256" / observed_sha256[:2] / observed_sha256
        artifact_directory.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_directory / "payload"
        if artifact_path.exists():
            if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != observed_sha256:
                raise ValueError("content-address collision in quarantine")
            temporary_path.unlink()
        else:
            temporary_path.replace(artifact_path)
        temporary_path = None
        manifest = {
            "fetch_id": fetch_id,
            "source_id": entry["source_id"],
            "source_version": entry["version"],
            "source_revision": entry["source_revision"],
            "status": "quarantined",
            "requested_uri": locator,
            "resolved_uri": locator,
            "requested_at": requested_at,
            "completed_at": utc_now(),
            "storage_zone": "quarantine",
            "content_address": content_address,
            "observed_sha256": observed_sha256,
            "observed_tree_hash": tree_hash(observed_sha256, byte_count),
            "bytes": byte_count,
            "media_type": media_type,
        }
        errors = contract_errors(manifest, "source-fetch-manifest.schema.json")
        if errors:
            raise ValueError("invalid generated fetch manifest: " + "; ".join(errors))
        return manifest
    finally:
        connection.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--fetch-id", required=True)
    parser.add_argument("--quarantine-root", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()
    try:
        entry = load_entry(args.register, args.source_id)
        errors = contract_errors(entry, "source-register.schema.json")
        errors += gate_errors(entry, "fetch", None, None)
        if errors:
            raise ValueError("; ".join(errors))
        if args.max_bytes <= 0 or args.timeout_seconds <= 0:
            raise ValueError("byte and timeout limits must be positive")
        manifest = fetch(
            entry,
            args.fetch_id,
            args.quarantine_root,
            args.max_bytes,
            args.timeout_seconds,
        )
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, http.client.HTTPException, json.JSONDecodeError) as error:
        print(f"DENIED: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"decision": "quarantined", **manifest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
