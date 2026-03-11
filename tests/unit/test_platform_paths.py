from __future__ import annotations

from pathlib import Path

from admin_assistant.infrastructure.platform import paths as platform_paths


def test_application_data_dir_uses_localappdata_when_available(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    data_dir = platform_paths.application_data_dir()

    assert data_dir == tmp_path / "AdminAssistant"
    assert data_dir.exists()


def test_application_data_dir_falls_back_when_localappdata_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(platform_paths.Path, "home", staticmethod(lambda: Path(tmp_path)))

    data_dir = platform_paths.application_data_dir()

    assert data_dir == tmp_path / "AppData" / "Local" / "AdminAssistant"
    assert data_dir.exists()


def test_application_log_path_uses_app_data_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert platform_paths.application_log_path() == tmp_path / "AdminAssistant" / "admin_assistant.log"


def test_application_icon_path_points_to_assets_icon() -> None:
    icon_path = platform_paths.application_icon_path()

    assert icon_path.name == "admin_assistant.ico"
    assert icon_path.exists()
