from __future__ import annotations

APP_NAME = "Admin Assistant"
__version__ = "0.1.5"
APP_TITLE = f"{APP_NAME} v{__version__}"
APP_DESCRIPTION = "Admin Assistant is an AI-powered desktop tool for server troubleshooting and incident investigation."
APP_AUTHOR = "Dmitrii Fedorov"
APP_CONTACT_EMAIL = "fedorovkingisepp@gmail.com"
APP_FEATURES = (
    "Remote command execution over SSH",
    "Script execution on multiple servers",
    "AI-powered log and output analysis",
    "Suggested actions and fix plans",
    "Incident investigation mode",
    "Safe execution approval workflow",
    "Support for OpenAI and local Ollama models",
)
APP_STACK = (
    "Python",
    "PySide6",
    "Paramiko",
    "SQLite",
    "PyInstaller",
)
ABOUT_TEXT = (
    f"{APP_NAME}\n"
    f"Version {__version__}\n\n"
    f"{APP_DESCRIPTION}\n\n"
    "Key Features\n"
    "\u2022 Remote command execution over SSH\n"
    "\u2022 Script execution on multiple servers\n"
    "\u2022 AI-powered log and output analysis\n"
    "\u2022 Suggested actions and fix plans\n"
    "\u2022 Incident investigation mode\n"
    "\u2022 Safe execution approval workflow\n"
    "\u2022 Support for OpenAI and local Ollama models\n\n"
    "Tech Stack\n"
    "Python\n"
    "PySide6\n"
    "Paramiko\n"
    "SQLite\n"
    "PyInstaller\n\n"
    "Author\n"
    f"{APP_AUTHOR}\n\n"
    "Contact\n"
    f"{APP_CONTACT_EMAIL}"
)
