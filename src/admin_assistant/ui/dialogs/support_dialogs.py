from __future__ import annotations

import os

from PySide6.QtWidgets import QMessageBox, QWidget

from admin_assistant.infrastructure.platform.paths import application_log_path


def open_log_folder() -> bool:
    log_dir = application_log_path().parent
    if hasattr(os, "startfile"):
        try:
            os.startfile(str(log_dir))
            return True
        except OSError:
            return False
    return False


def show_critical_error(parent: QWidget | None, title: str, message: str) -> None:
    log_path = application_log_path()
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Icon.Critical)
    dialog.setWindowTitle(title)
    dialog.setText(message)
    dialog.setInformativeText(
        "If you report this issue, please send the log file.\n"
        f"Log file: {log_path}"
    )
    open_button = dialog.addButton("Open Log Folder", QMessageBox.ButtonRole.ActionRole)
    dialog.addButton(QMessageBox.StandardButton.Ok)
    dialog.exec()
    if dialog.clickedButton() is open_button:
        open_log_folder()
