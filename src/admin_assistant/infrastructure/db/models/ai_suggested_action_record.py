from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from admin_assistant.infrastructure.db.base import Base


class AISuggestedActionRecord(Base):
    __tablename__ = "ai_suggested_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("ai_analyses.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    command_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_scope: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    requires_sudo: Mapped[bool] = mapped_column(nullable=False, default=False)
    requires_tty: Mapped[bool] = mapped_column(nullable=False, default=False)
    step_order: Mapped[int | None] = mapped_column(nullable=True)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("script_runs.id"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
