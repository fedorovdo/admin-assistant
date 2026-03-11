from __future__ import annotations

import os
import sys
from pathlib import Path


def application_data_dir() -> Path:
    if os.name == "nt":
        base_dir = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base_dir = str(Path.home() / ".local" / "share")
    path = Path(base_dir) / "AdminAssistant"
    path.mkdir(parents=True, exist_ok=True)
    return path


def application_log_path() -> Path:
    return application_data_dir() / "admin_assistant.log"


def resource_root_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[4]


def application_icon_path() -> Path:
    return resource_root_dir() / "assets" / "admin_assistant.ico"


def default_database_url() -> str:
    database_path = application_data_dir() / "admin_assistant.db"
    return f"sqlite+pysqlite:///{database_path.as_posix()}"
