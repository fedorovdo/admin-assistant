from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from admin_assistant.infrastructure.db.base import Base


class ScriptRunRecord(Base):
    __tablename__ = "script_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    script_id: Mapped[str | None] = mapped_column(String(36))
    script_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    command_snapshot: Mapped[str | None] = mapped_column(Text)
    shell_type: Mapped[str] = mapped_column(String(32), nullable=False)
    requires_sudo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_tty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_ai_analysis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    initiator: Mapped[str] = mapped_column(String(255), nullable=False, default="user")
    source_analysis_id: Mapped[str | None] = mapped_column(String(36))
    source_action_id: Mapped[str | None] = mapped_column(String(36))
