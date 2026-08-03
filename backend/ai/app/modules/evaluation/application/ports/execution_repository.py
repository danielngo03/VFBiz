from datetime import datetime
from typing import Protocol

from app.modules.evaluation.domain import (
    EvaluationCaseLease,
    EvaluationCaseResult,
    EvaluationSuiteSnapshot,
)


class EvaluationExecutionRepository(Protocol):
    async def materialize_suite(
        self,
        *,
        run_id: str,
        suite: EvaluationSuiteSnapshot,
        shard_count: int,
        max_attempts: int,
    ) -> None: ...

    async def claim_case(
        self,
        *,
        run_id: str,
        worker_id: str,
        lease_expires_at: datetime,
        shard_index: int | None = None,
    ) -> EvaluationCaseLease | None: ...

    async def complete_case(
        self,
        *,
        lease: EvaluationCaseLease,
        result: EvaluationCaseResult,
        completed_at: datetime,
    ) -> None: ...
