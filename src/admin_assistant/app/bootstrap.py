from __future__ import annotations

from dataclasses import dataclass, field

from admin_assistant.app.container import ServiceContainer, build_service_container
from admin_assistant.infrastructure.platform.paths import default_database_url
from admin_assistant.version import APP_NAME


@dataclass(frozen=True)
class AppConfig:
    app_name: str = APP_NAME
    database_url: str = field(default_factory=default_database_url)


class ApplicationBootstrap:
    def build_container(self, config: AppConfig | None = None) -> ServiceContainer:
        resolved_config = config or AppConfig()
        return build_service_container(resolved_config)

    def build_main_window(self, config: AppConfig | None = None):
        from admin_assistant.ui.main_window import MainWindow

        container = self.build_container(config)
        return MainWindow(container=container)
