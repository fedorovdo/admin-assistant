from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from admin_assistant.core.enums import RunKind, RunStatus, ShellType, StreamType


class RunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_kind: RunKind
    server_ids: tuple[str, ...]
    script_id: str | None = None
    command_text: str | None = None
    shell_type: ShellType
    requires_sudo: bool = False
    requires_tty: bool = False
    timeout_sec: int | None = None
    execution_preference: str = "auto"
    request_ai_analysis: bool = False
    initiator: str = "user"
    source_analysis_id: str | None = None
    source_action_id: str | None = None


class CancelRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str


class RunStatusQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str


class RunOutputQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str


class ActiveRunsQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    status_filter: tuple[RunStatus, ...] = ()


class OutputChunkDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_result_id: str
    seq_no: int
    stream: StreamType
    chunk_text: str
    created_at: datetime


class TargetResultView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    server_id: str
    server_name: str
    status: RunStatus
    exit_code: int | None = None
    error_message: str | None = None


class RunLaunchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    status: RunStatus


class CommandExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    stdout: str = ""
    stderr: str = ""
    exit_code: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class RunStatusSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    status: RunStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    targets: tuple[TargetResultView, ...] = ()


class RunSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    run_kind: RunKind
    status: RunStatus
    requested_at: datetime | None = None
