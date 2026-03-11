from __future__ import annotations

import json
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from admin_assistant.core.enums import ExecutionMethod, RunKind, RunStatus, ShellType, StreamType
from admin_assistant.core.time import utc_now
from admin_assistant.infrastructure.db.models.run_output_chunk_record import RunOutputChunkRecord
from admin_assistant.infrastructure.db.models.run_target_result_record import RunTargetResultRecord
from admin_assistant.infrastructure.db.models.script_run_record import ScriptRunRecord
from admin_assistant.modules.execution.dto import OutputChunkDTO
from admin_assistant.modules.execution.models import RunTargetResult, ScriptRun


def _run_to_record(script_run: ScriptRun) -> ScriptRunRecord:
    return ScriptRunRecord(
        id=script_run.id,
        run_kind=script_run.run_kind.value,
        script_id=script_run.script_id,
        script_snapshot_json=json.dumps(script_run.script_snapshot),
        command_snapshot=script_run.command_snapshot,
        shell_type=script_run.shell_type.value,
        requires_sudo=script_run.requires_sudo,
        requires_tty=script_run.requires_tty,
        status=script_run.status.value,
        trigger_source=script_run.trigger_source,
        requested_at=script_run.requested_at,
        started_at=script_run.started_at,
        completed_at=script_run.completed_at,
        request_ai_analysis=script_run.request_ai_analysis,
        initiator=script_run.initiator,
        source_analysis_id=script_run.source_analysis_id,
        source_action_id=script_run.source_action_id,
    )


def _target_to_record(target: RunTargetResult) -> RunTargetResultRecord:
    return RunTargetResultRecord(
        id=target.id,
        run_id=target.run_id,
        server_id=target.server_id,
        server_snapshot_json=json.dumps(target.server_snapshot),
        status=target.status.value,
        execution_method=target.execution_method.value if target.execution_method else None,
        exit_code=target.exit_code,
        started_at=target.started_at,
        completed_at=target.completed_at,
        error_message=target.error_message,
    )


def _run_to_domain(record: ScriptRunRecord) -> ScriptRun:
    return ScriptRun(
        id=record.id,
        run_kind=RunKind(record.run_kind),
        status=RunStatus(record.status),
        script_id=record.script_id,
        script_snapshot=json.loads(record.script_snapshot_json or "{}"),
        command_snapshot=record.command_snapshot,
        shell_type=ShellType(record.shell_type),
        requires_sudo=record.requires_sudo,
        requires_tty=record.requires_tty,
        trigger_source=record.trigger_source,
        requested_at=record.requested_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        request_ai_analysis=record.request_ai_analysis,
        initiator=record.initiator,
        source_analysis_id=record.source_analysis_id,
        source_action_id=record.source_action_id,
    )


def _target_to_domain(record: RunTargetResultRecord) -> RunTargetResult:
    return RunTargetResult(
        id=record.id,
        run_id=record.run_id,
        server_id=record.server_id,
        server_snapshot=json.loads(record.server_snapshot_json or "{}"),
        status=RunStatus(record.status),
        execution_method=ExecutionMethod(record.execution_method) if record.execution_method else None,
        exit_code=record.exit_code,
        started_at=record.started_at,
        completed_at=record.completed_at,
        error_message=record.error_message,
    )


class SqlAlchemyExecutionRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_run(self, script_run: ScriptRun, targets: Iterable[RunTargetResult]) -> ScriptRun:
        run_record = _run_to_record(script_run)
        target_records = [_target_to_record(target) for target in targets]
        with self._session_factory() as session:
            session.add(run_record)
            session.add_all(target_records)
            session.commit()
            session.refresh(run_record)
            return _run_to_domain(run_record)

    def update_run(self, script_run: ScriptRun) -> ScriptRun:
        with self._session_factory() as session:
            record = session.get(ScriptRunRecord, script_run.id)
            if record is None:
                raise KeyError(f"Run '{script_run.id}' not found.")

            record.run_kind = script_run.run_kind.value
            record.script_id = script_run.script_id
            record.script_snapshot_json = json.dumps(script_run.script_snapshot)
            record.command_snapshot = script_run.command_snapshot
            record.shell_type = script_run.shell_type.value
            record.requires_sudo = script_run.requires_sudo
            record.requires_tty = script_run.requires_tty
            record.status = script_run.status.value
            record.trigger_source = script_run.trigger_source
            record.requested_at = script_run.requested_at
            record.started_at = script_run.started_at
            record.completed_at = script_run.completed_at
            record.request_ai_analysis = script_run.request_ai_analysis
            record.initiator = script_run.initiator
            record.source_analysis_id = script_run.source_analysis_id
            record.source_action_id = script_run.source_action_id

            session.commit()
            session.refresh(record)
            return _run_to_domain(record)

    def get_run(self, run_id: str) -> ScriptRun | None:
        with self._session_factory() as session:
            record = session.get(ScriptRunRecord, run_id)
            if record is None:
                return None
            return _run_to_domain(record)

    def update_target_result(self, target: RunTargetResult) -> RunTargetResult:
        with self._session_factory() as session:
            record = session.get(RunTargetResultRecord, target.id)
            if record is None:
                raise KeyError(f"Target result '{target.id}' not found.")

            record.server_snapshot_json = json.dumps(target.server_snapshot)
            record.status = target.status.value
            record.execution_method = target.execution_method.value if target.execution_method else None
            record.exit_code = target.exit_code
            record.started_at = target.started_at
            record.completed_at = target.completed_at
            record.error_message = target.error_message

            session.commit()
            session.refresh(record)
            return _target_to_domain(record)

    def list_target_results(self, run_id: str) -> tuple[RunTargetResult, ...]:
        with self._session_factory() as session:
            statement = (
                select(RunTargetResultRecord)
                .where(RunTargetResultRecord.run_id == run_id)
                .order_by(RunTargetResultRecord.started_at.asc(), RunTargetResultRecord.id.asc())
            )
            records = session.scalars(statement).all()
            return tuple(_target_to_domain(record) for record in records)

    def append_output_chunk(
        self,
        target_result_id: str,
        stream: StreamType,
        seq_no: int,
        chunk_text: str,
    ) -> OutputChunkDTO:
        created_at = utc_now()
        record = RunOutputChunkRecord(
            target_result_id=target_result_id,
            seq_no=seq_no,
            stream=stream.value,
            chunk_text=chunk_text,
            created_at=created_at,
        )
        with self._session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return OutputChunkDTO(
                target_result_id=record.target_result_id,
                seq_no=record.seq_no,
                stream=StreamType(record.stream),
                chunk_text=record.chunk_text,
                created_at=record.created_at or created_at,
            )

    def list_output_chunks(self, run_id: str) -> tuple[OutputChunkDTO, ...]:
        with self._session_factory() as session:
            statement = (
                select(RunOutputChunkRecord)
                .join(
                    RunTargetResultRecord,
                    RunOutputChunkRecord.target_result_id == RunTargetResultRecord.id,
                )
                .where(RunTargetResultRecord.run_id == run_id)
                .order_by(RunOutputChunkRecord.created_at.asc(), RunOutputChunkRecord.id.asc())
            )
            records = session.scalars(statement).all()
            return tuple(
                OutputChunkDTO(
                    target_result_id=record.target_result_id,
                    seq_no=record.seq_no,
                    stream=StreamType(record.stream),
                    chunk_text=record.chunk_text,
                    created_at=record.created_at or utc_now(),
                )
                for record in records
            )
