from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from admin_assistant.app.bootstrap import ApplicationBootstrap
from admin_assistant.core.logging import configure_logging
from admin_assistant.infrastructure.platform.paths import application_icon_path
from admin_assistant.version import APP_NAME


def main() -> int:
    configure_logging()
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName(APP_NAME)
    icon_path = application_icon_path()
    if icon_path.exists():
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            qt_app.setWindowIcon(icon)
    bootstrap = ApplicationBootstrap()
    window = bootstrap.build_main_window()
    if icon_path.exists():
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            window.setWindowIcon(icon)
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
