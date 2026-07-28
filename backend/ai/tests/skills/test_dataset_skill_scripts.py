from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

from pytest import MonkeyPatch

AI_ROOT = Path(__file__).parents[2]
FIXTURES = AI_ROOT / "tests" / "fixtures" / "datasets"
GENERATOR_SCRIPTS = AI_ROOT / ".agents" / "skills" / "generate-synthetic-dataset" / "scripts"
SOURCE_GATE = (
    AI_ROOT / ".agents" / "skills" / "onboard-dataset" / "scripts" / "validate_source_entry.py"
)
FETCH_SCRIPT = SOURCE_GATE.with_name("fetch_to_quarantine.py")


def load_fetch_module() -> object:
    scripts_dir = str(FETCH_SCRIPT.parent)
    sys.path.insert(0, scripts_dir)
    try:
        spec = importlib.util.spec_from_file_location("fetch_to_quarantine", FETCH_SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts_dir)


def run(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, *(str(value) for value in arguments)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_candidate_validator_accepts_valid_and_rejects_unsafe() -> None:
    valid = run(
        GENERATOR_SCRIPTS / "validate_candidate.py",
        "--input",
        FIXTURES / "valid-candidate.jsonl",
    )
    invalid = run(
        GENERATOR_SCRIPTS / "validate_candidate.py",
        "--input",
        FIXTURES / "invalid-candidate.jsonl",
    )
    assert valid.returncode == 0, valid.stderr
    assert invalid.returncode == 1
    assert "possible PII" in invalid.stderr
    assert "True was expected" in invalid.stderr


def test_near_duplicate_gate_checks_across_shards() -> None:
    unique = run(
        GENERATOR_SCRIPTS / "detect_near_duplicates.py",
        FIXTURES / "valid-candidate.jsonl",
    )
    duplicate = run(
        GENERATOR_SCRIPTS / "detect_near_duplicates.py",
        FIXTURES / "valid-candidate.jsonl",
        FIXTURES / "duplicate-candidate.jsonl",
    )
    assert unique.returncode == 0, unique.stdout
    assert duplicate.returncode == 1
    assert json.loads(duplicate.stdout)["duplicates"]


def test_contamination_gate_rejects_held_out_overlap(tmp_path: Path) -> None:
    held_out = tmp_path / "held-out.jsonl"
    held_out.write_text(
        json.dumps({"example_id": "eval.intent.001", "split_family_id": "family-1"}) + "\n",
        encoding="utf-8",
    )
    clean = run(
        GENERATOR_SCRIPTS / "check_split_contamination.py",
        "--candidate",
        FIXTURES / "valid-candidate.jsonl",
        "--held-out",
        held_out,
    )
    assert clean.returncode == 0, clean.stdout
    contaminated = tmp_path / "candidate.jsonl"
    contaminated.write_text(
        json.dumps({"example_id": "candidate.1", "split_family_id": "family-1"}) + "\n",
        encoding="utf-8",
    )
    rejected = run(
        GENERATOR_SCRIPTS / "check_split_contamination.py",
        "--candidate",
        contaminated,
        "--held-out",
        held_out,
    )
    assert rejected.returncode == 1
    assert "family:family-1" in rejected.stdout


def test_manifest_builder_emits_candidate_only(tmp_path: Path) -> None:
    output = tmp_path / "manifest.json"
    result = run(
        GENERATOR_SCRIPTS / "build_manifest.py",
        "--dataset-id",
        "chatbot-evaluation-synthetic",
        "--version",
        "0.1.0",
        "--purpose",
        "retrieval-evaluation",
        "--profile",
        "public_customer",
        "--source-id",
        "synthetic-approved-seeds",
        "--shard",
        FIXTURES / "valid-candidate.jsonl",
        "--output",
        output,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["status"] == "candidate"
    assert {artifact["zone"] for artifact in manifest["artifacts"]} == {"candidate"}
    assert manifest["approval_evidence"] == []
    assert manifest["record_counts"]["candidate"] == 2

    manifest["record_counts"] = {"candidate": 1, "accepted": 1, "rejected": 1}
    manifest["approval_evidence"] = [
        {"actor_ref": "human:same"},
        {"actor_ref": "human:same"},
    ]
    output.write_text(json.dumps(manifest), encoding="utf-8")
    invalid = run(
        GENERATOR_SCRIPTS / "validate_manifest.py",
        "--manifest",
        output,
    )
    assert invalid.returncode == 1
    assert "accepted plus rejected cannot exceed candidate count" in invalid.stderr
    assert "approval decisions must use distinct human actors" in invalid.stderr


def test_manifest_builder_rejects_invalid_or_duplicate_shards(tmp_path: Path) -> None:
    invalid_shard = tmp_path / "invalid.jsonl"
    invalid_shard.write_text("not-json-at-all\n", encoding="utf-8")
    invalid = run(
        GENERATOR_SCRIPTS / "build_manifest.py",
        "--dataset-id",
        "invalid-candidate",
        "--version",
        "0.1.0",
        "--purpose",
        "intent-ood",
        "--profile",
        "public_customer",
        "--source-id",
        "synthetic-approved-seeds",
        "--shard",
        invalid_shard,
        "--output",
        tmp_path / "invalid-manifest.json",
    )
    assert invalid.returncode != 0
    assert "invalid candidate shard" in invalid.stderr

    duplicate = run(
        GENERATOR_SCRIPTS / "build_manifest.py",
        "--dataset-id",
        "duplicate-candidate",
        "--version",
        "0.1.0",
        "--purpose",
        "intent-ood",
        "--profile",
        "public_customer",
        "--source-id",
        "synthetic-approved-seeds",
        "--shard",
        FIXTURES / "valid-candidate.jsonl",
        "--shard",
        FIXTURES / "valid-candidate.jsonl",
        "--output",
        tmp_path / "duplicate-manifest.json",
    )
    assert duplicate.returncode != 0
    assert "duplicate example_id across shards" in duplicate.stderr


def test_source_gate_denies_candidate_and_accepts_evidence(tmp_path: Path) -> None:
    denied = run(
        SOURCE_GATE,
        "--register",
        AI_ROOT
        / "dataset-specs"
        / "catalog"
        / "sources"
        / "public"
        / "csconda-vietnamese-customer-support.json",
        "--source-id",
        "csconda-vietnamese-customer-support",
        "--gate",
        "fetch",
    )
    assert denied.returncode == 2
    approved = [
        {
            "source_id": "approved-synthetic-source",
            "version": "1",
            "title": "Approved synthetic source",
            "status": "purpose-approved",
            "source_type": "synthetic",
            "locator": "https://example.invalid/source.jsonl",
            "allowed_origin": "https://example.invalid/",
            "source_revision": "fixture-1",
            "proposed_purposes": ["intent-ood"],
            "approved_purposes": ["intent-ood"],
            "acl_namespaces": ["public_customer:customer-support:vi-VN"],
            "classification": "public",
            "custodian_role": "data-steward",
            "upstream_checksum_sha256": None,
            "verified_fetch_ids": ["FETCH-1"],
            "fetch_approval_evidence": [
                {
                    "decision_id": "LEGAL-FETCH-APPROVAL-1",
                    "role": "legal-owner",
                    "actor_ref": "human:legal-owner:test",
                    "decision": "approved",
                    "evidence_digest": "b" * 64,
                    "decided_at": "2026-07-28T00:00:00Z",
                }
            ],
            "purpose_approval_evidence": [
                {
                    "decision_id": "DATA-PURPOSE-APPROVAL-1",
                    "role": "data-owner",
                    "actor_ref": "human:data-owner:test",
                    "decision": "approved",
                    "evidence_digest": "c" * 64,
                    "decided_at": "2026-07-28T00:01:00Z",
                }
            ],
            "deletion_method": "Delete candidate objects.",
            "retention": {"policy_id": "test", "duration_days": 1},
            "rights": {
                "license_id": "internal-synthetic",
                "commercial_use": "permitted",
                "derivatives": "permitted",
                "redistribution": "prohibited",
                "access_conditions": "Synthetic test fixture.",
                "legal_review": "approved",
                "evidence_urls": ["https://example.invalid/license"],
            },
            "owner_role": "data-owner",
            "review_date": "2026-08-28",
        }
    ]
    register = tmp_path / "register.json"
    register.write_text(json.dumps(approved), encoding="utf-8")
    fetch_manifest = tmp_path / "fetch.json"
    fetch_manifest.write_text(
        json.dumps(
            {
                "fetch_id": "FETCH-1",
                "source_id": "approved-synthetic-source",
                "source_version": "1",
                "source_revision": "fixture-1",
                "status": "scan-passed",
                "requested_uri": "https://example.invalid/source.jsonl",
                "resolved_uri": "https://example.invalid/source.jsonl",
                "requested_at": "2026-07-28T00:00:00Z",
                "completed_at": "2026-07-28T00:01:00Z",
                "storage_zone": "quarantine",
                "content_address": f"sha256/{'a' * 2}/{'a' * 64}",
                "observed_sha256": "a" * 64,
                "observed_tree_hash": "b" * 64,
                "bytes": 1,
                "media_type": "application/x-ndjson",
                "scan_evidence_ids": ["SCAN-1"],
            }
        ),
        encoding="utf-8",
    )
    allowed = run(
        SOURCE_GATE,
        "--register",
        register,
        "--source-id",
        "approved-synthetic-source",
        "--gate",
        "purpose",
        "--purpose",
        "intent-ood",
        "--fetch-manifest",
        fetch_manifest,
    )
    assert allowed.returncode == 0, allowed.stderr
    wrong_purpose = run(
        SOURCE_GATE,
        "--register",
        register,
        "--source-id",
        "approved-synthetic-source",
        "--gate",
        "purpose",
        "--purpose",
        "knowledge",
        "--fetch-manifest",
        fetch_manifest,
    )
    assert wrong_purpose.returncode == 2
    assert "requested purpose is not approved" in wrong_purpose.stderr

    fetch_value = json.loads(fetch_manifest.read_text(encoding="utf-8"))
    fetch_value["source_version"] = "different-version"
    fetch_value["requested_uri"] = "https://example.invalid/other.jsonl"
    fetch_value["resolved_uri"] = "https://example.invalid/other.jsonl"
    fetch_manifest.write_text(json.dumps(fetch_value), encoding="utf-8")
    unbound = run(
        SOURCE_GATE,
        "--register",
        register,
        "--source-id",
        "approved-synthetic-source",
        "--gate",
        "purpose",
        "--purpose",
        "intent-ood",
        "--fetch-manifest",
        fetch_manifest,
    )
    assert unbound.returncode == 2
    assert "bound to this source revision" in unbound.stderr

    fetch_value["source_version"] = "1"
    fetch_value["requested_uri"] = approved[0]["locator"]
    fetch_value["resolved_uri"] = approved[0]["locator"]
    fetch_manifest.write_text(json.dumps(fetch_value), encoding="utf-8")

    approved[0]["upstream_checksum_sha256"] = "f" * 64
    register.write_text(json.dumps(approved), encoding="utf-8")
    checksum_mismatch = run(
        SOURCE_GATE,
        "--register",
        register,
        "--source-id",
        "approved-synthetic-source",
        "--gate",
        "purpose",
        "--purpose",
        "intent-ood",
        "--fetch-manifest",
        fetch_manifest,
    )
    assert checksum_mismatch.returncode == 2
    assert "observed checksum" in checksum_mismatch.stderr
    approved[0]["upstream_checksum_sha256"] = None

    approved[0]["approved_purposes"] = ["knowledge"]
    approved[0]["classification"] = "restricted"
    approved[0]["acl_namespaces"] = ["public_customer:customer-support:vi-VN"]
    register.write_text(json.dumps(approved), encoding="utf-8")
    unsafe_acl = run(
        SOURCE_GATE,
        "--register",
        register,
        "--source-id",
        "approved-synthetic-source",
        "--gate",
        "purpose",
        "--purpose",
        "knowledge",
        "--fetch-manifest",
        fetch_manifest,
    )
    assert unsafe_acl.returncode == 2
    assert "approved purposes are outside proposed purposes" in unsafe_acl.stderr
    assert "'public' was expected" in unsafe_acl.stderr


def test_quarantine_fetch_primitives_are_bounded_and_fail_closed(
    monkeypatch: MonkeyPatch,
) -> None:
    module = load_fetch_module()
    assert (
        module.validate_exact_locator(
            {
                "locator": "https://datasets.example.test/release/data.jsonl",
                "allowed_origin": "https://datasets.example.test/",
            }
        )
        == "https://datasets.example.test/release/data.jsonl"
    )
    for locator, origin in (
        ("http://datasets.example.test/data.jsonl", "https://datasets.example.test/"),
        ("https://127.0.0.1/data.jsonl", "https://127.0.0.1/"),
        ("https://other.example.test/data.jsonl", "https://datasets.example.test/"),
    ):
        try:
            module.validate_exact_locator({"locator": locator, "allowed_origin": origin})
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe locator was accepted: {locator}")

    destination = io.BytesIO()
    digest, size = module.copy_bounded(io.BytesIO(b'{"safe":true}\n'), destination, 64)
    assert size == len(destination.getvalue())
    assert digest == "7eeccb134911ebae5c9ab93e29604540babeda8e0f5a634d92fc0a1d3dc45c52"
    try:
        module.copy_bounded(io.BytesIO(b"too-large"), io.BytesIO(), 3)
    except ValueError as error:
        assert "exceeds byte limit" in str(error)
    else:
        raise AssertionError("oversized artifact was accepted")

    connected: dict[str, object] = {}

    def fake_create_connection(address: object, timeout: object, source: object) -> object:
        connected.update(address=address, timeout=timeout, source=source)
        return object()

    class FakeContext:
        def wrap_socket(self, raw_socket: object, server_hostname: str) -> object:
            connected.update(raw_socket=raw_socket, server_hostname=server_hostname)
            return "tls-socket"

    monkeypatch.setattr(module.socket, "create_connection", fake_create_connection)
    connection = object.__new__(module.PinnedHTTPSConnection)
    connection.pinned_address = "203.0.113.10"
    connection.port = 443
    connection.timeout = 5
    connection.source_address = None
    connection._context = FakeContext()
    connection.host = "datasets.example.test"
    connection.connect()
    assert connected["address"] == ("203.0.113.10", 443)
    assert connected["server_hostname"] == "datasets.example.test"
    assert connection.sock == "tls-socket"


def test_contamination_gate_reads_golden_v2_lineage(tmp_path: Path) -> None:
    held_out = tmp_path / "golden.jsonl"
    held_out.write_text(
        json.dumps(
            {
                "case_id": "golden.factual.001",
                "split_family_id": "golden-family",
                "lineage": {"source_refs": ["vinfast-manual@r1"]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    candidate = json.loads(
        (FIXTURES / "valid-candidate.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    candidate["source_refs"] = [{"source_id": "vinfast-manual", "revision": "r1"}]
    candidate_path = tmp_path / "candidate.jsonl"
    candidate_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
    result = run(
        GENERATOR_SCRIPTS / "check_split_contamination.py",
        "--candidate",
        candidate_path,
        "--held-out",
        held_out,
    )
    assert result.returncode == 1
    assert "source:vinfast-manual@r1" in result.stdout
