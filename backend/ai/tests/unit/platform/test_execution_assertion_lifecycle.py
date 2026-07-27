import pytest

from app.platform.config import Settings
from app.platform.security.execution_assertion import (
    ExecutionAssertionVerifier,
    InMemoryAssertionReplayStore,
    RedisAssertionReplayStore,
    build_execution_assertion_verifier,
    execution_assertion_verifier,
)


def _fake_request(configured: object) -> object:
    class _State:
        execution_assertion_verifier = configured

    class _App:
        state = _State()

    class _Request:
        app = _App()

    return _Request()


def test_build_falls_back_to_in_memory_store_in_test_environment() -> None:
    settings = Settings(environment="test", redis_url=None)

    verifier, redis_client = build_execution_assertion_verifier(settings)

    assert isinstance(verifier, ExecutionAssertionVerifier)
    assert isinstance(verifier._replay_store, InMemoryAssertionReplayStore)  # noqa: SLF001
    assert redis_client is None


# There is no test for "no redis_url and environment not in {development,
# test}": Settings.validate_runtime_policy already requires redis_url
# whenever environment is staging/production, so that combination can never
# reach build_execution_assertion_verifier through a validated Settings
# instance. The function's own `None, None` fallback for that case is
# intentional defense-in-depth, not a reachable path today.


def test_build_constructs_a_redis_backed_store_when_redis_url_is_configured() -> None:
    settings = Settings(environment="test", redis_url="redis://localhost:6379/0")

    verifier, redis_client = build_execution_assertion_verifier(settings)

    assert isinstance(verifier, ExecutionAssertionVerifier)
    assert isinstance(verifier._replay_store, RedisAssertionReplayStore)  # noqa: SLF001
    assert redis_client is not None


def test_accessor_returns_the_lifespan_configured_verifier() -> None:
    sentinel = ExecutionAssertionVerifier(
        key_resolver=object(),  # type: ignore[arg-type]
        replay_store=InMemoryAssertionReplayStore(),
    )

    request = _fake_request(sentinel)

    assert execution_assertion_verifier(request) is sentinel  # type: ignore[arg-type]


def test_accessor_fails_closed_when_lifespan_never_configured_it() -> None:
    request = _fake_request(None)

    with pytest.raises(Exception) as error:
        execution_assertion_verifier(request)  # type: ignore[arg-type]

    assert error.value.status_code == 503  # type: ignore[attr-defined]
    assert error.value.detail["code"] == "ASSERTION_INVALID"  # type: ignore[attr-defined]
