from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from admin_assistant.core.enums import AIAnalysisStatus, ApprovalStatus, RiskLevel
from admin_assistant.infrastructure.db.models.ai_analysis_record import AIAnalysisRecord
from admin_assistant.infrastructure.db.models.ai_suggested_action_record import AISuggestedActionRecord
from admin_assistant.modules.ai.models import AIAnalysis, AISuggestedAction


def _analysis_to_domain(record: AIAnalysisRecord) -> AIAnalysis:
    return AIAnalysis(
        id=record.id,
        run_id=record.run_id,
        provider_config_id=record.provider_config_id,
        status=AIAnalysisStatus(record.status),
        target_result_id=record.target_result_id,
        input_excerpt_redacted=record.input_excerpt_redacted,
        summary=record.summary,
        probable_causes=tuple(json.loads(record.probable_causes_json or "[]")),
        evidence=tuple(json.loads(record.evidence_json or "[]")),
        next_steps=tuple(json.loads(record.next_steps_json or "[]")),
        fix_plan_title=record.fix_plan_title,
        fix_plan_summary=record.fix_plan_summary,
        model_snapshot=record.model_snapshot,
        created_at=record.created_at,
    )


def _action_to_domain(record: AISuggestedActionRecord) -> AISuggestedAction:
    return AISuggestedAction(
        id=record.id,
        analysis_id=record.analysis_id,
        title=record.title,
        command_text=record.command_text,
        target_scope=record.target_scope,
        risk_level=RiskLevel(record.risk_level),
        requires_sudo=record.requires_sudo,
        requires_tty=record.requires_tty,
        step_order=record.step_order,
        approval_status=ApprovalStatus(record.approval_status),
        approved_at=record.approved_at,
        rejected_at=record.rejected_at,
        execution_run_id=record.execution_run_id,
        created_at=record.created_at,
    )


class SqlAlchemyAIRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_analysis(self, analysis: AIAnalysis) -> AIAnalysis:
        record = AIAnalysisRecord(
            id=analysis.id,
            run_id=analysis.run_id,
            target_result_id=analysis.target_result_id,
            provider_config_id=analysis.provider_config_id,
            status=analysis.status.value,
            input_excerpt_redacted=analysis.input_excerpt_redacted,
            summary=analysis.summary,
            probable_causes_json=json.dumps(list(analysis.probable_causes)),
            evidence_json=json.dumps(list(analysis.evidence)),
            next_steps_json=json.dumps(list(analysis.next_steps)),
            fix_plan_title=analysis.fix_plan_title,
            fix_plan_summary=analysis.fix_plan_summary,
            model_snapshot=analysis.model_snapshot,
            created_at=analysis.created_at,
        )
        with self._session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return _analysis_to_domain(record)

    def create_suggested_actions(
        self,
        actions: tuple[AISuggestedAction, ...],
    ) -> tuple[AISuggestedAction, ...]:
        if not actions:
            return ()

        records = [
            AISuggestedActionRecord(
                id=action.id,
                analysis_id=action.analysis_id,
                title=action.title,
                command_text=action.command_text,
                target_scope=action.target_scope,
                risk_level=action.risk_level.value,
                requires_sudo=action.requires_sudo,
                requires_tty=action.requires_tty,
                step_order=action.step_order,
                approval_status=action.approval_status.value,
                approved_at=action.approved_at,
                rejected_at=action.rejected_at,
                execution_run_id=action.execution_run_id,
                created_at=action.created_at,
            )
            for action in actions
        ]
        with self._session_factory() as session:
            session.add_all(records)
            session.commit()
            for record in records:
                session.refresh(record)
            return tuple(_action_to_domain(record) for record in records)

    def get_analysis(self, analysis_id: str) -> AIAnalysis | None:
        with self._session_factory() as session:
            record = session.get(AIAnalysisRecord, analysis_id)
            return _analysis_to_domain(record) if record is not None else None

    def get_suggested_action(self, action_id: str) -> AISuggestedAction | None:
        with self._session_factory() as session:
            record = session.get(AISuggestedActionRecord, action_id)
            return _action_to_domain(record) if record is not None else None

    def list_suggested_actions(self, analysis_id: str) -> tuple[AISuggestedAction, ...]:
        with self._session_factory() as session:
            statement = (
                select(AISuggestedActionRecord)
                .where(AISuggestedActionRecord.analysis_id == analysis_id)
                .order_by(AISuggestedActionRecord.created_at.asc(), AISuggestedActionRecord.id.asc())
            )
            records = session.scalars(statement).all()
            return tuple(_action_to_domain(record) for record in records)

    def update_suggested_action(self, action: AISuggestedAction) -> AISuggestedAction:
        with self._session_factory() as session:
            record = session.get(AISuggestedActionRecord, action.id)
            if record is None:
                raise KeyError(f"Suggested action '{action.id}' not found.")

            record.title = action.title
            record.command_text = action.command_text
            record.target_scope = action.target_scope
            record.risk_level = action.risk_level.value
            record.requires_sudo = action.requires_sudo
            record.requires_tty = action.requires_tty
            record.step_order = action.step_order
            record.approval_status = action.approval_status.value
            record.approved_at = action.approved_at
            record.rejected_at = action.rejected_at
            record.execution_run_id = action.execution_run_id
            record.created_at = action.created_at
            session.commit()
            session.refresh(record)
            return _action_to_domain(record)
