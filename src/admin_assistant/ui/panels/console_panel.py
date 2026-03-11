from __future__ import annotations

from concurrent.futures import Future

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from admin_assistant.app.events import (
    OutputChunkReceivedEvent,
    RunCompletedEvent,
    RunCreatedEvent,
    TargetCompletedEvent,
    TargetStartedEvent,
)
from admin_assistant.app.qt_bridge import QtEventBridge
from admin_assistant.app.task_runner import TaskRunner
from admin_assistant.core.enums import RunKind, RunStatus, ShellType, StreamType
from admin_assistant.modules.execution.dto import RunRequest
from admin_assistant.modules.execution.service import ExecutionService
from admin_assistant.ui.dialogs.support_dialogs import show_critical_error


class ConsolePanel(QWidget):
    run_failed = Signal(str)
    analyze_requested = Signal(str)
    investigate_requested = Signal(str)

    def __init__(
        self,
        execution_service: ExecutionService,
        history_service: object,
        task_runner: TaskRunner,
        qt_bridge: QtEventBridge,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._execution_service = execution_service
        self._history_service = history_service
        self._task_runner = task_runner
        self._qt_bridge = qt_bridge
        self._host_tabs: dict[str, QTextEdit] = {}
        self._selected_server_ids: tuple[str, ...] = ()
        self._selected_script_id: str | None = None
        self._selected_script_label: str | None = None
        self._run_in_progress = False
        self._external_flow_active = False
        self._hold_external_controls = False
        self._active_run_id: str | None = None
        self._last_completed_run_id: str | None = None
        self._target_host_names: dict[str, str] = {}

        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.mode_combo = QComboBox(self)
        self.mode_combo.addItems(["Manual Command", "Script"])
        self.shell_combo = QComboBox(self)
        self.shell_combo.addItems([ShellType.BASH.value, ShellType.SH.value])
        self.target_label = QLabel("Targets: 0 selected", self)
        self.sudo_checkbox = QCheckBox("Run with sudo", self)
        self.pty_checkbox = QCheckBox("Allocate PTY", self)
        self.run_button = QPushButton("Run", self)
        self.stop_button = QPushButton("Stop", self)
        self.analyze_button = QPushButton("Analyze", self)
        self.investigate_button = QPushButton("Investigate", self)
        self.stop_button.setToolTip("Active run control in the Execution panel.")

        controls.addWidget(self.mode_combo)
        controls.addWidget(self.shell_combo)
        controls.addWidget(self.target_label)
        controls.addWidget(self.sudo_checkbox)
        controls.addWidget(self.pty_checkbox)
        controls.addWidget(self.run_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.analyze_button)
        controls.addWidget(self.investigate_button)

        input_row = QHBoxLayout()
        self.input_label = QLabel("Command", self)
        self.command_input = QLineEdit(self)
        self.command_input.setPlaceholderText("Enter manual command")
        self.command_input.setClearButtonEnabled(True)
        self.script_display = QLineEdit(self)
        self.script_display.setReadOnly(True)
        self.script_display.setPlaceholderText("No script selected. Choose a script from the Scripts panel.")

        input_row.addWidget(self.input_label)
        input_row.addWidget(self.command_input, 1)
        input_row.addWidget(self.script_display, 1)

        self.tabs = QTabWidget(self)
        self.all_hosts_console = QTextEdit(self)
        self.all_hosts_console.setReadOnly(True)
        self.tabs.addTab(self.all_hosts_console, "All Hosts")

        layout.addLayout(controls)
        layout.addLayout(input_row)
        layout.addWidget(self.tabs)

        self.stop_button.setEnabled(False)
        self.analyze_button.setEnabled(False)
        self.analyze_button.setToolTip("Analyze the most recent completed run.")

        self.mode_combo.currentTextChanged.connect(self._update_ui_state)
        self.command_input.textChanged.connect(self._update_ui_state)
        self.sudo_checkbox.toggled.connect(self._sync_privilege_controls)
        self.pty_checkbox.toggled.connect(self._update_ui_state)
        self.run_button.clicked.connect(self._run_current_mode)
        self.analyze_button.clicked.connect(self._request_analysis)
        self.investigate_button.clicked.connect(self._request_investigation)
        self.run_failed.connect(self._handle_run_failed)
        self._qt_bridge.event_published.connect(self._on_app_event)
        self._sync_privilege_controls()
        self._update_ui_state()

    def set_selected_server_ids(self, server_ids: tuple[str, ...]) -> None:
        self._selected_server_ids = server_ids
        self.target_label.setText(f"Targets: {len(server_ids)} selected")
        self._update_ui_state()

    def ensure_host_tab(self, host_name: str) -> QTextEdit:
        if host_name not in self._host_tabs:
            console = QTextEdit(self)
            console.setReadOnly(True)
            self._host_tabs[host_name] = console
            self.tabs.addTab(console, host_name)
        return self._host_tabs[host_name]

    def set_selected_script(self, script_info: object) -> None:
        if isinstance(script_info, tuple) and len(script_info) == 2:
            script_id, script_label = script_info
            self._selected_script_id = script_id if isinstance(script_id, str) else None
            self._selected_script_label = script_label if isinstance(script_label, str) else None
        elif isinstance(script_info, str):
            self._selected_script_id = script_info
            self._selected_script_label = script_info
        else:
            self._selected_script_id = None
            self._selected_script_label = None
        self._update_script_display()
        self._update_ui_state()

    def set_selected_script_id(self, script_id: object) -> None:
        self.set_selected_script(script_id)

    def prepare_for_external_run(
        self,
        message: str = "[run][status] Starting approved AI action...",
        *,
        action_line: str = "[ACTION] Executing approved AI action via Execution panel",
        info_line: str = "[INFO] This run is now managed by the main Execution panel. Use its active run controls there.",
        hold_controls_until_complete: bool = False,
    ) -> None:
        self._reset_console()
        self._target_host_names.clear()
        self._active_run_id = None
        self._last_completed_run_id = None
        self._run_in_progress = True
        self._external_flow_active = True
        self._hold_external_controls = hold_controls_until_complete
        self.all_hosts_console.append(action_line)
        self.all_hosts_console.append(info_line)
        self.all_hosts_console.append(message)
        self._update_ui_state()

    def fail_external_run(self, message: str) -> None:
        if self._active_run_id is not None:
            return
        self._run_in_progress = False
        self._external_flow_active = False
        self._hold_external_controls = False
        self.all_hosts_console.append(f"[run][status] Failed to start: {message}")
        self._update_ui_state()

    def append_status_message(self, message: str) -> None:
        self.all_hosts_console.append(message)

    def complete_external_flow(self) -> None:
        self._external_flow_active = False
        self._hold_external_controls = False
        self._update_ui_state()

    def _run_current_mode(self) -> None:
        if self._run_in_progress:
            return
        if not self._selected_server_ids:
            QMessageBox.warning(self, "Run", "Select at least one server before running.")
            return

        try:
            request = self._build_run_request_for_current_mode()
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Run", str(exc))
            return

        self._reset_console()
        self._target_host_names.clear()
        self._active_run_id = None
        self._last_completed_run_id = None
        self._run_in_progress = True
        self.all_hosts_console.append("[run][status] Starting run in background...")
        self._update_ui_state()

        future = self._task_runner.submit(self._execution_service.start_run, request)
        future.add_done_callback(self._on_run_future_done)

    def _build_run_request_for_current_mode(self) -> RunRequest:
        if self.mode_combo.currentText() == "Manual Command":
            command_text = self.command_input.text().strip()
            if not command_text:
                raise ValueError("Enter a manual command before running.")
            return RunRequest(
                run_kind=RunKind.COMMAND,
                server_ids=self._selected_server_ids,
                command_text=command_text,
                shell_type=ShellType(self.shell_combo.currentText()),
                requires_sudo=self.sudo_checkbox.isChecked(),
                requires_tty=self.pty_checkbox.isChecked() or self.sudo_checkbox.isChecked(),
            )

        if not self._selected_script_id:
            raise ValueError("Select one script before running in Script mode.")
        return RunRequest(
            run_kind=RunKind.SCRIPT,
            server_ids=self._selected_server_ids,
            script_id=self._selected_script_id,
            shell_type=ShellType.BASH,
        )

    def _on_run_future_done(self, future: Future[object]) -> None:
        try:
            future.result()
        except Exception as exc:  # pragma: no cover - background error path
            self.run_failed.emit(str(exc))
            return

    def _handle_run_failed(self, message: str) -> None:
        self._run_in_progress = False
        self._active_run_id = None
        self._update_ui_state()
        show_critical_error(self, "Run", message)

    def _on_app_event(self, event: object) -> None:
        if isinstance(event, RunCreatedEvent):
            if self._run_in_progress and self._active_run_id is None:
                self._active_run_id = event.run_id
                self.all_hosts_console.append(
                    f"[run][status] Run created | Kind: {event.run_kind} | Targets: {len(event.server_ids)}"
                )
            return

        if self._active_run_id is None or getattr(event, "run_id", None) != self._active_run_id:
            return

        if isinstance(event, TargetStartedEvent):
            self._target_host_names[event.target_result_id] = event.server_name
            host_console = self.ensure_host_tab(event.server_name)
            self.all_hosts_console.append(f"[{event.server_name}][status] Started")
            host_console.append("Started")
            return

        if isinstance(event, OutputChunkReceivedEvent):
            self._target_host_names[event.target_result_id] = event.server_name
            host_console = self.ensure_host_tab(event.server_name)
            lines = event.chunk_text.rstrip().splitlines() or [""]
            for line in lines:
                self.all_hosts_console.append(f"[{event.server_name}][{event.stream}] {line}")
                host_prefix = "[stderr] " if event.stream == StreamType.STDERR.value else ""
                host_console.append(f"{host_prefix}{line}")
            return

        if isinstance(event, TargetCompletedEvent):
            host_name = self._target_host_names.get(event.target_result_id, event.server_id)
            host_console = self.ensure_host_tab(host_name)
            status_line = f"Status: {event.status}"
            if event.exit_code is not None:
                status_line += f" | Exit Code: {event.exit_code}"
            if event.error_message:
                status_line += f" | Error: {event.error_message}"
            self.all_hosts_console.append(f"[{host_name}][status] {status_line}")
            host_console.append(status_line)
            return

        if isinstance(event, RunCompletedEvent):
            overall_line = (
                f"[run][status] Overall: {event.status} | "
                f"Succeeded: {event.success_count}/{event.target_count}"
            )
            self.all_hosts_console.append(overall_line)
            self._last_completed_run_id = event.run_id
            self._active_run_id = None
            self._run_in_progress = False
            if not self._hold_external_controls:
                self._external_flow_active = False
            self._update_ui_state()
            return

    def _request_analysis(self) -> None:
        if not self._last_completed_run_id:
            QMessageBox.information(
                self,
                "Analyze",
                "Run a command or script first, then analyze the completed run.",
            )
            return
        self.analyze_requested.emit(self._last_completed_run_id)

    def _request_investigation(self) -> None:
        if self._run_in_progress:
            return
        if not self._selected_server_ids:
            QMessageBox.information(
                self,
                "Investigate",
                "Select at least one server before starting Incident Mode.",
            )
            return
        self.investigate_requested.emit(self.shell_combo.currentText())

    def _reset_console(self) -> None:
        self.all_hosts_console.clear()
        while self.tabs.count() > 1:
            self.tabs.removeTab(1)
        self._host_tabs.clear()

    def _update_ui_state(self, *_args: object) -> None:
        controls_locked = self._run_in_progress or self._external_flow_active
        manual_mode = self.mode_combo.currentText() == "Manual Command"
        self.shell_combo.setEnabled(manual_mode and not controls_locked)
        self.command_input.setEnabled(manual_mode and not controls_locked)
        self.command_input.setVisible(manual_mode)
        self.script_display.setVisible(not manual_mode)
        self.input_label.setText("Command" if manual_mode else "Script")
        self.sudo_checkbox.setEnabled(manual_mode and not controls_locked)
        self.pty_checkbox.setEnabled(manual_mode and not self.sudo_checkbox.isChecked() and not controls_locked)
        if manual_mode:
            self.command_input.setPlaceholderText("Enter manual command")
        else:
            self._update_script_display()
        self.run_button.setEnabled(
            not controls_locked
            and len(self._selected_server_ids) >= 1
            and (
                (manual_mode and bool(self.command_input.text().strip()))
                or ((not manual_mode) and bool(self._selected_script_id))
            )
        )
        self.analyze_button.setEnabled(self._last_completed_run_id is not None and not controls_locked)
        self.investigate_button.setEnabled(len(self._selected_server_ids) >= 1 and not controls_locked)

    def _sync_privilege_controls(self, *_args: object) -> None:
        manual_mode = self.mode_combo.currentText() == "Manual Command"
        if self.sudo_checkbox.isChecked():
            self.pty_checkbox.setChecked(True)
            self.pty_checkbox.setEnabled(False)
        else:
            self.pty_checkbox.setEnabled(manual_mode)
        self._update_ui_state()

    def _update_script_display(self) -> None:
        if self._selected_script_id:
            self.script_display.setText(self._selected_script_label or self._selected_script_id)
        else:
            self.script_display.clear()
            self.script_display.setPlaceholderText("No script selected. Choose a script from the Scripts panel.")
