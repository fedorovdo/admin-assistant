from __future__ import annotations

from uuid import uuid4
from typing import Protocol

from admin_assistant.core.enums import AnalysisLanguage
from admin_assistant.core.errors import NotFoundError
from admin_assistant.modules.ai.ports import AIProviderClient
from admin_assistant.core.result import OperationResult
from admin_assistant.core.time import utc_now
from admin_assistant.modules.servers.ports import SecretStore
from admin_assistant.modules.settings.dto import (
    AIProviderConfigCreateRequest,
    AIProviderConfigUpdateRequest,
    AIProviderConfigView,
    AppSettingsView,
    ProviderConnectionTestRequest,
    ProviderConnectionTestResult,
    ProviderConfigListQuery,
    SetDefaultProviderRequest,
    UpdateAppSettingsRequest,
)
from admin_assistant.modules.settings.models import AIProviderConfig, AppSettings
from admin_assistant.modules.settings.ports import SettingsRepository


class SettingsService(Protocol):
    def get_app_settings(self) -> AppSettingsView:
        ...

    def update_app_settings(self, request: UpdateAppSettingsRequest) -> AppSettingsView:
        ...

    def list_provider_configs(self, query: ProviderConfigListQuery) -> tuple[AIProviderConfigView, ...]:
        ...

    def get_provider_config(self, provider_config_id: str) -> AIProviderConfigView:
        ...

    def get_default_provider_config(self) -> AIProviderConfigView | None:
        ...

    def create_provider_config(self, request: AIProviderConfigCreateRequest) -> AIProviderConfigView:
        ...

    def update_provider_config(self, request: AIProviderConfigUpdateRequest) -> AIProviderConfigView:
        ...

    def delete_provider_config(self, provider_config_id: str) -> OperationResult:
        ...

    def set_default_provider(self, request: SetDefaultProviderRequest) -> AIProviderConfigView:
        ...

    def test_provider_connection(self, request: ProviderConnectionTestRequest) -> ProviderConnectionTestResult:
        ...


