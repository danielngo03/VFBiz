from typing import BinaryIO, Protocol

from app.modules.datasets.application.source_intake.models import ScanEvidence


class ArtifactScanner(Protocol):
    def scan_stream(self, stream: BinaryIO, *, media_type: str, byte_size: int) -> ScanEvidence: ...
