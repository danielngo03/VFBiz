from __future__ import annotations

import traceback
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

from scripts.prepare_cloud_sql_bootstrap_credential import (
    BootstrapCredentialError,
    BootstrapCredentialRequest,
    GoogleRestBootstrapGateway,
    ProviderOutcomeUnknown,
    prepare_bootstrap_credential,
)

PASSWORD = "A" * 64


def request(*, apply: bool = False) -> BootstrapCredentialRequest:
    return BootstrapCredentialRequest(
        project_id="vinfast-503003",
        project_number="81588547131",
        region="asia-southeast1",
        instance_name="vfbiz-ai-postgres-dev",
        database_name="vfbiz_ai",
        administrator_user="postgres",
        administrator_secret_id="vfbiz-ai-database-bootstrap-url-dev",  # noqa: S106
        evidence_bucket="vinfast-503003-evidence-dev",
        authority_digest="a" * 64,
        apply=apply,
    )


class FakeGateway:

    def __init__(self) -> None:
        self.instance: dict[str, Any] = {
            "name": "vfbiz-ai-postgres-dev",
            "project": "vinfast-503003",
            "region": "asia-southeast1",
            "state": "RUNNABLE",
            "databaseVersion": "POSTGRES_17",
            "settings": {
                "deletionProtectionEnabled": True,
                "ipConfiguration": {
                    "ipv4Enabled": False,
                    "sslMode": "ENCRYPTED_ONLY",
                },
            },
            "ipAddresses": [{"type": "PRIVATE", "ipAddress": "10.89.0.3"}],
        }
        self.secret: dict[str, Any] = {
            "name": (
                "projects/81588547131/secrets/"
                "vfbiz-ai-database-bootstrap-url-dev"
            ),
            "labels": {
                "environment": "development",
                "goog-terraform-provisioned": "true",
                "owner": "vfbiz-ai",
                "provenance": "managed-pipeline",
            },
            "replication": {
                "userManaged": {
                    "replicas": [{"location": "asia-southeast1"}]
                }
            },
        }
        self.database: dict[str, Any] = {
            "name": "vfbiz_ai",
            "project": "vinfast-503003",
            "instance": "vfbiz-ai-postgres-dev",
        }
        self.bucket: dict[str, Any] = {
            "name": "vinfast-503003-evidence-dev",
            "projectNumber": "81588547131",
            "location": "ASIA-SOUTHEAST1",
            "iamConfiguration": {
                "uniformBucketLevelAccess": {"enabled": True},
                "publicAccessPrevention": "enforced",
            },
            "retentionPolicy": {"retentionPeriod": "86400"},
            "versioning": {"enabled": True},
        }
        self.versions: dict[str, bytes] = {}
        self.passwords: list[str] = []
        self.operations: dict[str, dict[str, Any]] = {
            "operations/password-1": {"status": "DONE"}
        }
        self.witness: tuple[bytes, str] | None = None
        self.secret_outcomes: list[str] = []
        self.secret_add_calls = 0
        self.version_visibility_delays = 0
        self.password_outcomes: list[str] = []
        self.witness_outcomes: list[str] = []

    def describe_instance(self, _: BootstrapCredentialRequest) -> dict[str, Any]:
        return deepcopy(self.instance)

    def describe_database(self, _: BootstrapCredentialRequest) -> dict[str, Any]:
        return deepcopy(self.database)

    def describe_bucket(self, _: BootstrapCredentialRequest) -> dict[str, Any]:
        return deepcopy(self.bucket)

    def describe_secret(self, _: BootstrapCredentialRequest) -> dict[str, Any]:
        return deepcopy(self.secret)

    def list_secret_versions(self, _: BootstrapCredentialRequest) -> tuple[str, ...]:
        if self.version_visibility_delays > 0:
            self.version_visibility_delays -= 1
            return ()
        return tuple(self.versions)

    def set_administrator_password(
        self, _: BootstrapCredentialRequest, password: str
    ) -> str:
        self.passwords.append(password)
        outcome = self.password_outcomes.pop(0) if self.password_outcomes else "ok"
        if outcome == "unknown-with-operation":
            raise ProviderOutcomeUnknown("operations/password-1")
        if outcome == "unknown":
            raise ProviderOutcomeUnknown()
        return "operations/password-1"

    def get_operation(
        self, _: BootstrapCredentialRequest, operation_name: str
    ) -> dict[str, Any]:
        return self.operations[operation_name]

    def add_secret_version(
        self, _: BootstrapCredentialRequest, payload: bytes
    ) -> str:
        self.secret_add_calls += 1
        outcome = self.secret_outcomes.pop(0) if self.secret_outcomes else "ok"
        version = (
            "projects/81588547131/secrets/"
            "vfbiz-ai-database-bootstrap-url-dev/versions/1"
        )
        if outcome == "unknown-created":
            self.versions[version] = payload
            raise ProviderOutcomeUnknown()
        if outcome == "unknown-empty":
            raise ProviderOutcomeUnknown()
        self.versions[version] = payload
        return version

    def access_secret_version(
        self, _: BootstrapCredentialRequest, version_name: str
    ) -> bytes:
        return self.versions[version_name]

    def create_witness(
        self, _: BootstrapCredentialRequest, payload: bytes
    ) -> str:
        outcome = self.witness_outcomes.pop(0) if self.witness_outcomes else "ok"
        if outcome == "unknown-created":
            self.witness = (payload, "123")
            raise ProviderOutcomeUnknown()
        if outcome == "unknown-empty":
            raise ProviderOutcomeUnknown()
        if self.witness is not None:
            raise BootstrapCredentialError("witness already exists")
        self.witness = (payload, "123")
        return "123"

    def read_witness(
        self, _: BootstrapCredentialRequest
    ) -> tuple[bytes, str] | None:
        return self.witness


