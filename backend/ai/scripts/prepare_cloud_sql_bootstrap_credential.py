"""Prepare the initial private Cloud SQL administrator credential safely.

The operator is dry-run by default.  In apply mode the randomly generated
password and database URL are sent only in authenticated HTTPS request bodies;
they are never written to argv, files, logs, receipts or return values.
"""

from __future__ import annotations

import argparse
import base64
import hmac
import json
import re
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from urllib.parse import quote

import google.auth
from google.auth.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession
from requests import Response

_PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_RESOURCE_ID = re.compile(r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$")
_DATABASE_ID = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_VERSION_NAME = re.compile(
    r"^projects/[0-9]+/secrets/[a-z][a-z0-9-]{0,254}/versions/([1-9][0-9]*)$"
)
_OPERATION_NAME = re.compile(r"^operations/[a-zA-Z0-9._~+/=-]{1,512}$")
_PRIVATE_IP_TYPES = frozenset({"PRIVATE"})
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class BootstrapCredentialError(RuntimeError):
    """Content-free operator failure."""


class ProviderOutcomeUnknown(BootstrapCredentialError):

    def __init__(self, operation_name: str | None = None) -> None:
        super().__init__("provider outcome is unknown")
        self.operation_name = operation_name


@dataclass(frozen=True, slots=True)
class BootstrapCredentialRequest:
    project_id: str
    project_number: str
    region: str
    instance_name: str
    database_name: str
    administrator_user: str
    administrator_secret_id: str
    evidence_bucket: str
    authority_digest: str
    apply: bool = False

    @property
    def witness_object(self) -> str:
        return (
            "database-bootstrap/admin-credential/v1/"
            f"{self.authority_digest}.json"
        )


@dataclass(frozen=True, slots=True)
class BootstrapCredentialResult:
    applied: bool
    operation_name: str | None
    secret_version: str | None
    witness_generation: str | None
    witness_object: str


class CloudBootstrapGateway(Protocol):

    def describe_instance(self, request: BootstrapCredentialRequest) -> Mapping[str, Any]: ...

    def describe_database(self, request: BootstrapCredentialRequest) -> Mapping[str, Any]: ...

    def describe_bucket(self, request: BootstrapCredentialRequest) -> Mapping[str, Any]: ...

    def describe_secret(self, request: BootstrapCredentialRequest) -> Mapping[str, Any]: ...

    def list_secret_versions(self, request: BootstrapCredentialRequest) -> tuple[str, ...]: ...

    def set_administrator_password(
        self, request: BootstrapCredentialRequest, password: str
    ) -> str: ...

    def get_operation(
        self, request: BootstrapCredentialRequest, operation_name: str
    ) -> Mapping[str, Any]: ...

    def add_secret_version(
        self, request: BootstrapCredentialRequest, payload: bytes
    ) -> str: ...

    def access_secret_version(
        self, request: BootstrapCredentialRequest, version_name: str
    ) -> bytes: ...

    def create_witness(
        self, request: BootstrapCredentialRequest, payload: bytes
    ) -> str: ...

    def read_witness(
        self, request: BootstrapCredentialRequest
    ) -> tuple[bytes, str] | None: ...


class HttpSession(Protocol):

    def request(self, method: str, url: str, **kwargs: Any) -> Response: ...


def prepare_bootstrap_credential(
    request: BootstrapCredentialRequest,
    gateway: CloudBootstrapGateway,
    *,
    password_factory: Callable[[], str] = lambda: secrets.token_urlsafe(48),
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
) -> BootstrapCredentialResult:
    """Validate the foundation and optionally create one initial credential."""

    _validate_request(request)
    private_ip = _validate_instance(request, gateway.describe_instance(request))
    _validate_database(request, gateway.describe_database(request))
    _validate_bucket(request, gateway.describe_bucket(request))
    _validate_secret(request, gateway.describe_secret(request))
    if gateway.list_secret_versions(request):
        raise BootstrapCredentialError("administrator secret is not empty")
    if gateway.read_witness(request) is not None:
        raise BootstrapCredentialError("administrator credential witness already exists")
    if not request.apply:
        return BootstrapCredentialResult(
            applied=False,
            operation_name=None,
            secret_version=None,
            witness_generation=None,
            witness_object=request.witness_object,
        )

    password = password_factory()
    _validate_password(password)
    database_url = _database_url(request, private_ip, password)
    operation_name = _set_password_and_wait(
        request, gateway, password, sleep=sleep
    )
    secret_version = _create_and_verify_secret_version(
        request, gateway, database_url.encode("utf-8"), sleep=sleep
    )
    receipt = _canonical_json(
        {
            "administrator_secret_version": _numeric_version(secret_version),
            "authority_digest": request.authority_digest,
            "cloud_sql_operation": operation_name,
            "database_name": request.database_name,
            "instance_name": request.instance_name,
            "project_id": request.project_id,
            "region": request.region,
            "schema_version": 1,
            "witnessed_at": _canonical_timestamp(now()),
        }
    )
    witness_generation = _create_or_reconcile_witness(request, gateway, receipt)
    return BootstrapCredentialResult(
        applied=True,
        operation_name=operation_name,
        secret_version=_numeric_version(secret_version),
        witness_generation=witness_generation,
        witness_object=request.witness_object,
    )


def _validate_request(request: BootstrapCredentialRequest) -> None:
    if not _PROJECT_ID.fullmatch(request.project_id):
        raise BootstrapCredentialError("invalid project identity")
    if not request.project_number.isdigit() or int(request.project_number) < 1:
        raise BootstrapCredentialError("invalid project number")
    for value in (
        request.region,
        request.instance_name,
        request.administrator_secret_id,
    ):
        if not _RESOURCE_ID.fullmatch(value):
            raise BootstrapCredentialError("invalid resource identity")
    if not _DATABASE_ID.fullmatch(request.database_name):
        raise BootstrapCredentialError("invalid database identity")
    if request.administrator_user != "postgres":
        raise BootstrapCredentialError("unexpected administrator identity")
    if not _SHA256.fullmatch(request.authority_digest):
        raise BootstrapCredentialError("invalid authority digest")
    expected_bucket = f"{request.project_id}-evidence-dev"
    if request.evidence_bucket != expected_bucket:
        raise BootstrapCredentialError("unexpected evidence bucket")


def _validate_instance(
    request: BootstrapCredentialRequest, document: Mapping[str, Any]
) -> str:
    settings = _mapping(document.get("settings"), "instance settings")
    ip_configuration = _mapping(
        settings.get("ipConfiguration"), "instance IP configuration"
    )
    if (
        document.get("name") != request.instance_name
        or document.get("project") != request.project_id
        or document.get("region") != request.region
        or document.get("state") != "RUNNABLE"
        or document.get("databaseVersion") != "POSTGRES_17"
        or ip_configuration.get("ipv4Enabled") is not False
        or ip_configuration.get("sslMode") != "ENCRYPTED_ONLY"
        or settings.get("deletionProtectionEnabled") is not True
    ):
        raise BootstrapCredentialError("Cloud SQL instance policy mismatch")
    addresses = document.get("ipAddresses")
    if not isinstance(addresses, list):
        raise BootstrapCredentialError("Cloud SQL private address is missing")
    private_addresses: list[str] = []
    address_items = cast(list[object], addresses)
    for entry in _mapping_items(address_items, "instance addresses"):
        address = entry.get("ipAddress")
        if entry.get("type") not in _PRIVATE_IP_TYPES:
            raise BootstrapCredentialError("Cloud SQL public address is forbidden")
        if isinstance(address, str):
            private_addresses.append(address)
    if len(private_addresses) != 1 or not _is_private_ipv4(private_addresses[0]):
        raise BootstrapCredentialError("Cloud SQL private address is invalid")
    return private_addresses[0]


def _validate_database(
    request: BootstrapCredentialRequest, document: Mapping[str, Any]
) -> None:
    if (
        document.get("name") != request.database_name
        or document.get("project") != request.project_id
        or document.get("instance") != request.instance_name
    ):
        raise BootstrapCredentialError("Cloud SQL database identity mismatch")


def _validate_bucket(
    request: BootstrapCredentialRequest, document: Mapping[str, Any]
) -> None:
    iam = _mapping(document.get("iamConfiguration"), "bucket IAM configuration")
    uniform = _mapping(iam.get("uniformBucketLevelAccess"), "bucket uniform access")
    retention = _mapping(document.get("retentionPolicy"), "bucket retention policy")
    versioning = _mapping(document.get("versioning"), "bucket versioning")
    if (
        document.get("name") != request.evidence_bucket
        or str(document.get("projectNumber")) != request.project_number
        or document.get("location") != "ASIA-SOUTHEAST1"
        or request.region != "asia-southeast1"
        or uniform.get("enabled") is not True
        or iam.get("publicAccessPrevention") != "enforced"
        or retention.get("retentionPeriod") != "86400"
        or versioning.get("enabled") is not True
    ):
        raise BootstrapCredentialError("evidence bucket policy mismatch")


def _validate_secret(
    request: BootstrapCredentialRequest, document: Mapping[str, Any]
) -> None:
    expected_name = (
        f"projects/{request.project_number}/secrets/"
        f"{request.administrator_secret_id}"
    )
    replication = _mapping(document.get("replication"), "secret replication")
    labels = _mapping(document.get("labels"), "secret labels")
    user_managed = _mapping(replication.get("userManaged"), "secret replication")
    replicas = _mapping_items(user_managed.get("replicas"), "secret replicas")
    locations = {
        location
        for replica in replicas
        if isinstance((location := replica.get("location")), str)
    }
    if (
        document.get("name") != expected_name
        or set(replication) != {"userManaged"}
        or locations != {request.region}
        or len(replicas) != 1
        or labels
        != {
            "environment": "development",
            "goog-terraform-provisioned": "true",
            "owner": "vfbiz-ai",
            "provenance": "managed-pipeline",
        }
    ):
        raise BootstrapCredentialError("administrator secret policy mismatch")


def _set_password_and_wait(
    request: BootstrapCredentialRequest,
    gateway: CloudBootstrapGateway,
    password: str,
    *,
    sleep: Callable[[float], None],
) -> str:
    operation_name: str | None = None
    for attempt in range(2):
        try:
            operation_name = gateway.set_administrator_password(request, password)
            break
        except ProviderOutcomeUnknown as error:
            if error.operation_name is not None:
                operation_name = error.operation_name
                break
            if attempt == 1:
                raise BootstrapCredentialError(
                    "Cloud SQL password outcome could not be reconciled"
                ) from None
    if operation_name is None or not _OPERATION_NAME.fullmatch(operation_name):
        raise BootstrapCredentialError("invalid Cloud SQL operation identity")
    for attempt in range(60):
        operation = gateway.get_operation(request, operation_name)
        if operation.get("error") is not None:
            raise BootstrapCredentialError("Cloud SQL password operation failed")
        if operation.get("status") == "DONE":
            return operation_name
        if attempt < 59:
            sleep(2.0)
    raise BootstrapCredentialError("Cloud SQL password operation timed out")


def _create_and_verify_secret_version(
    request: BootstrapCredentialRequest,
    gateway: CloudBootstrapGateway,
    payload: bytes,
    *,
    sleep: Callable[[float], None],
) -> str:
    version_name: str | None = None
    try:
        version_name = gateway.add_secret_version(request, payload)
    except ProviderOutcomeUnknown:
        for attempt in range(10):
            observed = gateway.list_secret_versions(request)
            if len(observed) == 1:
                version_name = observed[0]
                break
            if len(observed) > 1:
                raise BootstrapCredentialError(
                    "ambiguous administrator secret versions"
                ) from None
            if attempt < 9:
                sleep(1.0)
        if version_name is None:
            raise BootstrapCredentialError(
                "administrator secret creation is indeterminate; do not rerun"
            ) from None
    observed_payload = gateway.access_secret_version(request, version_name)
    if not hmac.compare_digest(payload, observed_payload):
        raise BootstrapCredentialError("administrator secret read-back mismatch")
    _numeric_version(version_name)
    return version_name


def _create_or_reconcile_witness(
    request: BootstrapCredentialRequest,
    gateway: CloudBootstrapGateway,
    payload: bytes,
) -> str:
    try:
        return _positive_generation(gateway.create_witness(request, payload))
    except ProviderOutcomeUnknown:
        observed = gateway.read_witness(request)
        if observed is None:
            return _positive_generation(gateway.create_witness(request, payload))
        observed_payload, generation = observed
        if not hmac.compare_digest(payload, observed_payload):
            raise BootstrapCredentialError("administrator witness conflict") from None
        return _positive_generation(generation)


def _database_url(
    request: BootstrapCredentialRequest, private_ip: str, password: str
) -> str:
    credentials = f"{quote(request.administrator_user, safe='')}:{quote(password, safe='')}"
    database_name = quote(request.database_name, safe="")
    return (
        f"postgresql://{credentials}@{private_ip}:5432/{database_name}"
        "?sslmode=require"
    )


def _validate_password(password: str) -> None:
    if len(password) < 48 or len(password) > 128 or any(ord(char) < 33 for char in password):
        raise BootstrapCredentialError("password factory returned an unsafe value")


def _numeric_version(version_name: str) -> str:
    match = _VERSION_NAME.fullmatch(version_name)
    if match is None:
        raise BootstrapCredentialError("invalid administrator secret version")
    return match.group(1)


def _positive_generation(value: str) -> str:
    if not value.isdigit() or int(value) < 1:
        raise BootstrapCredentialError("invalid witness generation")
    return value


def _canonical_json(document: Mapping[str, Any]) -> bytes:
    return json.dumps(
        document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _canonical_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise BootstrapCredentialError("trusted time must be timezone-aware")
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BootstrapCredentialError(f"{label} is missing")
    return cast(Mapping[str, Any], value)


def _mapping_items(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise BootstrapCredentialError(f"{label} are missing")
    items: list[Mapping[str, Any]] = []
    for item in cast(list[object], value):
        if not isinstance(item, Mapping):
            raise BootstrapCredentialError(f"{label} are malformed")
        items.append(cast(Mapping[str, Any], item))
    return tuple(items)


def _is_private_ipv4(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split(".")
    if len(parts) != 4 or not all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
        return False
    first, second = int(parts[0]), int(parts[1])
    return first == 10 or (first == 172 and 16 <= second <= 31) or (first == 192 and second == 168)


class GoogleRestBootstrapGateway:
    """Minimal ADC-backed REST adapter with content-free errors."""

    def __init__(self, session: HttpSession) -> None:
        self._session = session

    @classmethod
    def from_adc(cls) -> GoogleRestBootstrapGateway:
        credentials_value, _ = google.auth.default(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            scopes=[_CLOUD_PLATFORM_SCOPE]
        )
        credentials = cast(Credentials, credentials_value)
        return cls(cast(HttpSession, AuthorizedSession(credentials)))

    def describe_instance(self, request: BootstrapCredentialRequest) -> Mapping[str, Any]:
        return self._json(
            "GET",
            f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{request.project_id}/instances/{request.instance_name}",
        )

    def describe_database(self, request: BootstrapCredentialRequest) -> Mapping[str, Any]:
        return self._json(
            "GET",
            f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{request.project_id}/instances/{request.instance_name}/databases/{request.database_name}",
        )

    def describe_bucket(self, request: BootstrapCredentialRequest) -> Mapping[str, Any]:
        return self._json(
            "GET",
            f"https://storage.googleapis.com/storage/v1/b/{request.evidence_bucket}",
        )

    def describe_secret(self, request: BootstrapCredentialRequest) -> Mapping[str, Any]:
        return self._json(
            "GET",
            f"https://secretmanager.googleapis.com/v1/projects/{request.project_id}/secrets/{request.administrator_secret_id}",
        )

    def list_secret_versions(self, request: BootstrapCredentialRequest) -> tuple[str, ...]:
        document = self._json(
            "GET",
            f"https://secretmanager.googleapis.com/v1/projects/{request.project_id}/secrets/{request.administrator_secret_id}/versions",
            params={"pageSize": "100"},
        )
        if document.get("nextPageToken"):
            raise BootstrapCredentialError("administrator secret history is unbounded")
        versions = _mapping_items(
            document.get("versions", []), "administrator secret versions"
        )
        history: list[str] = []
        for version in versions:
            name = version.get("name")
            if not isinstance(name, str) or _VERSION_NAME.fullmatch(name) is None:
                raise BootstrapCredentialError("administrator secret history is malformed")
            history.append(name)
        return tuple(history)

    def set_administrator_password(
        self, request: BootstrapCredentialRequest, password: str
    ) -> str:
        document = self._json(
            "PUT",
            f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{request.project_id}/instances/{request.instance_name}/users",
            params={"name": request.administrator_user},
            json_body={"password": password},
            mutation=True,
        )
        name = document.get("name")
        if not isinstance(name, str):
            raise ProviderOutcomeUnknown()
        return name

    def get_operation(
        self, request: BootstrapCredentialRequest, operation_name: str
    ) -> Mapping[str, Any]:
        return self._json(
            "GET",
            f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{request.project_id}/{operation_name}",
        )

    def add_secret_version(
        self, request: BootstrapCredentialRequest, payload: bytes
    ) -> str:
        document = self._json(
            "POST",
            f"https://secretmanager.googleapis.com/v1/projects/{request.project_id}/secrets/{request.administrator_secret_id}:addVersion",
            json_body={"payload": {"data": base64.b64encode(payload).decode("ascii")}},
            mutation=True,
        )
        name = document.get("name")
        if not isinstance(name, str):
            raise ProviderOutcomeUnknown()
        return name

    def access_secret_version(
        self, request: BootstrapCredentialRequest, version_name: str
    ) -> bytes:
        document = self._json(
            "GET", f"https://secretmanager.googleapis.com/v1/{version_name}:access"
        )
        payload = _mapping(document.get("payload"), "secret payload").get("data")
        if not isinstance(payload, str):
            raise BootstrapCredentialError("administrator secret payload is missing")
        try:
            return base64.b64decode(payload, validate=True)
        except ValueError as error:
            raise BootstrapCredentialError("administrator secret payload is malformed") from error

    def create_witness(
        self, request: BootstrapCredentialRequest, payload: bytes
    ) -> str:
        document = self._json(
            "POST",
            f"https://storage.googleapis.com/upload/storage/v1/b/{request.evidence_bucket}/o",
            params={
                "ifGenerationMatch": "0",
                "name": request.witness_object,
                "uploadType": "media",
            },
            data=payload,
            headers={"Content-Type": "application/json"},
            mutation=True,
        )
        generation = document.get("generation")
        if not isinstance(generation, str):
            raise ProviderOutcomeUnknown()
        return generation

    def read_witness(
        self, request: BootstrapCredentialRequest
    ) -> tuple[bytes, str] | None:
        object_name = quote(request.witness_object, safe="")
        metadata_response = self._session.request(
            "GET",
            f"https://storage.googleapis.com/storage/v1/b/{request.evidence_bucket}/o/{object_name}",
            timeout=30,
        )
        if metadata_response.status_code == 404:
            return None
        metadata = self._decode(metadata_response, "witness metadata")
        generation = metadata.get("generation")
        if not isinstance(generation, str):
            raise BootstrapCredentialError("witness generation is missing")
        payload_response = self._session.request(
            "GET",
            f"https://storage.googleapis.com/download/storage/v1/b/{request.evidence_bucket}/o/{object_name}",
            params={"alt": "media", "generation": generation},
            timeout=30,
        )
        self._check(payload_response, "witness read")
        return payload_response.content, generation

    def _json(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        mutation: bool = False,
    ) -> Mapping[str, Any]:
        try:
            response = self._session.request(
                method,
                url,
                params=params,
                json=json_body,
                data=data,
                headers=headers,
                timeout=30,
            )
        except Exception:
            raise ProviderOutcomeUnknown() from None
        if mutation and (
            response.status_code in {408, 409, 412, 425, 429}
            or response.status_code >= 500
        ):
            raise ProviderOutcomeUnknown() from None
        try:
            return self._decode(response, "provider request")
        except BootstrapCredentialError:
            if mutation and 200 <= response.status_code < 300:
                raise ProviderOutcomeUnknown() from None
            raise

    def _decode(self, response: Response, operation: str) -> Mapping[str, Any]:
        self._check(response, operation)
        try:
            document: object = response.json()
        except ValueError as error:
            raise BootstrapCredentialError(f"{operation} returned malformed JSON") from error
        if not isinstance(document, Mapping):
            raise BootstrapCredentialError(f"{operation} returned invalid JSON")
        return cast(Mapping[str, Any], document)

    @staticmethod
    def _check(response: Response, operation: str) -> None:
        if not 200 <= response.status_code < 300:
            raise BootstrapCredentialError(
                f"{operation} failed with status {response.status_code}"
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-number", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--administrator-user", default="postgres")
    parser.add_argument("--administrator-secret-id", required=True)
    parser.add_argument("--evidence-bucket", required=True)
    parser.add_argument("--authority-digest", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = _parse_args()
    request = BootstrapCredentialRequest(
        project_id=arguments.project_id,
        project_number=arguments.project_number,
        region=arguments.region,
        instance_name=arguments.instance,
        database_name=arguments.database,
        administrator_user=arguments.administrator_user,
        administrator_secret_id=arguments.administrator_secret_id,
        evidence_bucket=arguments.evidence_bucket,
        authority_digest=arguments.authority_digest,
        apply=arguments.apply,
    )
    result = prepare_bootstrap_credential(
        request, GoogleRestBootstrapGateway.from_adc()
    )
    print(
        json.dumps(
            {
                "applied": result.applied,
                "cloud_sql_operation": result.operation_name,
                "event": "cloud-sql-bootstrap-credential-prepared",
                "secret_version": result.secret_version,
                "witness_generation": result.witness_generation,
                "witness_object": result.witness_object,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
