from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from admin_assistant.app.events import AnalysisCompletedEvent, RunCompletedEvent, SuggestedActionExecutedEvent
from admin_assistant.app.qt_bridge import QtEventBridge
from admin_assistant.modules.history.dto import ConsoleReplayQuery, RunDetailsQuery, RunHistoryQuery
from admin_assistant.modules.history.service import HistoryQueryService
from admin_assistant.ui.dialogs.support_dialogs import show_critical_error


class HistoryPanel(QWidget):
    def __init__(
        self,
        service: HistoryQueryService,
        qt_bridge: QtEventBridge,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._qt_bridge = qt_bridge
        self._host_tabs: dict[str, QTextEdit] = {}

        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        left_widget = QWidget(splitter)
        right_widget = QWidget(splitter)
        left_layout = QVBoxLayout(left_widget)
        right_layout = QVBoxLayout(right_widget)

        left_header = QHBoxLayout()
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search runs")
        self.refresh_button = QPushButton("Refresh", self)
        self.run_list = QListWidget(self)

        left_header.addWidget(self.search_input, 1)
        left_header.addWidget(self.refresh_button)
        left_layout.addLayout(left_header)
        left_layout.addWidget(self.run_list)

        self.summary_text = QTextEdit(self)
        self.summary_text.setReadOnly(True)
        self.summary_text.setPlaceholderText("Select a run to inspect its details.")
        self.targets_list = QListWidget(self)
        self.detail_tabs = QTabWidget(self)
        self.output_tabs = QTabWidget(self)
        self.all_hosts_output = QTextEdit(self)
        self.all_hosts_output.setReadOnly(True)
        self.output_tabs.addTab(self.all_hosts_output, "All Hosts")
        self.ai_links_text = QTextEdit(self)
        self.ai_links_text.setReadOnly(True)
        self.ai_links_text.setPlaceholderText("Linked AI analyses and suggested actions will appear here.")
        self.detail_tabs.addTab(self.output_tabs, "Output")
        self.detail_tabs.addTab(self.ai_links_text, "AI Links")

        right_layout.addWidget(QLabel("Run Summary", self))
        right_layout.addWidget(self.summary_text)
        right_layout.addWidget(QLabel("Per-Target Status", self))
        right_layout.addWidget(self.targets_list)
        right_layout.addWidget(self.detail_tabs, 1)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([320, 900])

        layout.addWidget(splitter)

        self.search_input.textChanged.connect(self.refresh_runs)
        self.refresh_button.clicked.connect(self.refresh_runs)
        self.run_list.currentItemChanged.connect(self._on_run_selected)
        self._qt_bridge.event_published.connect(self._on_app_event)

        self.refresh_runs()

    def refresh_runs(self, *_args: object, selected_run_id: str | None = None) -> None:
        current_run_id = selected_run_id if selected_run_id is not None else self._current_run_id()
        self.run_list.clear()

        try:
            page = self._service.list_runs(
                RunHistoryQuery(search_text=self.search_input.text().strip() or None)
            )
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "History", str(exc))
            return

        restored_item: QListWidgetItem | None = None
        for item in page.items:
            time_text = item.requested_at.strftime("%Y-%m-%d %H:%M:%S") if item.requested_at else "Unknown time"
            list_item = QListWidgetItem(
                f"{time_text}\n{item.run_kind.value} | targets: {item.target_count} | {item.status.value}",
                self.run_list,
            )
            list_item.setData(Qt.ItemDataRole.UserRole, item.run_id)
            if item.run_id == current_run_id:
                restored_item = list_item

        if restored_item is not None:
            self.run_list.setCurrentItem(restored_item)
        elif self.run_list.count() > 0:
            self.run_list.setCurrentRow(0)
        else:
            self._clear_details()

    def _on_run_selected(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        del previous
        if current is None:
            self._clear_details()
            return

        run_id = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(run_id, str):
            self._clear_details()
            return

        try:
            details = self._service.get_run_details(RunDetailsQuery(run_id=run_id))
            console_replay = self._service.get_console_replay(ConsoleReplayQuery(run_id=run_id))
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "History", str(exc))
            return

        self._render_summary(details)
        self._render_targets(details)
        self._render_console_replay(console_replay)
        self._render_ai_links(details)

    def _render_summary(self, details) -> None:
        lines = [
            f"Run ID: {details.run_id}",
            f"Kind: {details.run_kind.value}",
            f"Status: {details.status.value}",
            f"Targets: {details.target_count}",
            f"Shell: {details.shell_type.value}",
            f"Sudo: {'yes' if details.requires_sudo else 'no'}",
            f"PTY: {'yes' if details.requires_tty else 'no'}",
        ]
        if details.requested_at:
            lines.append(f"Requested: {details.requested_at}")
        if details.started_at:
            lines.append(f"Started: {details.started_at}")
        if details.completed_at:
            lines.append(f"Completed: {details.completed_at}")
        if details.command_snapshot:
            lines.append(f"Command: {details.command_snapshot}")
        if details.script_name:
            lines.append(f"Script: {details.script_name}")
        if details.source_analysis_id:
            lines.append(f"Source Analysis: {details.source_analysis_id}")
        if details.source_action_id:
            lines.append(f"Source Suggested Action: {details.source_action_id}")
        self.summary_text.setPlainText("\n".join(lines))

    def _render_targets(self, details) -> None:
        self.targets_list.clear()
        for target in details.targets:
            status_text = f"{target.server_name} | {target.status.value}"
            if target.exit_code is not None:
                status_text += f" | exit {target.exit_code}"
            if target.error_message:
                status_text += f" | {target.error_message}"
            self.targets_list.addItem(status_text)

    def _render_console_replay(self, console_replay) -> None:
        self.all_hosts_output.clear()
        while self.output_tabs.count() > 1:
            self.output_tabs.removeTab(1)
        self._host_tabs.clear()

        for line in console_replay.all_hosts_lines:
            host_console = self._ensure_host_tab(line.server_name)
            raw_lines = line.chunk_text.rstrip().splitlines() or [""]
            for raw_line in raw_lines:
                self.all_hosts_output.append(f"[{line.server_name}][{line.stream.value}] {raw_line}")
                host_prefix = "[stderr] " if line.stream.value == "stderr" else ""
                host_console.append(f"{host_prefix}{raw_line}")

    def _render_ai_links(self, details) -> None:
        if not details.analyses and not details.source_action_id and not details.source_analysis_id:
            self.ai_links_text.setPlainText("No linked AI analysis for this run.")
            return

        lines: list[str] = []
        if details.source_analysis_id or details.source_action_id:
            lines.append("Run relationship")
            if details.source_analysis_id:
                lines.append(f"- Triggered by analysis: {details.source_analysis_id}")
            if details.source_action_id:
                lines.append(f"- Triggered by suggested action: {details.source_action_id}")
            lines.append("")

        for analysis in details.analyses:
            lines.append(f"Analysis {analysis.id} [{analysis.status.value}]")
            if analysis.created_at:
                lines.append(f"Created: {analysis.created_at}")
            lines.append(f"Summary: {analysis.summary or 'No summary'}")
            if analysis.probable_causes:
                lines.append("Probable causes:")
                lines.extend(f"- {cause}" for cause in analysis.probable_causes)
            if analysis.next_steps:
                lines.append("Next steps:")
                lines.extend(f"- {step}" for step in analysis.next_steps)
            if analysis.suggested_actions:
                lines.append("Suggested actions:")
                for action in analysis.suggested_actions:
                    action_line = (
                        f"- {action.title} [{action.risk_level.value}] [{action.approval_status.value}]"
                    )
                    if action.execution_run_id:
                        action_line += f" -> run {action.execution_run_id}"
                    lines.append(action_line)
                    lines.append(f"  target_scope={action.target_scope}")
                    lines.append(f"  command={action.command_text}")
            lines.append("")

        self.ai_links_text.setPlainText("\n".join(lines).strip())

    def _ensure_host_tab(self, host_name: str) -> QTextEdit:
        if host_name not in self._host_tabs:
            console = QTextEdit(self)
            console.setReadOnly(True)
            self._host_tabs[host_name] = console
            self.output_tabs.addTab(console, host_name)
        return self._host_tabs[host_name]

    def _current_run_id(self) -> str | None:
        item = self.run_list.currentItem()
        if item is None:
            return None
        run_id = item.data(Qt.ItemDataRole.UserRole)
        return run_id if isinstance(run_id, str) else None

    def _clear_details(self) -> None:
        self.summary_text.clear()
        self.targets_list.clear()
        self.all_hosts_output.clear()
        while self.output_tabs.count() > 1:
            self.output_tabs.removeTab(1)
        self._host_tabs.clear()
        self.ai_links_text.setPlainText("Select a run to inspect its linked AI analysis.")

    def _on_app_event(self, event: object) -> None:
        if isinstance(event, (RunCompletedEvent, AnalysisCompletedEvent, SuggestedActionExecutedEvent)):
            self.refresh_runs(selected_run_id=self._current_run_id())
