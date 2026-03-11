from __future__ import annotations

import json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from admin_assistant.core.enums import AuthType, HostKeyPolicy
from admin_assistant.infrastructure.db.models.server_record import ServerRecord
from admin_assistant.modules.servers.models import Server


def _to_record(server: Server) -> ServerRecord:
    return ServerRecord(
        id=server.id,
        name=server.name,
        host=server.host,
        port=server.port,
        username=server.username,
        auth_type=server.auth_type.value,
        credential_ref=server.credential_ref,
        key_path=server.key_path,
        key_passphrase_ref=server.key_passphrase_ref,
        host_key_policy=server.host_key_policy.value,
        tags_json=json.dumps(list(server.tags)),
        notes=server.notes,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


def _to_domain(record: ServerRecord) -> Server:
    return Server(
        id=record.id,
        name=record.name,
        host=record.host,
        port=record.port,
        username=record.username,
        auth_type=AuthType(record.auth_type),
        credential_ref=record.credential_ref,
        key_path=record.key_path,
        key_passphrase_ref=record.key_passphrase_ref,
        host_key_policy=HostKeyPolicy(record.host_key_policy),
        tags=tuple(json.loads(record.tags_json or "[]")),
        notes=record.notes,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class SqlAlchemyServerRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, server: Server) -> Server:
        record = _to_record(server)
        with self._session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return _to_domain(record)

    def update(self, server: Server) -> Server:
        with self._session_factory() as session:
            record = session.get(ServerRecord, server.id)
            if record is None:
                raise KeyError(f"Server '{server.id}' not found.")

            record.name = server.name
            record.host = server.host
            record.port = server.port
            record.username = server.username
            record.auth_type = server.auth_type.value
            record.credential_ref = server.credential_ref
            record.key_path = server.key_path
            record.key_passphrase_ref = server.key_passphrase_ref
            record.host_key_policy = server.host_key_policy.value
            record.tags_json = json.dumps(list(server.tags))
            record.notes = server.notes
            record.created_at = server.created_at
            record.updated_at = server.updated_at

            session.commit()
            session.refresh(record)
            return _to_domain(record)

    def delete(self, server_id: str) -> None:
        with self._session_factory() as session:
            record = session.get(ServerRecord, server_id)
            if record is None:
                return
            session.delete(record)
            session.commit()

    def get(self, server_id: str) -> Server | None:
        with self._session_factory() as session:
            record = session.get(ServerRecord, server_id)
            if record is None:
                return None
            return _to_domain(record)

    def list(self, search_text: str | None = None) -> list[Server]:
        with self._session_factory() as session:
            statement = select(ServerRecord).order_by(ServerRecord.name.asc())
            if search_text:
                pattern = f"%{search_text.strip()}%"
                statement = statement.where(
                    or_(
                        ServerRecord.name.ilike(pattern),
                        ServerRecord.host.ilike(pattern),
                        ServerRecord.username.ilike(pattern),
                    )
                )
            records = session.scalars(statement).all()
            return [_to_domain(record) for record in records]
