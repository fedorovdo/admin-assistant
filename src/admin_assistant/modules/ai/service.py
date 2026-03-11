from __future__ import annotations

from collections.abc import Callable
import re
from uuid import uuid4
from typing import Protocol

from admin_assistant.app.events import (
    AnalysisCompletedEvent,
    AnalysisRequestedEvent,
    AppEvent,
    SuggestedActionApprovedEvent,
    SuggestedActionExecutedEvent,
)
from admin_assistant.core.enums import AIAnalysisStatus, AnalysisLanguage, ApprovalStatus, RunKind, RunStatus
from admin_assistant.core.errors import NotFoundError, ValidationError
from admin_assistant.core.redaction import redact_sensitive_text, truncate_for_ai
from admin_assistant.core.time import utc_now
from admin_assistant.modules.ai.dto import (
    AIAnalysisView,
    AnalysisLaunchResult,
    AnalysisQuery,
    AnalysisRequest,
    ExecuteSuggestedActionRequest,
    SuggestedActionApprovalRequest,
    SuggestedActionRejectionRequest,
    SuggestedActionView,
)
from admin_assistant.modules.ai.models import AIAnalysis, AISuggestedAction
from admin_assistant.modules.ai.ports import AIProviderClient, AIRepository, AnalysisRunReader, ExecutionRunLauncher
from admin_assistant.modules.ai.prompt_builder import PromptBuilder
from admin_assistant.modules.execution.dto import RunLaunchResult, RunRequest
from admin_assistant.modules.servers.ports import SecretStore
from admin_assistant.modules.settings.ports import SettingsRepository


class AIAnalysisService(Protocol):
    def request_analysis(self, request: AnalysisRequest) -> AnalysisLaunchResult:
        ...

    def get_analysis(self, query: AnalysisQuery) -> AIAnalysisView:
        ...

    def list_suggested_actions(self, analysis_id: str) -> tuple[SuggestedActionView, ...]:
        ...

    def approve_action(self, request: SuggestedActionApprovalRequest) -> SuggestedActionView:
        ...

    def reject_action(self, request: SuggestedActionRejectionRequest) -> SuggestedActionView:
        ...

    def execute_approved_action(self, request: ExecuteSuggestedActionRequest) -> RunLaunchResult:
        ...

    def validate_action_command(self, command_text: str) -> None:
        ...


