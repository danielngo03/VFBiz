from types import SimpleNamespace

import pytest

from scripts import doctor


def test_safe_origin_rejects_credentials_paths_and_non_http_schemes() -> None:
    assert doctor._safe_origin("http://127.0.0.1:8888/") == "http://127.0.0.1:8888"

    for candidate in (
        "file:///tmp/socket",
        "https://user:secret@example.test",
        "https://example.test/internal",
        "https://example.test?token=secret",
    ):
        with pytest.raises(ValueError):
            doctor._safe_origin(candidate)


@pytest.mark.asyncio
async def test_live_probes_do_not_forward_assertion_to_database_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace()
    observed: dict[str, object] = {}

    async def postgres(_settings: object, profile: str):
        observed["profile"] = profile
        return (doctor.ProbeResult("PostgreSQL", "reachable", "ok", True),)

    async def redis(_settings: object):
        return doctor.ProbeResult("Redis", "reachable", "ok", True)

    async def http(base_url: str, assertion: str | None):
        observed["base_url"] = base_url
        observed["assertion"] = assertion
        return (doctor.ProbeResult("signed readiness", "ready", "ok", True),)

    monkeypatch.setattr(doctor, "_probe_postgres", postgres)
    monkeypatch.setattr(doctor, "_probe_redis", redis)
    monkeypatch.setattr(doctor, "_probe_http", http)
    monkeypatch.setenv("VFBIZ_DOCTOR_AI_ASSISTANT_PROFILE", "authenticated_customer")
    monkeypatch.setenv("VFBIZ_DOCTOR_AI_BASE_URL", "https://ai.internal.example")
    monkeypatch.setenv("VFBIZ_DOCTOR_AI_GATEWAY_ASSERTION", "secret.assertion.value")

    results = await doctor.run_live_probes(settings)  # type: ignore[arg-type]

    assert all(result.passed for result in results)
    assert observed == {
        "assertion": "secret.assertion.value",
        "base_url": "https://ai.internal.example",
        "profile": "authenticated_customer",
    }


@pytest.mark.asyncio
async def test_live_probes_reject_unknown_profile_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_probe(*_args: object) -> tuple[doctor.ProbeResult, ...]:
        pytest.fail("network probe must not run for an invalid profile")

    monkeypatch.setattr(doctor, "_probe_postgres", unexpected_probe)
    monkeypatch.setenv("VFBIZ_DOCTOR_AI_ASSISTANT_PROFILE", "untrusted-profile")

    results = await doctor.run_live_probes(SimpleNamespace())  # type: ignore[arg-type]

    assert results == (
        doctor.ProbeResult(
            "live probe configuration",
            "invalid",
            "VFBIZ_DOCTOR_AI_ASSISTANT_PROFILE is not an approved profile",
            False,
        ),
    )


def test_probe_output_never_contains_runtime_secret(
    capsys: pytest.CaptureFixture[str],
) -> None:
    doctor._print_probe(
        doctor.ProbeResult(
            name="signed readiness",
            state="failed",
            detail="signed readiness probe failed",
            passed=False,
        )
    )

    output = capsys.readouterr().out
    assert output == (
        "FAIL signed readiness: failed — signed readiness probe failed\n"
    )
    assert "token" not in output.lower()
    assert "assertion.value" not in output
