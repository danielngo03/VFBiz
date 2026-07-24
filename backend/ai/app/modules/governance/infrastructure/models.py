from typing import Any

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, UUIDTimestampMixin


class DatasetRelease(UUIDTimestampMixin, Base):
    __tablename__ = "ai_dataset_release"

    manifest_ref: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    owner_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AIRelease(UUIDTimestampMixin, Base):
    __tablename__ = "ai_release"

    manifest_ref: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    assistant_profile: Mapped[str] = mapped_column(String(40), nullable=False)
    model_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    embedding_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    retriever_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    dataset_revisions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    tool_registry_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    kill_switch_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
