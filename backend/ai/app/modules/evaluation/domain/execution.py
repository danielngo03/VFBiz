from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.modules.evaluation.domain.validation import (
    is_bounded_text,
    is_sha256,
)


@dataclass(frozen=True, slots=True)
class EvaluationCaseLease:
    run_id: str
    case_id: str
    case_digest: str
    suite_digest: str
    shard_index: int
    attempt: int
    lease_owner: str
    lease_token: str
    lease_expires_at: datetime
    max_input_tokens: int
    max_output_tokens: int
    max_duration_ms: int
    max_cost_usd: float

    def __post_init__(self) -> None:
        if (
            not is_bounded_text(self.run_id, maximum=160)
            or not is_bounded_text(self.case_id, maximum=200)
            or not is_sha256(self.case_digest)
            or not is_sha256(self.suite_digest)
            or self.shard_index < 0
            or not 1 <= self.attempt <= 3
            or not is_bounded_text(self.lease_owner, maximum=160)
            or not is_bounded_text(self.lease_token, maximum=36)
            or self.lease_expires_at.tzinfo is None
            or self.lease_expires_at.utcoffset() is None
            or self.max_input_tokens <= 0
            or self.max_output_tokens <= 0
            or self.max_duration_ms <= 0
            or Decimal(str(self.max_cost_usd)) <= 0
            or Decimal(str(self.max_cost_usd))
            != Decimal(str(self.max_cost_usd)).quantize(Decimal("0.000001"))
        ):
            raise ValueError("INVALID_EVALUATION_CASE_LEASE")
