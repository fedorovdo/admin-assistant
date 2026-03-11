from __future__ import annotations

import json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from admin_assistant.core.enums import ShellType
from admin_assistant.infrastructure.db.models.script_record import ScriptRecord
from admin_assistant.modules.scripts.models import Script


def _to_record(script: Script) -> ScriptRecord:
    return ScriptRecord(
        id=script.id,
        name=script.name,
        description=script.description,
        content=script.content,
        shell_type=script.shell_type.value,
        requires_tty=script.requires_tty,
        timeout_sec=script.timeout_sec,
        execution_mode=script.execution_mode,
        tags_json=json.dumps(list(script.tags)),
        version=script.version,
        created_at=script.created_at,
        updated_at=script.updated_at,
    )


def _to_domain(record: ScriptRecord) -> Script:
    return Script(
        id=record.id,
        name=record.name,
        description=record.description,
        content=record.content,
        shell_type=ShellType(record.shell_type),
        requires_tty=record.requires_tty,
        timeout_sec=record.timeout_sec,
        execution_mode=record.execution_mode,
        tags=tuple(json.loads(record.tags_json or "[]")),
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class SqlAlchemyScriptRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, script: Script) -> Script:
        record = _to_record(script)
        with self._session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return _to_domain(record)

    def update(self, script: Script) -> Script:
        with self._session_factory() as session:
            record = session.get(ScriptRecord, script.id)
            if record is None:
                raise KeyError(f"Script '{script.id}' not found.")

            record.name = script.name
            record.description = script.description
            record.content = script.content
            record.shell_type = script.shell_type.value
            record.requires_tty = script.requires_tty
            record.timeout_sec = script.timeout_sec
            record.execution_mode = script.execution_mode
            record.tags_json = json.dumps(list(script.tags))
            record.version = script.version
            record.created_at = script.created_at
            record.updated_at = script.updated_at

            session.commit()
            session.refresh(record)
            return _to_domain(record)

    def delete(self, script_id: str) -> None:
        with self._session_factory() as session:
            record = session.get(ScriptRecord, script_id)
            if record is None:
                return
            session.delete(record)
            session.commit()

    def get(self, script_id: str) -> Script | None:
        with self._session_factory() as session:
            record = session.get(ScriptRecord, script_id)
            if record is None:
                return None
            return _to_domain(record)

    def list(self, search_text: str | None = None) -> list[Script]:
        with self._session_factory() as session:
            statement = select(ScriptRecord).order_by(ScriptRecord.name.asc())
            if search_text:
                pattern = f"%{search_text.strip()}%"
                statement = statement.where(
                    or_(
                        ScriptRecord.name.ilike(pattern),
                        ScriptRecord.description.ilike(pattern),
                    )
                )
            records = session.scalars(statement).all()
            return [_to_domain(record) for record in records]
