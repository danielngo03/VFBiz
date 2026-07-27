from dataclasses import dataclass
from typing import cast

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool


def psycopg_conninfo(sqlalchemy_database_url: str) -> str:
    """Convert the SQLAlchemy asyncpg URL into a psycopg-compatible DSN.

    LangGraph's Postgres checkpointer uses psycopg natively; it does not go
    through SQLAlchemy's asyncpg dialect, so the two share a database but not
    a driver or a connection pool.
    """
    if sqlalchemy_database_url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + sqlalchemy_database_url.removeprefix(
            "postgresql+asyncpg://"
        )
    return sqlalchemy_database_url


def strict_checkpoint_serde() -> JsonPlusSerializer:
    """The only serde configuration `require_strict_checkpointer` accepts.

    `JsonPlusSerializer()`'s default `allowed_msgpack_modules` resolves to
    `True` unless `LANGGRAPH_STRICT_MSGPACK=true` is set process-wide; an
    explicit `None` here is the same guarantee without depending on that
    environment variable existing everywhere this process runs.
    """
    return JsonPlusSerializer(
        pickle_fallback=False,
        allowed_json_modules=None,
        allowed_msgpack_modules=None,
    )


@dataclass
class ConversationCheckpointerRuntime:
    pool: AsyncConnectionPool[AsyncConnection[DictRow]]
    saver: AsyncPostgresSaver

    async def close(self) -> None:
        await self.pool.close()


async def create_conversation_checkpointer_runtime(
    database_url: str,
) -> ConversationCheckpointerRuntime:
    # kwargs is opaque to the type checker, so the pool's connection-row type
    # is asserted here, not inferred; `row_factory=dict_row` below is what
    # actually produces DictRow connections at runtime (proven by the
    # checkpointer setup/round-trip integration tests).
    pool = cast(
        "AsyncConnectionPool[AsyncConnection[DictRow]]",
        AsyncConnectionPool(
            psycopg_conninfo(database_url),
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            open=False,
        ),
    )
    await pool.open()
    saver = AsyncPostgresSaver(conn=pool, serde=strict_checkpoint_serde())
    await saver.setup()
    return ConversationCheckpointerRuntime(pool=pool, saver=saver)
