from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform.database.session import create_engine, create_session_factory


@dataclass(frozen=True, slots=True)
class DatabaseRuntime:
    """AI PostgreSQL resources with an explicit application lifetime."""

    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]

    async def close(self) -> None:
        await self.engine.dispose()


def create_database_runtime(database_url: str) -> DatabaseRuntime:
    engine = create_engine(database_url)
    return DatabaseRuntime(
        engine=engine,
        sessions=create_session_factory(engine),
    )
