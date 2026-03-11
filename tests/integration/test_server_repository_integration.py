from __future__ import annotations

from dataclasses import replace

from pydantic import SecretStr

from admin_assistant.core.enums import AuthType, HostKeyPolicy
from admin_assistant.core.time import utc_now
from admin_assistant.infrastructure.db.models.server_record import ServerRecord
from admin_assistant.infrastructure.db.repositories.server_repository_sqlalchemy import (
    SqlAlchemyServerRepository,
)
from admin_assistant.infrastructure.db.session import create_session_factory
from admin_assistant.modules.servers.dto import ServerCreateRequest, ServerListQuery
from admin_assistant.modules.servers.models import Server
from admin_assistant.modules.servers.service import DefaultServerService


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def save_secret(self, key: str, value: str) -> str:
        self.values[key] = value
        return key

    def read_secret(self, key: str) -> str | None:
        return self.values.get(key)

    def delete_secret(self, key: str) -> None:
        self.values.pop(key, None)


class StubConnectivityProbe:
    def test_connection(self, server: Server):
        raise NotImplementedError


def test_create_and_list_servers_with_sqlite(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'servers.db').as_posix()}"
    session_factory = create_session_factory(database_url=database_url, create_schema=True)
    repository = SqlAlchemyServerRepository(session_factory=session_factory)
    secret_store = MemorySecretStore()
    service = DefaultServerService(
        repository=repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )

    created = service.create_server(
        ServerCreateRequest(
            name="db-01",
            host="198.51.100.50",
            username="admin",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("pw-123"),
            host_key_policy=HostKeyPolicy.STRICT,
        )
    )

    listed = service.list_servers(ServerListQuery())
    loaded = service.get_server(created.id)

    with session_factory() as session:
        record = session.get(ServerRecord, created.id)

    assert len(listed) == 1
    assert loaded.name == "db-01"
    assert record is not None
    assert record.host == "198.51.100.50"
    assert record.credential_ref == f"server:{created.id}:password"
    assert secret_store.read_secret(record.credential_ref) == "pw-123"


def test_repository_update_and_delete_with_sqlite(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'servers-update.db').as_posix()}"
    session_factory = create_session_factory(database_url=database_url, create_schema=True)
    repository = SqlAlchemyServerRepository(session_factory=session_factory)
    now = utc_now()

    created = repository.add(
        Server(
            id="server-1",
            name="app-01",
            host="203.0.113.10",
            port=22,
            username="deploy",
            auth_type=AuthType.PASSWORD,
            credential_ref="server:server-1:password",
            key_path=None,
            key_passphrase_ref=None,
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
            notes="Initial",
            created_at=now,
            updated_at=now,
        )
    )

    updated = repository.update(
        replace(
            created,
            name="app-01-updated",
            host="203.0.113.20",
            notes="Updated",
            updated_at=utc_now(),
        )
    )
    repository.delete(created.id)

    with session_factory() as session:
        record = session.get(ServerRecord, created.id)

    assert updated.name == "app-01-updated"
    assert updated.host == "203.0.113.20"
    assert repository.get(created.id) is None
    assert record is None
