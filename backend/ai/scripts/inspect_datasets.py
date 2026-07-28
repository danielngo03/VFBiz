from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.modules.datasets.presentation.workers import scan_local_downloads


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect downloaded ViVi dataset artifacts without promoting them."
    )
    parser.add_argument("--downloads", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    arguments = parser.parse_args()
    summary = scan_local_downloads(
        download_root=arguments.downloads,
        report_root=arguments.reports,
    )
    print(
        json.dumps(
            {
                "artifact_count": summary.artifact_count,
                "byte_size": summary.byte_size,
                "record_count": summary.record_count,
                "candidate_pass_count": summary.candidate_pass_count,
                "blocked_count": summary.blocked_count,
                "manifest_sha256": summary.manifest_sha256,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
