# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


project_root = Path(SPECPATH).resolve()
src_dir = project_root / "src"
entry_script = src_dir / "admin_assistant" / "main.py"
icon_path = project_root / "assets" / "admin_assistant.ico"

pyside6_hiddenimports = collect_submodules("PySide6")
shiboken_hiddenimports = collect_submodules("shiboken6")
keyring_hiddenimports = collect_submodules("keyring.backends") + collect_submodules("win32ctypes")

datas = (
    collect_data_files("PySide6")
    + collect_data_files("shiboken6")
    + collect_data_files("admin_assistant")
    + copy_metadata("keyring")
)
if icon_path.exists():
    datas.append((str(icon_path), "assets"))
binaries = collect_dynamic_libs("PySide6") + collect_dynamic_libs("shiboken6")
hiddenimports = pyside6_hiddenimports + shiboken_hiddenimports + keyring_hiddenimports


a = Analysis(
    [str(entry_script)],
    pathex=[str(project_root), str(src_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AdminAssistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AdminAssistant",
)