def run_apply(gateway: FakeGateway):
    return prepare_bootstrap_credential(
        request(apply=True),
        gateway,
        password_factory=lambda: PASSWORD,
        now=lambda: datetime(2026, 8, 2, 4, 0, tzinfo=UTC),
        sleep=lambda _: None,
    )


def test_dry_run_performs_no_mutation() -> None:
    gateway = FakeGateway()

    result = prepare_bootstrap_credential(request(), gateway)

    assert result.applied is False
    assert result.secret_version is None
    assert gateway.passwords == []
    assert gateway.versions == {}
    assert gateway.witness is None


def test_apply_keeps_password_and_database_url_out_of_result_and_witness() -> None:
    gateway = FakeGateway()

    result = run_apply(gateway)

    assert result.applied is True
    assert result.secret_version == "1"  # noqa: S105
    assert gateway.passwords == [PASSWORD]
    assert gateway.witness is not None
    witness_payload = gateway.witness[0]
    assert PASSWORD.encode() not in witness_payload
    assert b"postgresql://" not in witness_payload
    assert PASSWORD not in repr(result)
    assert gateway.versions
    assert PASSWORD.encode() in next(iter(gateway.versions.values()))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda gateway: gateway.instance["settings"]["ipConfiguration"].update(
                {"ipv4Enabled": True}
            ),
            "instance policy",
        ),
        (
            lambda gateway: gateway.instance.update({"region": "us-central1"}),
            "instance policy",
        ),
        (
            lambda gateway: gateway.secret["replication"]["userManaged"].update(
                {"replicas": [{"location": "us-central1"}]}
            ),
            "secret policy",
        ),
        (
            lambda gateway: gateway.secret["labels"].update(
                {"provenance": "manual"}
            ),
            "secret policy",
        ),
    ],
)
def test_preflight_rejects_identity_or_residency_drift(mutate, message: str) -> None:
    gateway = FakeGateway()
    mutate(gateway)

    with pytest.raises(BootstrapCredentialError, match=message):
        run_apply(gateway)

    assert gateway.passwords == []


def test_preflight_rejects_existing_secret_version() -> None:
    gateway = FakeGateway()
    gateway.versions[
        "projects/81588547131/secrets/"
        "vfbiz-ai-database-bootstrap-url-dev/versions/7"
    ] = b"existing"

    with pytest.raises(BootstrapCredentialError, match="not empty"):
        run_apply(gateway)

    assert gateway.passwords == []


def test_preflight_rejects_destroyed_secret_history() -> None:
    gateway = FakeGateway()
    gateway.versions[
        "projects/81588547131/secrets/"
        "vfbiz-ai-database-bootstrap-url-dev/versions/7"
    ] = b"destroyed-history"

    with pytest.raises(BootstrapCredentialError, match="not empty"):
        run_apply(gateway)

    assert gateway.passwords == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda gateway: gateway.database.update({"project": "other-project"}),
        lambda gateway: gateway.bucket.update({"location": "US"}),
        lambda gateway: gateway.bucket["iamConfiguration"].update(
            {"publicAccessPrevention": "inherited"}
        ),
        lambda gateway: gateway.instance["ipAddresses"].append(
            {"type": "PRIMARY", "ipAddress": "34.1.2.3"}
        ),
    ],
)
def test_preflight_rejects_database_bucket_or_public_ip_drift(mutate) -> None:
    gateway = FakeGateway()
    mutate(gateway)

    with pytest.raises(BootstrapCredentialError):
        run_apply(gateway)

    assert gateway.passwords == []


