from typing import Protocol

from app.modules.evaluation.domain import (
    EvaluationCaseResult,
    EvaluationRun,
    VerifiedEvidenceBundle,
)


class EvaluationEvidenceRepository(Protocol):
    async def list_case_results(
        self,
        run_id: str,
    ) -> tuple[EvaluationCaseResult, ...]: ...

    async def seal(
        self,
        run: EvaluationRun,
        evidence: VerifiedEvidenceBundle,
        *,
        expected_version: int,
    ) -> None: ...
