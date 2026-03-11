from __future__ import annotations

from typing import Protocol

from admin_assistant.modules.servers.dto import ConnectionTestResult
from admin_assistant.modules.servers.models import Server


class ServerRepository(Protocol):
    def add(self, server: Server) -> Server:
        ...

    def update(self, server: Server) -> Server:
        ...

    def delete(self, server_id: str) -> None:
        ...

    def get(self, server_id: str) -> Server | None:
        ...

    def list(self, search_text: str | None = None) -> list[Server]:
        ...


class SecretStore(Protocol):
    def save_secret(self, key: str, value: str) -> str:
        ...

    def read_secret(self, key: str) -> str | None:
        ...

    def delete_secret(self, key: str) -> None:
        ...


class SSHConnectivityProbe(Protocol):
    def test_connection(
        self,
        server: Server,
        password: str | None = None,
        key_passphrase: str | None = None,
    ) -> ConnectionTestResult:
        ...
