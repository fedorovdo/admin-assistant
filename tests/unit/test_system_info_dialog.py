from __future__ import annotations

import os

from admin_assistant.infrastructure.platform.paths import application_log_path
from admin_assistant.modules.settings.dto import AIProviderConfigView
from admin_assistant.ui.dialogs.support_dialogs import open_log_folder
from admin_assistant.ui.dialogs.system_info_dialog import build_system_info_text
from admin_assistant.version import APP_NAME, __version__


def test_build_system_info_text_includes_provider_details() -> None:
    provider = AIProviderConfigView(
        id="provider-1",
        provider_name="ollama",
        display_name="Ollama",
        base_url="http://127.0.0.1:11434",
        model_name="qwen2.5:7b",
        timeout_sec=180,
        temperature=0.1,
        is_default=True,
        is_enabled=True,
    )

    info_text = build_system_info_text(provider)

    assert f"{APP_NAME} System Info" in info_text
    assert "Application" in info_text
    assert f"{APP_NAME} v{__version__}" in info_text
    assert "Environment" in info_text
    assert "Python:" in info_text
    assert "OS:" in info_text
    assert "AI Configuration" in info_text
    assert "Provider: ollama" in info_text
    assert "Model: qwen2.5:7b" in info_text
    assert "Base URL: http://127.0.0.1:11434" in info_text
    assert f"Log File: {application_log_path()}" in info_text


def test_build_system_info_text_handles_missing_provider_config() -> None:
    info_text = build_system_info_text(None)

    assert "Provider: Not configured" in info_text
    assert "Model: Not configured" in info_text
    assert "Base URL: Not configured" in info_text
    assert f"Log File: {application_log_path()}" in info_text


def test_open_log_folder_uses_os_startfile(monkeypatch) -> None:
    opened: list[str] = []

    monkeypatch.setattr(os, "startfile", lambda path: opened.append(path))

    assert open_log_folder() is True
    assert opened == [str(application_log_path().parent)]
