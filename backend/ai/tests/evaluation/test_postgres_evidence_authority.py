import asyncio
import os
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.modules.evaluation.application.execution import (
    EvaluationCaseExecutionService,
    EvaluationExecutionError,
    EvaluationRunRegistrationService,
    EvidenceBundleAuthority,
)
from app.modules.evaluation.application.ports import (
    EvaluationRunConcurrencyError,
)
from app.modules.evaluation.application.release_evidence_authority import (
    AssistantReleaseEvidenceQuery,
    SealedAssistantReleaseEvidenceAuthority,
)
from app.modules.evaluation.domain import (
    MANDATORY_HARD_GATE_REVISIONS,
    AuthorityClass,
    BaselinePolicySnapshot,
    BudgetPolicy,
    CalibrationBinding,
    EvaluationCaseResult,
    EvaluationRunPlan,
    EvaluationRunState,
    EvaluationSuiteAuthority,
    EvaluationSuiteSnapshot,
    EvaluationUsage,
    GraderCalibration,
    GraderCaseOutcome,
    GraderDefinition,
    GraderKind,
    MetricCaseOutcome,
    build_verified_evidence,
    canonical_json,
    evaluation_case_bindings_digest,
)
from app.modules.evaluation.infrastructure.models import (
    EvaluationCaseResultRecord,
    EvaluationCaseTaskRecord,
    EvaluationDefinitionReleaseRecord,
    EvaluationEvidenceBundleRecord,
    EvaluationRunRecord,
)
from app.modules.evaluation.infrastructure.postgres_evidence_repository import (
    PostgresEvaluationEvidenceRepository,
)
from app.modules.evaluation.infrastructure.postgres_execution_repository import (
    PostgresEvaluationExecutionRepository,
)
from app.modules.evaluation.infrastructure.postgres_release_evidence import (
    PostgresAssistantReleaseEvidenceReader,
)
from app.modules.evaluation.infrastructure.postgres_run_registry import (
    PostgresEvaluationRunRegistry,
)
from app.platform.config import Settings
from app.platform.database.session import (
    create_engine,
    create_session_factory,
)
from tests.evaluation.postgres_release_fixtures import (
    release_plan_definitions,
)

pytestmark = pytest.mark.skipif(
    os.getenv("VFBIZ_RUN_DB_INTEGRATION") != "1",
    reason="requires an isolated migrated PostgreSQL database",
)

SHA_A = f"sha256:{'a' * 64}"
SHA_B = f"sha256:{'b' * 64}"
SHA_C = f"sha256:{'c' * 64}"
SHA_D = f"sha256:{'d' * 64}"
NOW = datetime.now(UTC)


def policy() -> BaselinePolicySnapshot:
    return BaselinePolicySnapshot.issue(
        {
            "binary_interval": "wilson-95",
            "composite_score_authoritative": False,
            "hard_gates": [
                {"gate_revision": revision, "required_value": 0}
                for revision in sorted(MANDATORY_HARD_GATE_REVISIONS)
            ],
            "operational_budgets": {
                "latency_p95_ms": 5000,
                "normalized_cost_usd": 1,
                "provider_failure_rate": 0,
            },
            "paired_comparison": {
                "confidence": 0.95,
                "method": "paired-bootstrap",
                "samples": 10000,
            },
            "policy_id": "assistant-release-baseline",
            "protected_metrics": [
                {
                    "direction": "higher-is-better",
                    "metric_revision": "citation-validity-v1",
                    "non_inferiority_margin": 0,
                    "require_protected_95_bound": True,
                    "required_slices": ["all"],
                }
            ],
            "revision": "v1",
            "waiver_policy": {
                "authority_contract_id": ("https://vfbiz.example/contracts/governance/waiver/v1"),
                "requires_expiry": True,
                "requires_mitigation": True,
                "requires_owner": True,
            },
        }
    )


def graders() -> tuple[str, ...]:
    return tuple(sorted(MANDATORY_HARD_GATE_REVISIONS))


