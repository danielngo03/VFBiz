from __future__ import annotations

import io
import json
import stat
from pathlib import Path

import httpx
import pytest

from app.modules.datasets.domain import RegistryInvariantError, TrustZone
from app.modules.datasets.infrastructure import (
    GcsTrustZoneObjectStore,
    LocalContentAddressedObjectStore,
)


def test_local_store_uses_private_permissions_and_rejects_symlink_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "datasets"
    store = LocalContentAddressedObjectStore(root)
    stored = store.put_stream(
        zone=TrustZone.QUARANTINE,
        stream=io.BytesIO(b'{"safe":true}\n'),
        media_type="application/x-ndjson",
        max_bytes=1024,
    )
    path = store.path_for_test(stored)
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    symlink = tmp_path / "linked-datasets"
    symlink.symlink_to(root, target_is_directory=True)
    with pytest.raises(RegistryInvariantError, match="symlink"):
        LocalContentAddressedObjectStore(symlink)


def test_gcs_412_requires_matching_immutable_metadata() -> None:
    content = b"vivi-dataset"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(412, request=request)
        return httpx.Response(
            200,
            request=request,
            json={
                "size": str(len(content)),
                "generation": "7",
                "crc32c": "ImIEBA==",
                "metadata": {
                    "sha256": "059bf60b1bcaa6afaf2c66eb5f9ea361256949f80c7755b91a9391fba62b1316"
                },
            },
        )

    buckets = {zone: f"bucket-{zone.value}" for zone in TrustZone}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        store = GcsTrustZoneObjectStore(
            buckets=buckets,
            access_token=lambda: "workload-token",
            client=client,
        )
        stored = store.put_stream(
            zone=TrustZone.CANDIDATE,
            stream=io.BytesIO(content),
            media_type="application/x-ndjson",
            max_bytes=1024,
        )
    assert stored.byte_size == len(content)


def test_gcs_412_rejects_preexisting_object_with_wrong_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(412, request=request)
        return httpx.Response(
            200,
            request=request,
            content=json.dumps(
                {
                    "size": "4",
                    "generation": "7",
                    "crc32c": "bad",
                    "metadata": {"sha256": "0" * 64},
                }
            ).encode(),
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        store = GcsTrustZoneObjectStore(
            buckets={zone: f"bucket-{zone.value}" for zone in TrustZone},
            access_token=lambda: "workload-token",
            client=client,
        )
        with pytest.raises(RegistryInvariantError, match="does not match"):
            store.put_stream(
                zone=TrustZone.CANDIDATE,
                stream=io.BytesIO(b"safe"),
                media_type="application/x-ndjson",
                max_bytes=1024,
            )
