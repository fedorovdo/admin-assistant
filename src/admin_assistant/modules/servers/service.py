from __future__ import annotations

from uuid import uuid4
from typing import Protocol

from admin_assistant.core.errors import NotFoundError, ValidationError
from admin_assistant.core.enums import AuthType
from admin_assistant.core.result import OperationResult
from admin_assistant.core.time import utc_now
from admin_assistant.modules.servers.dto import (
    ConnectionTestResult,
    ServerConnectionTestRequest,
    ServerCreateRequest,
    ServerDetails,
    ServerListQuery,
    ServerSummary,
    ServerUpdateRequest,
)
from admin_assistant.modules.servers.models import Server
from admin_assistant.modules.servers.ports import SSHConnectivityProbe, SecretStore, ServerRepository


def _to_details(server: Server) -> ServerDetails:
    return ServerDetails(
        id=server.id,
        name=server.name,
        host=server.host,
        port=server.port,
        username=server.username,
        auth_type=server.auth_type,
        key_path=server.key_path,
        host_key_policy=server.host_key_policy,
        tags=server.tags,
        notes=server.notes,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


def _to_summary(server: Server) -> ServerSummary:
    return ServerSummary(
        id=server.id,
        name=server.name,
        host=server.host,
        port=server.port,
        username=server.username,
        auth_type=server.auth_type,
        host_key_policy=server.host_key_policy,
        updated_at=server.updated_at,
    )


def _normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ServerService(Protocol):
    def create_server(self, request: ServerCreateRequest) -> ServerDetails:
        ...

    def update_server(self, request: ServerUpdateRequest) -> ServerDetails:
        ...

    def delete_server(self, server_id: str) -> OperationResult:
        ...

    def get_server(self, server_id: str) -> ServerDetails:
        ...

    def list_servers(self, query: ServerListQuery) -> tuple[ServerSummary, ...]:
        ...

    def test_connection(self, request: ServerConnectionTestRequest) -> ConnectionTestResult:
        ...


class DefaultServerService(ServerService):
    def __init__(
        self,
        repository: ServerRepository,
        secret_store: SecretStore,
        connectivity_probe: SSHConnectivityProbe,
    ) -> None:
        self._repository = repository
        self._secret_store = secret_store
        self._connectivity_probe = connectivity_probe

    def create_server(self, request: ServerCreateRequest) -> ServerDetails:
        server = self._build_new_server(request)
        saved = self._repository.add(server)
        return _to_details(saved)

    def update_server(self, request: ServerUpdateRequest) -> ServerDetails:
        existing = self._repository.get(request.server_id)
        if existing is None:
            raise NotFoundError(f"Server '{request.server_id}' was not found.")

        self._validate_common_fields(
            name=request.name,
            host=request.host,
            username=request.username,
        )

        password_value = request.password.get_secret_value() if request.password else None
        key_passphrase_value = request.key_passphrase.get_secret_value() if request.key_passphrase else None

        credential_ref = existing.credential_ref
        key_path = None
        key_passphrase_ref = existing.key_passphrase_ref

        if request.auth_type is AuthType.PASSWORD:
            if existing.auth_type is AuthType.KEY and not password_value:
                raise ValidationError("Switching to password authentication requires a password.")
            if existing.key_passphrase_ref:
                self._secret_store.delete_secret(existing.key_passphrase_ref)
                key_passphrase_ref = None
            if password_value:
                credential_ref = self._secret_store.save_secret(
                    key=existing.credential_ref or f"server:{existing.id}:password",
                    value=password_value,
                )
            elif not credential_ref:
                raise ValidationError("Password authentication requires a password.")
        else:
            key_path = _normalized_text(request.key_path)
            if not key_path:
                raise ValidationError("Key authentication requires a key path.")
            if existing.auth_type is AuthType.PASSWORD and existing.credential_ref:
                self._secret_store.delete_secret(existing.credential_ref)
                credential_ref = None
            if key_passphrase_value:
                key_passphrase_ref = self._secret_store.save_secret(
                    key=existing.key_passphrase_ref or f"server:{existing.id}:key_passphrase",
                    value=key_passphrase_value,
                )

        updated = Server(
            id=existing.id,
            name=request.name.strip(),
            host=request.host.strip(),
            port=request.port,
            username=request.username.strip(),
            auth_type=request.auth_type,
            credential_ref=credential_ref if request.auth_type is AuthType.PASSWORD else None,
            key_path=key_path,
            key_passphrase_ref=key_passphrase_ref if request.auth_type is AuthType.KEY else None,
            host_key_policy=request.host_key_policy,
            tags=tuple(tag.strip() for tag in request.tags if tag.strip()),
            notes=_normalized_text(request.notes),
            created_at=existing.created_at,
            updated_at=utc_now(),
        )
        saved = self._repository.update(updated)
        return _to_details(saved)

    def delete_server(self, server_id: str) -> OperationResult:
        existing = self._repository.get(server_id)
        if existing is None:
            raise NotFoundError(f"Server '{server_id}' was not found.")

        if existing.credential_ref:
            self._secret_store.delete_secret(existing.credential_ref)
        if existing.key_passphrase_ref:
            self._secret_store.delete_secret(existing.key_passphrase_ref)

        self._repository.delete(server_id)
        return OperationResult(success=True)

    def get_server(self, server_id: str) -> ServerDetails:
        server = self._repository.get(server_id)
        if server is None:
            raise NotFoundError(f"Server '{server_id}' was not found.")
        return _to_details(server)

    def list_servers(self, query: ServerListQuery) -> tuple[ServerSummary, ...]:
        servers = self._repository.list(search_text=query.search_text)
        return tuple(_to_summary(server) for server in servers)

    def test_connection(self, request: ServerConnectionTestRequest) -> ConnectionTestResult:
        server = self._repository.get(request.server_id)
        if server is None:
            return ConnectionTestResult(
                success=False,
                message=f"Server '{request.server_id}' was not found.",
            )

        password: str | None = None
        key_passphrase: str | None = None

        if server.auth_type is AuthType.PASSWORD:
            if not server.credential_ref:
                return ConnectionTestResult(
                    success=False,
                    message="No stored password reference was found for this server.",
                )
            password = self._secret_store.read_secret(server.credential_ref)
            if not password:
                return ConnectionTestResult(
                    success=False,
                    message="Stored password could not be resolved from secret storage.",
                )
        else:
            if not server.key_path:
                return ConnectionTestResult(
                    success=False,
                    message="No private key path is configured for this server.",
                )
            if server.key_passphrase_ref:
                key_passphrase = self._secret_store.read_secret(server.key_passphrase_ref)

        return self._connectivity_probe.test_connection(
            server=server,
            password=password,
            key_passphrase=key_passphrase,
        )

    def _build_new_server(self, request: ServerCreateRequest) -> Server:
        now = utc_now()
        server_id = str(uuid4())
        self._validate_common_fields(
            name=request.name,
            host=request.host,
            username=request.username,
        )

        password_value = request.password.get_secret_value() if request.password else None
        key_passphrase_value = request.key_passphrase.get_secret_value() if request.key_passphrase else None

        credential_ref: str | None = None
        key_path: str | None = None
        key_passphrase_ref: str | None = None

        if request.auth_type is AuthType.PASSWORD:
            if not password_value:
                raise ValidationError("Password authentication requires a password.")
            credential_ref = self._secret_store.save_secret(
                key=f"server:{server_id}:password",
                value=password_value,
            )
        else:
            key_path = _normalized_text(request.key_path)
            if not key_path:
                raise ValidationError("Key authentication requires a key path.")
            if key_passphrase_value:
                key_passphrase_ref = self._secret_store.save_secret(
                    key=f"server:{server_id}:key_passphrase",
                    value=key_passphrase_value,
                )

        return Server(
            id=server_id,
            name=request.name.strip(),
            host=request.host.strip(),
            port=request.port,
            username=request.username.strip(),
            auth_type=request.auth_type,
            credential_ref=credential_ref,
            key_path=key_path,
            key_passphrase_ref=key_passphrase_ref,
            host_key_policy=request.host_key_policy,
            tags=tuple(tag.strip() for tag in request.tags if tag.strip()),
            notes=_normalized_text(request.notes),
            created_at=now,
            updated_at=now,
        )

    def _validate_common_fields(self, name: str, host: str, username: str) -> None:
        if not name.strip():
            raise ValidationError("Server name is required.")
        if not host.strip():
            raise ValidationError("Server host is required.")
        if not username.strip():
            raise ValidationError("Server username is required.")
