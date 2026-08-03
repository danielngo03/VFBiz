from typing import Protocol

from app.modules.evaluation.domain import EvaluationRun


class EvaluationRunRegistry(Protocol):
    async def add_or_get(
        self,
        run: EvaluationRun,
        *,
        plan_document: dict[str, object],
    ) -> EvaluationRun: ...

    async def get(self, run_id: str) -> EvaluationRun | None: ...

    async def get_plan_document(
        self,
        run_id: str,
    ) -> dict[str, object] | None: ...

    async def save(self, run: EvaluationRun, *, expected_version: int) -> None: ...


class EvaluationRunConcurrencyError(RuntimeError):
    pass
