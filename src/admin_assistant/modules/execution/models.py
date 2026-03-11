from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from admin_assistant.core.enums import ExecutionMethod, RunKind, RunStatus, ShellType


@dataclass(slots=True)
class ScriptRun:
    id: str
    run_kind: RunKind
    status: RunStatus
    script_id: str | None = None
    script_snapshot: dict[str, Any] = field(default_factory=dict)
    command_snapshot: str | None = None
    shell_type: ShellType = ShellType.BASH
    requires_sudo: bool = False
    requires_tty: bool = False
    trigger_source: str = "user"
    requested_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    request_ai_analysis: bool = False
    initiator: str = ""
    source_analysis_id: str | None = None
    source_action_id: str | None = None


@dataclass(slots=True)
class RunTargetResult:
    id: str
    run_id: str
    server_id: str
    server_snapshot: dict[str, Any] = field(default_factory=dict)
    status: RunStatus = RunStatus.PENDING
    execution_method: ExecutionMethod | None = None
    exit_code: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
