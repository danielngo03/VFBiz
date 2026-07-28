from app.modules.evaluation.application.ports import EvaluationRunRegistry
from app.modules.evaluation.domain import EvaluationRun, EvaluationRunPlan


class RunRegistrationConflict(ValueError):
    pass


class EvaluationRunRegistrationService:
    def __init__(self, registry: EvaluationRunRegistry) -> None:
        self._registry = registry

    async def register(self, plan: EvaluationRunPlan) -> EvaluationRun:
        requested = EvaluationRun.requested(
            run_id=plan.run_id,
            plan_digest=plan.content_digest,
        )
        registered = await self._registry.add_or_get(
            requested,
            plan_document=plan.canonical_document,
        )
        if registered.plan_digest != requested.plan_digest:
            raise RunRegistrationConflict(f"RUN_PLAN_CONFLICT:{plan.run_id}")
        return registered
