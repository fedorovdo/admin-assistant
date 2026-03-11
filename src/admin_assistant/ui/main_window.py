from __future__ import annotations

from concurrent.futures import Future

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QSplitter, QWidget, QHBoxLayout, QTabWidget, QMessageBox

from admin_assistant.app.container import ServiceContainer
from admin_assistant.core.enums import ShellType
from admin_assistant.modules.incident.dto import IncidentInvestigateRequest, IncidentSession
from admin_assistant.ui.dialogs.incident_dialog import IncidentDialog
from admin_assistant.ui.dialogs.support_dialogs import show_critical_error
from admin_assistant.ui.dialogs.system_info_dialog import SystemInfoDialog, build_system_info_text
from admin_assistant.ui.panels.ai_panel import AIPanel
from admin_assistant.ui.panels.console_panel import ConsolePanel
from admin_assistant.ui.panels.history_panel import HistoryPanel
from admin_assistant.ui.panels.scripts_panel import ScriptsPanel
from admin_assistant.ui.panels.servers_panel import ServersPanel
from admin_assistant.version import ABOUT_TEXT, APP_NAME, APP_TITLE


class MainWindow(QMainWindow):
    incident_completed = Signal(object)
    incident_failed = Signal(str)
    incident_progress = Signal(str)

    def __init__(self, container: ServiceContainer) -> None:
        super().__init__()
        self._container = container
        self.setWindowTitle(APP_TITLE)
        self.resize(1400, 900)
        self._build_menu()

        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)

        main_splitter = QSplitter(Qt.Orientation.Horizontal, root)
        left_splitter = QSplitter(Qt.Orientation.Vertical, main_splitter)

        self.servers_panel = ServersPanel(service=container.server_service, parent=left_splitter)
        self.scripts_panel = ScriptsPanel(service=container.script_service, parent=left_splitter)
        self.console_panel = ConsolePanel(
            execution_service=container.execution_service,
            history_service=container.history_service,
            task_runner=container.task_runner,
            qt_bridge=container.qt_bridge,
            parent=None,
        )
        self.history_panel = HistoryPanel(
            service=container.history_service,
            qt_bridge=container.qt_bridge,
            parent=None,
        )
        self.ai_panel = AIPanel(
            service=container.ai_service,
            settings_service=container.settings_service,
            task_runner=container.task_runner,
            parent=main_splitter,
        )
        self.center_tabs = QTabWidget(main_splitter)
        self.center_tabs.addTab(self.console_panel, "Execution")
        self.center_tabs.addTab(self.history_panel, "History")

        self.servers_panel.selection_changed.connect(self.console_panel.set_selected_server_ids)
        self.scripts_panel.selection_changed.connect(self.console_panel.set_selected_script)
        self.console_panel.analyze_requested.connect(self.ai_panel.request_analysis_for_run)
        self.console_panel.investigate_requested.connect(self._start_incident_investigation)
        self.ai_panel.execution_requested.connect(self._activate_execution_tab)
        self.ai_panel.execution_requested.connect(self.console_panel.prepare_for_external_run)
        self.ai_panel.execution_failed.connect(self.console_panel.fail_external_run)
        self.incident_completed.connect(self._handle_incident_completed)
        self.incident_failed.connect(self._handle_incident_failed)
        self.incident_progress.connect(self.console_panel.append_status_message)
        self.console_panel.set_selected_server_ids(self.servers_panel.selected_server_ids())
        self.console_panel.set_selected_script(self.scripts_panel.selected_script_info())

        left_splitter.addWidget(self.servers_panel)
        left_splitter.addWidget(self.scripts_panel)
        left_splitter.setStretchFactor(0, 1)
        left_splitter.setStretchFactor(1, 1)

        main_splitter.addWidget(left_splitter)
        main_splitter.addWidget(self.center_tabs)
        main_splitter.addWidget(self.ai_panel)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 4)
        main_splitter.setStretchFactor(2, 1)
        main_splitter.setSizes([320, 820, 320])

        root_layout.addWidget(main_splitter)
        self.setCentralWidget(root)

    def _build_menu(self) -> None:
        help_menu = self.menuBar().addMenu("&Help")
        system_info_action = QAction("&System Info", self)
        about_action = QAction("&About", self)
        system_info_action.triggered.connect(self._show_system_info_dialog)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(system_info_action)
        help_menu.addAction(about_action)

    def _activate_execution_tab(self, _message: str) -> None:
        self.center_tabs.setCurrentWidget(self.console_panel)

    def _start_incident_investigation(self, shell_value: str) -> None:
        server_ids = self.servers_panel.selected_server_ids()
        if not server_ids:
            QMessageBox.information(self, "Investigate", "Select at least one server before starting Incident Mode.")
            return

        dialog = IncidentDialog(target_count=len(server_ids), parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        symptom = dialog.incident_symptom()
        if not symptom:
            QMessageBox.information(self, "Investigate", "Enter an incident symptom before starting Incident Mode.")
            return

        try:
            shell_type = ShellType(shell_value)
        except ValueError:
            shell_type = ShellType.BASH

        self._activate_execution_tab("")
        self.console_panel.prepare_for_external_run(
            "[incident][status] Starting Incident Mode...",
            action_line="[ACTION] Starting Incident Mode via Execution panel",
            info_line="[INFO] Incident Mode runs safe diagnostic commands through the main Execution panel.",
            hold_controls_until_complete=True,
        )

        request = IncidentInvestigateRequest(
            title=dialog.incident_title() or None,
            symptom=symptom,
            server_ids=server_ids,
            shell_type=shell_type,
            initiated_by="user",
        )
        future = self._container.task_runner.submit(
            self._container.incident_service.investigate,
            request,
            self.incident_progress.emit,
        )
        future.add_done_callback(self._on_incident_future_done)

    def _on_incident_future_done(self, future: Future[object]) -> None:
        try:
            result = future.result()
        except Exception as exc:  # pragma: no cover - background UI path
            self.incident_failed.emit(str(exc))
            return

        if isinstance(result, IncidentSession):
            self.incident_completed.emit(result)
            return
        self.incident_failed.emit("Incident Mode did not return a valid session result.")

    def _handle_incident_completed(self, session: IncidentSession) -> None:
        self.console_panel.complete_external_flow()
        if session.analysis is None:
            self.console_panel.append_status_message(
                "[incident][status] Investigation finished, but no analysis payload was returned."
            )
            return
        self.ai_panel.load_analysis_by_id(session.analysis.analysis_id)
        self.console_panel.append_status_message(
            f"[incident][status] Investigation complete. Review analysis '{session.analysis.analysis_id}' in the AI panel."
        )

    def _handle_incident_failed(self, message: str) -> None:
        self.console_panel.fail_external_run(message)
        show_critical_error(self, "Incident Mode", message)

    def _show_about_dialog(self) -> None:
        QMessageBox.about(self, f"About {APP_NAME}", ABOUT_TEXT)

    def _show_system_info_dialog(self) -> None:
        provider_config = self._container.settings_service.get_default_provider_config()
        dialog = SystemInfoDialog(build_system_info_text(provider_config), self)
        dialog.exec()
