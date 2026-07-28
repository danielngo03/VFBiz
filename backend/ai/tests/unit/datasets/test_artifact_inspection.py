import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.modules.datasets.infrastructure.scanners.artifact_inspection import inspect_artifact


def test_inspector_reads_all_parquet_rows_and_fails_closed_without_malware_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VFBIZ_AI_DATASET_CLAMAV_DATABASE", raising=False)
    artifact = tmp_path / "records.parquet"
    pq.write_table(pa.table({"text": ["xin chao", "hello"], "label": [1, 2]}), artifact)

    report = inspect_artifact(artifact, media_type="application/vnd.apache.parquet")

    assert report.record_count == 2
    assert report.malformed_records == 0
    assert len(report.schema_sha256) == 64
    if report.malware_status == "unavailable":
        assert not report.passed_for_candidate
        assert "production-malware-scan-required" in report.blockers


def test_inspector_detects_secret_across_binary_chunk_boundary(tmp_path: Path) -> None:
    artifact = tmp_path / "records.jsonl"
    opening = b'{"text":"'
    prefix = opening + (b"a" * (1024 * 1024 - len(opening) - 1)) + b" "
    synthetic_token = b"hf_" + b"abcdefghijklmnopqrstuvwxyz"
    artifact.write_bytes(prefix + synthetic_token + b'"}\n')

    report = inspect_artifact(artifact, media_type="application/x-ndjson")

    assert report.secret_findings["hugging-face-token"] == 1
    assert "secret-findings" in report.blockers


def test_inspector_streams_top_level_json_array(tmp_path: Path) -> None:
    artifact = tmp_path / "tools.json"
    artifact.write_text(
        json.dumps([{"query": "find vehicle"}, {"query": "list garage"}]),
        encoding="utf-8",
    )

    report = inspect_artifact(artifact, media_type="application/json")

    assert report.record_count == 2
    assert report.malformed_records == 0