def test_password_unknown_with_operation_is_polled_without_retry() -> None:
    gateway = FakeGateway()
    gateway.password_outcomes = ["unknown-with-operation"]

    result = run_apply(gateway)

    assert result.operation_name == "operations/password-1"
    assert gateway.passwords == [PASSWORD]


def test_password_unknown_without_operation_retries_the_same_password_once() -> None:
    gateway = FakeGateway()
    gateway.password_outcomes = ["unknown", "ok"]

    run_apply(gateway)

    assert gateway.passwords == [PASSWORD, PASSWORD]


def test_secret_version_unknown_created_is_reconciled_without_retry() -> None:
    gateway = FakeGateway()
    gateway.secret_outcomes = ["unknown-created"]

    result = run_apply(gateway)

    assert result.secret_version == "1"  # noqa: S105
    assert gateway.passwords == [PASSWORD]
    assert len(gateway.versions) == 1
    assert gateway.secret_add_calls == 1


def test_secret_version_eventual_visibility_polls_without_retry() -> None:
    gateway = FakeGateway()
    gateway.secret_outcomes = ["unknown-created"]
    gateway.version_visibility_delays = 3

    result = run_apply(gateway)

    assert result.secret_version == "1"  # noqa: S105
    assert gateway.secret_add_calls == 1


def test_secret_version_unknown_empty_is_indeterminate_without_retry() -> None:
    gateway = FakeGateway()
    gateway.secret_outcomes = ["unknown-empty"]

    with pytest.raises(BootstrapCredentialError, match="do not rerun"):
        run_apply(gateway)

    assert gateway.secret_outcomes == []
    assert gateway.secret_add_calls == 1
    assert gateway.versions == {}


class StubResponse:

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.content = b""

    def json(self) -> dict[str, Any]:
        return {}


class StatusSession:

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def request(self, *_args, **_kwargs):
        return StubResponse(self.status_code)


@pytest.mark.parametrize("status", [408, 429, 500, 503])
@pytest.mark.parametrize("mutation", ["password", "secret", "witness"])
def test_mutation_http_ambiguity_is_not_treated_as_definite(
    status: int, mutation: str
) -> None:
    gateway = GoogleRestBootstrapGateway(StatusSession(status))  # type: ignore[arg-type]

    with pytest.raises(ProviderOutcomeUnknown):
        if mutation == "password":
            gateway.set_administrator_password(request(), PASSWORD)
        elif mutation == "secret":
            gateway.add_secret_version(request(), b"sensitive")
        else:
            gateway.create_witness(request(), b"content-free")


class RaisingSession:

    def request(self, *_args, **kwargs):
        raise RuntimeError(repr(kwargs))


def test_transport_error_chain_does_not_expose_secret_payload() -> None:
    gateway = GoogleRestBootstrapGateway(RaisingSession())  # type: ignore[arg-type]

    with pytest.raises(ProviderOutcomeUnknown) as captured:
        gateway.set_administrator_password(request(), PASSWORD)

    rendered = "".join(
        traceback.format_exception(
            type(captured.value), captured.value, captured.value.__traceback__
        )
    )
    assert PASSWORD not in rendered


@pytest.mark.parametrize("outcome", ["unknown-created", "unknown-empty"])
def test_witness_unknown_is_reconciled_create_only(outcome: str) -> None:
    gateway = FakeGateway()
    gateway.witness_outcomes = [outcome]

    result = run_apply(gateway)

    assert result.witness_generation == "123"
    assert gateway.witness is not None


def test_witness_conflict_is_fail_closed() -> None:
    gateway = FakeGateway()
    gateway.witness_outcomes = ["unknown-created"]

    original_create = gateway.create_witness

    def conflicting_create(
        request_value: BootstrapCredentialRequest, payload: bytes
    ) -> str:
        gateway.witness = (b"different", "123")
        raise ProviderOutcomeUnknown()

    gateway.create_witness = conflicting_create  # type: ignore[method-assign]
    with pytest.raises(BootstrapCredentialError, match="witness conflict"):
        run_apply(gateway)
    gateway.create_witness = original_create  # type: ignore[method-assign]


def test_short_password_is_rejected_before_provider_mutation() -> None:
    gateway = FakeGateway()

    with pytest.raises(BootstrapCredentialError, match="unsafe value"):
        prepare_bootstrap_credential(
            request(apply=True), gateway, password_factory=lambda: "short"
        )

    assert gateway.passwords == []
