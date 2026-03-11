from __future__ import annotations

from admin_assistant.core.enums import ShellType
from admin_assistant.modules.scripts.dto import ScriptCreateRequest, ScriptUpdateRequest
from admin_assistant.modules.scripts.models import Script
from admin_assistant.modules.scripts.service import DefaultScriptService


class InMemoryScriptRepository:
    def __init__(self) -> None:
        self._items: dict[str, Script] = {}

    def add(self, script: Script) -> Script:
        self._items[script.id] = script
        return script

    def update(self, script: Script) -> Script:
        self._items[script.id] = script
        return script

    def delete(self, script_id: str) -> None:
        self._items.pop(script_id, None)

    def get(self, script_id: str) -> Script | None:
        return self._items.get(script_id)

    def list(self, search_text: str | None = None) -> list[Script]:
        items = list(self._items.values())
        if not search_text:
            return items
        search = search_text.lower()
        return [
            item
            for item in items
            if search in item.name.lower() or search in (item.description or "").lower()
        ]


def test_script_service_create_update_delete_flow() -> None:
    repository = InMemoryScriptRepository()
    service = DefaultScriptService(repository=repository)

    created = service.create_script(
        ScriptCreateRequest(
            name="Restart nginx",
            description="Restart the nginx service",
            content="systemctl restart nginx",
            shell_type=ShellType.BASH,
            requires_tty=False,
        )
    )

    updated = service.update_script(
        ScriptUpdateRequest(
            script_id=created.id,
            name="Restart nginx safely",
            description="Restart and verify nginx",
            content="systemctl restart nginx\nsystemctl status nginx --no-pager",
            shell_type=ShellType.SH,
            requires_tty=True,
            timeout_sec=600,
            version=created.version,
        )
    )
    delete_result = service.delete_script(created.id)

    assert created.timeout_sec == 300
    assert updated.name == "Restart nginx safely"
    assert updated.shell_type is ShellType.SH
    assert updated.requires_tty is True
    assert updated.timeout_sec == 600
    assert updated.version == 2
    assert delete_result.success is True
    assert repository.get(created.id) is None
