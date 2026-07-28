from types import TracebackType
from typing import BinaryIO, Protocol

from app.modules.datasets.application.source_intake.models import ApprovedSourceFetchPlan


class OpenedSource(Protocol):
    stream: BinaryIO
    byte_size: int

    def __enter__(self) -> "OpenedSource": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class SourceReader(Protocol):
    def open(self, plan: ApprovedSourceFetchPlan) -> OpenedSource: ...
