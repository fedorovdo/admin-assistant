from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar
from uuid import uuid4

from admin_assistant.core.time import utc_now


@dataclass(frozen=True, slots=True)
class AppEvent:
    correlation_id: str
    occurred_at: datetime = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True, slots=True)
class RunCreatedEvent(AppEvent):
    event_name: ClassVar[str] = "run_created"
    run_id: str = ""
    run_kind: str = ""
    server_ids: tuple[str, ...] = ()
    shell_type: str = ""
    requires_tty: bool = False
    request_ai_analysis: bool = False
    initiator: str = ""


@dataclass(frozen=True, slots=True)
class RunStartedEvent(AppEvent):
    event_name: ClassVar[str] = "run_started"
    run_id: str = ""
    started_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class TargetStartedEvent(AppEvent):
    event_name: ClassVar[str] = "target_started"
    run_id: str = ""
    target_result_id: str = ""
    server_id: str = ""
    server_name: str = ""
    execution_method: str = ""
    started_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class OutputChunkReceivedEvent(AppEvent):
    event_name: ClassVar[str] = "output_chunk_received"
    run_id: str = ""
    target_result_id: str = ""
    server_id: str = ""
    server_name: str = ""
    stream: str = ""
    seq_no: int = 0
    chunk_text: str = ""


@dataclass(frozen=True, slots=True)
class TargetCompletedEvent(AppEvent):
    event_name: ClassVar[str] = "target_completed"
    run_id: str = ""
    target_result_id: str = ""
    server_id: str = ""
    status: str = ""
    exit_code: int | None = None
    completed_at: datetime = field(default_factory=utc_now)
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class RunCompletedEvent(AppEvent):
    event_name: ClassVar[str] = "run_completed"
    run_id: str = ""
    status: str = ""
    completed_at: datetime = field(default_factory=utc_now)
    target_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    analysis_requested: bool = False


@dataclass(frozen=True, slots=True)
class AnalysisRequestedEvent(AppEvent):
    event_name: ClassVar[str] = "analysis_requested"
    analysis_id: str = ""
    run_id: str = ""
    target_result_id: str | None = None
    provider_config_id: str = ""
    trigger_source: str = ""


@dataclass(frozen=True, slots=True)
class AnalysisCompletedEvent(AppEvent):
    event_name: ClassVar[str] = "analysis_completed"
    analysis_id: str = ""
    run_id: str = ""
    target_result_id: str | None = None
    summary: str = ""
    probable_causes: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    suggested_action_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SuggestedActionCreatedEvent(AppEvent):
    event_name: ClassVar[str] = "suggested_action_created"
    action_id: str = ""
    analysis_id: str = ""
    title: str = ""
    risk_level: str = ""
    target_scope: str = ""
    approval_status: str = ""


@dataclass(frozen=True, slots=True)
class SuggestedActionApprovedEvent(AppEvent):
    event_name: ClassVar[str] = "suggested_action_approved"
    action_id: str = ""
    analysis_id: str = ""
    approved_at: datetime = field(default_factory=utc_now)
    approved_by: str = ""
    target_scope: str = ""


@dataclass(frozen=True, slots=True)
class SuggestedActionExecutedEvent(AppEvent):
    event_name: ClassVar[str] = "suggested_action_executed"
    action_id: str = ""
    analysis_id: str = ""
    execution_run_id: str = ""
    executed_at: datetime = field(default_factory=utc_now)