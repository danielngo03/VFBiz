from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, UUIDTimestampMixin


class EvaluationRun(UUIDTimestampMixin, Base):
    __tablename__ = "ai_evaluation_run"

    release_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_release.id", ondelete="RESTRICT"),
        nullable=False,
    )
    suite_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    security_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
