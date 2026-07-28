from datetime import datetime
from typing import Protocol

from app.modules.datasets.application.source_intake.models import ApprovedSourceFetchPlan


class FetchApprovalAuthority(Protocol):
    def assert_fetch_approved(
        self,
        plan: ApprovedSourceFetchPlan,
        *,
        at: datetime,
    ) -> None: ...
