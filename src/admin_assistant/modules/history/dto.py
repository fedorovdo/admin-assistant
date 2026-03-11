from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from admin_assistant.core.enums import (
    AIAnalysisStatus,
    ApprovalStatus,
    RiskLevel,
    RunKind,
    RunStatus,
    ShellType,
    StreamType,
)
from admin_assistant.core.result import PagedResult


class RunHistoryQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    search_text: str | None = None
    status_filter: tuple[RunStatus, ...] = ()
    page: int = 1
    page_size: int = 50


class RunHistoryItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    run_kind: RunKind
    status: RunStatus
    target_count: int = 0
    requested_at: datetime | None = None


class RunHistoryPage(PagedResult[RunHistoryItem]):
    pass


class RunDetailsQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str


class ConsoleReplayQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str


class ConsoleReplayLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_result_id: str
    server_name: str
    stream: StreamType
    seq_no: int
    chunk_text: str
    created_at: datetime


class ConsoleReplayView(BaseModel):
    model_config = ConfigDict(frozen=True)

    all_hosts_lines: tuple[ConsoleReplayLine, ...] = ()


class LinkedSuggestedActionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    command_text: str
    target_scope: str
    risk_level: RiskLevel
    approval_status: ApprovalStatus
    execution_run_id: str | None = None


class LinkedAnalysisView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: AIAnalysisStatus
    summary: str
    probable_causes: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    created_at: datetime | None = None
    suggested_actions: tuple[LinkedSuggestedActionView, ...] = ()


class RunTargetFactsView(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_result_id: str
    server_id: str
    server_name: str
    status: RunStatus
    exit_code: int | None = None
    error_message: str | None = None


class RunDetailsView(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    run_kind: RunKind
    status: RunStatus
    target_count: int = 0
    command_snapshot: str | None = None
    script_name: str | None = None
    shell_type: ShellType = ShellType.BASH
    requires_sudo: bool = False
    requires_tty: bool = False
    source_analysis_id: str | None = None
    source_action_id: str | None = None
    requested_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    targets: tuple[RunTargetFactsView, ...] = ()
    analyses: tuple[LinkedAnalysisView, ...] = ()


class AnalysisHistoryQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str | None = None
    page: int = 1
    page_size: int = 50


class AnalysisHistoryItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    run_id: str
    status: AIAnalysisStatus
    created_at: datetime | None = None


class AnalysisHistoryPage(PagedResult[AnalysisHistoryItem]):
    pass


class AnalysisDetailsQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