class DefaultAIAnalysisService(AIAnalysisService):
    _FORBIDDEN_AI_COMMAND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
        (
            re.compile(r"(^|[;&|()]\s*)top(\s|$)", re.IGNORECASE),
            "Interactive monitoring commands like top are not allowed.",
        ),
        (
            re.compile(r"(^|[;&|()]\s*)htop(\s|$)", re.IGNORECASE),
            "Interactive monitoring commands like htop are not allowed.",
        ),
        (
            re.compile(r"(^|[;&|()]\s*)watch(\s|$)", re.IGNORECASE),
            "Continuous watch commands are not allowed.",
        ),
        (
            re.compile(r"\btailf\b", re.IGNORECASE),
            "Streaming tail commands are not allowed.",
        ),
        (
            re.compile(r"\btail\b.*(?:\s-f(?:\s|$)|\s-F(?:\s|$)|\s--follow(?:[=\s]|$))", re.IGNORECASE),
            "Streaming tail follow commands are not allowed.",
        ),
        (
            re.compile(r"\bjournalctl\b.*(?:\s-f(?:\s|$)|\s--follow(?:[=\s]|$))", re.IGNORECASE),
            "Streaming journalctl follow commands are not allowed.",
        ),
        (
            re.compile(r"(^|[;&|()]\s*)(less|more|vi|vim|nano|emacs|man)(\s|$)", re.IGNORECASE),
            "Interactive pagers and editors are not allowed.",
        ),
        (
            re.compile(r"(^|[;&|()]\s*)(ssh|scp|sftp)(\s|$)", re.IGNORECASE),
            "Nested SSH, SCP, and SFTP commands are not allowed.",
        ),
    )
    _SAFE_SSHD_CONFIG_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"^\s*cat\b.*/etc/ssh/sshd_config(?:\s|$)", re.IGNORECASE),
        re.compile(r"^\s*grep\b.*/etc/ssh/sshd_config(?:\s|$)", re.IGNORECASE),
    )
    _SSH_SERVICE_RESTART_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(
            r"\bsystemctl\b.*\b(restart|reload|reload-or-restart|try-restart)\b.*\b(ssh|sshd)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\bservice\s+(ssh|sshd)\s+(restart|reload)\b", re.IGNORECASE),
    )

    def __init__(
        self,
        repository: AIRepository,
        run_reader: AnalysisRunReader,
        settings_repository: SettingsRepository,
        secret_store: SecretStore,
        provider_client: AIProviderClient,
        prompt_builder: PromptBuilder,
        run_launcher: ExecutionRunLauncher,
        publish_event: Callable[[AppEvent], None],
    ) -> None:
        self._repository = repository
        self._run_reader = run_reader
        self._settings_repository = settings_repository
        self._secret_store = secret_store
        self._provider_client = provider_client
        self._prompt_builder = prompt_builder
        self._run_launcher = run_launcher
        self._publish_event = publish_event

    def request_analysis(self, request: AnalysisRequest) -> AnalysisLaunchResult:
        script_run = self._run_reader.get_run(request.run_id)
        if script_run is None:
            raise NotFoundError(f"Run '{request.run_id}' was not found.")
        if script_run.status not in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
            raise ValidationError("Only completed runs can be analyzed.")

        provider_config = self._settings_repository.get_provider_config(request.provider_config_id)
        if provider_config is None:
            raise NotFoundError(f"Provider config '{request.provider_config_id}' was not found.")
        if not provider_config.is_enabled:
            raise ValidationError("The selected AI provider config is disabled.")
        provider_name = provider_config.provider_name.strip().lower()
        if provider_name not in {"openai", "ollama", "openai_compatible"}:
            raise ValidationError(f"Provider '{provider_config.provider_name}' is not supported.")

        api_key: str | None = None
        if self._provider_requires_api_key(provider_name):
            if not provider_config.api_key_ref:
                raise ValidationError("The selected AI provider does not have a stored API key.")
            api_key = self._secret_store.read_secret(provider_config.api_key_ref)
            if not api_key:
                raise ValidationError("The configured AI provider API key could not be loaded from secure storage.")

        target_results = self._run_reader.list_target_results(request.run_id)
        if request.target_result_id is not None:
            target_results = tuple(target for target in target_results if target.id == request.target_result_id)
            if not target_results:
                raise NotFoundError(
                    f"Target result '{request.target_result_id}' was not found for run '{request.run_id}'."
                )

        output_chunks = self._run_reader.list_output_chunks(request.run_id)
        if request.target_result_id is not None:
            output_chunks = tuple(
                chunk for chunk in output_chunks if chunk.target_result_id == request.target_result_id
            )

        prepared_input = self._prepare_analysis_input(
            script_run=script_run,
            target_results=target_results,
            output_chunks=output_chunks,
        )
        redacted_input = truncate_for_ai(redact_sensitive_text(prepared_input))
        app_settings = self._settings_repository.get_app_settings()
        analysis_language = (
            app_settings.analysis_language if app_settings is not None else AnalysisLanguage.EN
        )
        prompt = self._prompt_builder.build(redacted_input, analysis_language=analysis_language)
        analysis_id = str(uuid4())

        self._publish_event(
            AnalysisRequestedEvent(
                correlation_id=analysis_id,
                analysis_id=analysis_id,
                run_id=request.run_id,
                target_result_id=request.target_result_id,
                provider_config_id=request.provider_config_id,
                trigger_source=request.trigger_source,
            )
        )
        provider_response = self._provider_client.analyze(
            prompt=prompt,
            provider_config=provider_config,
            api_key=api_key,
        )

        created_at = utc_now()
        analysis = AIAnalysis(
            id=analysis_id,
            run_id=request.run_id,
            target_result_id=request.target_result_id,
            provider_config_id=request.provider_config_id,
            status=AIAnalysisStatus.COMPLETED,
            input_excerpt_redacted=redacted_input,
            summary=provider_response.summary,
            probable_causes=provider_response.probable_causes,
            evidence=provider_response.evidence,
            next_steps=provider_response.next_steps,
            fix_plan_title=provider_response.fix_plan_title,
            fix_plan_summary=provider_response.fix_plan_summary,
            model_snapshot=provider_config.model_name,
            created_at=created_at,
        )
        actions = self._build_suggested_actions(
            analysis_id=analysis_id,
            target_results=target_results,
            provider_response=provider_response,
            created_at=created_at,
        )
        saved_analysis = self._repository.create_analysis(analysis)
        self._repository.create_suggested_actions(actions)

        self._publish_event(
            AnalysisCompletedEvent(
                correlation_id=analysis_id,
                analysis_id=saved_analysis.id,
                run_id=saved_analysis.run_id,
                target_result_id=saved_analysis.target_result_id,
                summary=saved_analysis.summary,
                probable_causes=saved_analysis.probable_causes,
                next_steps=saved_analysis.next_steps,
                suggested_action_ids=tuple(action.id for action in actions),
            )
        )
        return AnalysisLaunchResult(analysis_id=saved_analysis.id, status=saved_analysis.status)

    def get_analysis(self, query: AnalysisQuery) -> AIAnalysisView:
        analysis = self._repository.get_analysis(query.analysis_id)
        if analysis is None:
            raise NotFoundError(f"Analysis '{query.analysis_id}' was not found.")
        return AIAnalysisView(
            id=analysis.id,
            run_id=analysis.run_id,
            target_result_id=analysis.target_result_id,
            provider_config_id=analysis.provider_config_id,
            status=analysis.status,
            input_excerpt_redacted=analysis.input_excerpt_redacted,
            summary=analysis.summary,
            probable_causes=analysis.probable_causes,
            evidence=analysis.evidence,
            next_steps=analysis.next_steps,
            fix_plan_title=analysis.fix_plan_title,
            fix_plan_summary=analysis.fix_plan_summary,
            suggested_actions=self._list_action_views(analysis.id, include_fix_steps=False),
            fix_steps=self._list_fix_step_views(analysis.id),
            created_at=analysis.created_at,
        )

    def list_suggested_actions(self, analysis_id: str) -> tuple[SuggestedActionView, ...]:
        return self._list_action_views(analysis_id, include_fix_steps=False)

    def approve_action(self, request: SuggestedActionApprovalRequest) -> SuggestedActionView:
        action = self._repository.get_suggested_action(request.action_id)
        if action is None:
            raise NotFoundError(f"Suggested action '{request.action_id}' was not found.")

        approved_at = utc_now()
        updated = AISuggestedAction(
            id=action.id,
            analysis_id=action.analysis_id,
            title=action.title,
            command_text=action.command_text,
            target_scope=action.target_scope,
            risk_level=action.risk_level,
            requires_sudo=action.requires_sudo,
            requires_tty=action.requires_tty,
            step_order=action.step_order,
            approval_status=ApprovalStatus.APPROVED,
            approved_at=approved_at,
            rejected_at=None,
            execution_run_id=action.execution_run_id,
            created_at=action.created_at,
        )
        saved = self._repository.update_suggested_action(updated)
        self._publish_event(
            SuggestedActionApprovedEvent(
                correlation_id=saved.analysis_id,
                action_id=saved.id,
                analysis_id=saved.analysis_id,
                approved_at=saved.approved_at or approved_at,
                approved_by=request.approved_by,
                target_scope=saved.target_scope,
            )
        )
        return self._to_suggested_action_view(saved)

    def reject_action(self, request: SuggestedActionRejectionRequest) -> SuggestedActionView:
        action = self._repository.get_suggested_action(request.action_id)
        if action is None:
            raise NotFoundError(f"Suggested action '{request.action_id}' was not found.")

        rejected_at = utc_now()
        updated = AISuggestedAction(
            id=action.id,
            analysis_id=action.analysis_id,
            title=action.title,
            command_text=action.command_text,
            target_scope=action.target_scope,
            risk_level=action.risk_level,
            requires_sudo=action.requires_sudo,
            requires_tty=action.requires_tty,
            step_order=action.step_order,
            approval_status=ApprovalStatus.REJECTED,
            approved_at=None,
            rejected_at=rejected_at,
            execution_run_id=action.execution_run_id,
            created_at=action.created_at,
        )
        saved = self._repository.update_suggested_action(updated)
        return self._to_suggested_action_view(saved)

    def execute_approved_action(self, request: ExecuteSuggestedActionRequest) -> RunLaunchResult:
        action = self._repository.get_suggested_action(request.action_id)
        if action is None:
            raise NotFoundError(f"Suggested action '{request.action_id}' was not found.")
        if action.approval_status is not ApprovalStatus.APPROVED:
            raise ValidationError("Only approved suggested actions can be executed.")
        if action.execution_run_id:
            raise ValidationError("This suggested action has already been executed.")
        self.validate_action_command(action.command_text)

        analysis = self._repository.get_analysis(action.analysis_id)
        if analysis is None:
            raise NotFoundError(f"Analysis '{action.analysis_id}' was not found.")

        source_run = self._run_reader.get_run(analysis.run_id)
        if source_run is None:
            raise NotFoundError(f"Run '{analysis.run_id}' was not found.")

        target_results = self._run_reader.list_target_results(analysis.run_id)
        server_ids = self._resolve_action_target_scope(action.target_scope, target_results)
        requires_sudo = action.requires_sudo or action.command_text.lstrip().startswith("sudo ")
        launch = self._run_launcher.start_run(
            RunRequest(
                run_kind=RunKind.AI_ACTION,
                server_ids=server_ids,
                command_text=action.command_text,
                shell_type=source_run.shell_type,
                requires_sudo=requires_sudo,
                requires_tty=source_run.requires_tty or action.requires_tty or requires_sudo,
                initiator=request.initiated_by,
                source_analysis_id=analysis.id,
                source_action_id=action.id,
            )
        )

        saved = self._repository.update_suggested_action(
            AISuggestedAction(
                id=action.id,
                analysis_id=action.analysis_id,
                title=action.title,
                command_text=action.command_text,
                target_scope=action.target_scope,
                risk_level=action.risk_level,
                requires_sudo=action.requires_sudo,
                requires_tty=action.requires_tty,
                step_order=action.step_order,
                approval_status=action.approval_status,
                approved_at=action.approved_at,
                rejected_at=action.rejected_at,
                execution_run_id=launch.run_id,
                created_at=action.created_at,
            )
        )
        self._publish_event(
            SuggestedActionExecutedEvent(
                correlation_id=saved.analysis_id,
                action_id=saved.id,
                analysis_id=saved.analysis_id,
                execution_run_id=launch.run_id,
                executed_at=utc_now(),
            )
        )
        return launch

    def _prepare_analysis_input(
        self,
        script_run,
        target_results,
        output_chunks,
    ) -> str:
        lines = [
            f"Run ID: {script_run.id}",
            f"Run kind: {script_run.run_kind.value}",
            f"Run status: {script_run.status.value}",
        ]
        if script_run.command_snapshot:
            lines.append(f"Manual command: {script_run.command_snapshot}")
        if script_run.script_snapshot:
            script_name = script_run.script_snapshot.get("name")
            if script_name:
                lines.append(f"Script name: {script_name}")
            shell_type = script_run.script_snapshot.get("shell_type")
            if shell_type:
                lines.append(f"Script shell: {shell_type}")

        lines.append("")
        lines.append("Targets:")
        for target in target_results:
            server_name = str(target.server_snapshot.get("name", target.server_id))
            target_line = f"- {server_name}: status={target.status.value}"
            if target.exit_code is not None:
                target_line += f", exit_code={target.exit_code}"
            if target.error_message:
                target_line += f", error={target.error_message}"
            lines.append(target_line)

        lines.append("")
        lines.append("Output:")
        target_names = {
            target.id: str(target.server_snapshot.get("name", target.server_id))
            for target in target_results
        }
        for chunk in output_chunks:
            server_name = target_names.get(chunk.target_result_id, chunk.target_result_id)
            for raw_line in chunk.chunk_text.splitlines() or [""]:
                lines.append(f"[{server_name}][{chunk.stream.value}] {raw_line}")

        return "\n".join(lines).strip()

    def _to_suggested_action_view(self, action: AISuggestedAction) -> SuggestedActionView:
        return SuggestedActionView(
            id=action.id,
            analysis_id=action.analysis_id,
            title=action.title,
            command_text=action.command_text,
            target_scope=action.target_scope,
            risk_level=action.risk_level,
            requires_sudo=action.requires_sudo,
            requires_tty=action.requires_tty,
            step_order=action.step_order,
            approval_status=action.approval_status,
            approved_at=action.approved_at,
            rejected_at=action.rejected_at,
            execution_run_id=action.execution_run_id,
            created_at=action.created_at,
        )

    def _list_action_views(
        self,
        analysis_id: str,
        *,
        include_fix_steps: bool,
    ) -> tuple[SuggestedActionView, ...]:
        actions = self._repository.list_suggested_actions(analysis_id)
        filtered = [
            action
            for action in actions
            if include_fix_steps or action.step_order is None
        ]
        if include_fix_steps:
            filtered.sort(
                key=lambda action: (
                    action.step_order is None,
                    action.step_order or 0,
                    action.created_at.isoformat() if action.created_at else "",
                    action.id,
                )
            )
        return tuple(self._to_suggested_action_view(action) for action in filtered)

    def _list_fix_step_views(self, analysis_id: str) -> tuple[SuggestedActionView, ...]:
        actions = [
            action
            for action in self._repository.list_suggested_actions(analysis_id)
            if action.step_order is not None
        ]
        actions.sort(
            key=lambda action: (
                action.step_order or 0,
                action.created_at.isoformat() if action.created_at else "",
                action.id,
            )
        )
        return tuple(self._to_suggested_action_view(action) for action in actions)

    def _build_suggested_actions(
        self,
        *,
        analysis_id: str,
        target_results,
        provider_response,
        created_at,
    ) -> tuple[AISuggestedAction, ...]:
        actions_list: list[AISuggestedAction] = []
        for action in provider_response.suggested_actions:
            built_action = self._build_action_from_provider(
                analysis_id=analysis_id,
                title=action.title,
                command_text=action.command_text,
                target_scope=action.target_scope,
                risk_level=action.risk_level,
                target_results=target_results,
                created_at=created_at,
            )
            if built_action is not None:
                actions_list.append(built_action)

        for index, step in enumerate(provider_response.fix_steps, start=1):
            built_step = self._build_action_from_provider(
                analysis_id=analysis_id,
                title=step.title,
                command_text=step.command_text,
                target_scope=step.target_scope,
                risk_level=step.risk_level,
                target_results=target_results,
                created_at=created_at,
                requires_sudo=step.requires_sudo,
                requires_tty=step.requires_tty,
                step_order=index,
            )
            if built_step is not None:
                actions_list.append(built_step)

        return tuple(actions_list)

    def _build_action_from_provider(
        self,
        *,
        analysis_id: str,
        title: str,
        command_text: str,
        target_scope: str,
        risk_level,
        target_results,
        created_at,
        requires_sudo: bool = False,
        requires_tty: bool = False,
        step_order: int | None = None,
    ) -> AISuggestedAction | None:
        try:
            canonical_target_scope = self._canonicalize_target_scope(
                target_scope=target_scope,
                target_results=target_results,
            )
        except ValidationError:
            return None
        try:
            self.validate_action_command(command_text)
        except ValidationError:
            return None

        return AISuggestedAction(
            id=str(uuid4()),
            analysis_id=analysis_id,
            title=title,
            command_text=command_text,
            target_scope=canonical_target_scope,
            risk_level=risk_level,
            requires_sudo=requires_sudo,
            requires_tty=requires_tty,
            step_order=step_order,
            approval_status=ApprovalStatus.PENDING,
            created_at=created_at,
        )

    def _resolve_action_target_scope(
        self,
        target_scope: str,
        target_results,
    ) -> tuple[str, ...]:
        normalized_scope = target_scope.strip().lower()
        if normalized_scope in {"all", "all hosts", "all servers", "all targets", "*"}:
            server_ids = tuple(target.server_id for target in target_results)
            if server_ids:
                return server_ids

        matches: list[str] = []
        for target in target_results:
            server_name = str(target.server_snapshot.get("name", "")).strip().lower()
            server_host = str(target.server_snapshot.get("host", "")).strip().lower()
            server_id = target.server_id.strip().lower()
            if normalized_scope in {server_name, server_host, server_id}:
                matches.append(target.server_id)

        if len(matches) == 1:
            return (matches[0],)

        raise ValidationError(
            f"Suggested action target scope '{target_scope}' could not be resolved to a safe server selection."
        )

    def _canonicalize_target_scope(
        self,
        target_scope: str,
        target_results,
    ) -> str:
        normalized_scope = target_scope.strip().lower()
        if normalized_scope in {
            "all",
            "all hosts",
            "all servers",
            "all targets",
            "*",
            "все",
            "все хосты",
            "все серверы",
            "все серверa",
            "все цели",
            "все таргеты",
            "все узлы",
        }:
            return "all"

        matches: list[str] = []
        for target in target_results:
            server_name = str(target.server_snapshot.get("name", "")).strip()
            server_host = str(target.server_snapshot.get("host", "")).strip()
            server_id = target.server_id.strip()
            candidates = (server_id, server_name, server_host)
            lowered_candidates = tuple(candidate.lower() for candidate in candidates if candidate)
            if normalized_scope in lowered_candidates or any(
                candidate and candidate in normalized_scope for candidate in lowered_candidates
            ):
                matches.append(server_id)

        unique_matches = tuple(dict.fromkeys(matches))
        if len(unique_matches) == 1:
            return unique_matches[0]

        if len(target_results) == 1:
            return target_results[0].server_id

        raise ValidationError(
            f"Suggested action target scope '{target_scope}' could not be canonicalized safely."
        )

    def _provider_requires_api_key(self, provider_name: str) -> bool:
        return provider_name in {"openai", "openai_compatible"}

    def validate_action_command(self, command_text: str) -> None:
        normalized = " ".join(command_text.strip().split())
        if not normalized:
            raise ValidationError("AI-generated command text cannot be empty.")

        for pattern, message in self._FORBIDDEN_AI_COMMAND_PATTERNS:
            if pattern.search(normalized):
                raise ValidationError(message)

        lowered = normalized.lower()
        if "/etc/ssh/sshd_config" in lowered and not any(
            pattern.search(normalized) for pattern in self._SAFE_SSHD_CONFIG_PATTERNS
        ):
            raise ValidationError(
                "Direct modifications to /etc/ssh/sshd_config are not allowed for executable AI actions."
            )
        for pattern in self._SSH_SERVICE_RESTART_PATTERNS:
            if pattern.search(normalized):
                raise ValidationError(
                    "Restarting or reloading ssh/sshd is not allowed for executable AI actions."
                )
        if "journalctl" in lowered and "--no-pager" not in lowered:
            raise ValidationError("journalctl commands must include --no-pager.")
        if "systemctl" in lowered and " status " in f" {lowered} " and "--no-pager" not in lowered:
            raise ValidationError("systemctl status commands must include --no-pager.")
