from __future__ import annotations

from uuid import uuid4
from typing import Protocol

from admin_assistant.core.errors import NotFoundError, ValidationError
from admin_assistant.core.result import OperationResult
from admin_assistant.core.time import utc_now
from admin_assistant.modules.scripts.dto import (
    ScriptCreateRequest,
    ScriptDetails,
    ScriptExportBundle,
    ScriptExportQuery,
    ScriptImportRequest,
    ScriptImportResult,
    ScriptListQuery,
    ScriptSummary,
    ScriptUpdateRequest,
)
from admin_assistant.modules.scripts.models import Script
from admin_assistant.modules.scripts.ports import ScriptRepository


def _normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_timeout(timeout_sec: int | None) -> int:
    if timeout_sec is None or timeout_sec <= 0:
        return 300
    return timeout_sec


def _to_details(script: Script) -> ScriptDetails:
    return ScriptDetails(
        id=script.id,
        name=script.name,
        description=script.description,
        content=script.content,
        shell_type=script.shell_type,
        requires_tty=script.requires_tty,
        timeout_sec=_normalize_timeout(script.timeout_sec),
        execution_mode=script.execution_mode,
        tags=script.tags,
        version=script.version,
        created_at=script.created_at,
        updated_at=script.updated_at,
    )


def _to_summary(script: Script) -> ScriptSummary:
    return ScriptSummary(
        id=script.id,
        name=script.name,
        shell_type=script.shell_type,
        requires_tty=script.requires_tty,
        updated_at=script.updated_at,
    )


class ScriptService(Protocol):
    def create_script(self, request: ScriptCreateRequest) -> ScriptDetails:
        ...

    def update_script(self, request: ScriptUpdateRequest) -> ScriptDetails:
        ...

    def delete_script(self, script_id: str) -> OperationResult:
        ...

    def get_script(self, script_id: str) -> ScriptDetails:
        ...

    def list_scripts(self, query: ScriptListQuery) -> tuple[ScriptSummary, ...]:
        ...

    def export_scripts(self, query: ScriptExportQuery) -> ScriptExportBundle:
        ...

    def import_scripts(self, request: ScriptImportRequest) -> ScriptImportResult:
        ...


class DefaultScriptService(ScriptService):
    def __init__(self, repository: ScriptRepository) -> None:
        self._repository = repository

    def create_script(self, request: ScriptCreateRequest) -> ScriptDetails:
        self._validate_fields(name=request.name, content=request.content)
        now = utc_now()
        script = Script(
            id=str(uuid4()),
            name=request.name.strip(),
            description=_normalized_text(request.description),
            content=request.content.strip(),
            shell_type=request.shell_type,
            requires_tty=request.requires_tty,
            timeout_sec=_normalize_timeout(request.timeout_sec),
            execution_mode=request.execution_mode,
            tags=tuple(tag.strip() for tag in request.tags if tag.strip()),
            version=1,
            created_at=now,
            updated_at=now,
        )
        saved = self._repository.add(script)
        return _to_details(saved)

    def update_script(self, request: ScriptUpdateRequest) -> ScriptDetails:
        self._validate_fields(name=request.name, content=request.content)
        existing = self._repository.get(request.script_id)
        if existing is None:
            raise NotFoundError(f"Script '{request.script_id}' was not found.")

        updated = Script(
            id=existing.id,
            name=request.name.strip(),
            description=_normalized_text(request.description),
            content=request.content.strip(),
            shell_type=request.shell_type,
            requires_tty=request.requires_tty,
            timeout_sec=_normalize_timeout(request.timeout_sec),
            execution_mode=request.execution_mode,
            tags=tuple(tag.strip() for tag in request.tags if tag.strip()),
            version=max(existing.version, request.version) + 1,
            created_at=existing.created_at,
            updated_at=utc_now(),
        )
        saved = self._repository.update(updated)
        return _to_details(saved)

    def delete_script(self, script_id: str) -> OperationResult:
        existing = self._repository.get(script_id)
        if existing is None:
            raise NotFoundError(f"Script '{script_id}' was not found.")
        self._repository.delete(script_id)
        return OperationResult(success=True)

    def get_script(self, script_id: str) -> ScriptDetails:
        script = self._repository.get(script_id)
        if script is None:
            raise NotFoundError(f"Script '{script_id}' was not found.")
        return _to_details(script)

    def list_scripts(self, query: ScriptListQuery) -> tuple[ScriptSummary, ...]:
        scripts = self._repository.list(search_text=query.search_text)
        return tuple(_to_summary(script) for script in scripts)

    def export_scripts(self, query: ScriptExportQuery) -> ScriptExportBundle:
        raise NotImplementedError

    def import_scripts(self, request: ScriptImportRequest) -> ScriptImportResult:
        raise NotImplementedError

    def _validate_fields(self, name: str, content: str) -> None:
        if not name.strip():
            raise ValidationError("Script name is required.")
        if not content.strip():
            raise ValidationError("Script content is required.")
