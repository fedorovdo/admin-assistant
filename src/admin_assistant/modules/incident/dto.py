from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from admin_assistant.core.enums import RiskLevel, ShellType
from admin_assistant.modules.ai.dto import SuggestedActionView


class IncidentInvestigateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str | None = None
    symptom: str
    server_ids: tuple[str, ...]
    shell_type: ShellType = ShellType.BASH
    initiated_by: str = "user"


class IncidentStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_order: int
    title: str
    command_text: str
    target_scope: str
    risk_level: RiskLevel
    requires_sudo: bool = False
    requires_tty: bool = False


class IncidentAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    run_id: str
    summary: str
    probable_root_cause: str | None = None
    evidence: tuple[str, ...] = ()
    next_checks: tuple[str, ...] = ()
    suggested_actions: tuple[SuggestedActionView, ...] = ()
    fix_plan_title: str | None = None
    fix_plan_summary: str | None = None
    fix_steps: tuple[SuggestedActionView, ...] = ()


class IncidentSession(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str
    title: str
    symptom: str
    category: str = "generic"
    server_ids: tuple[str, ...]
    status: str
    plan_title: str | None = None
    plan_summary: str | None = None
    steps: tuple[IncidentStep, ...] = ()
    skipped_steps: tuple[str, ...] = ()
    diagnostic_run_id: str | None = None
    analysis: IncidentAnalysis | None = None
    failure_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
