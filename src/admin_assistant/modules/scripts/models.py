from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from admin_assistant.core.enums import ShellType


@dataclass(slots=True)
class Script:
    id: str
    name: str
    description: str | None
    content: str
    shell_type: ShellType
    requires_tty: bool = False
    timeout_sec: int | None = None
    execution_mode: str = "auto"
    tags: tuple[str, ...] = field(default_factory=tuple)
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

