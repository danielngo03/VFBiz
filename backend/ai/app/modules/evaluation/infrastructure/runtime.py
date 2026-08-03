from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.evaluation.application.execution import (
    EvaluationCaseExecutionService,
    EvaluationQualificationRunner,
    EvaluationRunLifecycleService,
    EvaluationRunRegistrationService,
    EvidenceBundleAuthority,
)
from app.modules.evaluation.application.planning import EvaluationPlanner
from app.modules.evaluation.infrastructure.postgres_definition_registry import (
    PostgresEvaluationDefinitionRegistry,
)
from app.modules.evaluation.infrastructure.postgres_evidence_repository import (
    PostgresEvaluationEvidenceRepository,
)
from app.modules.evaluation.infrastructure.postgres_execution_repository import (
    PostgresEvaluationExecutionRepository,
)
from app.modules.evaluation.infrastructure.postgres_run_registry import (
    PostgresEvaluationRunRegistry,
)
from app.platform.database.session import create_engine, create_session_factory


@dataclass(frozen=True, slots=True)
class EvaluationRuntime:
    planner: EvaluationPlanner
    registration: EvaluationRunRegistrationService
    lifecycle: EvaluationRunLifecycleService
    execution: EvaluationCaseExecutionService
    evidence: EvidenceBundleAuthority
    qualification: EvaluationQualificationRunner


@dataclass(frozen=True, slots=True)
class EvaluationRuntimeResources:
    runtime: EvaluationRuntime
    engines: tuple[AsyncEngine, AsyncEngine, AsyncEngine]

    async def close(self) -> None:
        for engine in self.engines:
            await engine.dispose()


def build_evaluation_runtime(
    *,
    runner_sessions: async_sessionmaker[AsyncSession],
    sealer_sessions: async_sessionmaker[AsyncSession],
    definition_sessions: async_sessionmaker[AsyncSession],
    clock: Callable[[], datetime],
) -> EvaluationRuntime:
    definitions = PostgresEvaluationDefinitionRegistry(definition_sessions)
    runner_runs = PostgresEvaluationRunRegistry(runner_sessions)
    sealer_runs = PostgresEvaluationRunRegistry(sealer_sessions)
    execution = PostgresEvaluationExecutionRepository(runner_sessions)
    evidence = PostgresEvaluationEvidenceRepository(sealer_sessions)
    planner = EvaluationPlanner(registry=definitions, clock=clock)
    registration = EvaluationRunRegistrationService(runner_runs)
    lifecycle = EvaluationRunLifecycleService(runner_runs)
    execution_service = EvaluationCaseExecutionService(
        runs=runner_runs,
        execution=execution,
        clock=clock,
    )
    evidence_authority = EvidenceBundleAuthority(
        runs=sealer_runs,
        evidence=evidence,
        definitions=definitions,
        clock=clock,
    )
    return EvaluationRuntime(
        planner=planner,
        registration=registration,
        lifecycle=lifecycle,
        execution=execution_service,
        evidence=evidence_authority,
        qualification=EvaluationQualificationRunner(
            planner=planner,
            registration=registration,
            lifecycle=lifecycle,
            execution=execution_service,
            evidence=evidence_authority,
        ),
    )


def build_evaluation_runtime_from_database_urls(
    *,
    runner_database_url: str,
    sealer_database_url: str,
    definition_reader_database_url: str,
    clock: Callable[[], datetime],
) -> EvaluationRuntimeResources:
    urls = (
        runner_database_url,
        sealer_database_url,
        definition_reader_database_url,
    )
    if len(set(urls)) != 3:
        raise ValueError(
            "evaluation runtime requires distinct role-specific database URLs"
        )
    runner_engine = create_engine(
        runner_database_url,
        search_path="vfbiz_eval_runner,public",
    )
    sealer_engine = create_engine(
        sealer_database_url,
        search_path="vfbiz_eval_sealer,public",
    )
    definition_engine = create_engine(
        definition_reader_database_url,
        search_path="vfbiz_eval_reader,public",
    )
    engines = (runner_engine, sealer_engine, definition_engine)
    return EvaluationRuntimeResources(
        runtime=build_evaluation_runtime(
            runner_sessions=create_session_factory(runner_engine),
            sealer_sessions=create_session_factory(sealer_engine),
            definition_sessions=create_session_factory(definition_engine),
            clock=clock,
        ),
        engines=engines,
    )