def suite() -> EvaluationSuiteSnapshot:
    bindings = (
        ("case.001", SHA_A),
        ("case.002", SHA_B),
        ("case.003", SHA_C),
    )
    authority = EvaluationSuiteAuthority.issue(
        suite_id="integration-suite-v1",
        authority_class=AuthorityClass.PUBLIC_DIAGNOSTIC,
        qualification_profile="integration-diagnostic-v1",
        qualification_policy_digest=SHA_A,
        case_bindings_digest=evaluation_case_bindings_digest(bindings),
        case_composition_digest=SHA_B,
        risk_taxonomy_digest=SHA_A,
        provenance_digest=SHA_B,
        provenance_status="verified",
        provenance_evidence_uri="evidence://suite/provenance",
        contamination_scan_digest=SHA_C,
        contamination_status="passed",
        contamination_evidence_uri="evidence://suite/contamination",
        held_out=True,
        author_subject="subject:integration-author",
        evaluator_subject="subject:integration-evaluator",
        release_owner_subject="subject:integration-release-owner",
    )
    return EvaluationSuiteSnapshot.issue(
        suite_id="integration-suite-v1",
        case_bindings=bindings,
        authority=authority,
    )


def calibration(revision: str) -> GraderCalibration:
    return GraderCalibration.issue(
        grader_revision=revision,
        grader_definition_digest=SHA_A,
        implementation_digest=SHA_B,
        calibrated_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=30),
        human_labelled_suite_digest=SHA_D,
        sample_size=30,
        confusion_matrix=(15, 15, 0, 0),
        balanced_accuracy=1,
        f1=1,
        slice_metrics=(
            ("all", 30, 1, 1, 15, 15, 0, 0),
            ("high-risk", 30, 1, 1, 15, 15, 0, 0),
        ),
    )


class DefinitionRegistry:
    async def get_suite(
        self,
        suite_id: str,
        suite_digest: str,
    ) -> EvaluationSuiteSnapshot | None:
        released = suite()
        return (
            released
            if (suite_id, suite_digest) == (released.suite_id, released.suite_digest)
            else None
        )

    async def get_baseline_policy(
        self,
        policy_digest: str,
    ) -> BaselinePolicySnapshot | None:
        baseline = policy()
        return baseline if baseline.policy_digest == policy_digest else None

    async def get_grader(
        self,
        revision: str,
    ) -> GraderDefinition | None:
        if revision not in graders():
            return None
        return GraderDefinition(
            revision=revision,
            kind=(
                GraderKind.CITATION
                if revision == "citation-validity-v1"
                else GraderKind.DETERMINISTIC
            ),
            definition_digest=SHA_A,
            implementation_digest=SHA_B,
            calibration_required=True,
        )

    async def get_calibration(
        self,
        grader_revision: str,
    ) -> GraderCalibration | None:
        return calibration(grader_revision) if grader_revision in graders() else None

    async def get_benchmark(self, benchmark_id: str, revision: str) -> None:
        del benchmark_id, revision
        return None

    async def get_metric(self, revision: str) -> None:
        del revision
        return None


def plan(run_id: str) -> EvaluationRunPlan:
    released_suite = suite()
    return EvaluationRunPlan(
        run_id=run_id,
        authority_class=AuthorityClass.PUBLIC_DIAGNOSTIC,
        candidate_release_id="assistant-2.0.0",
        candidate_manifest_digest=SHA_C,
        baseline_release_id="assistant-1.9.0",
        baseline_manifest_digest=SHA_D,
        benchmark_definition_digest=SHA_B,
        suite_id=released_suite.suite_id,
        suite_digest=released_suite.suite_digest,
        runner_image_digest=SHA_A,
        harness_revision="integration-harness-v1",
        tool_simulator_revision="integration-tools-v1",
        metric_revisions=("citation-validity-v1",),
        grader_revisions=graders(),
        grader_calibrations=tuple(
            CalibrationBinding(
                grader_revision=revision,
                grader_definition_digest=SHA_A,
                implementation_digest=SHA_B,
                calibration_digest=calibration(revision).evidence_digest,
                human_labelled_suite_digest=SHA_D,
                calibrated_at=NOW - timedelta(days=1),
                expires_at=NOW + timedelta(days=30),
            )
            for revision in graders()
        ),
        environment_revision="integration-v1",
        random_seed=20260730,
        budgets=BudgetPolicy(
            max_input_tokens=100,
            max_output_tokens=100,
            max_duration_seconds=10,
            max_cost_usd=1,
        ),
        evaluation_claim="Validate the governed assistant candidate.",
        subject_under_test="assistant-2.0.0",
        requested_at=NOW - timedelta(minutes=1),
        max_attempts=3,
        retryable_failure_codes=("provider-timeout", "runner-unavailable"),
        grader_kinds=tuple(
            (
                revision,
                ("citation" if revision == "citation-validity-v1" else "deterministic"),
            )
            for revision in graders()
        ),
        baseline_policy_digest=policy().policy_digest,
    )


