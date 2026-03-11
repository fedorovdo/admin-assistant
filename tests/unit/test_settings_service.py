from __future__ import annotations

from admin_assistant.core.enums import AnalysisLanguage
from admin_assistant.modules.settings.dto import ProviderConnectionTestRequest
from admin_assistant.modules.settings.models import AIProviderConfig, AppSettings
from admin_assistant.modules.settings.service import DefaultSettingsService


class InMemorySettingsRepository:
    def __init__(self) -> None:
        self.settings: AppSettings | None = None
        self.providers: dict[str, AIProviderConfig] = {}

    def get_app_settings(self) -> AppSettings | None:
        return self.settings

    def save_app_settings(self, settings: AppSettings) -> AppSettings:
        self.settings = settings
        return settings

    def add_provider_config(self, config: AIProviderConfig) -> AIProviderConfig:
        self.providers[config.id] = config
        return config

    def update_provider_config(self, config: AIProviderConfig) -> AIProviderConfig:
        self.providers[config.id] = config
        return config

    def get_provider_config(self, provider_config_id: str) -> AIProviderConfig | None:
        return self.providers.get(provider_config_id)

    def list_provider_configs(self, include_disabled: bool = True) -> tuple[AIProviderConfig, ...]:
        providers = tuple(self.providers.values())
        if include_disabled:
            return providers
        return tuple(provider for provider in providers if provider.is_enabled)

    def delete_provider_config(self, provider_config_id: str) -> None:
        self.providers.pop(provider_config_id, None)


class MemorySecretStore:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = values or {}

    def save_secret(self, key: str, value: str) -> str:
        self.values[key] = value
        return key

    def read_secret(self, key: str) -> str | None:
        return self.values.get(key)

    def delete_secret(self, key: str) -> None:
        self.values.pop(key, None)


class FakeProviderClient:
    def __init__(self) -> None:
        self.last_provider_name: str | None = None
        self.last_api_key: str | None = None

    def analyze(self, prompt: str, provider_config, api_key: str | None = None):
        raise NotImplementedError

    def test_connection(self, provider_config, api_key: str | None = None):
        from admin_assistant.modules.settings.dto import ProviderConnectionTestResult

        self.last_provider_name = provider_config.provider_name
        self.last_api_key = api_key
        return ProviderConnectionTestResult(
            success=True,
            message=f"{provider_config.provider_name} ok",
        )


def test_settings_service_reports_missing_api_key_for_openai_connection_test() -> None:
    service = DefaultSettingsService(
        repository=InMemorySettingsRepository(),
        secret_store=MemorySecretStore(),
        provider_client=FakeProviderClient(),
    )

    result = service.test_provider_connection(
        ProviderConnectionTestRequest(
            provider_name="openai",
            base_url="https://api.openai.com/v1",
            model_name="gpt-4o-mini",
        )
    )

    assert result.success is False
    assert result.message == "API key missing."


def test_settings_service_uses_saved_api_key_for_existing_openai_provider_test() -> None:
    repository = InMemorySettingsRepository()
    repository.providers["provider-1"] = AIProviderConfig(
        id="provider-1",
        provider_name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4o-mini",
        api_key_ref="provider-1-key",
        is_default=True,
        is_enabled=True,
    )
    secret_store = MemorySecretStore({"provider-1-key": "sk-existing"})
    provider_client = FakeProviderClient()
    service = DefaultSettingsService(
        repository=repository,
        secret_store=secret_store,
        provider_client=provider_client,
    )

    result = service.test_provider_connection(
        ProviderConnectionTestRequest(
            provider_config_id="provider-1",
            provider_name="openai",
            base_url="https://api.openai.com/v1",
            model_name="gpt-4o-mini",
        )
    )

    assert result.success is True
    assert provider_client.last_provider_name == "openai"
    assert provider_client.last_api_key == "sk-existing"


def test_settings_service_tests_ollama_without_api_key() -> None:
    provider_client = FakeProviderClient()
    service = DefaultSettingsService(
        repository=InMemorySettingsRepository(),
        secret_store=MemorySecretStore(),
        provider_client=provider_client,
    )

    result = service.test_provider_connection(
        ProviderConnectionTestRequest(
            provider_name="ollama",
            base_url="http://localhost:11434",
            model_name="llama3",
        )
    )

    assert result.success is True
    assert result.message == "ollama ok"
    assert provider_client.last_provider_name == "ollama"
    assert provider_client.last_api_key is None
