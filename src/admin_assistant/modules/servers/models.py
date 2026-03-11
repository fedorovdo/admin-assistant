from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from admin_assistant.core.enums import AuthType, HostKeyPolicy


@dataclass(slots=True)
class Server:
    id: str
    name: str
    host: str
    port: int
    username: str
    auth_type: AuthType
    credential_ref: str | None = None
    key_path: str | None = None
    key_passphrase_ref: str | None = None
    host_key_policy: HostKeyPolicy = HostKeyPolicy.MANUAL_APPROVE
    tags: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

