from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
)

from pydantic import SecretStr

from admin_assistant.core.enums import AuthType, HostKeyPolicy
from admin_assistant.modules.servers.dto import ServerCreateRequest, ServerDetails, ServerUpdateRequest


class ServerDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Server")
        self._tags: tuple[str, ...] = ()

        layout = QFormLayout(self)
        self.name_input = QLineEdit(self)
        self.host_input = QLineEdit(self)
        self.port_input = QSpinBox(self)
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(22)
        self.username_input = QLineEdit(self)
        self.auth_type_combo = QComboBox(self)
        self.auth_type_combo.addItems(["password", "key"])
        self.password_input = QLineEdit(self)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_path_input = QLineEdit(self)
        self.host_key_policy_combo = QComboBox(self)
        self.host_key_policy_combo.addItems(["strict", "trust_on_first_use", "manual_approve"])
        self.notes_input = QPlainTextEdit(self)
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )

        layout.addRow("Name", self.name_input)
        layout.addRow("Host", self.host_input)
        layout.addRow("Port", self.port_input)
        layout.addRow("Username", self.username_input)
        layout.addRow("Auth Type", self.auth_type_combo)
        layout.addRow("Password", self.password_input)
        layout.addRow("Key Path", self.key_path_input)
        layout.addRow("Host Key Policy", self.host_key_policy_combo)
        layout.addRow("Notes", self.notes_input)
        layout.addRow(self.button_box)

        self.auth_type_combo.currentTextChanged.connect(self._update_auth_fields)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self._update_auth_fields(self.auth_type_combo.currentText())

    def to_create_request(self) -> ServerCreateRequest:
        password_text = self.password_input.text().strip()

        return ServerCreateRequest(
            name=self.name_input.text().strip(),
            host=self.host_input.text().strip(),
            port=self.port_input.value(),
            username=self.username_input.text().strip(),
            auth_type=AuthType(self.auth_type_combo.currentText()),
            password=SecretStr(password_text) if password_text else None,
            key_path=self.key_path_input.text().strip() or None,
            host_key_policy=HostKeyPolicy(self.host_key_policy_combo.currentText()),
            tags=self._tags,
            notes=self.notes_input.toPlainText().strip() or None,
        )

    def to_update_request(self, server_id: str) -> ServerUpdateRequest:
        password_text = self.password_input.text().strip()

        return ServerUpdateRequest(
            server_id=server_id,
            name=self.name_input.text().strip(),
            host=self.host_input.text().strip(),
            port=self.port_input.value(),
            username=self.username_input.text().strip(),
            auth_type=AuthType(self.auth_type_combo.currentText()),
            password=SecretStr(password_text) if password_text else None,
            key_path=self.key_path_input.text().strip() or None,
            host_key_policy=HostKeyPolicy(self.host_key_policy_combo.currentText()),
            tags=self._tags,
            notes=self.notes_input.toPlainText().strip() or None,
        )

    def load_server(self, server: ServerDetails) -> None:
        self.setWindowTitle("Edit Server")
        self._tags = server.tags
        self.name_input.setText(server.name)
        self.host_input.setText(server.host)
        self.port_input.setValue(server.port)
        self.username_input.setText(server.username)
        self.auth_type_combo.setCurrentText(server.auth_type.value)
        self.key_path_input.setText(server.key_path or "")
        self.host_key_policy_combo.setCurrentText(server.host_key_policy.value)
        self.notes_input.setPlainText(server.notes or "")
        self.password_input.clear()
        self._update_auth_fields(self.auth_type_combo.currentText())

    def _update_auth_fields(self, auth_type: str) -> None:
        is_password = auth_type == AuthType.PASSWORD.value
        self.password_input.setEnabled(is_password)
        self.password_input.setPlaceholderText("Leave blank to keep existing password")
        if not is_password:
            self.password_input.clear()
        self.key_path_input.setEnabled(not is_password)
