from unittest.mock import Mock, call

import pytest

from scripts import provision_document_ai_database_identities as provisioning
from scripts.provision_document_ai_database_identities import (
    _database_url_for_login,  # pyright: ignore[reportPrivateUsage]
    _publish_secret_version,  # pyright: ignore[reportPrivateUsage]
)


def test_database_url_replaces_admin_credentials_without_leaking_them() -> None:
    result = _database_url_for_login(
        "postgresql+asyncpg://admin:old-secret@db.internal:5432/vfbiz?sslmode=require",
        "restricted role",
        "new:/?# secret",
    )

    assert result == (
        "postgresql://restricted%20role:new%3A%2F%3F%23%20secret@"
        "db.internal:5432/vfbiz?sslmode=require"
    )
    assert "admin" not in result
    assert "old-secret" not in result


def test_database_url_requires_explicit_host_and_database() -> None:
    with pytest.raises(ValueError, match="host and database"):
        _database_url_for_login("postgresql:///vfbiz", "role", "password")


def test_secret_version_publish_uses_existing_container_and_bytes_payload() -> None:
    client = Mock()
    client.add_secret_version.return_value.name = "projects/p/secrets/s/versions/7"
    resource_identifier = "s"

    version = _publish_secret_version(
        client,
        project_id="p",
        secret_id=resource_identifier,
        payload="postgresql://restricted:secret@db/vfbiz",
    )

    assert version == "projects/p/secrets/s/versions/7"
    client.get_secret.assert_called_once_with(request={"name": "projects/p/secrets/s"})
    request = client.add_secret_version.call_args.kwargs["request"]
    assert request["parent"] == "projects/p/secrets/s"
    assert isinstance(request["payload"]["data"], bytes)


def test_provisioning_dry_run_only_checks_existing_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Mock()
    transaction = Mock()
    transaction.__enter__ = Mock(return_value=transaction)
    transaction.__exit__ = Mock(return_value=False)
    connection.transaction.return_value = transaction
    context = Mock()
    context.__enter__ = Mock(return_value=connection)
    context.__exit__ = Mock(return_value=False)
    connect = Mock(return_value=context)
    preflight = Mock()
    client = Mock()
    monkeypatch.setattr(provisioning.psycopg, "connect", connect)
    monkeypatch.setattr(provisioning, "_preflight_database", preflight)
    monkeypatch.setattr(
        provisioning.secretmanager,
        "SecretManagerServiceClient",
        client,
    )
    submitter_resource = "submitter"
    reconciler_resource = "reconciler"

    result = provisioning.provision_database_identities(
        project_id="p",
        submitter_secret_id=submitter_resource,
        reconciler_secret_id=reconciler_resource,
        admin_url="postgresql://admin:private@db/vfbiz",
        authority_digest="a" * 64,
        apply=False,
    )

    assert result == provisioning.ProvisioningResult(applied=False)
    preflight.assert_called_once_with(connection)
    client.assert_not_called()


