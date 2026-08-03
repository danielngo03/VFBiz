"""Provision two restricted Document AI database identities and secret versions.

The command is preflight-only unless ``--apply`` is supplied.  Database URLs
are read from an environment variable and secret payloads are never printed.
Terraform owns secret containers and IAM; this operator command owns only the
login-role password rotation and new immutable Secret Manager versions.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import UUID, uuid4

import psycopg
from google.cloud import secretmanager
from psycopg import sql

EXPECTED_ALEMBIC_HEAD = "20260802_0025"
BOOTSTRAP_EPOCH = "document-ai-database-identities-v1"
SUBMITTER_GROUP = "vfbiz_ai_document_submitter"
RECONCILER_GROUP = "vfbiz_ai_document_reconciler"
SUBMITTER_LOGIN = "vfbiz_ai_document_submitter_login"
RECONCILER_LOGIN = "vfbiz_ai_document_reconciler_login"
EXPECTED_TABLE_ACL = {
    (SUBMITTER_GROUP, "public", "ai_document_submission", "SELECT"),
    (SUBMITTER_GROUP, "public", "ai_document_submission", "INSERT"),
    (SUBMITTER_GROUP, "public", "ai_document_submission", "UPDATE"),
    (RECONCILER_GROUP, "public", "ai_document_submission", "SELECT"),
    (RECONCILER_GROUP, "public", "ai_document_reconciliation_claim", "SELECT"),
    (RECONCILER_GROUP, "public", "ai_document_reconciliation_claim", "INSERT"),
    (RECONCILER_GROUP, "public", "ai_document_reconciliation_claim", "UPDATE"),
    (RECONCILER_GROUP, "public", "ai_document_operation_observation", "SELECT"),
    (RECONCILER_GROUP, "public", "ai_document_operation_observation", "INSERT"),
    (RECONCILER_GROUP, "public", "ai_document_extraction_evidence", "SELECT"),
    (RECONCILER_GROUP, "public", "ai_document_extraction_evidence", "INSERT"),
    (RECONCILER_GROUP, "public", "ai_document_reconciliation_failure", "SELECT"),
    (RECONCILER_GROUP, "public", "ai_document_reconciliation_failure", "INSERT"),
}
EXPECTED_COLUMN_ACL = {
    (RECONCILER_GROUP, "public", "ai_document_submission", "id", "UPDATE"),
}
PROTECTED_TABLES = (
    "ai_document_submission",
    "ai_document_reconciliation_claim",
    "ai_document_operation_observation",
    "ai_document_extraction_evidence",
    "ai_document_reconciliation_failure",
)


@dataclass(frozen=True, slots=True)
class IdentityTarget:
    login_role: str
    group_role: str
    secret_id: str


@dataclass(frozen=True, slots=True)
class ProvisioningResult:
    applied: bool
    submitter_secret_version: str | None = None
    reconciler_secret_version: str | None = None


def _database_url_for_login(admin_url: str, login: str, password: str) -> str:
    normalized = admin_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parts = urlsplit(normalized)
    if not parts.hostname or not parts.path:
        raise ValueError("database URL must contain a host and database name")
    host = parts.hostname
    if ":" in host:
        host = f"[{host}]"
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    credentials = f"{quote(login, safe='')}:{quote(password, safe='')}"
    return urlunsplit((parts.scheme, f"{credentials}@{host}", parts.path, parts.query, ""))


def _new_password() -> str:
    return secrets.token_urlsafe(48)


def _preflight_database(connection: psycopg.Connection[tuple[Any, ...]]) -> None:
    head = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    if head is None or head[0] != EXPECTED_ALEMBIC_HEAD:
        raise RuntimeError(f"database must be at Alembic head {EXPECTED_ALEMBIC_HEAD}")
    capability_roles = {
        row[0]: row[1:]
        for row in connection.execute(
            """
            SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                   rolreplication, rolbypassrls
            FROM pg_roles
            WHERE rolname = ANY(%s)
            """,
            ([SUBMITTER_GROUP, RECONCILER_GROUP],),
        )
    }
    if set(capability_roles) != {SUBMITTER_GROUP, RECONCILER_GROUP}:
        raise RuntimeError("Document AI capability roles are missing")
    if any(any(properties) for properties in capability_roles.values()):
        raise RuntimeError("Document AI capability roles are not restricted NOLOGIN roles")
    login_roles = {
        row[0]: row[1:]
        for row in connection.execute(
            """
            SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                   rolreplication, rolbypassrls
            FROM pg_roles
            WHERE rolname = ANY(%s)
            """,
            ([SUBMITTER_LOGIN, RECONCILER_LOGIN],),
        )
    }
    if any(
        not properties[0] or any(properties[1:])
        for properties in login_roles.values()
    ):
        raise RuntimeError("Document AI login roles have elevated attributes")
    allowed_memberships = {
        (SUBMITTER_LOGIN, SUBMITTER_GROUP, False, True, True),
        (RECONCILER_LOGIN, RECONCILER_GROUP, False, True, True),
    }
    observed_memberships = set(
        connection.execute(
            """
            SELECT member.rolname, granted.rolname,
                   membership.admin_option,
                   membership.inherit_option,
                   membership.set_option
            FROM pg_auth_members membership
            JOIN pg_roles member ON member.oid = membership.member
            JOIN pg_roles granted ON granted.oid = membership.roleid
            WHERE member.rolname = ANY(%s) OR granted.rolname = ANY(%s)
            """,
            (
                [
                    SUBMITTER_LOGIN,
                    RECONCILER_LOGIN,
                    SUBMITTER_GROUP,
                    RECONCILER_GROUP,
                ],
                [
                    SUBMITTER_LOGIN,
                    RECONCILER_LOGIN,
                    SUBMITTER_GROUP,
                    RECONCILER_GROUP,
                ],
            ),
        ).fetchall()
    )
    if not observed_memberships.issubset(allowed_memberships):
        raise RuntimeError("Document AI login role has an unexpected role membership")
    protected_grantees = [
        SUBMITTER_GROUP,
        RECONCILER_GROUP,
        SUBMITTER_LOGIN,
        RECONCILER_LOGIN,
    ]
    table_acl = {
        (row[0], row[1], row[2], row[3].upper())
        for row in connection.execute(
            """
            SELECT CASE
                     WHEN privilege.grantee = 0 THEN 'PUBLIC'
                     ELSE grantee.rolname
                   END,
                   namespace.nspname, relation.relname,
                   privilege.privilege_type
            FROM pg_class relation
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            CROSS JOIN LATERAL aclexplode(
              COALESCE(relation.relacl, acldefault('r', relation.relowner))
            ) privilege
            LEFT JOIN pg_roles grantee ON grantee.oid = privilege.grantee
            WHERE namespace.nspname = 'public'
              AND relation.relname = ANY(%s)
              AND (
                privilege.grantee = 0
                OR grantee.rolname = ANY(%s)
              )
            """,
            (list(PROTECTED_TABLES), protected_grantees),
        ).fetchall()
    }
    column_acl = {
        (row[0], row[1], row[2], row[3], row[4].upper())
        for row in connection.execute(
            """
            SELECT CASE
                     WHEN privilege.grantee = 0 THEN 'PUBLIC'
                     ELSE grantee.rolname
                   END,
                   namespace.nspname, relation.relname,
                   attribute.attname, privilege.privilege_type
            FROM pg_attribute attribute
            JOIN pg_class relation ON relation.oid = attribute.attrelid
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            CROSS JOIN LATERAL aclexplode(attribute.attacl) privilege
            LEFT JOIN pg_roles grantee ON grantee.oid = privilege.grantee
            WHERE attribute.attnum > 0
              AND NOT attribute.attisdropped
              AND attribute.attacl IS NOT NULL
              AND namespace.nspname = 'public'
              AND relation.relname = ANY(%s)
              AND (
                privilege.grantee = 0
                OR grantee.rolname = ANY(%s)
              )
            """,
            (list(PROTECTED_TABLES), protected_grantees),
        ).fetchall()
    }
    if table_acl != EXPECTED_TABLE_ACL or column_acl != EXPECTED_COLUMN_ACL:
        raise RuntimeError("Document AI capability role ACLs do not match migration authority")


def _publish_secret_version(
    client: secretmanager.SecretManagerServiceClient,
    *,
    project_id: str,
    secret_id: str,
    payload: str,
) -> str:
    parent = f"projects/{project_id}/secrets/{secret_id}"
    client.get_secret(  # pyright: ignore[reportUnknownMemberType]
        request={"name": parent}
    )
    response = client.add_secret_version(  # pyright: ignore[reportUnknownMemberType]
        request={"parent": parent, "payload": {"data": payload.encode("utf-8")}}
    )
    return response.name


def _disable_secret_version(
    client: secretmanager.SecretManagerServiceClient,
    version_name: str,
) -> None:
    client.disable_secret_version(  # pyright: ignore[reportUnknownMemberType]
        request={"name": version_name}
    )


def _rotate_roles(
    connection: psycopg.Connection[tuple[Any, ...]],
    targets: tuple[tuple[IdentityTarget, str], ...],
) -> None:
    for target, password in targets:
        connection.execute(
            sql.SQL(
                "DO $$ BEGIN IF NOT EXISTS "
                "(SELECT 1 FROM pg_roles WHERE rolname = {role_literal}) "
                "THEN CREATE ROLE {role_identifier} LOGIN; END IF; END $$"
            ).format(
                role_literal=sql.Literal(target.login_role),
                role_identifier=sql.Identifier(target.login_role),
            )
        )
        connection.execute(
            sql.SQL(
                "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION NOBYPASSRLS PASSWORD {}"
            ).format(
                sql.Identifier(target.login_role),
                sql.Literal(password),
            )
        )
        connection.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(target.group_role),
                sql.Identifier(target.login_role),
            )
        )


def _reserve_bootstrap(
    connection: psycopg.Connection[tuple[Any, ...]],
    *,
    claim_id: UUID,
    authority_digest: str,
) -> None:
    try:
        with connection.transaction():
            connection.execute(
                """
                INSERT INTO public.ai_document_database_bootstrap (
                  singleton,
                  bootstrap_epoch,
                  claim_id,
                  authority_digest,
                  fencing_token,
                  state
                )
                VALUES (true, %s, %s, %s, 1, 'reserved')
                """,
                (BOOTSTRAP_EPOCH, claim_id, authority_digest),
            )
    except psycopg.errors.UniqueViolation as error:
        raise RuntimeError(
            "Document AI database bootstrap epoch is already reserved"
        ) from error


def _complete_bootstrap(
    connection: psycopg.Connection[tuple[Any, ...]],
    *,
    claim_id: UUID,
    submitter_secret_version: str,
    reconciler_secret_version: str,
) -> None:
    cursor = connection.execute(
        """
        UPDATE public.ai_document_database_bootstrap
        SET state = 'completed',
            completed_at = clock_timestamp(),
            submitter_secret_version = %s,
            reconciler_secret_version = %s
        WHERE singleton
          AND claim_id = %s
          AND state = 'reserved'
        """,
        (
            int(submitter_secret_version),
            int(reconciler_secret_version),
            claim_id,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("Document AI database bootstrap claim is no longer active")


def _fail_bootstrap(
    connection: psycopg.Connection[tuple[Any, ...]],
    *,
    claim_id: UUID,
    cleanup_incomplete: bool,
) -> None:
    failure_code = (
        "IDENTITY_PROVISIONING_FAILED_CLEANUP_INCOMPLETE"
        if cleanup_incomplete
        else "IDENTITY_PROVISIONING_FAILED"
    )
    with connection.transaction():
        cursor = connection.execute(
            """
            UPDATE public.ai_document_database_bootstrap
            SET state = 'failed',
                completed_at = clock_timestamp(),
                failure_code = %s
            WHERE singleton
              AND claim_id = %s
              AND state = 'reserved'
            """,
            (failure_code, claim_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Document AI database bootstrap claim is no longer active")


def _reconcile_bootstrap_commit(
    database_url: str,
    *,
    claim_id: UUID,
    submitter_secret_version: str,
    reconciler_secret_version: str,
) -> str:
    try:
        with psycopg.connect(database_url) as connection:
            with connection.transaction():
                connection.execute("SET LOCAL lock_timeout = '5s'")
                connection.execute("SET LOCAL statement_timeout = '6s'")
                row = connection.execute(
                    """
                    SELECT state, submitter_secret_version,
                           reconciler_secret_version
                    FROM public.ai_document_database_bootstrap
                    WHERE singleton AND claim_id = %s
                    FOR UPDATE
                    """,
                    (claim_id,),
                ).fetchone()
    except Exception:
        return "indeterminate"
    if row == (
        "completed",
        int(submitter_secret_version),
        int(reconciler_secret_version),
    ):
        return "completed"
    if row == ("reserved", None, None):
        return "reserved"
    return "indeterminate"


def _disable_created_versions(
    client: secretmanager.SecretManagerServiceClient,
    versions: list[str],
) -> bool:
    cleanup_incomplete = False
    for version in versions:
        try:
            _disable_secret_version(client, version)
        except Exception:
            cleanup_incomplete = True
    return cleanup_incomplete


def _record_failed_bootstrap(
    connection: psycopg.Connection[tuple[Any, ...]],
    *,
    claim_id: UUID,
    cleanup_incomplete: bool,
) -> bool:
    try:
        _fail_bootstrap(
            connection,
            claim_id=claim_id,
            cleanup_incomplete=cleanup_incomplete,
        )
    except Exception:
        return False
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--submitter-secret-id", required=True)
    parser.add_argument("--reconciler-secret-id", required=True)
    parser.add_argument("--authority-digest", required=True)
    parser.add_argument("--database-url-env", default="VFBIZ_AI_OPERATOR_DATABASE_URL")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def provision_database_identities(
    *,
    project_id: str,
    submitter_secret_id: str,
    reconciler_secret_id: str,
    admin_url: str,
    authority_digest: str,
    apply: bool,
) -> ProvisioningResult:
    if submitter_secret_id == reconciler_secret_id:
        raise ValueError("submitter and reconciler secret IDs must differ")
    if not admin_url:
        raise ValueError("operator database URL is required")
    if re.fullmatch(r"[0-9a-f]{64}", authority_digest) is None:
        raise ValueError("bootstrap authority digest must be a lowercase SHA-256")
    psycopg_url = admin_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    with psycopg.connect(psycopg_url, autocommit=True) as connection:
        _preflight_database(connection)
        if not apply:
            return ProvisioningResult(applied=False)
        claim_id = uuid4()
        _reserve_bootstrap(
            connection,
            claim_id=claim_id,
            authority_digest=authority_digest,
        )

        submitter_password = _new_password()
        reconciler_password = _new_password()
        targets = (
            (
                IdentityTarget(SUBMITTER_LOGIN, SUBMITTER_GROUP, submitter_secret_id),
                submitter_password,
            ),
            (
                IdentityTarget(RECONCILER_LOGIN, RECONCILER_GROUP, reconciler_secret_id),
                reconciler_password,
            ),
        )
        client = secretmanager.SecretManagerServiceClient()
        versions: list[str] = []
        try:
            for target, password in targets:
                versions.append(
                    _publish_secret_version(
                        client,
                        project_id=project_id,
                        secret_id=target.secret_id,
                        payload=_database_url_for_login(
                            admin_url,
                            target.login_role,
                            password,
                        ),
                    )
                )
            numeric_versions = [version.rsplit("/", 1)[-1] for version in versions]
        except Exception:
            cleanup_incomplete = _disable_created_versions(client, versions)
            _record_failed_bootstrap(
                connection,
                claim_id=claim_id,
                cleanup_incomplete=cleanup_incomplete,
            )
            raise
        try:
            with connection.transaction():
                _rotate_roles(connection, targets)
                _complete_bootstrap(
                    connection,
                    claim_id=claim_id,
                    submitter_secret_version=numeric_versions[0],
                    reconciler_secret_version=numeric_versions[1],
                )
        except Exception as error:
            commit_state = _reconcile_bootstrap_commit(
                psycopg_url,
                claim_id=claim_id,
                submitter_secret_version=numeric_versions[0],
                reconciler_secret_version=numeric_versions[1],
            )
            if commit_state == "completed":
                return ProvisioningResult(
                    applied=True,
                    submitter_secret_version=numeric_versions[0],
                    reconciler_secret_version=numeric_versions[1],
                )
            if commit_state == "reserved":
                cleanup_incomplete = _disable_created_versions(client, versions)
                _record_failed_bootstrap(
                    connection,
                    claim_id=claim_id,
                    cleanup_incomplete=cleanup_incomplete,
                )
                raise
            raise RuntimeError(
                "Document AI database bootstrap commit outcome is indeterminate; "
                "do not retry or disable secret versions"
            ) from error

    return ProvisioningResult(
        applied=True,
        submitter_secret_version=numeric_versions[0],
        reconciler_secret_version=numeric_versions[1],
    )


def main() -> int:
    args = _parse_args()
    admin_url = os.environ.get(args.database_url_env, "")
    if not admin_url:
        raise SystemExit(f"missing operator database URL in {args.database_url_env}")
    try:
        result = provision_database_identities(
            project_id=args.project_id,
            submitter_secret_id=args.submitter_secret_id,
            reconciler_secret_id=args.reconciler_secret_id,
            admin_url=admin_url,
            authority_digest=args.authority_digest,
            apply=args.apply,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if not result.applied:
        print("preflight passed; no database role or secret was changed")
        return 0
    print(
        "provisioned distinct database identities; numeric secret versions: "
        f"submitter={result.submitter_secret_version}, "
        f"reconciler={result.reconciler_secret_version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
