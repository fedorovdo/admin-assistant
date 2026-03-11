from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from admin_assistant.core.enums import AnalysisLanguage
from admin_assistant.infrastructure.db.models.ai_provider_config_record import AIProviderConfigRecord
from admin_assistant.infrastructure.db.models.app_setting_record import AppSettingRecord
from admin_assistant.modules.settings.models import AIProviderConfig, AppSettings


def _settings_to_domain(record: AppSettingRecord) -> AppSettings:
    return AppSettings(
        id=record.id,
        default_ai_provider_id=record.default_ai_provider_id,
        analysis_language=AnalysisLanguage(record.analysis_language or AnalysisLanguage.EN.value),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _provider_to_domain(record: AIProviderConfigRecord) -> AIProviderConfig:
    return AIProviderConfig(
        id=record.id,
        provider_name=record.provider_name,
        display_name=record.display_name,
        base_url=record.base_url,
        model_name=record.model_name,
        api_key_ref=record.api_key_ref,
        timeout_sec=record.timeout_sec,
        temperature=record.temperature,
        is_default=record.is_default,
        is_enabled=record.is_enabled,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class SqlAlchemySettingsRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_app_settings(self) -> AppSettings | None:
        with self._session_factory() as session:
            statement = select(AppSettingRecord).limit(1)
            record = session.scalars(statement).first()
            return _settings_to_domain(record) if record is not None else None

    def save_app_settings(self, settings: AppSettings) -> AppSettings:
        with self._session_factory() as session:
            record = session.get(AppSettingRecord, settings.id)
            if record is None:
                record = AppSettingRecord(
                    id=settings.id,
                    default_ai_provider_id=settings.default_ai_provider_id,
                    analysis_language=settings.analysis_language.value,
                    created_at=settings.created_at,
                    updated_at=settings.updated_at,
                )
                session.add(record)
            else:
                record.default_ai_provider_id = settings.default_ai_provider_id
                record.analysis_language = settings.analysis_language.value
                record.created_at = settings.created_at
                record.updated_at = settings.updated_at
            session.commit()
            session.refresh(record)
            return _settings_to_domain(record)

    def add_provider_config(self, config: AIProviderConfig) -> AIProviderConfig:
        record = AIProviderConfigRecord(
            id=config.id,
            provider_name=config.provider_name,
            display_name=config.display_name,
            base_url=config.base_url,
            model_name=config.model_name,
            api_key_ref=config.api_key_ref,
            timeout_sec=config.timeout_sec,
            temperature=config.temperature,
            is_default=config.is_default,
            is_enabled=config.is_enabled,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )
        with self._session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return _provider_to_domain(record)

    def update_provider_config(self, config: AIProviderConfig) -> AIProviderConfig:
        with self._session_factory() as session:
            record = session.get(AIProviderConfigRecord, config.id)
            if record is None:
                raise KeyError(f"Provider config '{config.id}' not found.")

            record.provider_name = config.provider_name
            record.display_name = config.display_name
            record.base_url = config.base_url
            record.model_name = config.model_name
            record.api_key_ref = config.api_key_ref
            record.timeout_sec = config.timeout_sec
            record.temperature = config.temperature
            record.is_default = config.is_default
            record.is_enabled = config.is_enabled
            record.created_at = config.created_at
            record.updated_at = config.updated_at
            session.commit()
            session.refresh(record)
            return _provider_to_domain(record)

    def get_provider_config(self, provider_config_id: str) -> AIProviderConfig | None:
        with self._session_factory() as session:
            record = session.get(AIProviderConfigRecord, provider_config_id)
            return _provider_to_domain(record) if record is not None else None

    def list_provider_configs(self, include_disabled: bool = True) -> tuple[AIProviderConfig, ...]:
        with self._session_factory() as session:
            statement = select(AIProviderConfigRecord).order_by(
                AIProviderConfigRecord.created_at.asc(),
                AIProviderConfigRecord.id.asc(),
            )
            if not include_disabled:
                statement = statement.where(AIProviderConfigRecord.is_enabled.is_(True))
            records = session.scalars(statement).all()
            return tuple(_provider_to_domain(record) for record in records)

    def delete_provider_config(self, provider_config_id: str) -> None:
        with self._session_factory() as session:
            record = session.get(AIProviderConfigRecord, provider_config_id)
            if record is None:
                return
            session.delete(record)
            session.commit()
