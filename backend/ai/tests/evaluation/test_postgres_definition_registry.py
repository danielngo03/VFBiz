import os
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import insert, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.evaluation.domain import (
    AuthorityClass,
    EvaluationRunState,
    EvaluationSuiteAuthority,
    EvaluationSuiteSnapshot,
    canonical_json,
    digest_document,
    evaluation_case_bindings_digest,
)
from app.modules.evaluation.infrastructure.models import (
    EvaluationDefinitionReleaseRecord,
)
from app.modules.evaluation.infrastructure.postgres_definition_registry import (
    PostgresEvaluationDefinitionRegistry,
)
from app.modules.evaluation.infrastructure.runtime import (
    build_evaluation_runtime_from_database_urls,
)
from app.platform.config import Settings
from app.platform.database.session import (
    create_engine,
    create_session_factory,
)
from tests.evaluation.test_evaluation_planning import (
    baseline_policy,
    definitions,
    released_suite,
    request,
)

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)

NOW = datetime(2026, 7, 31, 12, tzinfo=UTC)


def _release_values(
    *,
    kind: str,
    key: str,
    revision: str,
    document: dict[str, object],
) -> dict[str, object]:
    payload = canonical_json(document)
    return {
        "definition_kind": kind,
        "definition_key": key,
        "revision": revision,
        "content_digest": digest_document(document),
        "canonical_payload": payload,
        "release_evidence_uri": "evidence://evaluation-definition/test",
        "released_by_subject": str(
            document.get(
                "release_owner_subject",
                "subject:test-release-owner",
            )
        ),
        "released_at": NOW,
    }


