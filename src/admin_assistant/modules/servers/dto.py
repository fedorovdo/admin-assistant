from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, SecretStr

from admin_assistant.core.enums import AuthType, HostKeyPolicy


class ServerCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    host: str
    port: int = 22
    username: str
    auth_type: AuthType
    password: SecretStr | None = None
    key_path: str | None = None
    key_passphrase: SecretStr | None = None
    host_key_policy: HostKeyPolicy = HostKeyPolicy.MANUAL_APPROVE
    tags: tuple[str, ...] = ()
    notes: str | None = None


class ServerUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    server_id: str
    name: str
    host: str
    port: int = 22
    username: str
    auth_type: AuthType
    password: SecretStr | None = None
    key_path: str | None = None
    key_passphrase: SecretStr | None = None
    host_key_policy: HostKeyPolicy = HostKeyPolicy.MANUAL_APPROVE
    tags: tuple[str, ...] = ()
    notes: str | None = None


class ServerListQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    search_text: str | None = None


class ServerConnectionTestRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    server_id: str


class ServerSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    host: str
    port: int
    username: str
    auth_type: AuthType
    host_key_policy: HostKeyPolicy
    updated_at: datetime | None = None


class ServerDetails(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    host: str
    port: int
    username: str
    auth_type: AuthType
    key_path: str | None = None
    host_key_policy: HostKeyPolicy
    tags: tuple[str, ...] = ()
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConnectionTestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    message: str

