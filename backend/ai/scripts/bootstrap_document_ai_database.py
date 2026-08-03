"""Bootstrap the private Document AI database from a one-shot Cloud Run Job.

The job upgrades the database to the exact repository head before provisioning
the two restricted workload identities. It never creates Secret Manager
containers and never prints database URLs or generated credentials.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from scripts.provision_document_ai_database_identities import (
    ProvisioningResult,
    provision_database_identities,
)

_ROOT = Path(__file__).resolve().parents[1]


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _upgrade_database(admin_url: str) -> None:
    configuration = Config(str(_ROOT / "alembic.ini"))
    previous_url = os.environ.get("VFBIZ_AI_DATABASE_URL")
    os.environ["VFBIZ_AI_DATABASE_URL"] = admin_url
    try:
        command.upgrade(configuration, "head")
    finally:
        if previous_url is None:
            os.environ.pop("VFBIZ_AI_DATABASE_URL", None)
        else:
            os.environ["VFBIZ_AI_DATABASE_URL"] = previous_url


def run_bootstrap() -> ProvisioningResult:
    if os.environ.get("VFBIZ_AI_DATABASE_BOOTSTRAP_APPLY") != "true":
        raise RuntimeError("database bootstrap apply witness is not enabled")
    project_id = _required_environment("VFBIZ_AI_GCP_PROJECT_ID")
    submitter_secret_id = _required_environment(
        "VFBIZ_AI_DATABASE_SUBMITTER_SECRET_ID"
    )
    reconciler_secret_id = _required_environment(
        "VFBIZ_AI_DATABASE_RECONCILER_SECRET_ID"
    )
    authority_digest = _required_environment(
        "VFBIZ_AI_DATABASE_BOOTSTRAP_AUTHORITY_DIGEST"
    )
    admin_url = _required_environment("VFBIZ_AI_DATABASE_URL")

    _upgrade_database(admin_url)
    return provision_database_identities(
        project_id=project_id,
        submitter_secret_id=submitter_secret_id,
        reconciler_secret_id=reconciler_secret_id,
        admin_url=admin_url,
        authority_digest=authority_digest,
        apply=True,
    )


def main() -> int:
    result = run_bootstrap()
    print(
        json.dumps(
            {
                "event": "document-ai-database-bootstrap-complete",
                "reconciler_secret_version": result.reconciler_secret_version,
                "submitter_secret_version": result.submitter_secret_version,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
