from typing import Protocol

from app.modules.evaluation.domain import (
    BenchmarkDefinition,
    GraderCalibration,
    GraderDefinition,
    MetricDefinition,
)


class EvaluationDefinitionRegistry(Protocol):
    async def get_benchmark(
        self, benchmark_id: str, revision: str
    ) -> BenchmarkDefinition | None: ...

    async def get_metric(self, revision: str) -> MetricDefinition | None: ...

    async def get_grader(self, revision: str) -> GraderDefinition | None: ...

    async def get_calibration(
        self, grader_revision: str
    ) -> GraderCalibration | None: ...
