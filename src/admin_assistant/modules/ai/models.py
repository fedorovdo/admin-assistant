from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from admin_assistant.core.enums import AIAnalysisStatus, ApprovalStatus, RiskLevel


@dataclass(slots=True)
class AIAnalysis:
    id: str
    run_id: str
    provider_config_id: str
    status: AIAnalysisStatus
    target_result_id: str | None = None
    input_excerpt_redacted: str = ""
    summary: str = ""
    probable_causes: tuple[str, ...] = field(default_factory=tuple)
    evidence: tuple[str, ...] = field(default_factory=tuple)
    next_steps: tuple[str, ...] = field(default_factory=tuple)
    fix_plan_title: str | None = None
    fix_plan_summary: str | None = None
    model_snapshot: str | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class AISuggestedAction:
    id: str
    analysis_id: str
    title: str
    command_text: str
    target_scope: str
    risk_level: RiskLevel
    requires_sudo: bool = False
    requires_tty: bool = False
    step_order: int | None = None
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    execution_run_id: str | None = None
    created_at: datetime | None = None
