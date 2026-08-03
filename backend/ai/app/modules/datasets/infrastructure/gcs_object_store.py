from __future__ import annotations

import base64
import hashlib
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast
from urllib.parse import quote, unquote, urlsplit

import httpx

from app.modules.datasets.application.ports import StoredObject
from app.modules.datasets.domain import RegistryInvariantError, TrustZone


@dataclass(frozen=True, slots=True)
class VerifiedGcsObject:
    bucket: str
    object_name: str
    generation: int
    metageneration: int
    sha256: str
    byte_size: int
    crc32c: str


class GcsTrustZoneObjectStore:
    """GCS adapter using workload tokens and create-only object semantics."""

    _CHUNK_BYTES = 1024 * 1024
    _STORAGE_HOST = "storage.googleapis.com"

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
        crc32c = 0xFFFFFFFF
        size = 0
        descriptor, temporary_name = tempfile.mkstemp(prefix="vivi-gcs-upload-")
        try:
            with os.fdopen(descriptor, "wb") as output:
                while chunk := stream.read(self._CHUNK_BYTES):
                    size += len(chunk)
                    if size > max_bytes:
                        raise RegistryInvariantError("object exceeds configured byte limit")
                    digest.update(chunk)
                    crc32c = _crc32c_update(crc32c, chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            sha256 = digest.hexdigest()
            crc32c_b64 = _crc32c_base64(crc32c ^ 0xFFFFFFFF)
            object_name = f"sha256/{sha256[:2]}/{sha256}"
            bucket = self._buckets[zone]
            upload_endpoint = (
                f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o"
            )
            authorization = {"Authorization": f"Bearer {self._access_token()}"}
            response = self._client.post(
                upload_endpoint,
                params={
                    "uploadType": "resumable",
                    "ifGenerationMatch": "0",
                },
                headers={
                    **authorization,
                    "Content-Type": "application/json",
                    "X-Upload-Content-Length": str(size),
                    "X-Upload-Content-Type": media_type,
                },
                json={
                    "name": object_name,
                    "contentType": media_type,
                    "cacheControl": "no-store",
                    "metadata": {"sha256": sha256},
                },
                timeout=30,
            )
            if response.status_code == 412:
                verified = self._metadata(
                    bucket=bucket,
                    object_name=object_name,
                    expected_sha256=sha256,
                    expected_size=size,
                    expected_crc32c=crc32c_b64,
                )
                self._read_payload_verified(verified, max_bytes=max(1, size))
                return _stored_object(verified)
            response.raise_for_status()
            upload_url = response.headers.get("Location")
            if not upload_url or not self._is_storage_url(upload_url):
                raise RegistryInvariantError("GCS resumable upload location is invalid")
            with open(temporary_name, "rb") as payload:
                upload_response = self._client.put(
                    upload_url,
                    headers={
                        "Content-Type": media_type,
                        "Content-Length": str(size),
                        "X-Goog-Hash": f"crc32c={crc32c_b64}",
                    },
                    content=payload,
                    timeout=60,
                )
            upload_response.raise_for_status()
            created = self._validated_metadata(
                upload_response,
                bucket=bucket,
                object_name=object_name,
                expected_sha256=sha256,
                expected_size=size,
                expected_crc32c=crc32c_b64,
            )
            verified = self._metadata(
                bucket=bucket,
                object_name=object_name,
                expected_sha256=sha256,
                expected_size=size,
                expected_crc32c=crc32c_b64,
                expected_generation=created.generation,
            )
            self._read_payload_verified(verified, max_bytes=max(1, size))
            return _stored_object(verified)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    def read_verified(
        self,
        stored: StoredObject,
        *,
        max_bytes: int,
        expected_generation: int | None = None,
    ) -> bytes:
        """Read an immutable object only after metadata and payload integrity checks."""
        if max_bytes <= 0:
            raise RegistryInvariantError("object maximum size must be positive")
        bucket, object_name = self._parse_uri(stored.uri)
        if bucket not in self._buckets.values():
            raise RegistryInvariantError("GCS object bucket is outside configured trust zones")
        if expected_generation is None:
            expected_generation = stored.generation
        if expected_generation is None:
            raise RegistryInvariantError("GCS object generation is required for replay")
        verified = self._metadata(
            bucket=bucket,
            object_name=object_name,
            expected_sha256=stored.sha256,
            expected_size=stored.byte_size,
            expected_generation=expected_generation,
            expected_metageneration=stored.metageneration,
        )
        if verified.byte_size > max_bytes:
            raise RegistryInvariantError("object exceeds configured byte limit")
        return self._read_payload_verified(verified, max_bytes=max_bytes)

    def _read_payload_verified(self, verified: VerifiedGcsObject, *, max_bytes: int) -> bytes:
        """Stream a previously metadata-verified generation and re-hash its bytes."""
        endpoint = self._metadata_endpoint(verified.bucket, verified.object_name)
        digest = hashlib.sha256()
        crc32c = 0xFFFFFFFF
        size = 0
        content = bytearray()
        media_params = {
            "alt": "media",
            "generation": str(verified.generation),
            "ifGenerationMatch": str(verified.generation),
        }
        media_params["ifMetagenerationMatch"] = str(verified.metageneration)
        with self._client.stream(
            "GET",
            endpoint,
            params=media_params,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=60,
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(self._CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes or size > verified.byte_size:
                    raise RegistryInvariantError("GCS object payload exceeds verified size")
                digest.update(chunk)
                crc32c = _crc32c_update(crc32c, chunk)
                content.extend(chunk)
        if (
            size != verified.byte_size
            or digest.hexdigest() != verified.sha256
            or _crc32c_base64(crc32c ^ 0xFFFFFFFF) != verified.crc32c
        ):
            raise RegistryInvariantError("GCS object payload failed integrity verification")
        return bytes(content)

    def path_for_test(self, stored: StoredObject) -> Path:
        raise RuntimeError("GCS objects do not expose local filesystem paths")

    def _metadata(
        self,
        *,
        bucket: str,
        object_name: str,
        expected_sha256: str,
        expected_size: int,
        expected_crc32c: str | None = None,
        expected_generation: int | None = None,
        expected_metageneration: int | None = None,
    ) -> VerifiedGcsObject:
        response = self._client.get(
            self._metadata_endpoint(bucket, object_name),
            params=(
                {"generation": str(expected_generation)}
                if expected_generation is not None
                else None
            ),
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=30,
        )
        response.raise_for_status()
        return self._validated_metadata(
            response,
            bucket=bucket,
            object_name=object_name,
            expected_sha256=expected_sha256,
            expected_size=expected_size,
            expected_crc32c=expected_crc32c,
            expected_generation=expected_generation,
            expected_metageneration=expected_metageneration,
        )

    @staticmethod
    def _validated_metadata(
        response: httpx.Response,
        *,
        bucket: str,
        object_name: str,
        expected_sha256: str,
        expected_size: int,
        expected_crc32c: str | None,
        expected_generation: int | None = None,
        expected_metageneration: int | None = None,
    ) -> VerifiedGcsObject:
        raw_metadata = response.json()
        if not isinstance(raw_metadata, dict):
            raise RegistryInvariantError("GCS object metadata is invalid")
        metadata = cast(dict[str, object], raw_metadata)
        raw_custom_metadata = metadata.get("metadata")
        custom_metadata = (
            cast(dict[str, object], raw_custom_metadata)
            if isinstance(raw_custom_metadata, dict)
            else None
        )
        generation_value = metadata.get("generation")
        metageneration_value = metadata.get("metageneration")
        size_value = metadata.get("size")
        crc32c_value = metadata.get("crc32c")
        try:
            generation = int(generation_value) if isinstance(generation_value, str) else 0
            metageneration = (
                int(metageneration_value) if isinstance(metageneration_value, str) else 0
            )
            byte_size = int(size_value) if isinstance(size_value, str) else -1
        except ValueError as error:
            raise RegistryInvariantError("GCS object metadata is invalid") from error
        valid = (
            isinstance(custom_metadata, dict)
            and custom_metadata.get("sha256") == expected_sha256
            and metadata.get("bucket") in {None, bucket}
            and metadata.get("name") in {None, object_name}
            and byte_size == expected_size
            and generation > 0
            and metageneration > 0
            and isinstance(crc32c_value, str)
            and bool(crc32c_value)
            and (expected_crc32c is None or crc32c_value == expected_crc32c)
            and (expected_generation is None or generation == expected_generation)
            and (
                expected_metageneration is None
                or metageneration == expected_metageneration
            )
        )
        if not valid:
            raise RegistryInvariantError("GCS object does not match the immutable object identity")
        return VerifiedGcsObject(
            bucket=bucket,
            object_name=object_name,
            generation=generation,
            metageneration=metageneration,
            sha256=expected_sha256,
            byte_size=byte_size,
            crc32c=cast(str, crc32c_value),
        )

    @staticmethod
    def _metadata_endpoint(bucket: str, object_name: str) -> str:
        return (
            f"https://storage.googleapis.com/storage/v1/b/{quote(bucket, safe='')}/o/"
            f"{quote(object_name, safe='')}"
        )

    @classmethod
    def _is_storage_url(cls, value: str) -> bool:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and parsed.hostname == cls._STORAGE_HOST
            and parsed.username is None
            and parsed.password is None
            and parsed.fragment == ""
        )

    @staticmethod
    def _parse_uri(value: str) -> tuple[str, str]:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "gs"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise RegistryInvariantError("GCS object URI is invalid")
        object_name = unquote(parsed.path.lstrip("/"))
        if not object_name or object_name.startswith("/") or ".." in object_name.split("/"):
            raise RegistryInvariantError("GCS object name is invalid")
        return parsed.netloc, object_name


def _stored_object(value: VerifiedGcsObject) -> StoredObject:
    return StoredObject(
        uri=f"gs://{value.bucket}/{value.object_name}",
        sha256=value.sha256,
        byte_size=value.byte_size,
        generation=value.generation,
        metageneration=value.metageneration,
    )


def _crc32c_update(crc: int, content: bytes) -> int:
    for value in content:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return crc


def _crc32c_base64(value: int) -> str:
    return base64.b64encode(value.to_bytes(4, "big")).decode("ascii")
