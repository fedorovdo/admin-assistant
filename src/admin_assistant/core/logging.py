from __future__ import annotations

import logging

from admin_assistant.infrastructure.platform.paths import application_log_path


def configure_logging(level: int = logging.INFO) -> None:
    handlers: list[logging.Handler] = []

    try:
        handlers.append(logging.FileHandler(application_log_path(), encoding="utf-8"))
    except OSError:
        handlers = []

    handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=handlers,
        force=True,
    )
