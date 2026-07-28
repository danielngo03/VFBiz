from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.evaluation.application.ports import EvaluationRunConcurrencyError
from app.modules.evaluation.domain import (
    EvaluationRun,
    EvaluationRunState,
    digest_plan_document,
)
from app.modules.evaluation.infrastructure.models import EvaluationRunRecord


class PostgresEvaluationRunRegistry:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add_or_get(
        self,
        run: EvaluationRun,
        *,
        plan_document: dict[str, object],
    ) -> EvaluationRun:
        if digest_plan_document(plan_document) != run.plan_digest:
            raise EvaluationRunConcurrencyError(
                "evaluation run plan integrity check failed"
            )
        values = _insert_values(run, plan_document)
        async with self._sessions() as session, session.begin():
            await session.execute(
                insert(EvaluationRunRecord)
                .values(values)
                .on_conflict_do_nothing(index_elements=["run_key"])
            )
            record = await session.scalar(
                select(EvaluationRunRecord).where(
                    EvaluationRunRecord.run_key == run.run_id
                )
            )
            if record is None:
                raise EvaluationRunConcurrencyError("evaluation run registration vanished")
            return _run(record)

    async def get(self, run_id: str) -> EvaluationRun | None:
        async with self._sessions() as session:
            record = await session.scalar(
                select(EvaluationRunRecord).where(
                    EvaluationRunRecord.run_key == run_id
                )
            )
            return None if record is None else _run(record)

    async def save(self, run: EvaluationRun, *, expected_version: int) -> None:
        if run.row_version != expected_version + 1:
            raise EvaluationRunConcurrencyError(
                "evaluation run transition version is inconsistent"
            )
        async with self._sessions() as session, session.begin():
            current = await session.scalar(
                select(EvaluationRunRecord)
                .where(EvaluationRunRecord.run_key == run.run_id)
                .with_for_update()
            )
            if current is None:
                raise EvaluationRunConcurrencyError("evaluation run does not exist")
            persisted = _run(current)
            if (
                persisted.plan_digest != run.plan_digest
                or persisted.row_version != expected_version
            ):
                raise EvaluationRunConcurrencyError(
                    "evaluation run update lost optimistic concurrency"
                )
            result = cast(
                CursorResult[Any],
                await session.execute(
                    update(EvaluationRunRecord)
                    .where(
                        EvaluationRunRecord.run_key == run.run_id,
                        EvaluationRunRecord.plan_digest == run.plan_digest,
                        EvaluationRunRecord.row_version == expected_version,
                    )
                    .values(
                        status=run.state.value,
                        completed_case_count=run.completed_case_count,
                        attempt_count=run.attempt_count,
                        row_version=run.row_version,
                        evidence_bundle_digest=run.evidence_bundle_digest,
                        failure_code=run.failure_code,
                    )
                ),
            )
            if result.rowcount != 1:
                raise EvaluationRunConcurrencyError(
                    "evaluation run update lost optimistic concurrency"
                )


def _insert_values(
    run: EvaluationRun,
    plan_document: dict[str, object],
) -> dict[str, object]:
    candidate = cast(dict[str, object], plan_document["candidate"])
    baseline = cast(dict[str, object] | None, plan_document["baseline"])
    suite = cast(dict[str, object], plan_document["suite"])
    return {
        "release_id": None,
        "suite_revision": str(suite["id"]),
        "metrics": {"revisions": plan_document["metricRevisions"]},
        "security_passed": None,
        "status": run.state.value,
        "run_key": run.run_id,
        "plan_digest": run.plan_digest,
        "plan_document": plan_document,
        "authority_class": str(plan_document["authorityClass"]),
        "candidate_release_ref": str(candidate["releaseId"]),
        "candidate_manifest_digest": str(candidate["manifestDigest"]),
        "baseline_release_ref": (
            None if baseline is None else str(baseline["releaseId"])
        ),
        "baseline_manifest_digest": (
            None if baseline is None else str(baseline["manifestDigest"])
        ),
        "benchmark_definition_digest": str(
            plan_document["benchmarkDefinitionDigest"]
        ),
        "completed_case_count": run.completed_case_count,
        "attempt_count": run.attempt_count,
        "row_version": run.row_version,
        "evidence_bundle_digest": run.evidence_bundle_digest,
        "failure_code": run.failure_code,
    }


def _run(record: EvaluationRunRecord) -> EvaluationRun:
    if (
        record.run_key is None
        or record.plan_digest is None
        or record.plan_document is None
    ):
        raise EvaluationRunConcurrencyError(
            "legacy evaluation row is not a governed resumable run"
        )
    if (
        digest_plan_document(cast(dict[str, object], record.plan_document))
        != record.plan_digest
    ):
        raise EvaluationRunConcurrencyError(
            "evaluation run plan integrity check failed"
        )
    return EvaluationRun(
        run_id=record.run_key,
        plan_digest=record.plan_digest,
        state=EvaluationRunState(record.status),
        completed_case_count=record.completed_case_count,
        attempt_count=record.attempt_count,
        row_version=record.row_version,
        evidence_bundle_digest=record.evidence_bundle_digest,
        failure_code=record.failure_code,
    )
