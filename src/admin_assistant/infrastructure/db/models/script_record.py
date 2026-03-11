from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from admin_assistant.infrastructure.db.base import Base


class ScriptRecord(Base):
    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    shell_type: Mapped[str] = mapped_column(String(32), nullable=False)
    requires_tty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timeout_sec: Mapped[int | None] = mapped_column(Integer)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