def test_provisioning_disables_partial_secret_versions_on_rotation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Mock()
    transaction = Mock()
    transaction.__enter__ = Mock(return_value=transaction)
    transaction.__exit__ = Mock(return_value=False)
    connection.transaction.return_value = transaction
    context = Mock()
    context.__enter__ = Mock(return_value=connection)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(
        provisioning.psycopg,
        "connect",
        Mock(return_value=context),
    )
    monkeypatch.setattr(provisioning, "_preflight_database", Mock())
    monkeypatch.setattr(provisioning, "_new_password", Mock(return_value="generated"))
    client = Mock()
    monkeypatch.setattr(
        provisioning.secretmanager,
        "SecretManagerServiceClient",
        Mock(return_value=client),
    )
    monkeypatch.setattr(
        provisioning,
        "_publish_secret_version",
        Mock(
            side_effect=[
                "projects/p/secrets/submitter/versions/7",
                "projects/p/secrets/reconciler/versions/9",
            ]
        ),
    )
    monkeypatch.setattr(
        provisioning,
        "_rotate_roles",
        Mock(side_effect=RuntimeError("rotation failed")),
    )
    monkeypatch.setattr(provisioning, "_reserve_bootstrap", Mock())
    monkeypatch.setattr(
        provisioning,
        "_reconcile_bootstrap_commit",
        Mock(return_value="reserved"),
    )
    fail_bootstrap = Mock()
    monkeypatch.setattr(provisioning, "_fail_bootstrap", fail_bootstrap)
    disable = Mock(side_effect=[RuntimeError("disable unavailable"), None])
    monkeypatch.setattr(provisioning, "_disable_secret_version", disable)
    submitter_resource = "submitter"
    reconciler_resource = "reconciler"

    with pytest.raises(RuntimeError, match="rotation failed"):
        provisioning.provision_database_identities(
            project_id="p",
            submitter_secret_id=submitter_resource,
            reconciler_secret_id=reconciler_resource,
            admin_url="postgresql://admin:private@db/vfbiz",
            authority_digest="a" * 64,
            apply=True,
        )

    assert disable.call_args_list == [
        call(client, "projects/p/secrets/submitter/versions/7"),
        call(client, "projects/p/secrets/reconciler/versions/9"),
    ]
    assert fail_bootstrap.call_count == 1
    assert fail_bootstrap.call_args.kwargs["cleanup_incomplete"] is True


@pytest.mark.parametrize("commit_state", ["completed", "indeterminate"])
def test_ambiguous_commit_is_reconciled_before_secret_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    commit_state: str,
) -> None:
    connection = Mock()
    outer_context = Mock()
    outer_context.__enter__ = Mock(return_value=connection)
    outer_context.__exit__ = Mock(return_value=False)
    transaction = Mock()
    transaction.__enter__ = Mock(return_value=transaction)
    transaction.__exit__ = Mock(side_effect=RuntimeError("commit unavailable"))
    connection.transaction.return_value = transaction
    monkeypatch.setattr(
        provisioning.psycopg,
        "connect",
        Mock(return_value=outer_context),
    )
    monkeypatch.setattr(provisioning, "_preflight_database", Mock())
    monkeypatch.setattr(provisioning, "_reserve_bootstrap", Mock())
    monkeypatch.setattr(provisioning, "_new_password", Mock(return_value="generated"))
    client = Mock()
    monkeypatch.setattr(
        provisioning.secretmanager,
        "SecretManagerServiceClient",
        Mock(return_value=client),
    )
    monkeypatch.setattr(
        provisioning,
        "_publish_secret_version",
        Mock(
            side_effect=[
                "projects/p/secrets/submitter/versions/7",
                "projects/p/secrets/reconciler/versions/9",
            ]
        ),
    )
    monkeypatch.setattr(provisioning, "_rotate_roles", Mock())
    monkeypatch.setattr(provisioning, "_complete_bootstrap", Mock())
    monkeypatch.setattr(
        provisioning,
        "_reconcile_bootstrap_commit",
        Mock(return_value=commit_state),
    )
    disable = Mock()
    monkeypatch.setattr(provisioning, "_disable_secret_version", disable)
    fail_bootstrap = Mock()
    monkeypatch.setattr(provisioning, "_fail_bootstrap", fail_bootstrap)
    submitter_resource = "submitter"
    reconciler_resource = "reconciler"

    if commit_state == "completed":
        result = provisioning.provision_database_identities(
            project_id="p",
            submitter_secret_id=submitter_resource,
            reconciler_secret_id=reconciler_resource,
            admin_url="postgresql://admin:private@db/vfbiz",
            authority_digest="a" * 64,
            apply=True,
        )
        assert result.submitter_secret_version == str(7)
    else:
        with pytest.raises(RuntimeError, match="outcome is indeterminate"):
            provisioning.provision_database_identities(
                project_id="p",
                submitter_secret_id=submitter_resource,
                reconciler_secret_id=reconciler_resource,
                admin_url="postgresql://admin:private@db/vfbiz",
                authority_digest="a" * 64,
                apply=True,
            )

    disable.assert_not_called()
    fail_bootstrap.assert_not_called()
