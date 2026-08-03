from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from app.platform.config import Settings
from scripts.provision_document_ai_database_identities import (
    RECONCILER_GROUP,
    RECONCILER_LOGIN,
    SUBMITTER_GROUP,
    SUBMITTER_LOGIN,
    IdentityTarget,
    _complete_bootstrap,
    _fail_bootstrap,
    _reconcile_bootstrap_commit,
    _reserve_bootstrap,
    _rotate_roles,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("VFBIZ_AI_DATABASE_URL"),
    reason="PostgreSQL integration database is not configured",
)
AI_ROOT = Path(__file__).resolve().parents[3]


def _database_url() -> str:
    configured = Settings().database_url
    assert configured is not None
    return configured.replace("postgresql+asyncpg://", "postgresql://", 1)


def _clear_bootstrap_evidence(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    with connection.transaction():
        connection.execute(
            "ALTER TABLE public.ai_document_database_bootstrap DISABLE TRIGGER USER"
        )
        connection.execute("DELETE FROM public.ai_document_database_bootstrap")
        connection.execute(
            "ALTER TABLE public.ai_document_database_bootstrap ENABLE TRIGGER USER"
        )


def test_bootstrap_epoch_rejects_replay_and_terminal_mutation() -> None:
    claim_id = uuid4()
    with psycopg.connect(_database_url(), autocommit=True) as connection:
        _clear_bootstrap_evidence(connection)
        try:
            _reserve_bootstrap(
                connection,
                claim_id=claim_id,
                authority_digest="a" * 64,
            )
            with pytest.raises(RuntimeError, match="already reserved"):
                _reserve_bootstrap(
                    connection,
                    claim_id=uuid4(),
                    authority_digest="b" * 64,
                )

            with connection.transaction():
                _complete_bootstrap(
                    connection,
                    claim_id=claim_id,
                    submitter_secret_version=str(7),
                    reconciler_secret_version=str(9),
                )
            with pytest.raises(RuntimeError, match="no longer active"):
                _fail_bootstrap(
                    connection,
                    claim_id=claim_id,
                    cleanup_incomplete=False,
                )
            with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
                connection.execute("DELETE FROM public.ai_document_database_bootstrap")
            with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
                connection.execute("TRUNCATE public.ai_document_database_bootstrap")
        finally:
            _clear_bootstrap_evidence(connection)


def test_concurrent_bootstrap_reservation_has_exactly_one_winner() -> None:
    barrier = Barrier(2)

    def reserve(claim_seed: str) -> str:
        with psycopg.connect(_database_url(), autocommit=True) as connection:
            barrier.wait()
            try:
                _reserve_bootstrap(
                    connection,
                    claim_id=uuid4(),
                    authority_digest=claim_seed * 64,
                )
            except RuntimeError:
                return "rejected"
            return "reserved"

    with psycopg.connect(_database_url(), autocommit=True) as connection:
        _clear_bootstrap_evidence(connection)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(reserve, ("a", "b")))
        assert sorted(outcomes) == ["rejected", "reserved"]
        with psycopg.connect(_database_url(), autocommit=True) as connection:
            row = connection.execute(
                """
                SELECT count(*), min(state), min(fencing_token)
                FROM public.ai_document_database_bootstrap
                """
            ).fetchone()
            assert row == (1, "reserved", 1)
    finally:
        with psycopg.connect(_database_url(), autocommit=True) as connection:
            _clear_bootstrap_evidence(connection)


def test_role_rotation_uses_valid_postgresql_utility_sql() -> None:
    with psycopg.connect(_database_url(), autocommit=True) as connection:
        connection.execute("BEGIN")
        try:
            _rotate_roles(
                connection,
                (
                    (
                        IdentityTarget(
                            SUBMITTER_LOGIN,
                            SUBMITTER_GROUP,
                            "submitter-secret",
                        ),
                        "submitter-password",
                    ),
                    (
                        IdentityTarget(
                            RECONCILER_LOGIN,
                            RECONCILER_GROUP,
                            "reconciler-secret",
                        ),
                        "reconciler-password",
                    ),
                ),
            )
            rows = connection.execute(
                """
                SELECT member.rolname, granted.rolname, membership.admin_option
                FROM pg_auth_members membership
                JOIN pg_roles member ON member.oid = membership.member
                JOIN pg_roles granted ON granted.oid = membership.roleid
                WHERE member.rolname = ANY(%s)
                ORDER BY member.rolname
                """,
                ([SUBMITTER_LOGIN, RECONCILER_LOGIN],),
            ).fetchall()
            assert rows == [
                (RECONCILER_LOGIN, RECONCILER_GROUP, False),
                (SUBMITTER_LOGIN, SUBMITTER_GROUP, False),
            ]
        finally:
            connection.execute("ROLLBACK")


def test_commit_reconciliation_waits_for_terminal_transaction_outcome() -> None:
    claim_id = uuid4()
    submitter_version = str(17)
    reconciler_version = str(19)
    with psycopg.connect(_database_url(), autocommit=True) as setup:
        _clear_bootstrap_evidence(setup)
        _reserve_bootstrap(
            setup,
            claim_id=claim_id,
            authority_digest="d" * 64,
        )
    try:
        with psycopg.connect(_database_url(), autocommit=True) as writer:
            with ThreadPoolExecutor(max_workers=1) as executor:
                with writer.transaction():
                    _complete_bootstrap(
                        writer,
                        claim_id=claim_id,
                        submitter_secret_version=submitter_version,
                        reconciler_secret_version=reconciler_version,
                    )
                    outcome = executor.submit(
                        _reconcile_bootstrap_commit,
                        _database_url(),
                        claim_id=claim_id,
                        submitter_secret_version=submitter_version,
                        reconciler_secret_version=reconciler_version,
                    )
                    with pytest.raises(FutureTimeoutError):
                        outcome.result(timeout=0.25)
                assert outcome.result(timeout=2) == "completed"
    finally:
        with psycopg.connect(_database_url(), autocommit=True) as cleanup:
            _clear_bootstrap_evidence(cleanup)


@pytest.mark.parametrize("state", ["reserved", "completed", "failed"])
def test_bootstrap_evidence_refuses_downgrade_for_every_state(state: str) -> None:
    claim_id = uuid4()
    with psycopg.connect(_database_url(), autocommit=True) as connection:
        _clear_bootstrap_evidence(connection)
        _reserve_bootstrap(
            connection,
            claim_id=claim_id,
            authority_digest="c" * 64,
        )
        if state == "completed":
            with connection.transaction():
                _complete_bootstrap(
                    connection,
                    claim_id=claim_id,
                    submitter_secret_version=str(11),
                    reconciler_secret_version=str(12),
                )
        elif state == "failed":
            _fail_bootstrap(
                connection,
                claim_id=claim_id,
                cleanup_incomplete=False,
            )

    configuration = Config(str(AI_ROOT / "alembic.ini"))
    try:
        with pytest.raises(Exception, match="downgrade refused"):
            command.downgrade(configuration, "20260802_0024")
        with psycopg.connect(_database_url(), autocommit=True) as connection:
            head = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            assert head == ("20260802_0025",)
    finally:
        with psycopg.connect(_database_url(), autocommit=True) as connection:
            _clear_bootstrap_evidence(connection)
