from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, cast
from urllib.parse import quote

import httpx

from app.modules.datasets.application.ports import StoredObject
from app.modules.datasets.domain import RegistryInvariantError, TrustZone


class GcsTrustZoneObjectStore:
    """GCS adapter using workload tokens and create-only object semantics."""

    _CHUNK_BYTES = 1024 * 1024

    def __init__(
        self,
        *,
        buckets: dict[TrustZone, str],
        access_token: Callable[[], str],
        client: httpx.Client,
    ) -> None:
        missing = set(TrustZone) - set(buckets)
        if missing:
            missing_names = ", ".join(sorted(item.value for item in missing))
            raise RegistryInvariantError(f"missing GCS bucket mapping for: {missing_names}")
        if len(set(buckets.values())) != len(buckets):
            raise RegistryInvariantError("each trust zone must use a distinct GCS bucket")
        self._buckets = buckets
        self._access_token = access_token
        self._client = client

    def put_stream(
        self,
        *,
        zone: TrustZone,
        stream: BinaryIO,
        media_type: str,
        max_bytes: int,
    ) -> StoredObject:
        if max_bytes <= 0:
            raise RegistryInvariantError("object maximum size must be positive")
        digest = hashlib.sha256()
        size = 0
        descriptor, temporary_name = tempfile.mkstemp(prefix="vivi-gcs-upload-")
        try:
            with os.fdopen(descriptor, "wb") as output:
                while chunk := stream.read(self._CHUNK_BYTES):
                    size += len(chunk)
                    if size > max_bytes:
                        raise RegistryInvariantError("object exceeds configured byte limit")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            sha256 = digest.hexdigest()
            object_name = f"sha256/{sha256[:2]}/{sha256}"
            bucket = self._buckets[zone]
            upload_endpoint = (
                f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o"
            )
            with open(temporary_name, "rb") as payload:
                response = self._client.post(
                    upload_endpoint,
                    params={
                        "uploadType": "media",
                        "name": object_name,
                        "ifGenerationMatch": "0",
                    },
                    headers={
                        "Authorization": f"Bearer {self._access_token()}",
                        "Content-Type": media_type,
                        "X-Goog-Meta-Sha256": sha256,
                        "Cache-Control": "no-store",
                    },
                    content=payload,
                    timeout=60,
                )
        finally:
            Path(temporary_name).unlink(missing_ok=True)
        if response.status_code == 412:
            metadata_endpoint = (
                f"https://storage.googleapis.com/storage/v1/b/{quote(bucket, safe='')}/o/"
                f"{quote(object_name, safe='')}"
            )
            metadata_response = self._client.get(
                metadata_endpoint,
                headers={"Authorization": f"Bearer {self._access_token()}"},
                timeout=30,
            )
            metadata_response.raise_for_status()
            raw_metadata = metadata_response.json()
            if not isinstance(raw_metadata, dict):
                raise RegistryInvariantError("existing GCS object metadata is invalid")
            metadata = cast(dict[str, object], raw_metadata)
            raw_custom_metadata = metadata.get("metadata")
            custom_metadata = (
                cast(dict[str, object], raw_custom_metadata)
                if isinstance(raw_custom_metadata, dict)
                else None
            )
            if (
                not isinstance(custom_metadata, dict)
                or custom_metadata.get("sha256") != sha256
                or metadata.get("size") != str(size)
                or not metadata.get("generation")
                or not metadata.get("crc32c")
            ):
                raise RegistryInvariantError(
                    "existing GCS object does not match the immutable upload"
                )
            return StoredObject(
                uri=f"gs://{bucket}/{object_name}",
                sha256=sha256,
                byte_size=size,
            )
        response.raise_for_status()
        return StoredObject(
            uri=f"gs://{bucket}/{object_name}",
            sha256=sha256,
            byte_size=size,
        )

    def path_for_test(self, stored: StoredObject) -> Path:
        raise RuntimeError("GCS objects do not expose local filesystem paths")
