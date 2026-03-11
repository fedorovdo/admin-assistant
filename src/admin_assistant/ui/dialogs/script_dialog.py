from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
)

from admin_assistant.core.enums import ShellType
from admin_assistant.modules.scripts.dto import ScriptCreateRequest, ScriptDetails, ScriptUpdateRequest


class ScriptDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Script")
        self._version = 1

        layout = QFormLayout(self)
        self.name_input = QLineEdit(self)
        self.description_input = QLineEdit(self)
        self.shell_type_combo = QComboBox(self)
        self.shell_type_combo.addItems(["bash", "sh"])
        self.requires_tty_checkbox = QCheckBox("Requires TTY", self)
        self.timeout_input = QSpinBox(self)
        self.timeout_input.setRange(1, 86400)
        self.timeout_input.setValue(300)
        self.content_input = QPlainTextEdit(self)
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )

        layout.addRow("Name", self.name_input)
        layout.addRow("Description", self.description_input)
        layout.addRow("Shell", self.shell_type_combo)
        layout.addRow("", self.requires_tty_checkbox)
        layout.addRow("Timeout (sec)", self.timeout_input)
        layout.addRow("Content", self.content_input)
        layout.addRow(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def to_create_request(self) -> ScriptCreateRequest:
        return ScriptCreateRequest(
            name=self.name_input.text().strip(),
            description=self.description_input.text().strip() or None,
            content=self.content_input.toPlainText().strip(),
            shell_type=ShellType(self.shell_type_combo.currentText()),
            requires_tty=self.requires_tty_checkbox.isChecked(),
            timeout_sec=self.timeout_input.value(),
            execution_mode="auto",
        )

    def to_update_request(self, script_id: str) -> ScriptUpdateRequest:
        return ScriptUpdateRequest(
            script_id=script_id,
            name=self.name_input.text().strip(),
            description=self.description_input.text().strip() or None,
            content=self.content_input.toPlainText().strip(),
            shell_type=ShellType(self.shell_type_combo.currentText()),
            requires_tty=self.requires_tty_checkbox.isChecked(),
            timeout_sec=self.timeout_input.value(),
            execution_mode="auto",
            version=self._version,
        )

    def load_script(self, script: ScriptDetails) -> None:
        self.setWindowTitle("Edit Script")
        self._version = script.version
        self.name_input.setText(script.name)
        self.description_input.setText(script.description or "")
        self.shell_type_combo.setCurrentText(script.shell_type.value)
        self.requires_tty_checkbox.setChecked(script.requires_tty)
        self.timeout_input.setValue(script.timeout_sec)
        self.content_input.setPlainText(script.content)
