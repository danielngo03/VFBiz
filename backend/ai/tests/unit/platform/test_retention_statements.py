from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from app.platform.checkpoints.retention_statements import (
    expire_abandoned_resume_gate_claims_statement,
    purge_stale_execution_fences_statement,
    purge_terminal_resume_gate_claims_statement,
)

CUTOFF = datetime(2026, 7, 25, tzinfo=UTC)


def compile_sql(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[union-attr]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_expire_abandoned_claims_only_targets_non_terminal_states_past_their_deadline() -> None:
    sql = compile_sql(expire_abandoned_resume_gate_claims_statement(now=CUTOFF))

    assert "UPDATE ai_conversation_resume_gate SET" in sql
    assert "state='expired'" in sql
    assert "'reserved'" in sql and "'waiting'" in sql and "'claimed'" in sql
    assert "'completed'" not in sql and "'failed_closed'" not in sql
    assert "deadline_at <=" in sql


def test_purge_terminal_claims_only_targets_terminal_states_via_bounded_subquery() -> None:
    sql = compile_sql(
        purge_terminal_resume_gate_claims_statement(older_than=CUTOFF, limit=500)
    )

    assert sql.startswith("DELETE FROM ai_conversation_resume_gate")
    assert "'completed'" in sql and "'failed_closed'" in sql and "'expired'" in sql
    assert "'reserved'" not in sql and "'waiting'" not in sql
    assert "updated_at <" in sql
    assert "LIMIT 500" in sql


def test_purge_stale_execution_fences_has_no_state_filter_only_age() -> None:
    sql = compile_sql(
        purge_stale_execution_fences_statement(older_than=CUTOFF, limit=250)
    )

    assert sql.startswith("DELETE FROM ai_conversation_execution_fence")
    assert "updated_at <" in sql
    assert "LIMIT 250" in sql
    assert "cancelled" not in sql.lower()
