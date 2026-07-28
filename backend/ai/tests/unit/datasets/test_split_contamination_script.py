from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_script_rejects_near_duplicate_and_durable_lineage_overlap(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[5]
    script = (
        root
        / "backend/ai/.agents/skills/generate-synthetic-dataset/scripts"
        / "check_split_contamination.py"
    )
    held_out = tmp_path / "held-out.jsonl"
    held_out.write_text(
        json.dumps(
            {
                "case_id": "golden-1",
                "turns": [
                    {
                        "role": "user",
                        "content": "Chính sách bảo hành pin áp dụng từ tháng tám.",
                    }
                ],
                "lineage": {
                    "source_record_id": "source-record-1",
                    "source_content_sha256": "a" * 64,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    candidate = tmp_path / "candidate.jsonl"
    candidate.write_text(
        json.dumps(
            {
                "example_id": "candidate-1",
                "turns": [
                    {
                        "role": "user",
                        "content": "Chính sách bảo hành pin áp dụng từ tháng chín.",
                    }
                ],
                "lineage": {"source_record_id": "different-record"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(script),
            "--candidate",
            str(candidate),
            "--held-out",
            str(held_out),
            "--near-duplicate-threshold",
            "0.60",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "near-duplicate:candidate-1" in result.stdout

    candidate.write_text(
        json.dumps(
            {
                "example_id": "candidate-2",
                "lineage": {"source_content_sha256": "a" * 64},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lineage_result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(script),
            "--candidate",
            str(candidate),
            "--held-out",
            str(held_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert lineage_result.returncode == 1
    assert f"source_content_sha256:{'a' * 64}" in lineage_result.stdout
