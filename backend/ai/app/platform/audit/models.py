from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, UUIDTimestampMixin


class AuditEvent(UUIDTimestampMixin, Base):
    __tablename__ = "ai_audit_event"

    actor_ref: Mapped[str | None] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_ref: Mapped[str | None] = mapped_column(String(160))
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
