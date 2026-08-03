from __future__ import annotations

import json

import pytest
from alembic.config import Config

from scripts import bootstrap_document_ai_database as bootstrap
from scripts.provision_document_ai_database_identities import ProvisioningResult


def test_bootstrap_requires_explicit_apply_witness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VFBIZ_AI_DATABASE_BOOTSTRAP_APPLY", raising=False)

    with pytest.raises(RuntimeError, match="apply witness"):
        bootstrap.run_bootstrap()


def test_bootstrap_migrates_before_provisioning_without_exposing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upgraded_urls: list[str] = []
    provision_calls: list[dict[str, object]] = []
    admin_url = "postgresql://admin:private@10.0.0.3/vfbiz_ai"
    monkeypatch.setenv("VFBIZ_AI_DATABASE_BOOTSTRAP_APPLY", "true")
    monkeypatch.setenv("VFBIZ_AI_GCP_PROJECT_ID", "vinfast-test")
    monkeypatch.setenv("VFBIZ_AI_DATABASE_SUBMITTER_SECRET_ID", "submitter")
    monkeypatch.setenv("VFBIZ_AI_DATABASE_RECONCILER_SECRET_ID", "reconciler")
    monkeypatch.setenv("VFBIZ_AI_DATABASE_BOOTSTRAP_AUTHORITY_DIGEST", "a" * 64)
    monkeypatch.setenv("VFBIZ_AI_DATABASE_URL", admin_url)
    def upgrade(observed_url: str) -> None:
        upgraded_urls.append(observed_url)

    monkeypatch.setattr(bootstrap, "_upgrade_database", upgrade)

    def provision(**kwargs: object) -> ProvisioningResult:
        provision_calls.append(kwargs)
        return ProvisioningResult(
            applied=True,
            submitter_secret_version=str(7),
            reconciler_secret_version=str(9),
        )

    monkeypatch.setattr(bootstrap, "provision_database_identities", provision)

    result = bootstrap.run_bootstrap()

    assert result.submitter_secret_version == str(7)
    assert upgraded_urls == [admin_url]
    assert provision_calls == [{
        "project_id": "vinfast-test",
        "submitter_secret_id": "submitter",
        "reconciler_secret_id": "reconciler",
        "admin_url": admin_url,
        "authority_digest": "a" * 64,
        "apply": True,
    }]


def test_upgrade_database_restores_preexisting_runtime_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []
    monkeypatch.setenv("VFBIZ_AI_DATABASE_URL", "postgresql://previous/db")
    def upgrade(_configuration: Config, _revision: str) -> None:
        observed.append(bootstrap.os.environ["VFBIZ_AI_DATABASE_URL"])

    monkeypatch.setattr(bootstrap.command, "upgrade", upgrade)

    bootstrap._upgrade_database(  # pyright: ignore[reportPrivateUsage]
        "postgresql://bootstrap/db"
    )

    assert observed == ["postgresql://bootstrap/db"]
    assert bootstrap.os.environ["VFBIZ_AI_DATABASE_URL"] == "postgresql://previous/db"


def test_main_emits_content_free_numeric_version_receipt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        bootstrap,
        "run_bootstrap",
        lambda: ProvisioningResult(
            applied=True,
            submitter_secret_version=str(11),
            reconciler_secret_version=str(12),
        ),
    )

    assert bootstrap.main() == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == {
        "event": "document-ai-database-bootstrap-complete",
        "reconciler_secret_version": "12",
        "submitter_secret_version": "11",
    }
