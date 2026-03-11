from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from admin_assistant.core.enums import AIAnalysisStatus, ApprovalStatus, RiskLevel


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    target_result_id: str | None = None
    provider_config_id: str
    trigger_source: str = "user"


class AnalysisQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str


class AIAnalysisSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    run_id: str
    status: AIAnalysisStatus
    created_at: datetime | None = None


class SuggestedActionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    analysis_id: str
    title: str
    command_text: str
    target_scope: str
    risk_level: RiskLevel
    requires_sudo: bool = False
    requires_tty: bool = False
    step_order: int | None = None
    approval_status: ApprovalStatus
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    execution_run_id: str | None = None
    created_at: datetime | None = None


class ProviderSuggestedActionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    command_text: str
    target_scope: str
    risk_level: RiskLevel


class ProviderFixStepResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    command_text: str
    target_scope: str
    risk_level: RiskLevel
    requires_sudo: bool = False
    requires_tty: bool = False


class AIProviderAnalysisResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str
    probable_causes: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    suggested_actions: tuple[ProviderSuggestedActionResponse, ...] = ()
    fix_plan_title: str | None = None
    fix_plan_summary: str | None = None
    fix_steps: tuple[ProviderFixStepResponse, ...] = ()


class AIAnalysisView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    run_id: str
    target_result_id: str | None = None
    provider_config_id: str
    status: AIAnalysisStatus
    input_excerpt_redacted: str = ""
    summary: str = ""
    probable_causes: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    fix_plan_title: str | None = None
    fix_plan_summary: str | None = None
    suggested_actions: tuple[SuggestedActionView, ...] = ()
    fix_steps: tuple[SuggestedActionView, ...] = ()
    created_at: datetime | None = None


class AnalysisLaunchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    status: AIAnalysisStatus


class SuggestedActionApprovalRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    approved_by: str


class SuggestedActionRejectionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    rejected_by: str
    reason: str | None = None


class ExecuteSuggestedActionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    initiated_by: str
