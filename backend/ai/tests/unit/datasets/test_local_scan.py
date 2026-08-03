import json
from pathlib import Path

from app.modules.datasets.presentation.workers.local_scan import scan_local_downloads


def test_local_scan_writes_content_bound_manifest(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "records.jsonl").write_text(
        '{"prompt":"xin chao","response":"chao ban"}\n', encoding="utf-8"
    )

    summary = scan_local_downloads(
        download_root=downloads,
        report_root=tmp_path / "reports",
    )

    manifest = json.loads((tmp_path / "reports/inspection-manifest.json").read_text())
    assert summary.artifact_count == 1
    assert manifest["manifest_sha256"] == summary.manifest_sha256
    assert manifest["download_root"] == "local-downloads"
    assert str(tmp_path) not in json.dumps(manifest)
    assert len(manifest["artifacts"][0]["artifact_sha256"]) == 64
    assert manifest["artifacts"][0]["report_sha256"]


def test_local_scan_ignores_hugging_face_transport_metadata(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "records.jsonl").write_text('{"text":"xin chao"}\n', encoding="utf-8")
    cache = downloads / ".cache" / "huggingface"
    cache.mkdir(parents=True)
    (cache / ".gitignore").write_text("*\n", encoding="utf-8")

    summary = scan_local_downloads(
        download_root=downloads,
        report_root=tmp_path / "reports",
    )

    assert summary.artifact_count == 1
    assert summary.record_count == 1


def test_local_scan_ignores_nested_hugging_face_transport_metadata(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    nested = downloads / "dataset" / "revision" / ".cache" / "huggingface"
    nested.mkdir(parents=True)
    (nested / ".gitignore").write_text("*\n", encoding="utf-8")
    artifact = downloads / "dataset" / "revision" / "records.jsonl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"text":"safe fixture"}\n', encoding="utf-8")

    summary = scan_local_downloads(download_root=downloads, report_root=tmp_path / "reports")

    assert summary.artifact_count == 1
    assert summary.record_count == 1