class DefaultSettingsService(SettingsService):
    _APP_SETTINGS_ID = "app-settings"

    def __init__(
        self,
        repository: SettingsRepository,
        secret_store: SecretStore,
        provider_client: AIProviderClient,
    ) -> None:
        self._repository = repository
        self._secret_store = secret_store
        self._provider_client = provider_client

    def get_app_settings(self) -> AppSettingsView:
        settings = self._repository.get_app_settings()
        if settings is None:
            return AppSettingsView(default_ai_provider_id=None, analysis_language=AnalysisLanguage.EN)
        return AppSettingsView(
            default_ai_provider_id=settings.default_ai_provider_id,
            analysis_language=settings.analysis_language,
        )

    def update_app_settings(self, request: UpdateAppSettingsRequest) -> AppSettingsView:
        existing = self._repository.get_app_settings()
        request_fields = request.model_fields_set
        settings = AppSettings(
            id=existing.id if existing is not None else self._APP_SETTINGS_ID,
            default_ai_provider_id=(
                request.default_ai_provider_id
                if "default_ai_provider_id" in request_fields
                else (existing.default_ai_provider_id if existing is not None else None)
            ),
            analysis_language=(
                request.analysis_language
                if "analysis_language" in request_fields and request.analysis_language is not None
                else (existing.analysis_language if existing is not None else AnalysisLanguage.EN)
            ),
            created_at=existing.created_at if existing is not None else utc_now(),
            updated_at=utc_now(),
        )
        saved = self._repository.save_app_settings(settings)
        return AppSettingsView(
            default_ai_provider_id=saved.default_ai_provider_id,
            analysis_language=saved.analysis_language,
        )

    def list_provider_configs(self, query: ProviderConfigListQuery) -> tuple[AIProviderConfigView, ...]:
        return tuple(
            self._to_view(config)
            for config in self._repository.list_provider_configs(include_disabled=query.include_disabled)
        )

    def get_provider_config(self, provider_config_id: str) -> AIProviderConfigView:
        config = self._repository.get_provider_config(provider_config_id)
        if config is None:
            raise NotFoundError(f"Provider config '{provider_config_id}' was not found.")
        return self._to_view(config)

    def get_default_provider_config(self) -> AIProviderConfigView | None:
        settings = self._repository.get_app_settings()
        if settings and settings.default_ai_provider_id:
            config = self._repository.get_provider_config(settings.default_ai_provider_id)
            if config is not None and config.is_enabled:
                return self._to_view(config)

        configs = self._repository.list_provider_configs(include_disabled=False)
        for config in configs:
            if config.is_default:
                return self._to_view(config)
        return self._to_view(configs[0]) if configs else None

    def create_provider_config(self, request: AIProviderConfigCreateRequest) -> AIProviderConfigView:
        config_id = str(uuid4())
        api_key_ref = None
        provider_name = request.provider_name.strip().lower()
        if self._provider_requires_api_key(provider_name) and request.api_key is not None and request.api_key.get_secret_value().strip():
            api_key_ref = self._secret_store.save_secret(
                f"ai-provider:{config_id}:api-key",
                request.api_key.get_secret_value().strip(),
            )

        config = AIProviderConfig(
            id=config_id,
            provider_name=provider_name,
            display_name=request.display_name.strip(),
            base_url=request.base_url.strip(),
            model_name=request.model_name.strip(),
            api_key_ref=api_key_ref,
            timeout_sec=request.timeout_sec,
            temperature=request.temperature,
            is_default=request.is_default,
            is_enabled=request.is_enabled,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        saved = self._repository.add_provider_config(config)
        if request.is_default or self.get_app_settings().default_ai_provider_id is None:
            return self.set_default_provider(SetDefaultProviderRequest(provider_config_id=saved.id))
        return self._to_view(saved)

    def update_provider_config(self, request: AIProviderConfigUpdateRequest) -> AIProviderConfigView:
        existing = self._repository.get_provider_config(request.provider_config_id)
        if existing is None:
            raise NotFoundError(f"Provider config '{request.provider_config_id}' was not found.")

        provider_name = request.provider_name.strip().lower()
        api_key_ref = existing.api_key_ref
        if self._provider_requires_api_key(provider_name) and request.api_key is not None and request.api_key.get_secret_value().strip():
            key_ref = api_key_ref or f"ai-provider:{existing.id}:api-key"
            api_key_ref = self._secret_store.save_secret(key_ref, request.api_key.get_secret_value().strip())
        elif not self._provider_requires_api_key(provider_name):
            if api_key_ref:
                self._secret_store.delete_secret(api_key_ref)
            api_key_ref = None

        updated = AIProviderConfig(
            id=existing.id,
            provider_name=provider_name,
            display_name=request.display_name.strip(),
            base_url=request.base_url.strip(),
            model_name=request.model_name.strip(),
            api_key_ref=api_key_ref,
            timeout_sec=request.timeout_sec,
            temperature=request.temperature,
            is_default=request.is_default or existing.is_default,
            is_enabled=request.is_enabled,
            created_at=existing.created_at,
            updated_at=utc_now(),
        )
        saved = self._repository.update_provider_config(updated)
        if request.is_default:
            return self.set_default_provider(SetDefaultProviderRequest(provider_config_id=saved.id))
        return self._to_view(saved)

    def delete_provider_config(self, provider_config_id: str) -> OperationResult:
        existing = self._repository.get_provider_config(provider_config_id)
        if existing is None:
            raise NotFoundError(f"Provider config '{provider_config_id}' was not found.")

        if existing.api_key_ref:
            self._secret_store.delete_secret(existing.api_key_ref)
        self._repository.delete_provider_config(provider_config_id)

        settings = self._repository.get_app_settings()
        if settings and settings.default_ai_provider_id == provider_config_id:
            self.update_app_settings(UpdateAppSettingsRequest(default_ai_provider_id=None))
        return OperationResult(success=True)

    def set_default_provider(self, request: SetDefaultProviderRequest) -> AIProviderConfigView:
        target = self._repository.get_provider_config(request.provider_config_id)
        if target is None:
            raise NotFoundError(f"Provider config '{request.provider_config_id}' was not found.")

        for config in self._repository.list_provider_configs(include_disabled=True):
            desired_default = config.id == target.id
            if config.is_default != desired_default:
                self._repository.update_provider_config(
                    AIProviderConfig(
                        id=config.id,
                        provider_name=config.provider_name,
                        display_name=config.display_name,
                        base_url=config.base_url,
                        model_name=config.model_name,
                        api_key_ref=config.api_key_ref,
                        timeout_sec=config.timeout_sec,
                        temperature=config.temperature,
                        is_default=desired_default,
                        is_enabled=config.is_enabled,
                        created_at=config.created_at,
                        updated_at=utc_now(),
                    )
                )

        self.update_app_settings(UpdateAppSettingsRequest(default_ai_provider_id=target.id))
        refreshed = self._repository.get_provider_config(target.id)
        if refreshed is None:
            raise NotFoundError(f"Provider config '{target.id}' was not found.")
        return self._to_view(refreshed)

    def test_provider_connection(self, request: ProviderConnectionTestRequest) -> ProviderConnectionTestResult:
        provider_name = request.provider_name.strip().lower()
        api_key: str | None = None

        if self._provider_requires_api_key(provider_name):
            if request.api_key is not None and request.api_key.get_secret_value().strip():
                api_key = request.api_key.get_secret_value().strip()
            elif request.provider_config_id:
                existing = self._repository.get_provider_config(request.provider_config_id)
                if existing is not None and existing.api_key_ref:
                    api_key = self._secret_store.read_secret(existing.api_key_ref)

            if not api_key:
                return ProviderConnectionTestResult(success=False, message="API key missing.")

        config = AIProviderConfig(
            id=request.provider_config_id or "provider-test",
            provider_name=provider_name,
            display_name=request.provider_name.strip() or provider_name,
            base_url=request.base_url.strip(),
            model_name=request.model_name.strip(),
            api_key_ref=None,
            timeout_sec=request.timeout_sec,
            temperature=0.1,
            is_default=False,
            is_enabled=True,
        )
        return self._provider_client.test_connection(config, api_key=api_key)

    def _to_view(self, config: AIProviderConfig) -> AIProviderConfigView:
        return AIProviderConfigView(
            id=config.id,
            provider_name=config.provider_name,
            display_name=config.display_name,
            base_url=config.base_url,
            model_name=config.model_name,
            timeout_sec=config.timeout_sec,
            temperature=config.temperature,
            is_default=config.is_default,
            is_enabled=config.is_enabled,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    def _provider_requires_api_key(self, provider_name: str) -> bool:
        return provider_name in {"openai", "openai_compatible"}
