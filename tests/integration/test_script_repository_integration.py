from __future__ import annotations

from admin_assistant.core.enums import ShellType
from admin_assistant.core.time import utc_now
from admin_assistant.infrastructure.db.models.script_record import ScriptRecord
from admin_assistant.infrastructure.db.repositories.script_repository_sqlalchemy import (
    SqlAlchemyScriptRepository,
)
from admin_assistant.infrastructure.db.session import create_session_factory
from admin_assistant.modules.scripts.models import Script


def test_script_repository_crud_with_sqlite(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'scripts.db').as_posix()}"
    session_factory = create_session_factory(database_url=database_url, create_schema=True)
    repository = SqlAlchemyScriptRepository(session_factory=session_factory)
    now = utc_now()

    created = repository.add(
        Script(
            id="script-1",
            name="Disk usage",
            description="Check disk usage",
            content="df -h",
            shell_type=ShellType.BASH,
            requires_tty=False,
            timeout_sec=300,
            execution_mode="auto",
            version=1,
            created_at=now,
            updated_at=now,
        )
    )

    updated = repository.update(
        Script(
            id=created.id,
            name="Disk usage extended",
            description="Check disk usage and inodes",
            content="df -h\ndf -i",
            shell_type=ShellType.SH,
            requires_tty=True,
            timeout_sec=600,
            execution_mode="auto",
            version=2,
            created_at=created.created_at,
            updated_at=utc_now(),
        )
    )
    listed = repository.list()
    loaded = repository.get(created.id)
    repository.delete(created.id)

    with session_factory() as session:
        record = session.get(ScriptRecord, created.id)

    assert len(listed) == 1
    assert updated.name == "Disk usage extended"
    assert loaded is not None
    assert loaded.shell_type is ShellType.SH
    assert loaded.requires_tty is True
    assert repository.get(created.id) is None
    assert record is None
