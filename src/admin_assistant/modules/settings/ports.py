from __future__ import annotations

from typing import Protocol

from admin_assistant.modules.settings.models import AIProviderConfig, AppSettings


class SettingsRepository(Protocol):
    def get_app_settings(self) -> AppSettings | None:
        ...

    def save_app_settings(self, settings: AppSettings) -> AppSettings:
        ...

    def add_provider_config(self, config: AIProviderConfig) -> AIProviderConfig:
        ...

    def update_provider_config(self, config: AIProviderConfig) -> AIProviderConfig:
        ...

    def get_provider_config(self, provider_config_id: str) -> AIProviderConfig | None:
        ...

    def list_provider_configs(self, include_disabled: bool = True) -> tuple[AIProviderConfig, ...]:
        ...

    def delete_provider_config(self, provider_config_id: str) -> None:
        ...