async def _create_login_role_factories(
    *,
    engine: AsyncEngine,
    database_url: str,
) -> tuple[
    dict[str, async_sessionmaker[AsyncSession]],
    tuple[AsyncEngine, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    suffix = uuid4().hex
    role_password = uuid4().hex
    groups = {
        "runner": "vfbiz_ai_evaluation_runner",
        "sealer": "vfbiz_ai_evaluation_sealer",
        "reader": "vfbiz_ai_evaluation_reader",
    }
    role_names = tuple(f"vfbiz_eval_test_{capability}_{suffix}" for capability in groups)
    async with engine.begin() as connection:
        database_name = await connection.scalar(text("SELECT current_database()"))
        assert isinstance(database_name, str)
        quoted_database_name = database_name.replace('"', '""')
        for role_name, group_name in zip(
            role_names,
            groups.values(),
            strict=True,
        ):
            await connection.execute(
                text(
                    f'CREATE ROLE "{role_name}" LOGIN PASSWORD '
                    f"'{role_password}' IN ROLE {group_name}"
                )
            )
            capability = group_name.removeprefix("vfbiz_ai_evaluation_")
            schema_name = {
                "runner": "vfbiz_eval_runner",
                "sealer": "vfbiz_eval_sealer",
                "reader": "vfbiz_eval_reader",
            }[capability]
            await connection.execute(
                text(
                    f'ALTER ROLE "{role_name}" IN DATABASE '
                    f'"{quoted_database_name}" SET search_path = '
                    f"{schema_name}, public"
                )
            )
    base_url = make_url(database_url)
    role_urls = tuple(
        base_url.set(
            username=role_name,
            password=role_password,
        ).render_as_string(hide_password=False)
        for role_name in role_names
    )
    role_engines = tuple(create_engine(role_url) for role_url in role_urls)
    factories = {
        capability: create_session_factory(role_engine)
        for capability, role_engine in zip(
            groups,
            role_engines,
            strict=True,
        )
    }
    return factories, role_engines, role_names, role_urls


async def _drop_login_roles(
    *,
    engine: AsyncEngine,
    role_engines: tuple[AsyncEngine, ...],
    role_names: tuple[str, ...],
) -> None:
    for role_engine in role_engines:
        await role_engine.dispose()
    async with engine.begin() as connection:
        for role_name in role_names:
            await connection.execute(text(f'DROP ROLE "{role_name}"'))


def _sqlstate(error: DBAPIError) -> str | None:
    original = error.orig
    return getattr(original, "sqlstate", None)


@pytest.mark.asyncio
async def test_postgres_registry_loads_only_exact_released_definitions() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    role_engines: tuple[AsyncEngine, ...] = ()
    role_names: tuple[str, ...] = ()
    resources = None
    benchmark, metric, grader, calibration = definitions()
    benchmark = replace(
        benchmark,
        authority_class=AuthorityClass.PUBLIC_DIAGNOSTIC,
    )
    released = released_suite()
    suite_authority = EvaluationSuiteAuthority.issue(
        suite_id=released.suite_id,
        authority_class=AuthorityClass.PUBLIC_DIAGNOSTIC,
        qualification_profile=released.qualification_profile,
        qualification_policy_digest=released.qualification_policy_digest,
        case_bindings_digest=evaluation_case_bindings_digest(released.case_bindings),
        case_composition_digest=released.case_composition_digest,
        risk_taxonomy_digest=released.risk_taxonomy_digest,
        provenance_digest=released.provenance_digest,
        provenance_status=released.provenance_status,
        provenance_evidence_uri=released.provenance_evidence_uri,
        contamination_scan_digest=released.contamination_scan_digest,
        contamination_status=released.contamination_status,
        contamination_evidence_uri=released.contamination_evidence_uri,
        held_out=released.held_out,
        author_subject=released.author_subject,
        evaluator_subject=released.evaluator_subject,
        release_owner_subject=released.release_owner_subject,
    )
    suite = EvaluationSuiteSnapshot.issue(
        suite_id=released.suite_id,
        case_bindings=released.case_bindings,
        authority=suite_authority,
    )
    benchmark = replace(benchmark, suite_digest=suite.suite_digest)
    assert suite_authority.authority_digest == suite.authority_record_digest
    policy = baseline_policy()
    releases = (
        _release_values(
            kind="benchmark",
            key=benchmark.benchmark_id,
            revision=benchmark.revision,
            document=benchmark.canonical_document,
        ),
        _release_values(
            kind="metric",
            key=metric.revision,
            revision=metric.revision,
            document=metric.canonical_document,
        ),
        _release_values(
            kind="grader",
            key=grader.revision,
            revision=grader.revision,
            document=grader.canonical_document,
        ),
        _release_values(
            kind="calibration",
            key=calibration.grader_revision,
            revision=calibration.evidence_digest,
            document=calibration.contract_document,
        ),
        _release_values(
            kind="suite-authority",
            key=suite.suite_id,
            revision=suite_authority.authority_digest,
            document=suite_authority.contract_document,
        ),
        _release_values(
            kind="suite",
            key=suite.suite_id,
            revision=suite.suite_digest,
            document=suite.contract_document,
        ),
        _release_values(
            kind="baseline-policy",
            key=policy.policy_digest,
            revision=policy.policy_digest,
            document=policy.contract_document,
        ),
    )
    try:
        forged_acceptance = EvaluationSuiteAuthority.issue(
            suite_id=released.suite_id,
            authority_class=AuthorityClass.VINFAST_ACCEPTANCE,
            qualification_profile=released.qualification_profile,
            qualification_policy_digest=released.qualification_policy_digest,
            case_bindings_digest=evaluation_case_bindings_digest(released.case_bindings),
            case_composition_digest=released.case_composition_digest,
            risk_taxonomy_digest=released.risk_taxonomy_digest,
            provenance_digest=released.provenance_digest,
            provenance_status="verified",
            provenance_evidence_uri="evidence://forged/provenance",
            contamination_scan_digest=released.contamination_scan_digest,
            contamination_status="passed",
            contamination_evidence_uri="evidence://forged/contamination",
            held_out=True,
            author_subject="subject:forged-author",
            evaluator_subject="subject:forged-evaluator",
            release_owner_subject="subject:forged-release-owner",
        )
        with pytest.raises(
            IntegrityError,
            match="invalid evaluation suite authority record",
        ):
            async with sessions() as session, session.begin():
                await session.execute(
                    insert(EvaluationDefinitionReleaseRecord).values(
                        **_release_values(
                            kind="suite-authority",
                            key=forged_acceptance.suite_id,
                            revision=forged_acceptance.authority_digest,
                            document=forged_acceptance.contract_document,
                        )
                    )
                )

        async with sessions() as session, session.begin():
            for values in releases:
                await session.execute(insert(EvaluationDefinitionReleaseRecord).values(**values))

        role_factories, role_engines, role_names, role_urls = await _create_login_role_factories(
            engine=engine,
            database_url=settings.database_url,
        )
        registry = PostgresEvaluationDefinitionRegistry(role_factories["reader"])
        assert (
            await registry.get_benchmark(
                benchmark.benchmark_id,
                benchmark.revision,
            )
            == benchmark
        )
        assert await registry.get_metric(metric.revision) == metric
        assert await registry.get_grader(grader.revision) == grader
        assert await registry.get_calibration(grader.revision) == calibration
        assert await registry.get_suite(suite.suite_id, suite.suite_digest) == suite
        assert await registry.get_baseline_policy(policy.policy_digest) == policy
        assert await registry.get_metric("unknown-v1") is None
        resources = build_evaluation_runtime_from_database_urls(
            runner_database_url=role_urls[0],
            sealer_database_url=role_urls[1],
            definition_reader_database_url=role_urls[2],
            clock=lambda: datetime.now(UTC),
        )
        planned = await resources.runtime.planner.plan(
            replace(
                request(),
                required_authority=AuthorityClass.PUBLIC_DIAGNOSTIC,
            )
        )
        registered = await resources.runtime.registration.register(planned)
        assert registered.plan_digest == planned.content_digest

        async with role_factories["runner"]() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE ai_evaluation_run "
                    "SET status = 'queued', row_version = row_version + 1 "
                    "WHERE run_key = :run_key"
                ),
                {"run_key": planned.run_id},
            )
        await resources.runtime.execution.materialize(
            run_id=planned.run_id,
            suite=suite,
            shard_count=1,
        )
        async with role_factories["runner"]() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE ai_evaluation_run "
                    "SET status = 'running', row_version = row_version + 1 "
                    "WHERE run_key = :run_key"
                ),
                {"run_key": planned.run_id},
            )
        lease = await resources.runtime.execution.claim(
            run_id=planned.run_id,
            worker_id="worker:role-regression",
            lease_seconds=60,
        )
        assert lease is not None

        with pytest.raises(
            DBAPIError,
            match="illegal evaluation task transition",
        ):
            async with role_factories["runner"]() as session, session.begin():
                await session.execute(
                    text(
                        "UPDATE ai_evaluation_case_task "
                        "SET attempt_count = attempt_count + 1, "
                        "lease_owner = 'worker:forged-retry', "
                        "lease_token = gen_random_uuid(), "
                        "lease_expires_at = now() + interval '60 seconds' "
                        "WHERE run_key = :run_key AND case_key = :case_key"
                    ),
                    {"run_key": planned.run_id, "case_key": lease.case_id},
                )

        cancelled = await resources.runtime.lifecycle.cancel(planned.run_id)
        assert cancelled.state is EvaluationRunState.CANCELLED
        with pytest.raises(
            DBAPIError,
            match="terminal evaluation run is immutable",
        ):
            async with role_factories["runner"]() as session, session.begin():
                await session.execute(
                    text(
                        "UPDATE ai_evaluation_run "
                        "SET status = 'requested', failure_code = NULL, "
                        "row_version = row_version + 1 "
                        "WHERE run_key = :run_key"
                    ),
                    {"run_key": planned.run_id},
                )

        async with sessions() as session, session.begin():
            await session.execute(
                update(EvaluationDefinitionReleaseRecord)
                .where(
                    EvaluationDefinitionReleaseRecord.definition_kind == "metric",
                    EvaluationDefinitionReleaseRecord.definition_key == metric.revision,
                )
                .values(revoked_at=NOW)
            )
        assert await registry.get_metric(metric.revision) is None
    finally:
        if resources is not None:
            await resources.close()
        if role_names:
            await _drop_login_roles(
                engine=engine,
                role_engines=role_engines,
                role_names=role_names,
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_registry_rejects_noncanonical_or_self_hashed_payload() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    _, metric, _, _ = definitions()
    values = _release_values(
        kind="metric",
        key=metric.revision,
        revision=metric.revision,
        document=metric.canonical_document,
    )
    try:
        noncanonical = dict(values)
        noncanonical["canonical_payload"] = '{"revision": "citation-validity-v1"}'
        noncanonical["content_digest"] = digest_document({"revision": "citation-validity-v1"})
        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                await session.execute(
                    insert(EvaluationDefinitionReleaseRecord).values(**noncanonical)
                )

        forged = dict(values)
        forged["content_digest"] = f"sha256:{'f' * 64}"
        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                await session.execute(insert(EvaluationDefinitionReleaseRecord).values(**forged))

        aliased = dict(values)
        aliased["definition_key"] = "column-alias-v1"
        aliased["revision"] = "column-alias-v1"
        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                await session.execute(insert(EvaluationDefinitionReleaseRecord).values(**aliased))

        for invalid_revision in ("missing", "null"):
            identity_document = dict(metric.canonical_document)
            if invalid_revision == "missing":
                identity_document.pop("revision")
            else:
                identity_document["revision"] = None
            identity_values = _release_values(
                kind="metric",
                key=metric.revision,
                revision=metric.revision,
                document=identity_document,
            )
            with pytest.raises(IntegrityError):
                async with sessions() as session, session.begin():
                    await session.execute(
                        insert(EvaluationDefinitionReleaseRecord).values(**identity_values)
                    )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_evaluation_runtime_roles_have_no_base_table_dml() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    role_engines: tuple[AsyncEngine, ...] = ()
    role_names: tuple[str, ...] = ()
    try:
        async with sessions() as session:
            checks = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT
                          has_table_privilege(
                            'vfbiz_ai_evaluation_runner',
                            'public.ai_evaluation_run',
                            'INSERT,UPDATE,DELETE'
                          ) AS runner_base_dml,
                          has_table_privilege(
                            'vfbiz_ai_evaluation_runner',
                            'vfbiz_eval_runner.ai_evaluation_run',
                            'INSERT,UPDATE'
                          ) AS runner_capability,
                          has_table_privilege(
                            'vfbiz_ai_evaluation_runner',
                            'vfbiz_eval_runner.ai_evaluation_evidence_bundle',
                            'INSERT'
                          ) AS runner_can_seal,
                          has_table_privilege(
                            'vfbiz_ai_evaluation_sealer',
                            'public.ai_evaluation_evidence_bundle',
                            'INSERT,UPDATE,DELETE'
                          ) AS sealer_base_dml,
                          has_table_privilege(
                            'vfbiz_ai_evaluation_sealer',
                            'vfbiz_eval_sealer.ai_evaluation_evidence_bundle',
                            'INSERT'
                          ) AS sealer_capability,
                          has_table_privilege(
                            'vfbiz_ai_evaluation_sealer',
                            'vfbiz_eval_sealer.ai_evaluation_case_result',
                            'INSERT,UPDATE,DELETE'
                          ) AS sealer_can_write_results,
                          has_table_privilege(
                            'vfbiz_ai_evaluation_reader',
                            'vfbiz_eval_reader.ai_evaluation_definition_release',
                            'SELECT'
                          ) AS reader_capability
                        """
                        )
                    )
                )
                .mappings()
                .one()
            )
        assert checks == {
            "runner_base_dml": False,
            "runner_capability": True,
            "runner_can_seal": False,
            "sealer_base_dml": False,
            "sealer_capability": True,
            "sealer_can_write_results": False,
            "reader_capability": True,
        }
        role_factories, role_engines, role_names, _ = await _create_login_role_factories(
            engine=engine,
            database_url=settings.database_url,
        )
        for capability, role_name in zip(
            ("runner", "sealer", "reader"),
            role_names,
            strict=True,
        ):
            async with role_factories[capability]() as session:
                assert await session.scalar(text("SELECT current_user")) == role_name

        with pytest.raises(DBAPIError) as runner_denied:
            async with role_factories["runner"]() as session, session.begin():
                await session.execute(
                    text("INSERT INTO ai_evaluation_evidence_bundle (run_key) VALUES ('forbidden')")
                )
        assert _sqlstate(runner_denied.value) == "42501"

        with pytest.raises(DBAPIError) as sealer_reaches_table_guard:
            async with role_factories["sealer"]() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO ai_evaluation_evidence_bundle (run_key) VALUES ('incomplete')"
                    )
                )
        assert _sqlstate(sealer_reaches_table_guard.value) != "42501"

        with pytest.raises(DBAPIError) as reader_denied:
            async with role_factories["reader"]() as session, session.begin():
                await session.execute(
                    text(
                        "UPDATE ai_evaluation_definition_release SET revoked_at = now() WHERE false"
                    )
                )
        assert _sqlstate(reader_denied.value) == "42501"
    finally:
        if role_names:
            await _drop_login_roles(
                engine=engine,
                role_engines=role_engines,
                role_names=role_names,
            )
        await engine.dispose()