def result(
    run_id: str,
    case_id: str,
    case_digest: str,
    *,
    metric_value: float = 1,
) -> EvaluationCaseResult:
    return EvaluationCaseResult.issue(
        run_id=run_id,
        case_id=case_id,
        case_digest=case_digest,
        attempt=1,
        status="valid",
        output_digest=SHA_C,
        latency_ms=100,
        usage=EvaluationUsage(
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.01,
        ),
        sanitized_trace_ref="artifact://evaluation/redacted",
        metric_outputs=(
            MetricCaseOutcome(
                metric_revision="citation-validity-v1",
                slice="all",
                value=metric_value,
            ),
        ),
        grader_outputs=tuple(
            GraderCaseOutcome(
                grader_revision=revision,
                outcome="pass",
                evidence_digest=SHA_D,
            )
            for revision in graders()
        ),
    )


def direct_result_values(
    case_result: EvaluationCaseResult,
    *,
    lease_owner: str,
    lease_token: str,
) -> dict[str, object]:
    return {
        "run_key": case_result.run_id,
        "case_key": case_result.case_id,
        "case_digest": case_result.case_digest,
        "attempt": case_result.attempt,
        "lease_owner": lease_owner,
        "lease_token": UUID(lease_token),
        "status": case_result.status,
        "output_digest": case_result.output_digest,
        "latency_ms": case_result.latency_ms,
        "usage": case_result.semantic_document["usage"],
        "sanitized_trace_ref": case_result.sanitized_trace_ref,
        "grader_outputs": case_result.semantic_document["grader_outputs"],
        "metric_outputs": case_result.semantic_document["metric_outputs"],
        "validity_flags": list(case_result.validity_flags),
        "result_digest": case_result.result_digest,
        "canonical_payload": case_result.canonical_payload,
    }


