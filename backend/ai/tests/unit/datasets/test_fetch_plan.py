import hashlib
import io
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

import httpx
import pytest

from app.modules.datasets.application.ports import StoredObject
from app.modules.datasets.application.source_intake.models import ApprovedSourceFetchPlan
from app.modules.datasets.application.source_intake.quarantine import (
    QuarantineApprovedSource,
)
from app.modules.datasets.domain import RegistryInvariantError, TrustZone
from app.modules.datasets.infrastructure.scanners.quarantine import (
    StructuralQuarantineScanner,
    scan_quarantine_stream,
)
from app.modules.datasets.infrastructure.source_readers import ControlledHttpSourceReader


class MemoryStore:
    def put_stream(
        self,
        *,
        zone: TrustZone,
        stream: BinaryIO,
        media_type: str,
        max_bytes: int,
    ) -> StoredObject:
        content = stream.read()
        return StoredObject(
            uri=f"memory://{zone.value}/artifact",
            sha256=hashlib.sha256(content).hexdigest(),
            byte_size=len(content),
        )

    def path_for_test(self, stored: StoredObject) -> Path:
        raise NotImplementedError


class ApprovedFetchAuthority:
    def assert_fetch_approved(
        self,
        plan: ApprovedSourceFetchPlan,
        *,
        at: datetime,
    ) -> None:
        del plan, at


class RejectingFetchAuthority:
    def assert_fetch_approved(
        self,
        plan: ApprovedSourceFetchPlan,
        *,
        at: datetime,
    ) -> None:
        del plan, at
        raise RegistryInvariantError("fetch approval is not active")


def allow_public_host(host: str) -> tuple[str, ...]:
    del host
    return ("93.184.216.34",)


def plan(*, upstream_sha256: str | None = None) -> ApprovedSourceFetchPlan:
    return ApprovedSourceFetchPlan(
        plan_id="wave-a-artifact-1",
        source_id="source-a",
        source_revision="abc123",
        artifact_selector="data/train.json",
        url="https://datasets.example/source/resolve/abc123/data/train.json",
        media_type="application/json",
        max_bytes=1024,
        fetch_approval_digest="a" * 64,
        upstream_sha256=upstream_sha256,
        expected_byte_size=12,
    )


def test_fetch_plan_binds_revision_and_selector() -> None:
    with pytest.raises(RegistryInvariantError, match="bind the exact"):
        ApprovedSourceFetchPlan(
            plan_id="bad",
            source_id="source-a",
            source_revision="abc123",
            artifact_selector="data/train.json",
            url="https://datasets.example/source/resolve/main/data/other.json",
            media_type="application/json",
            max_bytes=1024,
            fetch_approval_digest="a" * 64,
        )


def test_controlled_fetch_verifies_plan_digest_size_and_upstream_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b'{"ok": true}'
    expected = __import__("hashlib").sha256(payload).hexdigest()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=payload))
    reader = ControlledHttpSourceReader(
        client=httpx.Client(transport=transport),
    )
    fetcher = QuarantineApprovedSource(
        approval_authority=ApprovedFetchAuthority(),
        source_reader=reader,
        scanner=StructuralQuarantineScanner(),
        object_store=MemoryStore(),
    )
    monkeypatch.setattr(reader, "_resolve_public_addresses", allow_public_host)

    result = fetcher.execute(
        plan(upstream_sha256=expected),
        now=datetime(2026, 7, 28, tzinfo=UTC),
    )

    assert result.stored.sha256 == expected
    assert result.fetch_plan_sha256 == plan(upstream_sha256=expected).digest


def test_controlled_fetch_rejects_upstream_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b'{"ok": true}'))
    reader = ControlledHttpSourceReader(
        client=httpx.Client(transport=transport),
    )
    fetcher = QuarantineApprovedSource(
        approval_authority=ApprovedFetchAuthority(),
        source_reader=reader,
        scanner=StructuralQuarantineScanner(),
        object_store=MemoryStore(),
    )
    monkeypatch.setattr(reader, "_resolve_public_addresses", allow_public_host)

    with pytest.raises(RegistryInvariantError, match="upstream digest"):
        fetcher.execute(
            plan(upstream_sha256="b" * 64),
            now=datetime(2026, 7, 28, tzinfo=UTC),
        )


def test_quarantine_refuses_a_digest_without_active_registry_authority() -> None:
    fetcher = QuarantineApprovedSource(
        approval_authority=RejectingFetchAuthority(),
        source_reader=ControlledHttpSourceReader(
            client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
        ),
        scanner=StructuralQuarantineScanner(),
        object_store=MemoryStore(),
    )

    with pytest.raises(RegistryInvariantError, match="approval is not active"):
        fetcher.execute(plan(), now=datetime(2026, 7, 28, tzinfo=UTC))


def test_controlled_reader_pins_the_validated_ip_and_original_tls_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        observed["host"] = request.url.host
        observed["host_header"] = request.headers["host"]
        observed["sni_hostname"] = request.extensions["sni_hostname"]
        return httpx.Response(200, content=b'{"ok": true}')

    reader = ControlledHttpSourceReader(
        client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    monkeypatch.setattr(
        reader,
        "_resolve_public_addresses",
        lambda _host: ("93.184.216.34",),
    )

    with reader.open(plan()) as opened:
        assert opened.stream.read() == b'{"ok": true}'

    assert observed == {
        "host": "93.184.216.34",
        "host_header": "datasets.example",
        "sni_hostname": "datasets.example",
    }


def test_ndjson_scanner_streams_files_larger_than_the_sample_window() -> None:
    record = b'{"question":"xin chao","answer":"chao ban"}\n'
    payload = record * ((9 * 1024 * 1024 // len(record)) + 1)

    evidence = scan_quarantine_stream(
        io.BytesIO(payload),
        media_type="application/x-ndjson",
        byte_size=len(payload),
    )

    assert evidence.structural_valid is True
    assert evidence.observed_sha256 == hashlib.sha256(payload).hexdigest()


def test_ndjson_scanner_rejects_malformed_record_after_sample_window() -> None:
    record = b'{"question":"xin chao"}\n'
    payload = record * ((9 * 1024 * 1024 // len(record)) + 1) + b'{"broken":\n'

    evidence = scan_quarantine_stream(
        io.BytesIO(payload),
        media_type="application/x-ndjson",
        byte_size=len(payload),
    )

    assert evidence.structural_valid is False
    assert "invalid-structure" in evidence.reasons


def test_quarantine_scans_for_secrets_beyond_the_initial_sample_window() -> None:
    record = b'{"question":"xin chao"}\n'
    payload = (
        record * ((9 * 1024 * 1024 // len(record)) + 1)
        + b'{"metadata":"api_key=exposed-after-sample"}\n'
    )

    evidence = scan_quarantine_stream(
        io.BytesIO(payload),
        media_type="application/x-ndjson",
        byte_size=len(payload),
    )

    assert evidence.secret_candidate_count == 1
    assert evidence.passed is False
    assert "secret-candidate" in evidence.reasons
