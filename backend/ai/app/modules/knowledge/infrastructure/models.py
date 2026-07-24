from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base, UUIDTimestampMixin


class KnowledgeSource(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_source"

    uri: Mapped[str] = mapped_column(String(1_024), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_ai_knowledge_source_status_revision", "status", "source_revision"),
    )


class KnowledgeChunk(UUIDTimestampMixin, Base):
    __tablename__ = "ai_knowledge_chunk"

    source_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ai_knowledge_source.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    redacted_text: Mapped[str] = mapped_column(Text, nullable=False)
    acl: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)

    __table_args__ = (
        Index("ix_ai_knowledge_chunk_source_revision", "source_id", "chunk_revision"),
    )