@pytest.mark.asyncio
async def test_postgres_seal_is_atomic_immutable_and_blocks_direct_ready() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    runs = PostgresEvaluationRunRegistry(sessions)
    evidence = PostgresEvaluationEvidenceRepository(sessions)
    execution_repository = PostgresEvaluationExecutionRepository(sessions)
    registration = EvaluationRunRegistrationService(runs)
    execution = EvaluationCaseExecutionService(
        runs=runs,
        execution=execution_repository,
        clock=lambda: datetime.now(UTC),
    )
    authority = EvidenceBundleAuthority(
        runs=runs,
        evidence=evidence,
        definitions=DefinitionRegistry(),  # type: ignore[arg-type]
        clock=lambda: NOW,
    )
    run_id = f"eval:integration:evidence:{uuid4()}"
    direct_run_id = f"eval:integration:direct:{uuid4()}"
    try:
        numeric_document: dict[str, object] = {
            "large": 1e21,
            "negative_zero": -0.0,
            "small": 1e-7,
            "text": "Việt",
            "whole": 1.0,
        }
        expected_canonical = canonical_json(numeric_document)
        async with sessions() as session:
            database_canonical = await session.scalar(
                text("SELECT evaluation_canonical_json(CAST(:document AS jsonb))"),
                {"document": expected_canonical},
            )
        assert database_canonical == expected_canonical

        await release_plan_definitions(
            sessions,
            plan(run_id).canonical_document,
            suite_document=suite().contract_document,
            policy_document=policy().contract_document,
        )
        requested = await registration.register(plan(run_id))
        queued = requested.transition(EvaluationRunState.QUEUED)
        await runs.save(queued, expected_version=requested.row_version)
        await execution.materialize(
            run_id=run_id,
            suite=suite(),
            shard_count=2,
        )
        running = queued.transition(EvaluationRunState.RUNNING)
        await runs.save(running, expected_version=queued.row_version)
        case_digests = dict(suite().case_bindings)
        for index in range(len(case_digests)):
            lease = await execution.claim(
                run_id=run_id,
                worker_id=f"worker:{index}",
                lease_seconds=60,
            )
            assert lease is not None
            issued_result = result(
                run_id,
                lease.case_id,
                case_digests[lease.case_id],
                metric_value=1 if index == 0 else 0,
            )
            if index == 0:
                with pytest.raises(IntegrityError):
                    async with sessions() as session, session.begin():
                        forged = direct_result_values(
                            issued_result,
                            lease_owner="attacker",
                            lease_token=lease.lease_token,
                        )
                        await session.execute(insert(EvaluationCaseResultRecord).values(**forged))
                with pytest.raises(IntegrityError):
                    async with sessions() as session, session.begin():
                        malformed = direct_result_values(
                            issued_result,
                            lease_owner=lease.lease_owner,
                            lease_token=lease.lease_token,
                        )
                        malformed["usage"] = {
                            "cost_usd": -1,
                            "input_tokens": 10,
                            "output_tokens": 5,
                        }
                        await session.execute(
                            insert(EvaluationCaseResultRecord).values(**malformed)
                        )
            await execution.complete(
                lease=lease,
                result=issued_result,
            )
        progressed = await runs.get(run_id)
        assert progressed is not None
        assert progressed.completed_case_count == 3
        grading = progressed.transition(EvaluationRunState.GRADING)
        await runs.save(grading, expected_version=progressed.row_version)
        comparing = grading.transition(EvaluationRunState.COMPARING)
        await runs.save(comparing, expected_version=grading.row_version)

        planned = plan(run_id)
        candidate_evidence = build_verified_evidence(
            run_id=run_id,
            plan_digest=planned.content_digest,
            authority_class=planned.authority_class,
            suite=suite(),
            cases=await evidence.list_case_results(run_id),
            required_metrics=planned.metric_revisions,
            required_graders=planned.grader_revisions,
            grader_kinds=planned.grader_kinds,
            grader_calibrations=planned.grader_calibrations,
            budget=planned.budgets,
            baseline_policy=policy(),
            benchmark_definition_digest=planned.benchmark_definition_digest,
            candidate_release_id=planned.candidate_release_id,
            candidate_manifest_digest=planned.candidate_manifest_digest,
            baseline_release_id=planned.baseline_release_id,
            baseline_manifest_digest=planned.baseline_manifest_digest,
            created_at=NOW,
            started_at=planned.requested_at,
        )
        authority_tamper_cases: tuple[tuple[str, object], ...] = (
            ("human_approval_included", True),
            ("case_set_complete", False),
            ("authority_class", AuthorityClass.PUBLIC_DIAGNOSTIC.value),
            ("run_request_digest", SHA_A),
        )
        for field, forged_value in authority_tamper_cases:
            forged_document = deepcopy(candidate_evidence.semantic_document)
            forged_document[field] = forged_value
            forged_payload = canonical_json(forged_document)
            forged_digest = f"sha256:{sha256(forged_payload.encode()).hexdigest()}"
            forged_contract = {
                **forged_document,
                "bundle_digest": forged_digest,
            }
            with pytest.raises(IntegrityError):
                async with sessions() as session, session.begin():
                    await session.execute(
                        insert(EvaluationEvidenceBundleRecord).values(
                            run_key=run_id,
                            plan_digest=planned.content_digest,
                            bundle_digest=forged_digest,
                            case_results_digest=str(forged_document["case_results_digest"]),
                            run_result_digest=str(forged_document["run_result_digest"]),
                            authority_class=str(forged_document["authority_class"]),
                            recommendation=str(forged_document["recommendation"]),
                            sealed_from_row_version=comparing.row_version,
                            suite_snapshot_payload=(candidate_evidence.suite_snapshot_payload),
                            baseline_policy_payload=(candidate_evidence.baseline_policy_payload),
                            run_result_payload=(candidate_evidence.run_result_payload),
                            canonical_document=forged_contract,
                            canonical_payload=forged_payload,
                        )
                    )

        seal_session = sessions()
        seal_transaction = await seal_session.begin()
        try:
            await seal_session.execute(
                insert(EvaluationEvidenceBundleRecord).values(
                    run_key=run_id,
                    plan_digest=planned.content_digest,
                    bundle_digest=candidate_evidence.bundle_digest,
                    case_results_digest=str(
                        candidate_evidence.semantic_document["case_results_digest"]
                    ),
                    run_result_digest=str(
                        candidate_evidence.semantic_document["run_result_digest"]
                    ),
                    authority_class=planned.authority_class.value,
                    recommendation=candidate_evidence.recommendation,
                    sealed_from_row_version=comparing.row_version,
                    suite_snapshot_payload=(candidate_evidence.suite_snapshot_payload),
                    baseline_policy_payload=(candidate_evidence.baseline_policy_payload),
                    run_result_payload=candidate_evidence.run_result_payload,
                    canonical_document=(candidate_evidence.contract_document),
                    canonical_payload=candidate_evidence.canonical_payload,
                )
            )
            with pytest.raises(DBAPIError):
                async with sessions() as revocation_session:
                    async with revocation_session.begin():
                        await revocation_session.execute(text("SET LOCAL lock_timeout = '100ms'"))
                        await revocation_session.execute(
                            update(EvaluationDefinitionReleaseRecord)
                            .where(
                                EvaluationDefinitionReleaseRecord.definition_kind == "suite",
                                EvaluationDefinitionReleaseRecord.definition_key
                                == suite().suite_id,
                                EvaluationDefinitionReleaseRecord.revision == suite().suite_digest,
                            )
                            .values(revoked_at=NOW)
                        )
        finally:
            await seal_transaction.rollback()
            await seal_session.close()

        sealed = await authority.seal(run_id=run_id)

        assert sealed.state is EvaluationRunState.DECISION_READY
        sealed_result = cast(
            dict[str, object],
            candidate_evidence.semantic_document["run_result"],
        )
        sealed_metrics = cast(
            list[dict[str, object]],
            sealed_result["metrics"],
        )
        assert sealed_metrics[0]["value"] == 0.333333333333333
        async with sessions() as session:
            bundle = await session.scalar(
                select(EvaluationEvidenceBundleRecord).where(
                    EvaluationEvidenceBundleRecord.run_key == run_id
                )
            )
            assert bundle is not None
        release_reader = PostgresAssistantReleaseEvidenceReader(sessions)
        release_snapshot = await release_reader.get_for_run(run_id)
        assert release_snapshot is not None
        assert release_snapshot.run_id == run_id
        assert release_snapshot.run_state == "decision_ready"
        assert (
            release_snapshot.run_evidence_bundle_digest
            == candidate_evidence.bundle_digest
        )
        assert release_snapshot.bundle_digest == candidate_evidence.bundle_digest
        assert release_snapshot.document_bundle_digest == candidate_evidence.bundle_digest
        assert release_snapshot.bundle_recommendation == "needs-human-decision"
        assert release_snapshot.document_recommendation == "needs-human-decision"
        assert release_snapshot.document_human_approval_included is False
        assert not await SealedAssistantReleaseEvidenceAuthority(
            release_reader
        ).verify(
            AssistantReleaseEvidenceQuery(
                evidence_ref=f"evaluation://{run_id}",
                evidence_sha256=candidate_evidence.bundle_digest.removeprefix(
                    "sha256:"
                ),
                candidate_release_id=planned.candidate_release_id,
                candidate_manifest_sha256=planned.candidate_manifest_digest.removeprefix(
                    "sha256:"
                ),
            )
        )
        assert release_snapshot.bundle_authority_class == "public-diagnostic"
        async with sessions() as session:
            with pytest.raises(IntegrityError):
                async with session.begin():
                    await session.execute(
                        update(EvaluationEvidenceBundleRecord)
                        .where(EvaluationEvidenceBundleRecord.run_key == run_id)
                        .values(recommendation="recommend")
                    )

        async with sessions() as session:
            with pytest.raises(IntegrityError):
                async with session.begin():
                    await session.execute(
                        update(EvaluationCaseResultRecord)
                        .where(EvaluationCaseResultRecord.run_key == run_id)
                        .values(latency_ms=0)
                    )

        for truncate_statement in (
            "TRUNCATE TABLE ai_evaluation_case_result",
            "TRUNCATE TABLE ai_evaluation_case_task",
            "TRUNCATE TABLE ai_evaluation_evidence_bundle CASCADE",
        ):
            async with sessions() as session:
                with pytest.raises(IntegrityError):
                    async with session.begin():
                        await session.execute(text(truncate_statement))

        async with sessions() as session:
            with pytest.raises(IntegrityError):
                async with session.begin():
                    await session.execute(
                        delete(EvaluationCaseTaskRecord).where(
                            EvaluationCaseTaskRecord.run_key == run_id
                        )
                    )

        await registration.register(plan(direct_run_id))
        async with sessions() as session:
            with pytest.raises(IntegrityError):
                async with session.begin():
                    await session.execute(
                        update(EvaluationRunRecord)
                        .where(EvaluationRunRecord.run_key == direct_run_id)
                        .values(
                            status=EvaluationRunState.DECISION_READY.value,
                            evidence_bundle_digest=SHA_A,
                        )
                    )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_execution_retries_cancels_and_blocks_overspend() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    runs = PostgresEvaluationRunRegistry(sessions)
    execution_repository = PostgresEvaluationExecutionRepository(sessions)
    registration = EvaluationRunRegistrationService(runs)
    execution = EvaluationCaseExecutionService(
        runs=runs,
        execution=execution_repository,
        clock=lambda: datetime.now(UTC),
    )
    retry_run_id = f"eval:integration:retry:{uuid4()}"
    exhausted_run_id = f"eval:integration:exhausted:{uuid4()}"
    budget_run_id = f"eval:integration:budget:{uuid4()}"
    try:
        await release_plan_definitions(
            sessions,
            plan(retry_run_id).canonical_document,
            suite_document=suite().contract_document,
            policy_document=policy().contract_document,
        )
        requested = await registration.register(plan(retry_run_id))
        queued = requested.transition(EvaluationRunState.QUEUED)
        await runs.save(queued, expected_version=requested.row_version)
        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                await session.execute(
                    insert(EvaluationCaseTaskRecord).values(
                        run_key=retry_run_id,
                        case_key="forged.case",
                        case_digest=SHA_A,
                        suite_digest=suite().suite_digest,
                        shard_index=0,
                        status="pending",
                        attempt_count=0,
                        max_attempts=2,
                    )
                )
        await execution.materialize(
            run_id=retry_run_id,
            suite=suite(),
            shard_count=2,
        )
        running = queued.transition(EvaluationRunState.RUNNING)
        await runs.save(running, expected_version=queued.row_version)
        first = await execution.claim(
            run_id=retry_run_id,
            worker_id="worker:first",
            lease_seconds=60,
        )
        assert first is not None
        with pytest.raises(IntegrityError, match="illegal evaluation task transition"):
            async with sessions() as session, session.begin():
                await session.execute(
                    update(EvaluationCaseTaskRecord)
                    .where(
                        EvaluationCaseTaskRecord.run_key == retry_run_id,
                        EvaluationCaseTaskRecord.case_key == first.case_id,
                    )
                    .values(
                        attempt_count=first.attempt + 1,
                        lease_owner="worker:direct-retry",
                        lease_token=uuid4(),
                        lease_expires_at=datetime.now(UTC) + timedelta(seconds=60),
                    )
                )
        known_retryable_failure = EvaluationCaseResult.issue(
            run_id=retry_run_id,
            case_id=first.case_id,
            case_digest=first.case_digest,
            attempt=first.attempt,
            status="failed",
            output_digest=None,
            latency_ms=5,
            usage=EvaluationUsage(
                input_tokens=3,
                output_tokens=0,
                cost_usd=0.000001,
            ),
            sanitized_trace_ref="evidence://provider-timeout/attempt-1",
            metric_outputs=(),
            grader_outputs=(),
            validity_flags=("provider-timeout",),
        )
        await execution.complete(lease=first, result=known_retryable_failure)
        second = await execution.claim(
            run_id=retry_run_id,
            worker_id="worker:second",
            lease_seconds=1,
        )
        assert second is not None
        assert second.case_id == first.case_id
        assert second.attempt == 2
        assert second.max_input_tokens == 97
        assert second.max_output_tokens == 100
        assert second.max_duration_ms == 9995
        assert second.max_cost_usd == 0.999999
        await asyncio.sleep(1.1)
        dishonest_unknown_usage = EvaluationCaseResult.issue(
            run_id=retry_run_id,
            case_id=second.case_id,
            case_digest=second.case_digest,
            attempt=second.attempt,
            status="failed",
            output_digest=None,
            latency_ms=0,
            usage=EvaluationUsage(
                input_tokens=0,
                output_tokens=0,
                cost_usd=0,
            ),
            sanitized_trace_ref=None,
            metric_outputs=(),
            grader_outputs=(),
            validity_flags=("runner-unavailable", "usage-unknown"),
        )
        with pytest.raises(
            IntegrityError,
            match="must reserve remaining budget",
        ):
            async with sessions() as session, session.begin():
                await session.execute(
                    insert(EvaluationCaseResultRecord).values(
                        **direct_result_values(
                            dishonest_unknown_usage,
                            lease_owner=second.lease_owner,
                            lease_token=second.lease_token,
                        )
                    )
                )
        claimed = await execution.claim(
            run_id=retry_run_id,
            worker_id="worker:after-expiry",
            lease_seconds=60,
        )
        assert claimed is None
        async with sessions() as session:
            expired_attempt = await session.scalar(
                select(EvaluationCaseResultRecord).where(
                    EvaluationCaseResultRecord.run_key == retry_run_id,
                    EvaluationCaseResultRecord.case_key == second.case_id,
                    EvaluationCaseResultRecord.attempt == 2,
                )
            )
            retried_task = await session.scalar(
                select(EvaluationCaseTaskRecord).where(
                    EvaluationCaseTaskRecord.run_key == retry_run_id,
                    EvaluationCaseTaskRecord.case_key == second.case_id,
                )
            )
            failed_run = await session.scalar(
                select(EvaluationRunRecord).where(EvaluationRunRecord.run_key == retry_run_id)
            )
        assert expired_attempt is not None
        assert expired_attempt.status == "failed"
        assert expired_attempt.validity_flags == [
            "runner-unavailable",
            "usage-unknown",
        ]
        assert expired_attempt.usage == {
            "cost_usd": plan(retry_run_id).budgets.max_cost_usd - 0.000001,
            "input_tokens": plan(retry_run_id).budgets.max_input_tokens - 3,
            "output_tokens": plan(retry_run_id).budgets.max_output_tokens,
        }
        assert retried_task is not None
        assert retried_task.status == "failed"
        assert retried_task.attempt_count == 2
        assert retried_task.max_attempts == plan(retry_run_id).max_attempts
        assert failed_run is not None
        assert failed_run.status == EvaluationRunState.FAILED.value
        with pytest.raises(IntegrityError, match="terminal evaluation run is immutable"):
            async with sessions() as session, session.begin():
                await session.execute(
                    update(EvaluationRunRecord)
                    .where(EvaluationRunRecord.run_key == retry_run_id)
                    .values(
                        status=EvaluationRunState.REQUESTED.value,
                        failure_code=None,
                    )
                )
        with pytest.raises(
            EvaluationRunConcurrencyError,
            match="requires running run",
        ):
            await execution.claim(
                run_id=retry_run_id,
                worker_id="worker:after-cancel",
                lease_seconds=60,
            )

        await release_plan_definitions(
            sessions,
            plan(exhausted_run_id).canonical_document,
            suite_document=suite().contract_document,
            policy_document=policy().contract_document,
        )
        exhausted_requested = await registration.register(plan(exhausted_run_id))
        exhausted_queued = exhausted_requested.transition(EvaluationRunState.QUEUED)
        await runs.save(
            exhausted_queued,
            expected_version=exhausted_requested.row_version,
        )
        await execution.materialize(
            run_id=exhausted_run_id,
            suite=suite(),
            shard_count=1,
        )
        exhausted_running = exhausted_queued.transition(EvaluationRunState.RUNNING)
        await runs.save(
            exhausted_running,
            expected_version=exhausted_queued.row_version,
        )
        exhausted_lease = await execution.claim(
            run_id=exhausted_run_id,
            worker_id="worker:exhaust-budget",
            lease_seconds=60,
        )
        assert exhausted_lease is not None
        exhausted_result = EvaluationCaseResult.issue(
            run_id=exhausted_run_id,
            case_id=exhausted_lease.case_id,
            case_digest=exhausted_lease.case_digest,
            attempt=exhausted_lease.attempt,
            status="failed",
            output_digest=None,
            latency_ms=exhausted_lease.max_duration_ms,
            usage=EvaluationUsage(
                input_tokens=exhausted_lease.max_input_tokens,
                output_tokens=exhausted_lease.max_output_tokens,
                cost_usd=exhausted_lease.max_cost_usd,
            ),
            sanitized_trace_ref="evidence://provider-timeout/exhausted-budget",
            metric_outputs=(),
            grader_outputs=(),
            validity_flags=("provider-timeout",),
        )
        await execution.complete(
            lease=exhausted_lease,
            result=exhausted_result,
        )
        assert (
            await execution.claim(
                run_id=exhausted_run_id,
                worker_id="worker:must-not-dispatch",
                lease_seconds=60,
            )
            is None
        )
        exhausted_run = await runs.get(exhausted_run_id)
        assert exhausted_run is not None
        assert exhausted_run.state is EvaluationRunState.FAILED
        assert exhausted_run.failure_code == "EVALUATION_BUDGET_EXHAUSTED"

        budget_plan = replace(
            plan(budget_run_id),
            benchmark_definition_digest=(f"sha256:{sha256(budget_run_id.encode()).hexdigest()}"),
            budgets=BudgetPolicy(
                max_input_tokens=1,
                max_output_tokens=1,
                max_duration_seconds=1,
                max_cost_usd=0.001,
            ),
        )
        await release_plan_definitions(
            sessions,
            budget_plan.canonical_document,
            suite_document=suite().contract_document,
            policy_document=policy().contract_document,
        )
        budget_requested = await registration.register(budget_plan)
        budget_queued = budget_requested.transition(EvaluationRunState.QUEUED)
        await runs.save(
            budget_queued,
            expected_version=budget_requested.row_version,
        )
        await execution.materialize(
            run_id=budget_run_id,
            suite=suite(),
            shard_count=1,
        )
        budget_running = budget_queued.transition(EvaluationRunState.RUNNING)
        await runs.save(
            budget_running,
            expected_version=budget_queued.row_version,
        )
        budget_lease = await execution.claim(
            run_id=budget_run_id,
            worker_id="worker:budget",
            lease_seconds=60,
        )
        assert budget_lease is not None
        with pytest.raises(
            EvaluationExecutionError,
            match="EVALUATION_RESULT_EXCEEDS_LEASE_BUDGET",
        ):
            await execution.complete(
                lease=budget_lease,
                result=result(
                    budget_run_id,
                    budget_lease.case_id,
                    dict(suite().case_bindings)[budget_lease.case_id],
                ),
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_execution_keeps_exact_cap_completed_run_valid() -> None:
    settings = Settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    runs = PostgresEvaluationRunRegistry(sessions)
    execution = EvaluationCaseExecutionService(
        runs=runs,
        execution=PostgresEvaluationExecutionRepository(sessions),
        clock=lambda: datetime.now(UTC),
    )
    registration = EvaluationRunRegistrationService(runs)
    run_id = f"eval:integration:exact-cap-complete:{uuid4()}"
    exact_cap_plan = replace(
        plan(run_id),
        benchmark_definition_digest=f"sha256:{sha256(run_id.encode()).hexdigest()}",
        budgets=BudgetPolicy(
            max_input_tokens=3,
            max_output_tokens=3,
            max_duration_seconds=3,
            max_cost_usd=0.000003,
        ),
    )
    try:
        await release_plan_definitions(
            sessions,
            exact_cap_plan.canonical_document,
            suite_document=suite().contract_document,
            policy_document=policy().contract_document,
        )
        requested = await registration.register(exact_cap_plan)
        queued = requested.transition(EvaluationRunState.QUEUED)
        await runs.save(queued, expected_version=requested.row_version)
        await execution.materialize(run_id=run_id, suite=suite(), shard_count=1)
        running = queued.transition(EvaluationRunState.RUNNING)
        await runs.save(running, expected_version=queued.row_version)

        for _ in suite().case_bindings:
            lease = await execution.claim(
                run_id=run_id,
                worker_id="worker:exact-cap",
                lease_seconds=60,
            )
            assert lease is not None
            await execution.complete(
                lease=lease,
                result=EvaluationCaseResult.issue(
                    run_id=run_id,
                    case_id=lease.case_id,
                    case_digest=lease.case_digest,
                    attempt=lease.attempt,
                    status="valid",
                    output_digest=SHA_C,
                    latency_ms=1000,
                    usage=EvaluationUsage(
                        input_tokens=1,
                        output_tokens=1,
                        cost_usd=0.000001,
                    ),
                    sanitized_trace_ref="artifact://evaluation/redacted",
                    metric_outputs=(
                        MetricCaseOutcome(
                            metric_revision="citation-validity-v1",
                            slice="all",
                            value=1,
                        ),
                    ),
                    grader_outputs=tuple(
                        GraderCaseOutcome(
                            grader_revision=revision,
                            outcome="pass",
                            evidence_digest=SHA_D,
                        )
                        for revision in graders()
                    ),
                ),
            )

        assert (
            await execution.claim(
                run_id=run_id,
                worker_id="worker:after-complete",
                lease_seconds=60,
            )
            is None
        )
        completed = await runs.get(run_id)
        assert completed is not None
        assert completed.state is EvaluationRunState.RUNNING
        assert completed.completed_case_count == len(suite().case_bindings)
        assert completed.failure_code is None
    finally:
        await engine.dispose()
