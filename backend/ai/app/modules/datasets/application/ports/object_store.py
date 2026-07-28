from typing import BinaryIO, Protocol

from app.modules.datasets.application.source_intake.models import StoredObject
from app.modules.datasets.domain import TrustZone


class ObjectStore(Protocol):
    def put_stream(
        self,
        *,
        zone: TrustZone,
        stream: BinaryIO,
        media_type: str,
        max_bytes: int,
    ) -> StoredObject: ...
