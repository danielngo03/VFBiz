from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

AI_ROOT = Path(__file__).parents[2]
FIXTURES = AI_ROOT / "tests" / "fixtures" / "datasets"
GENERATOR_SCRIPTS = AI_ROOT / ".agents" / "skills" / "generate-synthetic-dataset" / "scripts"
SOURCE_GATE = (
    AI_ROOT / ".agents" / "skills" / "onboard-dataset" / "scripts" / "validate_source_entry.py"
)


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
    assert "requires human review" in invalid.stderr


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


def test_manifest_builder_emits_candidate_only(tmp_path: Path) -> None:
    output = tmp_path / "manifest.json"
    result = run(
        GENERATOR_SCRIPTS / "build_manifest.py",
        "--dataset-id",
        "chatbot-evaluation-synthetic",
        "--version",
        "0.1.0",
        "--purpose",
        "evaluation",
        "--profile",
        "public_customer",
        "--shard",
        FIXTURES / "valid-candidate.jsonl",
        "--output",
        output,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["status"] == "candidate"
    assert manifest["approval_evidence"] == []
    assert manifest["record_counts"]["candidate"] == 2


def test_source_gate_denies_candidate_and_accepts_evidence(tmp_path: Path) -> None:
    denied = run(
        SOURCE_GATE,
        "--register",
        AI_ROOT / "dataset-specs" / "public-source-candidates.json",
        "--source-id",
        "csconda-vietnamese-customer-support",
        "--purpose",
        "conversation-quality",
    )
    assert denied.returncode == 2
    approved = [
        {
            "source_id": "approved-synthetic-source",
            "version": "1",
            "status": "approved",
            "proposed_purposes": ["intent-ood"],
                "approved_purposes": ["intent-ood"],
                "acl_namespaces": ["public_customer:customer-support:vi-VN"],
                "classification": "public",
                "custodian_role": "data-steward",
            "checksum_sha256": "a" * 64,
            "approval_evidence": ["DATA-APPROVAL-1", "LEGAL-APPROVAL-1"],
            "deletion_method": "Delete candidate objects.",
            "retention": {"policy_id": "test", "duration_days": 1},
            "rights": {
                "commercial_use": "permitted",
                "derivatives": "permitted",
                "legal_review": "approved",
                "evidence_urls": ["https://example.invalid/license"],
            },
        }
    ]
    register = tmp_path / "register.json"
    register.write_text(json.dumps(approved), encoding="utf-8")
    allowed = run(
        SOURCE_GATE,
        "--register",
        register,
        "--source-id",
        "approved-synthetic-source",
        "--purpose",
        "intent-ood",
    )
    assert allowed.returncode == 0, allowed.stderr
    wrong_purpose = run(
        SOURCE_GATE,
        "--register",
        register,
        "--source-id",
        "approved-synthetic-source",
        "--purpose",
        "knowledge",
    )
    assert wrong_purpose.returncode == 2
    assert "requested purpose is not approved" in wrong_purpose.stderr

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
        "--purpose",
        "knowledge",
    )
    assert unsafe_acl.returncode == 2
    assert "approved purpose is outside proposed purposes" in unsafe_acl.stderr
    assert "public customer namespace requires public classification" in unsafe_acl.stderr
