from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from admin_assistant.core.enums import ShellType


class ScriptCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str | None = None
    content: str
    shell_type: ShellType
    requires_tty: bool = False
    timeout_sec: int = 300
    execution_mode: str = "auto"
    tags: tuple[str, ...] = ()


class ScriptUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    script_id: str
    name: str
    description: str | None = None
    content: str
    shell_type: ShellType
    requires_tty: bool = False
    timeout_sec: int = 300
    execution_mode: str = "auto"
    tags: tuple[str, ...] = ()
    version: int


class ScriptListQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    search_text: str | None = None


class ScriptExportQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    script_ids: tuple[str, ...] = ()


class ScriptImportRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    payload_json: str


class ScriptSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    shell_type: ShellType
    requires_tty: bool
    updated_at: datetime | None = None


class ScriptDetails(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str | None = None
    content: str
    shell_type: ShellType
    requires_tty: bool
    timeout_sec: int
    execution_mode: str
    tags: tuple[str, ...] = ()
    version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ScriptExportBundle(BaseModel):
    model_config = ConfigDict(frozen=True)

    payload_json: str


class ScriptImportResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    imported_count: int
    skipped_count: int = 0
