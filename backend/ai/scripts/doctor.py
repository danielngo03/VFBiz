"""Safe local readiness diagnostics for the private AI runtime.

This command deliberately reports configuration names and component states,
never values from ``.env`` or any secret material. It is an operator aid, not
a release approval mechanism.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import tempfile
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import text

if TYPE_CHECKING:
    from app.platform.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_DEPRECATED = (
    "VFBIZ_AI_PROVIDER",
    "VFBIZ_AI_CHAT_MODEL",
)
_MIGRATIONS = {
    "VFBIZ_AI_PROVIDER": "VFBIZ_AI_GENERATION_PROVIDER",
    "VFBIZ_AI_CHAT_MODEL": "VFBIZ_AI_GENERATION_MODEL",
}
_DOCTOR_ASSERTION_ENV = "VFBIZ_DOCTOR_AI_GATEWAY_ASSERTION"
_DOCTOR_BASE_URL_ENV = "VFBIZ_DOCTOR_AI_BASE_URL"
_DOCTOR_PROFILE_ENV = "VFBIZ_DOCTOR_AI_ASSISTANT_PROFILE"
_APPROVED_PROFILES = frozenset(
    {"public_customer", "authenticated_customer", "employee"}
)


@dataclass(frozen=True, slots=True)
class ProbeResult:
    name: str
    state: str
    detail: str
    passed: bool


def _safe_origin(raw_value: str) -> str:
    parsed = urlsplit(raw_value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("doctor base URL must be an HTTP(S) origin")
    return raw_value.rstrip("/")


async def _probe_postgres(settings: Settings, assistant_profile: str) -> tuple[ProbeResult, ...]:
    if settings.database_url is None:
        return (
            ProbeResult("PostgreSQL", "not-configured", "database URL is absent", False),
            ProbeResult("pgvector", "not-checked", "PostgreSQL is unavailable", False),
            ProbeResult(
                "active release pointer",
                "not-checked",
                "PostgreSQL is unavailable",
                False,
            ),
        )
    from app.platform.database.session import create_engine

    engine = create_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            vector_enabled = bool(
                await connection.scalar(
                    text(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                        ")"
                    )
                )
            )
            pointer_present = bool(
                await connection.scalar(
                    text(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM ai_assistant_release_pointer "
                        "WHERE assistant_profile = :assistant_profile "
                        "AND environment = :environment"
                        ")"
                    ),
                    {
                        "assistant_profile": assistant_profile,
                        "environment": settings.environment,
                    },
                )
            )
        return (
            ProbeResult("PostgreSQL", "reachable", "connection and SELECT succeeded", True),
            ProbeResult(
                "pgvector",
                "available" if vector_enabled else "missing",
                "vector extension is installed" if vector_enabled else "vector extension is absent",
                vector_enabled,
            ),
            ProbeResult(
                "active release pointer",
                "present" if pointer_present else "absent",
                (
                    "raw pointer is visible; this is not release approval"
                    if pointer_present
                    else "no raw pointer exists for the selected profile/environment"
                ),
                pointer_present,
            ),
        )
    except Exception:
        return (
            ProbeResult("PostgreSQL", "unreachable", "connection or query failed", False),
            ProbeResult("pgvector", "not-checked", "PostgreSQL probe failed", False),
            ProbeResult(
                "active release pointer",
                "not-checked",
                "PostgreSQL probe failed",
                False,
            ),
        )
    finally:
        await engine.dispose()


async def _probe_redis(settings: Settings) -> ProbeResult:
    if settings.redis_url is None:
        return ProbeResult("Redis", "not-configured", "Redis URL is absent", False)
    client: Redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        str(settings.redis_url),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        reply = await cast(
            Awaitable[bool],
            client.ping(),  # pyright: ignore[reportUnknownMemberType]
        )
        return ProbeResult(
            "Redis",
            "reachable" if reply else "invalid-response",
            "PING succeeded" if reply else "PING returned an invalid response",
            bool(reply),
        )
    except Exception:
        return ProbeResult("Redis", "unreachable", "connection or PING failed", False)
    finally:
        await client.aclose()


async def _probe_http(base_url: str, assertion: str | None) -> tuple[ProbeResult, ...]:
    limits = httpx.Limits(max_connections=2, max_keepalive_connections=0)
    timeout = httpx.Timeout(3)
    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            follow_redirects=False,
            limits=limits,
            timeout=timeout,
            trust_env=False,
        ) as client:
            try:
                liveness = await client.get("/health/live")
                liveness_passed = (
                    liveness.status_code == 200
                    and liveness.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    and liveness.json() == {"status": "ok"}
                )
            except Exception:
                liveness_passed = False
            liveness_result = ProbeResult(
                "FastAPI liveness",
                "ready" if liveness_passed else "failed",
                "typed liveness response verified" if liveness_passed else "probe failed",
                liveness_passed,
            )
            if assertion is None:
                readiness_result = ProbeResult(
                    "signed readiness",
                    "not-configured",
                    f"{_DOCTOR_ASSERTION_ENV} is absent",
                    False,
                )
            else:
                try:
                    readiness = await client.get(
                        "/internal/v1/health/ready",
                        headers={"authorization": f"Bearer {assertion}"},
                    )
                    readiness_passed = (
                        readiness.status_code == 200
                        and readiness.headers.get("content-type", "").startswith(
                            "application/json"
                        )
                        and readiness.json() == {"status": "ready"}
                    )
                except Exception:
                    readiness_passed = False
                readiness_result = ProbeResult(
                    "signed readiness",
                    "ready" if readiness_passed else "failed",
                    (
                        "signed readiness response verified"
                        if readiness_passed
                        else "signed readiness probe failed"
                    ),
                    readiness_passed,
                )
            return (liveness_result, readiness_result)
    except Exception:
        return (
            ProbeResult("FastAPI liveness", "failed", "HTTP client failed", False),
            ProbeResult("signed readiness", "failed", "HTTP client failed", False),
        )


async def _bounded_postgres(
    settings: Settings, assistant_profile: str
) -> tuple[ProbeResult, ...]:
    try:
        return await asyncio.wait_for(
            _probe_postgres(settings, assistant_profile),
            timeout=5,
        )
    except TimeoutError:
        return (
            ProbeResult("PostgreSQL", "timeout", "probe exceeded five seconds", False),
            ProbeResult("pgvector", "not-checked", "PostgreSQL probe timed out", False),
            ProbeResult(
                "active release pointer",
                "not-checked",
                "PostgreSQL probe timed out",
                False,
            ),
        )


async def _bounded_redis(settings: Settings) -> ProbeResult:
    try:
        return await asyncio.wait_for(_probe_redis(settings), timeout=5)
    except TimeoutError:
        return ProbeResult("Redis", "timeout", "probe exceeded five seconds", False)


async def _bounded_http(
    base_url: str, assertion: str | None
) -> tuple[ProbeResult, ...]:
    try:
        return await asyncio.wait_for(_probe_http(base_url, assertion), timeout=5)
    except TimeoutError:
        return (
            ProbeResult(
                "FastAPI liveness",
                "timeout",
                "probe exceeded five seconds",
                False,
            ),
            ProbeResult(
                "signed readiness",
                "not-checked",
                "FastAPI probe timed out",
                False,
            ),
        )


async def run_live_probes(settings: Settings) -> tuple[ProbeResult, ...]:
    profile = os.getenv(_DOCTOR_PROFILE_ENV, "public_customer")
    if profile not in _APPROVED_PROFILES:
        return (
            ProbeResult(
                "live probe configuration",
                "invalid",
                f"{_DOCTOR_PROFILE_ENV} is not an approved profile",
                False,
            ),
        )
    try:
        base_url = _safe_origin(
            os.getenv(_DOCTOR_BASE_URL_ENV, "http://127.0.0.1:8888")
        )
    except ValueError:
        return (
            ProbeResult(
                "live probe configuration",
                "invalid",
                f"{_DOCTOR_BASE_URL_ENV} must be an HTTP(S) origin",
                False,
            ),
        )
    assertion = os.getenv(_DOCTOR_ASSERTION_ENV) or None
    postgres, redis, http = await asyncio.gather(
        _bounded_postgres(settings, profile),
        _bounded_redis(settings),
        _bounded_http(base_url, assertion),
    )
    return (*postgres, redis, *http)


def _print_probe(result: ProbeResult) -> None:
    prefix = "OK" if result.passed else "FAIL"
    print(f"{prefix} {result.name}: {result.state} — {result.detail}")


def _env_assignments(content: str) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for line in content.splitlines():
        match = re.match(r"^\s*(VFBIZ_AI_[A-Z0-9_]+)\s*=\s*(.*)$", line)
        if match:
            assignments[match.group(1)] = match.group(2)
    return assignments


def migrate_deprecated_environment(env_file: Path) -> int:
    """Atomically rename unambiguous local configuration keys.

    Values never leave the process or command output. A conflict leaves the
    file untouched: runtime configuration must not be silently overwritten.
    """
    if not env_file.exists():
        print("FAIL local .env is not present; nothing can be migrated")
        return 2
    content = env_file.read_text(encoding="utf-8")
    assignments = _env_assignments(content)
    conflicts = [
        legacy
        for legacy, canonical in _MIGRATIONS.items()
        if legacy in assignments
        and canonical in assignments
        and assignments[legacy] != assignments[canonical]
    ]
    if conflicts:
        print("FAIL canonical and deprecated variables disagree: " + ", ".join(conflicts))
        print("Resolve the conflict manually; the local .env was not changed.")
        return 2

    changed: list[str] = []
    migrated_lines: list[str] = []
    for line in content.splitlines(keepends=True):
        match = re.match(r"^(\s*)(VFBIZ_AI_[A-Z0-9_]+)(\s*=.*)$", line)
        if match and match.group(2) in _MIGRATIONS:
            legacy = match.group(2)
            canonical = _MIGRATIONS[legacy]
            if canonical in assignments:
                changed.append(legacy)
                continue
            migrated_lines.append(f"{match.group(1)}{canonical}{match.group(3)}")
            changed.append(f"{legacy} -> {canonical}")
            continue
        migrated_lines.append(line)

    if not changed:
        print("OK no deprecated AI environment variables need migration")
        return 0
    mode = env_file.stat().st_mode & 0o777
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=env_file.parent,
        prefix=f".{env_file.name}.",
        delete=False,
    ) as temporary:
        temporary.writelines(migrated_lines)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.chmod(mode)
    temporary_path.replace(env_file)
    print("OK migrated deprecated AI environment variable name(s): " + ", ".join(changed))
    return 0


def disable_unapproved_providers(env_file: Path) -> int:
    """Fail closed when a legacy local provider value cannot be validated.

    This intentionally changes provider selection only. It does not print,
    copy or delete model identifiers, credentials, database URLs, or approval
    evidence. Enabling a provider remains a separate approved-release action.
    """
    if not env_file.exists():
        print("FAIL local .env is not present; nothing can be normalized")
        return 2
    content = env_file.read_text(encoding="utf-8")
    provider_names = (
        "VFBIZ_AI_GENERATION_PROVIDER",
        "VFBIZ_AI_EMBEDDING_PROVIDER",
    )
    seen: set[str] = set()
    normalized_lines: list[str] = []
    for line in content.splitlines(keepends=True):
        match = re.match(r"^(\s*)(VFBIZ_AI_[A-Z0-9_]+)(\s*=.*)$", line)
        if match and match.group(2) in provider_names:
            normalized_lines.append(f"{match.group(1)}{match.group(2)}=disabled\n")
            seen.add(match.group(2))
            continue
        normalized_lines.append(line)
    for name in provider_names:
        if name not in seen:
            if normalized_lines and not normalized_lines[-1].endswith("\n"):
                normalized_lines[-1] = normalized_lines[-1] + "\n"
            normalized_lines.append(f"{name}=disabled\n")

    mode = env_file.stat().st_mode & 0o777
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=env_file.parent,
        prefix=f".{env_file.name}.",
        delete=False,
    ) as temporary:
        temporary.writelines(normalized_lines)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.chmod(mode)
    temporary_path.replace(env_file)
    print("OK disabled local generation and embedding providers pending release approval")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--migrate-deprecated-env",
        action="store_true",
        help="atomically rename unambiguous deprecated variables in backend/ai/.env",
    )
    parser.add_argument(
        "--disable-unapproved-providers",
        action="store_true",
        help="set local generation and embedding providers to disabled without touching secrets",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "run opt-in PostgreSQL, pgvector, Redis and local HTTP probes; "
            "never prints configured URLs, credentials, assertions or release identifiers"
        ),
    )
    arguments = parser.parse_args(argv)
    from app.platform.config import Settings

    env_file = PROJECT_ROOT / ".env"
    if arguments.migrate_deprecated_env:
        return migrate_deprecated_environment(env_file)
    if arguments.disable_unapproved_providers:
        return disable_unapproved_providers(env_file)
    file_names: set[str] = set()
    if env_file.exists():
        file_names = set(_env_assignments(env_file.read_text(encoding="utf-8")))
    stale = tuple(name for name in _DEPRECATED if os.environ.get(name) or name in file_names)
    if stale:
        print(f"FAIL deprecated environment variable(s): {', '.join(stale)}")
        print("Use VFBIZ_AI_GENERATION_PROVIDER/MODEL and VFBIZ_AI_EMBEDDING_PROVIDER/MODEL.")
        return 2

    try:
        settings = Settings()
    except ValidationError as error:
        print("FAIL typed AI configuration is invalid")
        for item in error.errors(include_url=False):
            location = ".".join(str(part) for part in item["loc"])
            print(f"- {location}: {item['msg']}")
        return 2

    print(f"OK configuration validated ({settings.environment})")
    print(f"- local env file: {'present' if env_file.exists() else 'not present'}")
    print(f"- PostgreSQL: {'configured' if settings.database_url else 'not configured'}")
    print(f"- Redis: {'configured' if settings.redis_url else 'not configured'}")
    print(f"- generation provider: {settings.generation_provider}")
    print(f"- embedding provider: {settings.embedding_provider}")
    print(
        "- release-manifest bootstrap digest: "
        + ("configured" if settings.model_release_manifest_sha256 else "not configured")
    )
    release_blocked = (
        settings.generation_provider == "disabled"
        or settings.embedding_provider == "disabled"
        or settings.model_release_manifest_sha256 is None
    )
    if release_blocked:
        print(
            "WARN configuration is incomplete; factual answers also require an approved, "
            "active release resolved from PostgreSQL"
        )
    else:
        print(
            "WARN configuration and bootstrap digest are not release approval; PostgreSQL "
            "authority, signed readiness and release gates must pass before dispatch"
        )

    live_failed = False
    if arguments.live:
        print("Live probes (identifiers and secrets are intentionally omitted):")
        results = asyncio.run(run_live_probes(settings))
        for result in results:
            _print_probe(result)
        live_failed = any(not result.passed for result in results)
    if live_failed:
        return 2
    return 1 if release_blocked else 0


if __name__ == "__main__":
    sys.exit(main())
