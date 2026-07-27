from dataclasses import dataclass

import pytest

from app.bootstrap import application as application_module
from app.platform.config import Settings
from app.platform.security.execution_assertion import ExecutionAssertionVerifier


@dataclass
class FakeDatabaseRuntime:
    closed: bool = False
    sessions: object = None

    async def close(self) -> None:
        self.closed = True


@dataclass
class FakeConversationRuntimeDependencies:
    closed: bool = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_application_composes_and_closes_database_without_starting_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeDatabaseRuntime()
    observed_urls: list[str] = []

    def fake_create_database_runtime(database_url: str) -> FakeDatabaseRuntime:
        observed_urls.append(database_url)
        return runtime

    monkeypatch.setattr(
        application_module,
        "create_database_runtime",
        fake_create_database_runtime,
    )
    conversation_dependencies = FakeConversationRuntimeDependencies()

    async def fake_build_conversation_runtime_dependencies(
        _settings: Settings, _sessions: object
    ) -> FakeConversationRuntimeDependencies:
        return conversation_dependencies

    monkeypatch.setattr(
        application_module,
        "build_conversation_runtime_dependencies",
        fake_build_conversation_runtime_dependencies,
    )
    settings = Settings(
        environment="test",
        database_url="postgresql+asyncpg://vfbiz:test@localhost:5432/vfbiz_ai",
        generation_provider="disabled",
        embedding_provider="disabled",
    )
    application = application_module.create_application(settings)

    async with application.router.lifespan_context(application):
        assert application.state.database_runtime is runtime
        assert observed_urls == [settings.database_url]
        assert runtime.closed is False
        assert application.state.execution_cancellation_port is not None
        assert hasattr(application.state.execution_cancellation_port, "accept_durably")
        assert application.state.conversation_dependencies is conversation_dependencies
        assert conversation_dependencies.closed is False

    assert runtime.closed is True
    assert conversation_dependencies.closed is True


@pytest.mark.asyncio
async def test_application_does_not_create_database_runtime_without_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_database_runtime(_database_url: str) -> FakeDatabaseRuntime:
        raise AssertionError("database runtime must not be created")

    monkeypatch.setattr(
        application_module,
        "create_database_runtime",
        unexpected_database_runtime,
    )
    application = application_module.create_application(
        Settings(environment="test", database_url=None)
    )

    async with application.router.lifespan_context(application):
        assert application.state.database_runtime is None
        assert application.state.execution_cancellation_port is None
        assert application.state.conversation_dependencies is None


@dataclass
class FakeRedisClient:
    closed: bool = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_application_composes_and_closes_the_assertion_verifier_and_its_redis_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_verifier = object()
    redis_client = FakeRedisClient()

    def fake_build_execution_assertion_verifier(
        _settings: Settings,
    ) -> tuple[object, FakeRedisClient]:
        return sentinel_verifier, redis_client

    monkeypatch.setattr(
        application_module,
        "build_execution_assertion_verifier",
        fake_build_execution_assertion_verifier,
    )
    application = application_module.create_application(
        Settings(environment="test", database_url=None)
    )

    async with application.router.lifespan_context(application):
        assert application.state.execution_assertion_verifier is sentinel_verifier
        assert redis_client.closed is False

    assert redis_client.closed is True


@pytest.mark.asyncio
async def test_application_does_not_close_a_redis_client_that_was_never_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_build_execution_assertion_verifier(
        _settings: Settings,
    ) -> tuple[ExecutionAssertionVerifier | None, None]:
        return None, None

    monkeypatch.setattr(
        application_module,
        "build_execution_assertion_verifier",
        fake_build_execution_assertion_verifier,
    )
    application = application_module.create_application(
        Settings(environment="test", database_url=None)
    )

    async with application.router.lifespan_context(application):
        assert application.state.execution_assertion_verifier is None
