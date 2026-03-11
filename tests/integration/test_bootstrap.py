from __future__ import annotations

from admin_assistant.app.bootstrap import AppConfig, ApplicationBootstrap


def test_bootstrap_builds_service_container() -> None:
    bootstrap = ApplicationBootstrap()
    container = bootstrap.build_container(AppConfig(database_url="sqlite+pysqlite:///:memory:"))

    assert container.server_service is not None
    assert container.script_service is not None
    assert container.execution_service is not None
    assert container.ai_service is not None
    assert container.incident_service is not None
    assert container.history_service is not None
    assert container.settings_service is not None
