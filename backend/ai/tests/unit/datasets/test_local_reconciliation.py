from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.modules.datasets.domain import RegistryInvariantError
from app.modules.datasets.presentation.cli.local_reconciliation import (
    reconcile_local_downloads,
)


def test_reconciliation_is_content_addressed_and_never_promotes(
    tmp_path: Path,
) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    payload = b'{"record":"synthetic"}\n'
    source = downloads / "source.jsonl"
    source.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "evidence_id": "wave-a-test",
                "artifacts": [
                    {
                        "source_id": "synthetic-source",
                        "revision": "revision-1",
                        "selector": "default/train",
                        "sha256": digest,
                        "media_type": "application/x-ndjson",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = reconcile_local_downloads(
        evidence_path=evidence,
        downloads_root=downloads,
        object_store_root=tmp_path / "objects",
        observed_at="2026-07-28T06:30:00Z",
    )
    artifact = report["artifacts"][0]  # type: ignore[index]
    assert artifact["content_address"].endswith(f"{digest}.jsonl")  # type: ignore[index,union-attr]
    assert artifact["origin_binding"] == "pending-exact-fetch-plan"  # type: ignore[index]
    assert artifact["release_eligible"] is False  # type: ignore[index]
    assert "purpose approval" in report["promotion_blockers"]  # type: ignore[operator]


def test_reconciliation_reports_missing_sources_and_selector_drift(
    tmp_path: Path,
) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    payload = b'{"record":"synthetic"}\n'
    (downloads / "source.jsonl").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "evidence_id": "wave-a-test",
                "artifacts": [
                    {
                        "source_id": "source-a",
                        "revision": "revision-1",
                        "selector": "unexpected/train",
                        "sha256": digest,
                        "media_type": "application/x-ndjson",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "source-a",
                        "selectors": {"configs": ["default"], "splits": ["train"]},
                    },
                    {"source_id": "source-b", "selectors": {"files": ["test.json"]}},
                ]
            }
        ),
        encoding="utf-8",
    )
    report = reconcile_local_downloads(
        evidence_path=evidence,
        downloads_root=downloads,
        object_store_root=tmp_path / "objects",
        observed_at="2026-07-28T06:30:00Z",
        portfolio_path=portfolio,
    )
    reconciliation = report["portfolio_reconciliation"]  # type: ignore[assignment]
    assert reconciliation["pending_source_ids"] == ["source-b"]  # type: ignore[index]
    assert reconciliation["unplanned_artifacts"] == [  # type: ignore[index]
        "source-a:unexpected/train"
    ]


def test_reconciliation_rejects_evidence_without_exact_payload(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "evidence_id": "wave-a-test",
                "artifacts": [
                    {
                        "source_id": "synthetic-source",
                        "revision": "revision-1",
                        "selector": "default/train",
                        "sha256": "a" * 64,
                        "media_type": "application/x-ndjson",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RegistryInvariantError, match="exactly one local payload"):
        reconcile_local_downloads(
            evidence_path=evidence,
            downloads_root=downloads,
            object_store_root=tmp_path / "objects",
            observed_at="2026-07-28T06:30:00Z",
        )


def test_reconciliation_understands_file_objects_and_release_artifacts(
    tmp_path: Path,
) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    payload = b'{"record":"evaluation"}\n'
    (downloads / "test.jsonl").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "evidence_id": "evaluation-test",
                "source_scope": ["nested-release"],
                "artifacts": [
                    {
                        "source_id": "nested-release",
                        "revision": "v1",
                        "selector": "suite/test.jsonl",
                        "sha256": digest,
                        "media_type": "application/x-ndjson",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    portfolio = tmp_path / "portfolio.json"
    portfolio.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "nested-release",
                        "selectors": {"releases": [{"artifacts": [{"path": "suite/test.jsonl"}]}]},
                    },
                    {
                        "source_id": "file-object",
                        "selectors": {"files": [{"path": "public-test.jsonl"}]},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = reconcile_local_downloads(
        evidence_path=evidence,
        downloads_root=downloads,
        object_store_root=tmp_path / "objects",
        observed_at="2026-07-28T06:30:00Z",
        portfolio_path=portfolio,
    )

    reconciliation = report["portfolio_reconciliation"]  # type: ignore[assignment]
    assert reconciliation["unplanned_artifacts"] == []  # type: ignore[index]
    assert reconciliation["scope"] == "incremental"  # type: ignore[index]
    assert reconciliation["pending_source_ids"] == []  # type: ignore[index]
