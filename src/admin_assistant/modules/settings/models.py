from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from admin_assistant.core.enums import AnalysisLanguage


@dataclass(slots=True)
class AIProviderConfig:
    id: str
    provider_name: str
    display_name: str
    base_url: str
    model_name: str
    api_key_ref: str | None = None
    timeout_sec: int = 30
    temperature: float = 0.1
    is_default: bool = False
    is_enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class AppSettings:
    id: str
    default_ai_provider_id: str | None = None
    analysis_language: AnalysisLanguage = AnalysisLanguage.EN
    created_at: datetime | None = None
    updated_at: datetime | None = None
