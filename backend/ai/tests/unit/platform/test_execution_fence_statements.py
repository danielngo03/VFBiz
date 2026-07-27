from sqlalchemy.dialects import postgresql

from app.platform.checkpoints.execution_fence_statements import (
    advance_cancellation_statement,
    advance_fencing_token_statement,
    read_fence_statement,
)

TURN_HASH = "a" * 64


def compile_sql(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[union-attr]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )


def test_advance_fencing_token_never_lowers_stored_token_and_leaves_cancelled_alone() -> None:
    sql = compile_sql(
        advance_fencing_token_statement(turn_hash=TURN_HASH, fencing_token=7)
    )
    set_clause = sql.split("DO UPDATE SET", 1)[1].split("RETURNING")[0]

    assert "ON CONFLICT (turn_hash) DO UPDATE" in sql
    assert "greatest(" in sql.lower()
    assert "cancelled" not in set_clause.lower()
    assert "RETURNING" in sql
    assert "cancelled" in sql.split("RETURNING", 1)[1].lower()


def test_advance_cancellation_uses_case_to_reject_a_stale_fencing_token() -> None:
    sql = compile_sql(
        advance_cancellation_statement(turn_hash=TURN_HASH, fencing_token=7)
    )

    assert "ON CONFLICT (turn_hash) DO UPDATE" in sql
    assert "greatest(" in sql.lower()
    assert "CASE WHEN" in sql
    assert "RETURNING" in sql


def test_read_fence_selects_by_turn_hash_only() -> None:
    sql = compile_sql(read_fence_statement(turn_hash=TURN_HASH))

    assert "WHERE" in sql
    assert "turn_hash" in sql
    assert "SELECT" in sql
