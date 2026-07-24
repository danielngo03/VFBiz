from asyncio import run
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.platform.config import Settings
from app.platform.database.base import Base
from app.platform.database.model_registry import load_models

configuration = context.config

if configuration.config_file_name is not None:
    fileConfig(configuration.config_file_name)

load_models()
target_metadata = Base.metadata


def database_url() -> str:
    settings = Settings()
    if settings.database_url is not None:
        return settings.database_url
    return configuration.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_sync_migrations(connection: object) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section = configuration.get_section(configuration.config_ini_section, {})
    section["sqlalchemy.url"] = database_url()
    engine = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(run_sync_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run(run_async_migrations())
