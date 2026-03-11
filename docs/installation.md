# Installation

This guide explains how to install and build Admin Assistant for local use or testing.

## Requirements

- Windows 10 or Windows 11 recommended
- Python 3.11 or newer for source-based runs
- Network access to the Linux hosts you want to manage

## Install From Windows Installer

If you have a release package:

1. Run `AdminAssistant_Setup.exe`.
2. Accept the default install location under `Program Files`.
3. Launch **Admin Assistant** from the Start Menu.

The installer also supports an optional Desktop shortcut.

## Run From Source

From the repository root:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
$env:PYTHONPATH = "src"
python -m admin_assistant.main
```

## Build the PyInstaller EXE

Install build tools:

```powershell
.\venv\Scripts\python.exe -m pip install -e .[build]
```

Build:

```powershell
.\venv\Scripts\python.exe -m PyInstaller --clean -y .\AdminAssistant.spec
```

Output:

- `dist\AdminAssistant\AdminAssistant.exe`

## Build the Windows Installer

Requirements:

- PyInstaller build completed successfully
- Inno Setup 6 installed

Build:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

Output:

- `installer\AdminAssistant_Setup.exe`
- or a versioned installer name depending on the current installer script

## Writable Application Data

Admin Assistant stores runtime data under:

```text
%LOCALAPPDATA%\AdminAssistant
```

Important files:

- `admin_assistant.db`
- `admin_assistant.log`

This allows the packaged EXE to run without trying to write into `Program Files`.

## Troubleshooting

If the app does not start correctly:

1. Open `%LOCALAPPDATA%\AdminAssistant`
2. Check `admin_assistant.log`
3. Open `Help -> System Info`
4. Use `Copy Info` and include the log when reporting issues
