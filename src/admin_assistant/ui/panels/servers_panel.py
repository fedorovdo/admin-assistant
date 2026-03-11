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
    QAbstractItemView,
    QVBoxLayout,
    QWidget,
)

from admin_assistant.modules.servers.dto import (
    ServerConnectionTestRequest,
    ServerDetails,
    ServerListQuery,
)
from admin_assistant.modules.servers.service import ServerService
from admin_assistant.ui.dialogs.server_dialog import ServerDialog
from admin_assistant.ui.dialogs.support_dialogs import show_critical_error


class ServersPanel(QWidget):
    selection_changed = Signal(tuple)

    def __init__(self, service: ServerService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service

        layout = QVBoxLayout(self)
        header = QLabel("Servers", self)
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search servers")

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("Add", self)
        self.edit_button = QPushButton("Edit", self)
        self.delete_button = QPushButton("Delete", self)
        self.test_button = QPushButton("Test", self)

        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.edit_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addWidget(self.test_button)

        self.server_list = QListWidget(self)
        self.server_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.details_label = QLabel("No server selected.", self)
        self.details_label.setWordWrap(True)

        layout.addWidget(header)
        layout.addWidget(self.search_input)
        layout.addLayout(toolbar)
        layout.addWidget(self.server_list)
        layout.addWidget(self.details_label)

        self.add_button.clicked.connect(self._open_create_dialog)
        self.edit_button.clicked.connect(self._open_edit_dialog)
        self.delete_button.clicked.connect(self._delete_selected_server)
        self.test_button.clicked.connect(self._test_selected_server)
        self.search_input.textChanged.connect(self.refresh_servers)
        self.server_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.refresh_servers()

    def refresh_servers(
        self,
        *_args: object,
        selected_server_ids: tuple[str, ...] | None = None,
        auto_select_first: bool = True,
    ) -> None:
        current_server_ids = selected_server_ids if selected_server_ids is not None else self.selected_server_ids()
        self.server_list.clear()

        try:
            servers = self._service.list_servers(ServerListQuery(search_text=self.search_input.text().strip() or None))
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Load Servers", str(exc))
            return

        restored_items: list[QListWidgetItem] = []
        for server in servers:
            item = QListWidgetItem(f"{server.name} ({server.host})")
            item.setData(Qt.ItemDataRole.UserRole, server.id)
            self.server_list.addItem(item)
            if server.id in current_server_ids:
                restored_items.append(item)

        if restored_items:
            for item in restored_items:
                item.setSelected(True)
            self.server_list.setCurrentItem(restored_items[0])
        elif auto_select_first and self.server_list.count() > 0:
            self.server_list.item(0).setSelected(True)
            self.server_list.setCurrentRow(0)
        else:
            self.server_list.clearSelection()
            self._clear_details()

        self._on_selection_changed()
        self._update_button_states()

    def _open_create_dialog(self) -> None:
        dialog = ServerDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        try:
            created = self._service.create_server(dialog.to_create_request())
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Create Server", str(exc))
            return

        self.refresh_servers(selected_server_ids=(created.id,))

    def _open_edit_dialog(self) -> None:
        server_id = self._single_selected_server_id()
        if server_id is None:
            return

        try:
            server = self._service.get_server(server_id)
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Edit Server", str(exc))
            return

        dialog = ServerDialog(self)
        dialog.load_server(server)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        try:
            updated = self._service.update_server(dialog.to_update_request(server_id))
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Edit Server", str(exc))
            return

        self.refresh_servers(selected_server_ids=(updated.id,))

    def _delete_selected_server(self) -> None:
        server_id = self._single_selected_server_id()
        if server_id is None:
            return

        try:
            server = self._service.get_server(server_id)
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Delete Server", str(exc))
            return

        answer = QMessageBox.question(
            self,
            "Delete Server",
            f"Delete server '{server.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service.delete_server(server_id)
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Delete Server", str(exc))
            return

        self.refresh_servers(selected_server_ids=(), auto_select_first=False)

    def _test_selected_server(self) -> None:
        server_id = self._single_selected_server_id()
        if server_id is None:
            return

        try:
            result = self._service.test_connection(ServerConnectionTestRequest(server_id=server_id))
        except Exception as exc:  # pragma: no cover - UI display path
            show_critical_error(self, "Test Connection", str(exc))
            return

        if result.success:
            QMessageBox.information(self, "Test Connection", result.message)
        else:
            QMessageBox.warning(self, "Test Connection", result.message)

    def selected_server_ids(self) -> tuple[str, ...]:
        return tuple(
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self.server_list.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole)
        )

    def _single_selected_server_id(self) -> str | None:
        selected_ids = self.selected_server_ids()
        if len(selected_ids) != 1:
            return None
        return selected_ids[0]

    def _on_selection_changed(self) -> None:
        selected_ids = self.selected_server_ids()
        if not selected_ids:
            self._clear_details()
            self._update_button_states()
            self.selection_changed.emit(())
            return

        if len(selected_ids) > 1:
            self.details_label.setText(f"{len(selected_ids)} servers selected.")
            self._update_button_states()
            self.selection_changed.emit(selected_ids)
            return

        try:
            server = self._service.get_server(selected_ids[0])
        except Exception as exc:  # pragma: no cover - UI display path
            self.details_label.setText(str(exc))
            self._update_button_states()
            self.selection_changed.emit(())
            return

        self._show_server_details(server)
        self._update_button_states()
        self.selection_changed.emit(selected_ids)

    def _show_server_details(self, server: ServerDetails) -> None:
        lines = [
            server.name,
            f"{server.username}@{server.host}:{server.port}",
            f"Auth: {server.auth_type.value}",
            f"Host Key: {server.host_key_policy.value}",
        ]
        if server.key_path:
            lines.append(f"Key Path: {server.key_path}")
        if server.notes:
            lines.append(f"Notes: {server.notes}")
        self.details_label.setText("\n".join(lines))

    def _clear_details(self) -> None:
        if self.server_list.count() == 0:
            self.details_label.setText("No servers yet. Click Add to create one.")
        else:
            self.details_label.setText("No server selected.")

    def _update_button_states(self) -> None:
        has_single_selection = len(self.selected_server_ids()) == 1
        self.edit_button.setEnabled(has_single_selection)
        self.delete_button.setEnabled(has_single_selection)
        self.test_button.setEnabled(has_single_selection)
