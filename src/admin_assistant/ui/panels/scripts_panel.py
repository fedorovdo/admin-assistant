from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from admin_assistant.modules.scripts.dto import ScriptDetails, ScriptListQuery
from admin_assistant.modules.scripts.service import ScriptService
from admin_assistant.ui.dialogs.script_dialog import ScriptDialog
from admin_assistant.ui.dialogs.support_dialogs import show_critical_error


class ScriptsPanel(QWidget):
    selection_changed = Signal(object)

    def __init__(self, service: ScriptService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service

        layout = QVBoxLayout(self)
        header = QLabel("Scripts", self)
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search scripts")

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("Add", self)
        self.edit_button = QPushButton("Edit", self)
        self.delete_button = QPushButton("Delete", self)
        self.import_button = QPushButton("Import", self)
        self.export_button = QPushButton("Export", self)

        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.edit_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addWidget(self.import_button)
        toolbar.addWidget(self.export_button)

        self.script_list = QListWidget(self)
        self.details_label = QLabel("No script selected.", self)
        self.details_label.setWordWrap(True)

        layout.addWidget(header)
        layout.addWidget(self.search_input)
        layout.addLayout(toolbar)
        layout.addWidget(self.script_list)
        layout.addWidget(self.details_label)

        self.edit_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.import_button.setToolTip("Import is not implemented yet.")
        self.export_button.setToolTip("Export is not implemented yet.")

        self.add_button.clicked.connect(self._open_create_dialog)
        self.edit_button.clicked.connect(self._open_edit_dialog)
        self.delete_button.clicked.connect(self._delete_selected_script)
        self.search_input.textChanged.connect(self.refresh_scripts)
        self.script_list.currentItemChanged.connect(self._on_current_item_changed)
        self.refresh_scripts()

    def refresh_scripts(
        self,
        *_args: object,
        selected_script_id: str | None = None,
        auto_select_first: bool = True,
    ) -> None:
        current_script_id = selected_script_id if selected_script_id is not None else self._current_script_id()
        self.script_list.clear()

        try:
            scripts = self._service.list_scripts(ScriptListQuery(search_text=self.search_input.text().strip() or None))
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Load Scripts", str(exc))
            return

        restored_item: QListWidgetItem | None = None
        for script in scripts:
            item = QListWidgetItem(f"{script.name} [{script.shell_type.value}]")
            item.setData(Qt.ItemDataRole.UserRole, script.id)
            self.script_list.addItem(item)
            if script.id == current_script_id:
                restored_item = item

        if restored_item is not None:
            self.script_list.setCurrentItem(restored_item)
        elif auto_select_first and self.script_list.count() > 0:
            self.script_list.setCurrentRow(0)
        else:
            self.script_list.clearSelection()
            self._clear_details()

        self._update_button_states()

    def _open_create_dialog(self) -> None:
        dialog = ScriptDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        try:
            created = self._service.create_script(dialog.to_create_request())
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Create Script", str(exc))
            return

        self.refresh_scripts(selected_script_id=created.id)

    def _open_edit_dialog(self) -> None:
        script_id = self._current_script_id()
        if script_id is None:
            return

        try:
            script = self._service.get_script(script_id)
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Edit Script", str(exc))
            return

        dialog = ScriptDialog(self)
        dialog.load_script(script)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        try:
            updated = self._service.update_script(dialog.to_update_request(script_id))
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Edit Script", str(exc))
            return

        self.refresh_scripts(selected_script_id=updated.id)

    def _delete_selected_script(self) -> None:
        script_id = self._current_script_id()
        if script_id is None:
            return

        try:
            script = self._service.get_script(script_id)
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Delete Script", str(exc))
            return

        answer = QMessageBox.question(
            self,
            "Delete Script",
            f"Delete script '{script.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service.delete_script(script_id)
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Delete Script", str(exc))
            return

        self.refresh_scripts(selected_script_id=None, auto_select_first=False)

    def _current_script_id(self) -> str | None:
        item = self.script_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def selected_script_id(self) -> str | None:
        return self._current_script_id()

    def selected_script_info(self) -> tuple[str, str] | None:
        item = self.script_list.currentItem()
        if item is None:
            return None
        script_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(script_id, str):
            return None
        try:
            script = self._service.get_script(script_id)
        except Exception:
            return (script_id, script_id)
        return (script.id, script.name)

    def _on_current_item_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        del previous
        if current is None:
            self._clear_details()
            self._update_button_states()
            self.selection_changed.emit(None)
            return

        script_id = current.data(Qt.ItemDataRole.UserRole)
        try:
            script = self._service.get_script(script_id)
        except Exception as exc:  # pragma: no cover - UI display path
            self.details_label.setText(str(exc))
            self._update_button_states()
            self.selection_changed.emit(None)
            return

        self._show_script_details(script)
        self._update_button_states()
        self.selection_changed.emit((script.id, script.name))

    def _show_script_details(self, script: ScriptDetails) -> None:
        preview = script.content.splitlines()
        preview_text = preview[0] if preview else ""
        lines = [
            script.name,
            f"Shell: {script.shell_type.value}",
            f"TTY: {'yes' if script.requires_tty else 'no'}",
            f"Timeout: {script.timeout_sec}s",
        ]
        if script.description:
            lines.append(f"Description: {script.description}")
        if preview_text:
            lines.append(f"Preview: {preview_text[:120]}")
        self.details_label.setText("\n".join(lines))

    def _clear_details(self) -> None:
        if self.script_list.count() == 0:
            self.details_label.setText("No scripts yet. Click Add to create one.")
        else:
            self.details_label.setText("No script selected.")

    def _update_button_states(self) -> None:
        has_selection = self._current_script_id() is not None
        self.edit_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
