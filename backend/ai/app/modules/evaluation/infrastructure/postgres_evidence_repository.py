from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.evaluation.application.ports import EvaluationRunConcurrencyError
from app.modules.evaluation.domain import (
    EvaluationCaseResult,
    EvaluationRun,
    EvaluationUsage,
    GraderCaseOutcome,
    MetricCaseOutcome,
    VerifiedEvidenceBundle,
)
from app.modules.evaluation.infrastructure.models import (
    EvaluationCaseResultRecord,
    EvaluationEvidenceBundleRecord,
    EvaluationRunRecord,
)


class PostgresEvaluationEvidenceRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_case_results(
        self,
        run_id: str,
    ) -> tuple[EvaluationCaseResult, ...]:
        async with self._sessions() as session:
            records = (
                await session.scalars(
                    select(EvaluationCaseResultRecord)
                    .where(EvaluationCaseResultRecord.run_key == run_id)
                    .order_by(
                        EvaluationCaseResultRecord.case_key,
                        EvaluationCaseResultRecord.attempt,
                    )
                )
            ).all()
            return tuple(_case_result(record) for record in records)

    async def seal(
        self,
        run: EvaluationRun,
        evidence: VerifiedEvidenceBundle,
        *,
        expected_version: int,
    ) -> None:
        if (
            run.row_version != expected_version + 1
            or run.evidence_bundle_digest != evidence.bundle_digest
            or run.run_id != evidence.run_id
            or run.plan_digest != evidence.plan_digest
        ):
            raise EvaluationRunConcurrencyError("evaluation evidence seal binding is inconsistent")
        async with self._sessions() as session, session.begin():
            current = await session.scalar(
                select(EvaluationRunRecord)
                .where(EvaluationRunRecord.run_key == run.run_id)
                .with_for_update()
            )
            if (
                current is None
                or current.row_version != expected_version
                or current.plan_digest != evidence.plan_digest
            ):
                raise EvaluationRunConcurrencyError(
                    "evaluation evidence seal lost optimistic concurrency"
                )
            await session.execute(
                insert(EvaluationEvidenceBundleRecord).values(
                    run_key=evidence.run_id,
                    plan_digest=evidence.plan_digest,
                    bundle_digest=evidence.bundle_digest,
                    case_results_digest=str(evidence.semantic_document["case_results_digest"]),
                    run_result_digest=str(evidence.semantic_document["run_result_digest"]),
                    authority_class=evidence.authority_class.value,
                    recommendation=evidence.recommendation,
                    sealed_from_row_version=expected_version,
                    suite_snapshot_payload=evidence.suite_snapshot_payload,
                    baseline_policy_payload=evidence.baseline_policy_payload,
                    run_result_payload=evidence.run_result_payload,
                    canonical_document=evidence.contract_document,
                    canonical_payload=evidence.canonical_payload,
                )
            )
            result = cast(
                CursorResult[Any],
                await session.execute(
                    update(EvaluationRunRecord)
                    .where(
                        EvaluationRunRecord.run_key == run.run_id,
                        EvaluationRunRecord.row_version == expected_version,
                        EvaluationRunRecord.plan_digest == evidence.plan_digest,
                    )
                    .values(
                        status=run.state.value,
                        row_version=run.row_version,
                        evidence_bundle_digest=evidence.bundle_digest,
                    )
                ),
            )
            if result.rowcount != 1:
                raise EvaluationRunConcurrencyError(
                    "evaluation evidence seal lost optimistic concurrency"
                )


def _case_result(record: EvaluationCaseResultRecord) -> EvaluationCaseResult:
    usage = record.usage
    return EvaluationCaseResult(
        run_id=record.run_key,
        case_id=record.case_key,
        case_digest=record.case_digest,
        attempt=record.attempt,
        status=record.status,
        output_digest=record.output_digest,
        latency_ms=record.latency_ms,
        usage=EvaluationUsage(
            input_tokens=int(usage["input_tokens"]),
            output_tokens=int(usage["output_tokens"]),
            cost_usd=float(usage["cost_usd"]),
        ),
        sanitized_trace_ref=record.sanitized_trace_ref,
        metric_outputs=tuple(
            MetricCaseOutcome(
                metric_revision=str(item["metric_revision"]),
                slice=str(item["slice"]),
                value=float(item["value"]),
            )
            for item in record.metric_outputs
        ),
        grader_outputs=tuple(
            GraderCaseOutcome(
                grader_revision=str(item["grader_revision"]),
                outcome=str(item["outcome"]),
                evidence_digest=str(item["evidence_digest"]),
                score=(None if item.get("score") is None else float(item["score"])),
            )
            for item in record.grader_outputs
        ),
        validity_flags=tuple(record.validity_flags),
        result_digest=record.result_digest,
    )
