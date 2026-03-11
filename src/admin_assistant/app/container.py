from __future__ import annotations

from dataclasses import dataclass

from admin_assistant.app.event_bus import InMemoryEventBus
from admin_assistant.app.qt_bridge import QtEventBridge
from admin_assistant.app.task_runner import DefaultTaskRunner
from admin_assistant.infrastructure.ai.httpx_provider import HttpxAIProviderClient
from admin_assistant.infrastructure.db.repositories.ai_repository_sqlalchemy import (
    SqlAlchemyAIRepository,
)
from admin_assistant.infrastructure.db.repositories.execution_repository_sqlalchemy import (
    SqlAlchemyExecutionRepository,
)
from admin_assistant.infrastructure.db.repositories.history_query_sqlalchemy import (
    SqlAlchemyHistoryReadStore,
)
from admin_assistant.infrastructure.db.repositories.script_repository_sqlalchemy import (
    SqlAlchemyScriptRepository,
)
from admin_assistant.infrastructure.db.repositories.server_repository_sqlalchemy import (
    SqlAlchemyServerRepository,
)
from admin_assistant.infrastructure.db.repositories.settings_repository_sqlalchemy import (
    SqlAlchemySettingsRepository,
)
from admin_assistant.infrastructure.db.session import create_session_factory
from admin_assistant.infrastructure.secrets.keyring_store import KeyringSecretStore
from admin_assistant.infrastructure.ssh.paramiko_gateway import (
    ParamikoConnectivityProbe,
    ParamikoSSHExecutionGateway,
)
from admin_assistant.modules.ai.service import DefaultAIAnalysisService
from admin_assistant.modules.ai.prompt_builder import DefaultPromptBuilder
from admin_assistant.modules.execution.service import DefaultExecutionService
from admin_assistant.modules.history.service import DefaultHistoryQueryService
from admin_assistant.modules.incident.prompt_builder import DefaultIncidentPromptBuilder
from admin_assistant.modules.incident.service import DefaultIncidentService
from admin_assistant.modules.scripts.service import DefaultScriptService
from admin_assistant.modules.servers.service import DefaultServerService
from admin_assistant.modules.settings.service import DefaultSettingsService


@dataclass
class ServiceContainer:
    config: object
    event_bus: InMemoryEventBus
    qt_bridge: QtEventBridge
    task_runner: DefaultTaskRunner
    server_service: DefaultServerService
    script_service: DefaultScriptService
    execution_service: DefaultExecutionService
    ai_service: DefaultAIAnalysisService
    incident_service: DefaultIncidentService
    history_service: DefaultHistoryQueryService
    settings_service: DefaultSettingsService


def build_service_container(config: object) -> ServiceContainer:
    event_bus = InMemoryEventBus()
    qt_bridge = QtEventBridge(event_bus=event_bus)
    task_runner = DefaultTaskRunner()
    session_factory = create_session_factory(database_url=config.database_url, create_schema=True)

    server_repository = SqlAlchemyServerRepository(session_factory=session_factory)
    script_repository = SqlAlchemyScriptRepository(session_factory=session_factory)
    execution_repository = SqlAlchemyExecutionRepository(session_factory=session_factory)
    ai_repository = SqlAlchemyAIRepository(session_factory=session_factory)
    history_store = SqlAlchemyHistoryReadStore(session_factory=session_factory)
    settings_repository = SqlAlchemySettingsRepository(session_factory=session_factory)

    secret_store = KeyringSecretStore(service_name=config.app_name)
    connectivity_probe = ParamikoConnectivityProbe()
    ssh_gateway = ParamikoSSHExecutionGateway()
    ai_provider = HttpxAIProviderClient()
    prompt_builder = DefaultPromptBuilder()
    incident_prompt_builder = DefaultIncidentPromptBuilder()

    server_service = DefaultServerService(
        repository=server_repository,
        secret_store=secret_store,
        connectivity_probe=connectivity_probe,
    )
    script_service = DefaultScriptService(repository=script_repository)
    execution_service = DefaultExecutionService(
        repository=execution_repository,
        output_repository=execution_repository,
        server_reader=server_repository,
        script_reader=script_repository,
        secret_store=secret_store,
        ssh_gateway=ssh_gateway,
        publish_event=event_bus.publish,
        task_runner=task_runner,
    )
    settings_service = DefaultSettingsService(
        repository=settings_repository,
        secret_store=secret_store,
        provider_client=ai_provider,
    )
    ai_service = DefaultAIAnalysisService(
        repository=ai_repository,
        run_reader=execution_repository,
        settings_repository=settings_repository,
        secret_store=secret_store,
        provider_client=ai_provider,
        prompt_builder=prompt_builder,
        run_launcher=execution_service,
        publish_event=event_bus.publish,
    )
    incident_service = DefaultIncidentService(
        settings_repository=settings_repository,
        secret_store=secret_store,
        provider_client=ai_provider,
        prompt_builder=incident_prompt_builder,
        execution_service=execution_service,
        ai_service=ai_service,
    )
    history_service = DefaultHistoryQueryService(read_store=history_store)

    return ServiceContainer(
        config=config,
        event_bus=event_bus,
        qt_bridge=qt_bridge,
        task_runner=task_runner,
        server_service=server_service,
        script_service=script_service,
        execution_service=execution_service,
        ai_service=ai_service,
        incident_service=incident_service,
        history_service=history_service,
        settings_service=settings_service,
    )
