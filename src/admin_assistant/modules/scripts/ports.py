from __future__ import annotations

from typing import Protocol

from admin_assistant.modules.scripts.models import Script


class ScriptRepository(Protocol):
    def add(self, script: Script) -> Script:
        ...

    def update(self, script: Script) -> Script:
        ...

    def delete(self, script_id: str) -> None:
        ...

    def get(self, script_id: str) -> Script | None:
        ...

    def list(self, search_text: str | None = None) -> list[Script]:
        ...

