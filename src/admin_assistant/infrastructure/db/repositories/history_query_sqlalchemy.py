from __future__ import annotations

import json

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from admin_assistant.core.enums import AIAnalysisStatus, ApprovalStatus, RiskLevel, RunKind, RunStatus, ShellType, StreamType
from admin_assistant.core.errors import NotFoundError
from admin_assistant.core.time import utc_now
from admin_assistant.infrastructure.db.models.ai_analysis_record import AIAnalysisRecord
from admin_assistant.infrastructure.db.models.ai_suggested_action_record import AISuggestedActionRecord
from admin_assistant.infrastructure.db.models.run_output_chunk_record import RunOutputChunkRecord
from admin_assistant.infrastructure.db.models.run_target_result_record import RunTargetResultRecord
from admin_assistant.infrastructure.db.models.script_run_record import ScriptRunRecord
from admin_assistant.modules.ai.dto import AIAnalysisView, SuggestedActionView
from admin_assistant.modules.history.dto import (
    AnalysisDetailsQuery,
    AnalysisHistoryItem,
    AnalysisHistoryPage,
    AnalysisHistoryQuery,
    ConsoleReplayLine,
    ConsoleReplayQuery,
    ConsoleReplayView,
    LinkedAnalysisView,
    LinkedSuggestedActionView,
    RunDetailsQuery,
    RunDetailsView,
    RunHistoryItem,
    RunHistoryPage,
    RunHistoryQuery,
    RunTargetFactsView,
)


def _load_json(value: str | None, default):
    if not value:
        return default
    return json.loads(value)


class SqlAlchemyHistoryReadStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_runs(self, query: RunHistoryQuery) -> RunHistoryPage:
        target_counts = (
            select(
                RunTargetResultRecord.run_id.label("run_id"),
                func.count(RunTargetResultRecord.id).label("target_count"),
            )
            .group_by(RunTargetResultRecord.run_id)
            .subquery()
        )

        with self._session_factory() as session:
            statement = (
                select(
                    ScriptRunRecord,
                    func.coalesce(target_counts.c.target_count, 0).label("target_count"),
                )
                .outerjoin(target_counts, target_counts.c.run_id == ScriptRunRecord.id)
            )

            if query.search_text:
                pattern = f"%{query.search_text.strip().lower()}%"
                statement = statement.where(
                    or_(
                        func.lower(ScriptRunRecord.id).like(pattern),
                        func.lower(func.coalesce(ScriptRunRecord.command_snapshot, "")).like(pattern),
                        func.lower(func.coalesce(ScriptRunRecord.script_snapshot_json, "")).like(pattern),
                        func.lower(ScriptRunRecord.run_kind).like(pattern),
                    )
                )

            if query.status_filter:
                statement = statement.where(
                    ScriptRunRecord.status.in_([status.value for status in query.status_filter])
                )

            total_count = session.execute(
                select(func.count()).select_from(statement.subquery())
            ).scalar_one()

            offset = max(query.page - 1, 0) * query.page_size
            rows = session.execute(
                statement
                .order_by(ScriptRunRecord.requested_at.desc(), ScriptRunRecord.id.desc())
                .offset(offset)
                .limit(query.page_size)
            ).all()

            items = tuple(
                RunHistoryItem(
                    run_id=record.id,
                    run_kind=RunKind(record.run_kind),
                    status=RunStatus(record.status),
                    target_count=int(target_count or 0),
                    requested_at=record.requested_at,
                )
                for record, target_count in rows
            )
            return RunHistoryPage(items=items, total_count=total_count)

    def get_run_details(self, query: RunDetailsQuery) -> RunDetailsView:
        with self._session_factory() as session:
            run_record = session.get(ScriptRunRecord, query.run_id)
            if run_record is None:
                raise NotFoundError(f"Run '{query.run_id}' was not found.")

            target_records = session.scalars(
                select(RunTargetResultRecord)
                .where(RunTargetResultRecord.run_id == query.run_id)
                .order_by(RunTargetResultRecord.started_at.asc(), RunTargetResultRecord.id.asc())
            ).all()

            analysis_records = session.scalars(
                select(AIAnalysisRecord)
                .where(AIAnalysisRecord.run_id == query.run_id)
                .order_by(AIAnalysisRecord.created_at.desc(), AIAnalysisRecord.id.desc())
            ).all()

            action_records = ()
            analysis_ids = [record.id for record in analysis_records]
            if analysis_ids:
                action_records = session.scalars(
                    select(AISuggestedActionRecord)
                    .where(AISuggestedActionRecord.analysis_id.in_(analysis_ids))
                    .order_by(AISuggestedActionRecord.created_at.asc(), AISuggestedActionRecord.id.asc())
                ).all()

            actions_by_analysis: dict[str, list[LinkedSuggestedActionView]] = {}
            for record in action_records:
                actions_by_analysis.setdefault(record.analysis_id, []).append(
                    LinkedSuggestedActionView(
                        id=record.id,
                        title=record.title,
                        command_text=record.command_text,
                        target_scope=record.target_scope,
                        risk_level=RiskLevel(record.risk_level),
                        approval_status=ApprovalStatus(record.approval_status),
                        execution_run_id=record.execution_run_id,
                    )
                )

            targets = tuple(
                RunTargetFactsView(
                    target_result_id=record.id,
                    server_id=record.server_id,
                    server_name=str(_load_json(record.server_snapshot_json, {}).get("name", record.server_id)),
                    status=RunStatus(record.status),
                    exit_code=record.exit_code,
                    error_message=record.error_message,
                )
                for record in target_records
            )

            analyses = tuple(
                LinkedAnalysisView(
                    id=record.id,
                    status=AIAnalysisStatus(record.status),
                    summary=record.summary,
                    probable_causes=tuple(_load_json(record.probable_causes_json, [])),
                    next_steps=tuple(_load_json(record.next_steps_json, [])),
                    created_at=record.created_at,
                    suggested_actions=tuple(actions_by_analysis.get(record.id, [])),
                )
                for record in analysis_records
            )

            script_snapshot = _load_json(run_record.script_snapshot_json, {})
            script_name = script_snapshot.get("name") if isinstance(script_snapshot, dict) else None

            return RunDetailsView(
                run_id=run_record.id,
                run_kind=RunKind(run_record.run_kind),
                status=RunStatus(run_record.status),
                target_count=len(targets),
                command_snapshot=run_record.command_snapshot,
                script_name=script_name,
                shell_type=ShellType(run_record.shell_type),
                requires_sudo=run_record.requires_sudo,
                requires_tty=run_record.requires_tty,
                source_analysis_id=run_record.source_analysis_id,
                source_action_id=run_record.source_action_id,
                requested_at=run_record.requested_at,
                started_at=run_record.started_at,
                completed_at=run_record.completed_at,
                targets=targets,
                analyses=analyses,
            )

    def get_console_replay(self, query: ConsoleReplayQuery) -> ConsoleReplayView:
        with self._session_factory() as session:
            records = session.execute(
                select(RunOutputChunkRecord, RunTargetResultRecord.server_snapshot_json)
                .join(
                    RunTargetResultRecord,
                    RunOutputChunkRecord.target_result_id == RunTargetResultRecord.id,
                )
                .where(RunTargetResultRecord.run_id == query.run_id)
                .order_by(
                    RunOutputChunkRecord.created_at.asc(),
                    RunOutputChunkRecord.id.asc(),
                )
            ).all()

            lines = tuple(
                ConsoleReplayLine(
                    target_result_id=record.target_result_id,
                    server_name=str(_load_json(server_snapshot_json, {}).get("name", record.target_result_id)),
                    stream=StreamType(record.stream),
                    seq_no=record.seq_no,
                    chunk_text=record.chunk_text,
                    created_at=record.created_at or utc_now(),
                )
                for record, server_snapshot_json in records
            )
            return ConsoleReplayView(all_hosts_lines=lines)

    def list_analyses(self, query: AnalysisHistoryQuery) -> AnalysisHistoryPage:
        with self._session_factory() as session:
            statement = select(AIAnalysisRecord)
            if query.run_id:
                statement = statement.where(AIAnalysisRecord.run_id == query.run_id)

            total_count = session.execute(
                select(func.count()).select_from(statement.subquery())
            ).scalar_one()

            offset = max(query.page - 1, 0) * query.page_size
            records = session.scalars(
                statement
                .order_by(AIAnalysisRecord.created_at.desc(), AIAnalysisRecord.id.desc())
                .offset(offset)
                .limit(query.page_size)
            ).all()

            items = tuple(
                AnalysisHistoryItem(
                    analysis_id=record.id,
                    run_id=record.run_id,
                    status=AIAnalysisStatus(record.status),
                    created_at=record.created_at,
                )
                for record in records
            )
            return AnalysisHistoryPage(items=items, total_count=total_count)

    def get_analysis_details(self, query: AnalysisDetailsQuery) -> AIAnalysisView:
        with self._session_factory() as session:
            analysis_record = session.get(AIAnalysisRecord, query.analysis_id)
            if analysis_record is None:
                raise NotFoundError(f"Analysis '{query.analysis_id}' was not found.")

            action_records = session.scalars(
                select(AISuggestedActionRecord)
                .where(AISuggestedActionRecord.analysis_id == query.analysis_id)
                .order_by(AISuggestedActionRecord.created_at.asc(), AISuggestedActionRecord.id.asc())
            ).all()

            actions = tuple(
                SuggestedActionView(
                    id=record.id,
                    analysis_id=record.analysis_id,
                    title=record.title,
                    command_text=record.command_text,
                    target_scope=record.target_scope,
                    risk_level=RiskLevel(record.risk_level),
                    approval_status=ApprovalStatus(record.approval_status),
                    approved_at=record.approved_at,
                    rejected_at=record.rejected_at,
                    execution_run_id=record.execution_run_id,
                    created_at=record.created_at,
                )
                for record in action_records
            )

            return AIAnalysisView(
                id=analysis_record.id,
                run_id=analysis_record.run_id,
                target_result_id=analysis_record.target_result_id,
                provider_config_id=analysis_record.provider_config_id,
                status=AIAnalysisStatus(analysis_record.status),
                input_excerpt_redacted=analysis_record.input_excerpt_redacted,
                summary=analysis_record.summary,
                probable_causes=tuple(_load_json(analysis_record.probable_causes_json, [])),
                next_steps=tuple(_load_json(analysis_record.next_steps_json, [])),
                suggested_actions=actions,
                created_at=analysis_record.created_at,
            )
