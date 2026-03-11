from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from admin_assistant.infrastructure.db.base import Base


class AIAnalysisRecord(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("script_runs.id"), nullable=False)
    target_result_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("run_target_results.id"))
    provider_config_id: Mapped[str] = mapped_column(String(36), ForeignKey("ai_provider_configs.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_excerpt_redacted: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    probable_causes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    next_steps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    fix_plan_title: Mapped[str | None] = mapped_column(Text)
    fix_plan_summary: Mapped[str | None] = mapped_column(Text)
    model_snapshot: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
