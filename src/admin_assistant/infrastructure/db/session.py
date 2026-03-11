from __future__ import annotations

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from admin_assistant.infrastructure.db.base import Base
from admin_assistant.infrastructure.db import models  # noqa: F401


def create_engine_from_url(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.drivername.startswith("sqlite") and url.database in (None, "", ":memory:"):
        return create_engine(
            database_url,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    if url.drivername.startswith("sqlite"):
        return create_engine(
            database_url,
            future=True,
            connect_args={"check_same_thread": False},
        )
    return create_engine(database_url, future=True)


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_compatible_schema(engine)


def _ensure_compatible_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "app_settings" in table_names:
        existing_columns = {column["name"] for column in inspector.get_columns("app_settings")}
        if "analysis_language" not in existing_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE app_settings ADD COLUMN analysis_language VARCHAR(8)"))

    if "script_runs" in table_names:
        script_run_columns = {column["name"] for column in inspector.get_columns("script_runs")}
        if "requires_sudo" not in script_run_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE script_runs ADD COLUMN requires_sudo BOOLEAN DEFAULT 0"))

    if "ai_analyses" in table_names:
        analysis_columns = {column["name"] for column in inspector.get_columns("ai_analyses")}
        with engine.begin() as connection:
            if "fix_plan_title" not in analysis_columns:
                connection.execute(text("ALTER TABLE ai_analyses ADD COLUMN fix_plan_title TEXT"))
            if "fix_plan_summary" not in analysis_columns:
                connection.execute(text("ALTER TABLE ai_analyses ADD COLUMN fix_plan_summary TEXT"))
            if "evidence_json" not in analysis_columns:
                connection.execute(text("ALTER TABLE ai_analyses ADD COLUMN evidence_json TEXT DEFAULT '[]'"))

    if "ai_suggested_actions" in table_names:
        action_columns = {column["name"] for column in inspector.get_columns("ai_suggested_actions")}
        with engine.begin() as connection:
            if "requires_sudo" not in action_columns:
                connection.execute(text("ALTER TABLE ai_suggested_actions ADD COLUMN requires_sudo BOOLEAN DEFAULT 0"))
            if "requires_tty" not in action_columns:
                connection.execute(text("ALTER TABLE ai_suggested_actions ADD COLUMN requires_tty BOOLEAN DEFAULT 0"))
            if "step_order" not in action_columns:
                connection.execute(text("ALTER TABLE ai_suggested_actions ADD COLUMN step_order INTEGER"))


def create_session_factory(database_url: str, create_schema: bool = False) -> sessionmaker[Session]:
    engine = create_engine_from_url(database_url)
    if create_schema:
        initialize_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
