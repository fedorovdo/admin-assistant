from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from admin_assistant.infrastructure.db.base import Base


class RunOutputChunkRecord(Base):
    __tablename__ = "run_output_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_result_id: Mapped[str] = mapped_column(String(36), ForeignKey("run_target_results.id"), nullable=False)
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    stream: Mapped[str] = mapped_column(String(16), nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

