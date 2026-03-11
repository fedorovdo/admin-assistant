from __future__ import annotations

from pydantic import SecretStr

from admin_assistant.core.enums import AuthType, HostKeyPolicy
from admin_assistant.modules.servers.dto import (
    ConnectionTestResult,
    ServerConnectionTestRequest,
    ServerCreateRequest,
    ServerListQuery,
    ServerUpdateRequest,
)
from admin_assistant.modules.servers.models import Server
from admin_assistant.modules.servers.service import DefaultServerService


class InMemoryServerRepository:
    def __init__(self) -> None:
        self._items: dict[str, Server] = {}

    def add(self, server: Server) -> Server:
        self._items[server.id] = server
        return server

    def update(self, server: Server) -> Server:
        self._items[server.id] = server
        return server

    def delete(self, server_id: str) -> None:
        self._items.pop(server_id, None)

    def get(self, server_id: str) -> Server | None:
        return self._items.get(server_id)

    def list(self, search_text: str | None = None) -> list[Server]:
        items = list(self._items.values())
        if not search_text:
            return items
        search = search_text.lower()
        return [
            item
            for item in items
            if search in item.name.lower() or search in item.host.lower() or search in item.username.lower()
        ]


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
    def test_connection(
        self,
        server: Server,
        password: str | None = None,
        key_passphrase: str | None = None,
    ):
        raise NotImplementedError


class RecordingConnectivityProbe:
    def __init__(self, result: ConnectionTestResult) -> None:
        self.result = result
        self.last_server: Server | None = None
        self.last_password: str | None = None
        self.last_key_passphrase: str | None = None

    def test_connection(
        self,
        server: Server,
        password: str | None = None,
        key_passphrase: str | None = None,
    ) -> ConnectionTestResult:
        self.last_server = server
        self.last_password = password
        self.last_key_passphrase = key_passphrase
        return self.result


def test_create_server_stores_secret_reference_and_supports_get_and_list() -> None:
    repository = InMemoryServerRepository()
    secret_store = MemorySecretStore()
    service = DefaultServerService(
        repository=repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )

    created = service.create_server(
        ServerCreateRequest(
            name="web-01",
            host="192.0.2.10",
            username="root",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("super-secret"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )

    listed = service.list_servers(ServerListQuery())
    fetched = service.get_server(created.id)
    stored = repository.get(created.id)

    assert created.id
    assert listed[0].id == created.id
    assert fetched.host == "192.0.2.10"
    assert stored is not None
    assert stored.credential_ref == f"server:{created.id}:password"
    assert secret_store.read_secret(stored.credential_ref) == "super-secret"


def test_update_and_delete_server_preserve_and_cleanup_secret_references() -> None:
    repository = InMemoryServerRepository()
    secret_store = MemorySecretStore()
    service = DefaultServerService(
        repository=repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )

    created = service.create_server(
        ServerCreateRequest(
            name="web-01",
            host="192.0.2.10",
            username="root",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("super-secret"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )

    updated = service.update_server(
        ServerUpdateRequest(
            server_id=created.id,
            name="web-01-renamed",
            host="192.0.2.20",
            port=2222,
            username="administrator",
            auth_type=AuthType.PASSWORD,
            host_key_policy=HostKeyPolicy.STRICT,
            notes="Updated server",
        )
    )
    stored_after_update = repository.get(created.id)
    preserved_secret = (
        secret_store.read_secret(stored_after_update.credential_ref)
        if stored_after_update and stored_after_update.credential_ref
        else None
    )

    delete_result = service.delete_server(created.id)

    assert updated.name == "web-01-renamed"
    assert updated.host == "192.0.2.20"
    assert stored_after_update is not None
    assert stored_after_update.credential_ref == f"server:{created.id}:password"
    assert preserved_secret == "super-secret"
    assert delete_result.success is True
    assert repository.get(created.id) is None
    assert secret_store.read_secret(f"server:{created.id}:password") is None


def test_connection_test_resolves_secret_and_returns_probe_result() -> None:
    repository = InMemoryServerRepository()
    secret_store = MemorySecretStore()
    probe = RecordingConnectivityProbe(ConnectionTestResult(success=True, message="Connected"))
    service = DefaultServerService(
        repository=repository,
        secret_store=secret_store,
        connectivity_probe=probe,
    )

    created = service.create_server(
        ServerCreateRequest(
            name="web-01",
            host="192.0.2.10",
            username="root",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("super-secret"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )

    result = service.test_connection(ServerConnectionTestRequest(server_id=created.id))

    assert result.success is True
    assert probe.last_server is not None
    assert probe.last_server.id == created.id
    assert probe.last_password == "super-secret"
