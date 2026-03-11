from __future__ import annotations

import platform
import sys

import PySide6
from PySide6.QtCore import qVersion
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from admin_assistant.infrastructure.platform.paths import application_log_path
from admin_assistant.modules.settings.dto import AIProviderConfigView
from admin_assistant.version import APP_NAME, __version__
from admin_assistant.ui.dialogs.support_dialogs import open_log_folder


def build_system_info_text(provider_config: AIProviderConfigView | None) -> str:
    python_version = sys.version.split()[0]
    platform_name = platform.platform()
    architecture = platform.machine() or "Unknown"
    pyside_version = getattr(PySide6, "__version__", "Unknown")
    qt_version = qVersion()

    provider_type = provider_config.provider_name if provider_config is not None else "Not configured"
    provider_model = provider_config.model_name if provider_config is not None else "Not configured"
    provider_base_url = provider_config.base_url if provider_config is not None else "Not configured"
    log_path = application_log_path()

    return (
        f"{APP_NAME} System Info\n\n"
        "Application\n"
        f"{APP_NAME} v{__version__}\n\n"
        "Environment\n"
        f"Python: {python_version}\n"
        f"OS: {platform_name}\n"
        f"Architecture: {architecture}\n"
        f"Qt: {qt_version}\n"
        f"PySide6: {pyside_version}\n"
        f"Log File: {log_path}\n\n"
        "AI Configuration\n"
        f"Provider: {provider_type}\n"
        f"Model: {provider_model}\n"
        f"Base URL: {provider_base_url}"
    )


class SystemInfoDialog(QDialog):
    def __init__(self, info_text: str, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} System Info")
        self.resize(640, 360)

        layout = QVBoxLayout(self)
        self.info_text = QPlainTextEdit(self)
        self.info_text.setReadOnly(True)
        self.info_text.setPlainText(info_text)

        button_row = QHBoxLayout()
        self.copy_button = QPushButton("Copy Info", self)
        self.open_log_folder_button = QPushButton("Open Log Folder", self)
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)

        button_row.addWidget(self.copy_button)
        button_row.addWidget(self.open_log_folder_button)
        button_row.addStretch(1)
        button_row.addWidget(self.button_box)

        layout.addWidget(self.info_text)
        layout.addLayout(button_row)

        self.copy_button.clicked.connect(self._copy_info)
        self.open_log_folder_button.clicked.connect(self._open_log_folder)
        self.button_box.rejected.connect(self.reject)

    def _copy_info(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.info_text.toPlainText())

    def _open_log_folder(self) -> None:
        open_log_folder()
