from __future__ import annotations

from concurrent.futures import Future

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from admin_assistant.app.task_runner import TaskRunner
from admin_assistant.core.enums import AnalysisLanguage, ApprovalStatus
from admin_assistant.modules.ai.dto import (
    AIAnalysisView,
    AnalysisLaunchResult,
    AnalysisQuery,
    AnalysisRequest,
    ExecuteSuggestedActionRequest,
    SuggestedActionApprovalRequest,
    SuggestedActionRejectionRequest,
)
from admin_assistant.modules.ai.service import AIAnalysisService
from admin_assistant.modules.settings.dto import UpdateAppSettingsRequest
from admin_assistant.modules.settings.service import SettingsService
from admin_assistant.ui.dialogs.provider_dialog import ProviderDialog
from admin_assistant.ui.dialogs.support_dialogs import show_critical_error


class AIPanel(QWidget):
    analysis_ready = Signal(str)
    analysis_failed = Signal(str)
    execution_ready = Signal(str)
    execution_failed = Signal(str)
    execution_requested = Signal(str)

    def __init__(
        self,
        service: AIAnalysisService,
        settings_service: SettingsService,
        task_runner: TaskRunner,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._settings_service = settings_service
        self._task_runner = task_runner
        self._analysis_in_progress = False
        self._execution_in_progress = False
        self._current_analysis_id: str | None = None
        self._current_analysis: AIAnalysisView | None = None
        self._preferred_action_id: str | None = None
        self._loading_language = False

        layout = QVBoxLayout(self)
        self.summary_label = QLabel("AI Analysis", self)
        language_row = QHBoxLayout()
        self.language_label = QLabel("Language", self)
        self.language_combo = QComboBox(self)
        self.language_combo.addItem("English", AnalysisLanguage.EN.value)
        self.language_combo.addItem("Russian", AnalysisLanguage.RU.value)
        self.provider_button = QPushButton("Configure AI Provider", self)
        self.summary_text = QTextEdit(self)
        self.summary_text.setReadOnly(True)
        self.summary_text.setPlaceholderText("AI explanations and next steps will appear here.")
        self.fix_plan_label = QLabel("Fix Plan", self)
        self.fix_plan_text = QTextEdit(self)
        self.fix_plan_text.setReadOnly(True)
        self.fix_plan_text.setPlaceholderText("A step-by-step remediation plan will appear here when available.")
        self.fix_steps_list = QListWidget(self)
        self.fix_steps_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.fix_steps_list.setAlternatingRowColors(True)
        self.actions_label = QLabel("Suggested Actions", self)
        self.actions_list = QListWidget(self)
        self.actions_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.actions_list.setAlternatingRowColors(True)
        self.approve_button = QPushButton("Approve", self)
        self.reject_button = QPushButton("Reject", self)
        self.execute_button = QPushButton("Execute Approved", self)

        language_row.addWidget(self.language_label)
        language_row.addWidget(self.language_combo, 1)

        layout.addWidget(self.summary_label)
        layout.addLayout(language_row)
        layout.addWidget(self.provider_button)
        layout.addWidget(self.summary_text)
        layout.addWidget(self.fix_plan_label)
        layout.addWidget(self.fix_plan_text)
        layout.addWidget(self.fix_steps_list)
        layout.addWidget(self.actions_label)
        layout.addWidget(self.actions_list)
        layout.addWidget(self.approve_button)
        layout.addWidget(self.reject_button)
        layout.addWidget(self.execute_button)

        self.approve_button.setEnabled(False)
        self.reject_button.setEnabled(False)
        self.execute_button.setEnabled(False)
        self.summary_text.setPlainText("No analysis yet.")

        self.provider_button.clicked.connect(self._open_provider_dialog)
        self.language_combo.currentIndexChanged.connect(self._save_language_selection)
        self.analysis_ready.connect(self._load_analysis)
        self.analysis_failed.connect(self._handle_analysis_failed)
        self.execution_ready.connect(self._handle_execution_ready)
        self.execution_failed.connect(self._handle_execution_failed)
        self.actions_list.itemSelectionChanged.connect(lambda: self._handle_action_selection(self.actions_list))
        self.fix_steps_list.itemSelectionChanged.connect(lambda: self._handle_action_selection(self.fix_steps_list))
        self.approve_button.clicked.connect(self._approve_selected_action)
        self.reject_button.clicked.connect(self._reject_selected_action)
        self.execute_button.clicked.connect(self._execute_selected_action)
        self._load_language_selection()
        self._set_fix_plan_visibility(False)

    def request_analysis_for_run(self, run_id: str) -> None:
        if self._analysis_in_progress:
            QMessageBox.information(self, "AI Analysis", "Analysis is already running.")
            return

        provider_config = self._settings_service.get_default_provider_config()
        if provider_config is None:
            QMessageBox.information(
                self,
                "AI Analysis",
                "No AI provider is configured yet. Use 'Configure AI Provider' in the AI panel first.",
            )
            return

        self._analysis_in_progress = True
        self._current_analysis = None
        self._current_analysis_id = None
        self._preferred_action_id = None
        self.summary_text.setPlainText("Analyzing run output...")
        self.fix_plan_text.clear()
        self.fix_steps_list.clear()
        self.actions_list.clear()
        self._set_fix_plan_visibility(False)
        self._update_action_buttons()

        future = self._task_runner.submit(
            self._service.request_analysis,
            AnalysisRequest(run_id=run_id, provider_config_id=provider_config.id),
        )
        future.add_done_callback(self._on_analysis_future_done)

    def load_analysis_by_id(self, analysis_id: str) -> None:
        self._preferred_action_id = None
        self._load_analysis(analysis_id)

    def _on_analysis_future_done(self, future: Future[object]) -> None:
        try:
            result = future.result()
        except Exception as exc:  # pragma: no cover - background error path
            self.analysis_failed.emit(str(exc))
            return

        if isinstance(result, AnalysisLaunchResult):
            self.analysis_ready.emit(result.analysis_id)
            return
        self.analysis_failed.emit("Analysis did not return a valid result.")

    def _load_analysis(self, analysis_id: str) -> None:
        self._analysis_in_progress = False
        try:
            analysis = self._service.get_analysis(AnalysisQuery(analysis_id=analysis_id))
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "AI Analysis", str(exc))
            self.summary_text.setPlainText(str(exc))
            return

        self._current_analysis_id = analysis.id
        self._current_analysis = analysis
        probable_causes = "\n".join(f"- {cause}" for cause in analysis.probable_causes) or "- None"
        evidence = "\n".join(f"- {item}" for item in analysis.evidence) or "- None"
        next_steps = "\n".join(f"- {step}" for step in analysis.next_steps) or "- None"
        self.summary_text.setPlainText(
            f"Summary\n{analysis.summary or 'No summary returned.'}\n\n"
            f"Probable Causes\n{probable_causes}\n\n"
            f"Evidence\n{evidence}\n\n"
            f"Next Steps\n{next_steps}"
        )
        self.fix_plan_text.setPlainText(self._format_fix_plan_summary(analysis))
        self._set_fix_plan_visibility(bool(analysis.fix_plan_title or analysis.fix_plan_summary or analysis.fix_steps))
        self.fix_steps_list.clear()
        for step in analysis.fix_steps:
            item = QListWidgetItem(self._format_fix_step_text(step), self.fix_steps_list)
            item.setData(Qt.ItemDataRole.UserRole, step.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, step.approval_status.value)
            item.setData(Qt.ItemDataRole.UserRole + 2, step.execution_run_id)
        self.actions_list.clear()
        for action in analysis.suggested_actions:
            item = QListWidgetItem(self._format_action_text(action), self.actions_list)
            item.setData(Qt.ItemDataRole.UserRole, action.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, action.approval_status.value)
            item.setData(Qt.ItemDataRole.UserRole + 2, action.execution_run_id)
        self._restore_selected_action()
        self._update_action_buttons()

    def _handle_analysis_failed(self, message: str) -> None:
        self._analysis_in_progress = False
        self.summary_text.setPlainText(f"Analysis failed.\n\n{message}")
        self.fix_plan_text.clear()
        self.fix_steps_list.clear()
        self._set_fix_plan_visibility(False)
        self._update_action_buttons()
        show_critical_error(self, "AI Analysis", message)

    def _open_provider_dialog(self) -> None:
        dialog = ProviderDialog(self._settings_service, self)
        existing = self._settings_service.get_default_provider_config()
        if existing is not None:
            dialog.load_provider(existing)

        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        try:
            if existing is None:
                created = self._settings_service.create_provider_config(dialog.to_create_request())
            else:
                created = self._settings_service.update_provider_config(dialog.to_update_request())
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Configure AI Provider", str(exc))
            return

        QMessageBox.information(
            self,
            "Configure AI Provider",
            f"Saved {created.provider_name} config '{created.display_name}' using model '{created.model_name}'.",
        )

    def _load_language_selection(self) -> None:
        self._loading_language = True
        try:
            settings = self._settings_service.get_app_settings()
            language = settings.analysis_language
        except Exception:
            language = AnalysisLanguage.EN

        index = self.language_combo.findData(language.value)
        self.language_combo.setCurrentIndex(index if index >= 0 else 0)
        self._loading_language = False

    def _save_language_selection(self, _index: int) -> None:
        if self._loading_language:
            return

        data = self.language_combo.currentData()
        if not isinstance(data, str):
            return

        try:
            self._settings_service.update_app_settings(
                UpdateAppSettingsRequest(analysis_language=AnalysisLanguage(data))
            )
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "AI Language", str(exc))
            self._load_language_selection()

    def _approve_selected_action(self) -> None:
        action_id = self._selected_action_id()
        if action_id is None:
            return
        self._preferred_action_id = action_id
        try:
            self._service.approve_action(
                SuggestedActionApprovalRequest(action_id=action_id, approved_by="user")
            )
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Approve Action", str(exc))
            return
        self._refresh_current_analysis()

    def _reject_selected_action(self) -> None:
        action_id = self._selected_action_id()
        if action_id is None:
            return
        self._preferred_action_id = action_id
        try:
            self._service.reject_action(
                SuggestedActionRejectionRequest(action_id=action_id, rejected_by="user")
            )
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Reject Action", str(exc))
            return
        self._refresh_current_analysis()

    def _execute_selected_action(self) -> None:
        action_id = self._selected_action_id()
        if action_id is None or self._execution_in_progress:
            return

        self._preferred_action_id = action_id
        self._execution_in_progress = True
        self.execution_requested.emit("[run][status] Starting approved AI action...")
        self._update_action_buttons()

        future = self._task_runner.submit(
            self._service.execute_approved_action,
            ExecuteSuggestedActionRequest(action_id=action_id, initiated_by="user"),
        )
        future.add_done_callback(self._on_execution_future_done)

    def _on_execution_future_done(self, future: Future[object]) -> None:
        try:
            result = future.result()
        except Exception as exc:  # pragma: no cover - background error path
            self.execution_failed.emit(str(exc))
            return

        run_id = getattr(result, "run_id", None)
        if isinstance(run_id, str):
            self.execution_ready.emit(run_id)
            return
        self.execution_failed.emit("Approved action execution did not return a valid run result.")

    def _handle_execution_ready(self, _run_id: str) -> None:
        self._execution_in_progress = False
        self._refresh_current_analysis()

    def _handle_execution_failed(self, message: str) -> None:
        self._execution_in_progress = False
        self._update_action_buttons()
        show_critical_error(self, "Execute Approved", message)

    def _refresh_current_analysis(self) -> None:
        if self._current_analysis_id is None:
            return
        self._load_analysis(self._current_analysis_id)

    def _selected_action_id(self) -> str | None:
        item = self._selected_action_item()
        if item is None:
            return None
        action_id = item.data(Qt.ItemDataRole.UserRole)
        return action_id if isinstance(action_id, str) else None

    def _selected_action_status(self) -> ApprovalStatus | None:
        item = self._selected_action_item()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole + 1)
        if not isinstance(value, str):
            return None
        return ApprovalStatus(value)

    def _selected_action_execution_run_id(self) -> str | None:
        item = self._selected_action_item()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole + 2)
        return value if isinstance(value, str) and value else None

    def _update_action_buttons(self) -> None:
        status = self._selected_action_status()
        execution_run_id = self._selected_action_execution_run_id()
        has_selection = status is not None
        already_executed = execution_run_id is not None
        self.approve_button.setEnabled(
            has_selection
            and not self._execution_in_progress
            and not already_executed
            and status is not ApprovalStatus.APPROVED
        )
        self.reject_button.setEnabled(
            has_selection
            and not self._execution_in_progress
            and not already_executed
            and status is not ApprovalStatus.REJECTED
        )
        self.execute_button.setEnabled(
            has_selection
            and not self._execution_in_progress
            and not already_executed
            and status is ApprovalStatus.APPROVED
        )

    def _format_action_text(self, action) -> str:
        text = (
            f"{action.title} [{action.risk_level.value}] [{action.approval_status.value}]"
            f"\n{action.command_text}"
        )
        if action.execution_run_id:
            text += f"\nExecuted as run: {action.execution_run_id}"
        return text

    def _format_fix_step_text(self, step) -> str:
        flags: list[str] = []
        if step.requires_sudo:
            flags.append("sudo")
        if step.requires_tty:
            flags.append("pty")
        flag_text = f" [{' '.join(flags)}]" if flags else ""
        text = (
            f"Step {step.step_order or '?'}: {step.title} "
            f"[{step.risk_level.value}] [{step.approval_status.value}]{flag_text}"
            f"\n{step.command_text}"
        )
        if step.execution_run_id:
            text += f"\nExecuted as run: {step.execution_run_id}"
        return text

    def _format_fix_plan_summary(self, analysis: AIAnalysisView) -> str:
        if not analysis.fix_plan_title and not analysis.fix_plan_summary:
            return "No fix plan returned for this analysis."
        lines: list[str] = []
        if analysis.fix_plan_title:
            lines.append(analysis.fix_plan_title)
        if analysis.fix_plan_summary:
            if lines:
                lines.append("")
            lines.append(analysis.fix_plan_summary)
        return "\n".join(lines)

    def _set_fix_plan_visibility(self, visible: bool) -> None:
        self.fix_plan_label.setVisible(visible)
        self.fix_plan_text.setVisible(visible)
        self.fix_steps_list.setVisible(visible)

    def _handle_action_selection(self, source_list: QListWidget) -> None:
        if source_list.currentItem() is None:
            self._update_action_buttons()
            return

        other_list = self.fix_steps_list if source_list is self.actions_list else self.actions_list
        if other_list.currentItem() is not None:
            other_list.blockSignals(True)
            other_list.clearSelection()
            other_list.setCurrentRow(-1)
            other_list.blockSignals(False)
        self._update_action_buttons()

    def _selected_action_item(self) -> QListWidgetItem | None:
        item = self.actions_list.currentItem()
        if item is not None:
            return item
        return self.fix_steps_list.currentItem()

    def _restore_selected_action(self) -> None:
        if self._preferred_action_id is None:
            return
        for list_widget in (self.actions_list, self.fix_steps_list):
            for index in range(list_widget.count()):
                item = list_widget.item(index)
                action_id = item.data(Qt.ItemDataRole.UserRole)
                if action_id == self._preferred_action_id:
                    list_widget.setCurrentItem(item)
                    return
