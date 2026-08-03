from app.modules.evaluation.application.ports import (
    EvaluationRunConcurrencyError,
    EvaluationRunRegistry,
)
from app.modules.evaluation.domain import EvaluationRun, EvaluationRunState


class EvaluationRunNotFound(LookupError):
    pass


class EvaluationRunLifecycleService:
    def __init__(self, registry: EvaluationRunRegistry) -> None:
        self._registry = registry

    async def queue(self, run_id: str) -> EvaluationRun:
        return await self.transition(run_id, EvaluationRunState.QUEUED)

    async def start(self, run_id: str) -> EvaluationRun:
        return await self.transition(run_id, EvaluationRunState.RUNNING)

    async def mark_grading(self, run_id: str) -> EvaluationRun:
        return await self.transition(run_id, EvaluationRunState.GRADING)

    async def mark_comparing(self, run_id: str) -> EvaluationRun:
        return await self.transition(run_id, EvaluationRunState.COMPARING)

    async def transition(
        self,
        run_id: str,
        target: EvaluationRunState,
    ) -> EvaluationRun:
        current = await self._registry.get(run_id)
        if current is None:
            raise EvaluationRunNotFound(f"EVALUATION_RUN_NOT_FOUND:{run_id}")
        if current.state is target:
            return current
        transitioned = current.transition(target)
        await self._registry.save(transitioned, expected_version=current.row_version)
        return transitioned

    async def cancel(self, run_id: str) -> EvaluationRun:
        current = await self._registry.get(run_id)
        if current is None:
            raise EvaluationRunNotFound(f"EVALUATION_RUN_NOT_FOUND:{run_id}")
        cancelled = current.cancel()
        if cancelled == current:
            return current
        try:
            await self._registry.save(
                cancelled,
                expected_version=current.row_version,
            )
        except EvaluationRunConcurrencyError:
            reloaded = await self._registry.get(run_id)
            if reloaded is not None and reloaded.state is EvaluationRunState.CANCELLED:
                return reloaded
            raise
        return cancelled
