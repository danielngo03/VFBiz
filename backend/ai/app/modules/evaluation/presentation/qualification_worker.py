"""Bounded worker entry point for a governed qualification run."""

from __future__ import annotations

from app.modules.evaluation.application.execution import (
    CaseHandler,
    EvaluationQualificationRunner,
    QualificationRunRequest,
)
from app.modules.evaluation.domain import EvaluationRun


async def run_qualification(
    runner: EvaluationQualificationRunner,
    request: QualificationRunRequest,
    *,
    handle_case: CaseHandler,
) -> EvaluationRun:
    """Execute one release-bound run and return only sealed evidence state.

    The worker delegates all state changes to the application runner. It has
    no release activation capability and cannot replace the case handler's
    provider or alter the authority-bound request.
    """

    return await runner.run(request, handle_case=handle_case)


__all__ = ["run_qualification"]
