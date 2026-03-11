from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, SecretStr

from admin_assistant.core.enums import AnalysisLanguage


class UpdateAppSettingsRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    default_ai_provider_id: str | None = None
    analysis_language: AnalysisLanguage | None = None


class AppSettingsView(BaseModel):
    model_config = ConfigDict(frozen=True)

    default_ai_provider_id: str | None = None
    analysis_language: AnalysisLanguage = AnalysisLanguage.EN


class ProviderConfigListQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    include_disabled: bool = True


class AIProviderConfigCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_name: str
    display_name: str
    base_url: str
    model_name: str
    api_key: SecretStr | None = None
    timeout_sec: int = 30
    temperature: float = 0.1
    is_default: bool = False
    is_enabled: bool = True


class AIProviderConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_config_id: str
    provider_name: str
    display_name: str
    base_url: str
    model_name: str
    api_key: SecretStr | None = None
    timeout_sec: int = 30
    temperature: float = 0.1
    is_default: bool = False
    is_enabled: bool = True


class AIProviderConfigView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    provider_name: str
    display_name: str
    base_url: str
    model_name: str
    timeout_sec: int
    temperature: float
    is_default: bool
    is_enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SetDefaultProviderRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_config_id: str


class ProviderConnectionTestRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_config_id: str | None = None
    provider_name: str
    base_url: str
    model_name: str
    api_key: SecretStr | None = None
    timeout_sec: int = 30


class ProviderConnectionTestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    message: str
