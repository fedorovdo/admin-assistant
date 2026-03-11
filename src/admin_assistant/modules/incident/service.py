from __future__ import annotations

from collections.abc import Callable
import re
import shlex
from typing import Protocol
from uuid import uuid4

from admin_assistant.core.enums import AnalysisLanguage, RunKind
from admin_assistant.core.errors import ExternalIntegrationError, ValidationError
from admin_assistant.core.time import utc_now
from admin_assistant.modules.ai.dto import AnalysisQuery, AnalysisRequest, ProviderFixStepResponse
from admin_assistant.modules.ai.ports import AIProviderClient
from admin_assistant.modules.ai.service import AIAnalysisService
from admin_assistant.modules.execution.dto import RunOutputQuery, RunRequest, RunStatusQuery
from admin_assistant.modules.execution.service import ExecutionService
from admin_assistant.modules.incident.dto import (
    IncidentAnalysis,
    IncidentInvestigateRequest,
    IncidentSession,
    IncidentStep,
)
from admin_assistant.modules.incident.prompt_builder import IncidentPromptBuilder
from admin_assistant.modules.incident.runbooks import (
    IncidentRunbookTemplate,
    get_runbook_template,
    infer_incident_category,
)
from admin_assistant.modules.servers.ports import SecretStore
from admin_assistant.modules.settings.models import AIProviderConfig
from admin_assistant.modules.settings.ports import SettingsRepository


class IncidentService(Protocol):
    def investigate(
        self,
        request: IncidentInvestigateRequest,
        progress_callback: Callable[[str], None] | None = None,
    ) -> IncidentSession:
        ...

    def get_session(self, session_id: str) -> IncidentSession | None:
        ...


class DefaultIncidentService(IncidentService):
    _ALLOWED_INCIDENT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"^\s*uptime\s*$", re.IGNORECASE), "uptime"),
        (re.compile(r"^\s*free\b", re.IGNORECASE), "free"),
        (re.compile(r"^\s*df\b", re.IGNORECASE), "df"),
        (re.compile(r"^\s*du\b", re.IGNORECASE), "du"),
        (re.compile(r"^\s*ps\b", re.IGNORECASE), "ps"),
        (re.compile(r"^\s*ss\b", re.IGNORECASE), "ss"),
        (re.compile(r"^\s*hostname\b", re.IGNORECASE), "hostname"),
        (re.compile(r"^\s*uname\b", re.IGNORECASE), "uname"),
        (re.compile(r"^\s*ip\b", re.IGNORECASE), "ip"),
        (re.compile(r"^\s*journalctl\b", re.IGNORECASE), "journalctl"),
        (re.compile(r"^\s*systemctl\s+status\b", re.IGNORECASE), "systemctl status"),
        (re.compile(r"^\s*cat\b", re.IGNORECASE), "cat"),
        (re.compile(r"^\s*grep\b", re.IGNORECASE), "grep"),
        (re.compile(r"^\s*sshd\s+-t\s*$", re.IGNORECASE), "sshd -t"),
    )
    _FORBIDDEN_SHELL_TOKENS: tuple[str, ...] = ("&&", "||", ";", "|", ">", "<", "`", "$(")

    def __init__(
        self,
        settings_repository: SettingsRepository,
        secret_store: SecretStore,
        provider_client: AIProviderClient,
        prompt_builder: IncidentPromptBuilder,
        execution_service: ExecutionService,
        ai_service: AIAnalysisService,
    ) -> None:
        self._settings_repository = settings_repository
        self._secret_store = secret_store
        self._provider_client = provider_client
        self._prompt_builder = prompt_builder
        self._execution_service = execution_service
        self._ai_service = ai_service
        self._sessions: dict[str, IncidentSession] = {}

    def investigate(
        self,
        request: IncidentInvestigateRequest,
        progress_callback: Callable[[str], None] | None = None,
    ) -> IncidentSession:
        symptom = request.symptom.strip()
        if not symptom:
            raise ValidationError("Enter an incident symptom before starting Incident Mode.")
        if not request.server_ids:
            raise ValidationError("Select at least one server before starting Incident Mode.")

        provider_config, api_key, analysis_language = self._resolve_provider_context()
        now = utc_now()
        session_id = str(uuid4())
        session_title = (request.title or symptom).strip()
        category = infer_incident_category(symptom)
        runbook_template = get_runbook_template(category)
        base_session = IncidentSession(
            session_id=session_id,
            title=session_title,
            symptom=symptom,
            category=category.value,
            server_ids=request.server_ids,
            status="planning",
            created_at=now,
            updated_at=now,
        )
        self._sessions[session_id] = base_session
        plan_title: str | None = None
        plan_summary: str | None = None
        safe_steps: tuple[IncidentStep, ...] = ()
        skipped_steps: tuple[str, ...] = ()
        diagnostic_run_id: str | None = None

        try:
            self._emit_progress(
                progress_callback,
                f"[incident][status] Using incident runbook template: {category.value}.",
            )
            self._emit_progress(progress_callback, "[incident][status] Generating investigation plan...")
            plan_prompt = self._prompt_builder.build_investigation_plan(
                title=session_title,
                symptom=symptom,
                server_count=len(request.server_ids),
                category=category,
                template=runbook_template,
                analysis_language=analysis_language,
            )
            try:
                provider_response = self._provider_client.analyze(
                    prompt=plan_prompt,
                    provider_config=provider_config,
                    api_key=api_key,
                )
            except ExternalIntegrationError as exc:
                raise ExternalIntegrationError(f"Incident plan generation failed: {exc}") from exc

            plan_title = provider_response.fix_plan_title
            plan_summary = provider_response.fix_plan_summary
            safe_steps, skipped_step_messages = self._build_safe_steps(provider_response.fix_steps)
            skipped_steps = tuple(skipped_step_messages)
            if skipped_steps:
                self._emit_progress(
                    progress_callback,
                    f"[incident][status] Filtered out {len(skipped_steps)} unsafe or unsupported incident step(s).",
                )
            if not safe_steps:
                self._emit_progress(
                    progress_callback,
                    f"[incident][status] Falling back to the built-in {category.value} runbook template.",
                )
                safe_steps = self._build_template_fallback_steps(runbook_template)
            if not safe_steps:
                raise ValidationError(
                    "Incident Mode could not produce any safe auto-runnable diagnostic commands after safety filtering. "
                    "Try refining the symptom or run diagnostics manually."
                )

            self._emit_progress(
                progress_callback,
                f"[incident][status] Running {len(safe_steps)} safe diagnostic step(s)...",
            )
            combined_command = self._build_combined_command(
                title=session_title,
                symptom=symptom,
                steps=safe_steps,
            )
            requires_sudo = any(step.requires_sudo for step in safe_steps)
            requires_tty = requires_sudo or any(step.requires_tty for step in safe_steps)
            launched_run = self._execution_service.start_run(
                RunRequest(
                    run_kind=RunKind.COMMAND,
                    server_ids=request.server_ids,
                    command_text=combined_command,
                    shell_type=request.shell_type,
                    requires_sudo=requires_sudo,
                    requires_tty=requires_tty,
                    initiator=request.initiated_by,
                )
            )
            diagnostic_run_id = launched_run.run_id

            run_status = self._execution_service.get_run_status(RunStatusQuery(run_id=launched_run.run_id))
            target_count = len(run_status.targets)
            failure_count = sum(1 for target in run_status.targets if target.status.value != "succeeded")
            if failure_count:
                self._emit_progress(
                    progress_callback,
                    f"[incident][status] Diagnostic run completed with failures on {failure_count}/{target_count} target(s). Analyzing collected evidence anyway.",
                )
            else:
                self._emit_progress(
                    progress_callback,
                    f"[incident][status] Safe diagnostic run completed across {target_count} target(s).",
                )

            output_chunks = self._execution_service.list_run_output(RunOutputQuery(run_id=launched_run.run_id))
            has_non_empty_output = any(chunk.chunk_text.strip() for chunk in output_chunks)
            if not has_non_empty_output:
                self._emit_progress(
                    progress_callback,
                    "[incident][status] No command output was collected. AI analysis will use target status and errors only.",
                )

            self._emit_progress(progress_callback, "[incident][status] Analyzing collected evidence...")
            try:
                analysis_launch = self._ai_service.request_analysis(
                    AnalysisRequest(
                        run_id=launched_run.run_id,
                        provider_config_id=provider_config.id,
                        trigger_source="incident_mode",
                    )
                )
            except ExternalIntegrationError as exc:
                raise ExternalIntegrationError(f"Incident evidence analysis failed: {exc}") from exc

            analysis_view = self._ai_service.get_analysis(AnalysisQuery(analysis_id=analysis_launch.analysis_id))
            if not analysis_view.evidence:
                self._emit_progress(
                    progress_callback,
                    "[incident][status] Analysis returned no explicit evidence list. Review the summary and next checks.",
                )

            incident_analysis = IncidentAnalysis(
                analysis_id=analysis_view.id,
                run_id=analysis_view.run_id,
                summary=analysis_view.summary,
                probable_root_cause=analysis_view.probable_causes[0] if analysis_view.probable_causes else None,
                evidence=analysis_view.evidence,
                next_checks=analysis_view.next_steps,
                suggested_actions=analysis_view.suggested_actions,
                fix_plan_title=analysis_view.fix_plan_title,
                fix_plan_summary=analysis_view.fix_plan_summary,
                fix_steps=analysis_view.fix_steps,
            )

            completed_session = IncidentSession(
                session_id=session_id,
                title=session_title,
                symptom=symptom,
                category=category.value,
                server_ids=request.server_ids,
                status="completed",
                plan_title=plan_title,
                plan_summary=plan_summary,
                steps=safe_steps,
                skipped_steps=skipped_steps,
                diagnostic_run_id=diagnostic_run_id,
                analysis=incident_analysis,
                created_at=now,
                updated_at=utc_now(),
            )
            self._sessions[session_id] = completed_session
            self._emit_progress(progress_callback, "[incident][status] Investigation complete.")
            return completed_session
        except Exception as exc:
            failed_session = IncidentSession(
                session_id=session_id,
                title=session_title,
                symptom=symptom,
                category=category.value,
                server_ids=request.server_ids,
                status="failed",
                plan_title=plan_title,
                plan_summary=plan_summary,
                steps=safe_steps,
                skipped_steps=skipped_steps,
                diagnostic_run_id=diagnostic_run_id,
                failure_message=str(exc),
                created_at=now,
                updated_at=utc_now(),
            )
            self._sessions[session_id] = failed_session
            self._emit_progress(progress_callback, f"[incident][status] Investigation failed: {exc}")
            raise

    def get_session(self, session_id: str) -> IncidentSession | None:
        return self._sessions.get(session_id)

    def _emit_progress(
        self,
        progress_callback: Callable[[str], None] | None,
        message: str,
    ) -> None:
        if progress_callback is not None:
            progress_callback(message)

    def _resolve_provider_context(self) -> tuple[AIProviderConfig, str | None, AnalysisLanguage]:
        settings = self._settings_repository.get_app_settings()
        provider_config = None
        if settings is not None and settings.default_ai_provider_id:
            provider_config = self._settings_repository.get_provider_config(settings.default_ai_provider_id)
        if provider_config is None:
            for candidate in self._settings_repository.list_provider_configs(include_disabled=False):
                if candidate.is_default:
                    provider_config = candidate
                    break
            if provider_config is None:
                configs = self._settings_repository.list_provider_configs(include_disabled=False)
                provider_config = configs[0] if configs else None
        if provider_config is None:
            raise ValidationError("No AI provider is configured yet. Configure a default provider before using Incident Mode.")
        if not provider_config.is_enabled:
            raise ValidationError("The default AI provider is disabled.")

        provider_name = provider_config.provider_name.strip().lower()
        api_key: str | None = None
        if provider_name in {"openai", "openai_compatible"}:
            if not provider_config.api_key_ref:
                raise ValidationError("The default AI provider does not have a stored API key.")
            api_key = self._secret_store.read_secret(provider_config.api_key_ref)
            if not api_key:
                raise ValidationError("The configured AI provider API key could not be loaded from secure storage.")

        language = settings.analysis_language if settings is not None else AnalysisLanguage.EN
        return provider_config, api_key, language

    def _build_safe_steps(
        self,
        provider_steps: tuple[ProviderFixStepResponse, ...],
    ) -> tuple[tuple[IncidentStep, ...], list[str]]:
        safe_steps: list[IncidentStep] = []
        skipped_steps: list[str] = []
        for index, step in enumerate(provider_steps, start=1):
            try:
                safe_command, requires_sudo = self._validate_incident_step(step)
            except ValidationError as exc:
                skipped_steps.append(f"{step.title}: {exc}")
                continue

            safe_steps.append(
                IncidentStep(
                    step_order=index,
                    title=step.title,
                    command_text=safe_command,
                    target_scope="all",
                    risk_level=step.risk_level,
                    requires_sudo=requires_sudo,
                    requires_tty=step.requires_tty or requires_sudo,
                )
            )
        return tuple(safe_steps), skipped_steps

    def _build_template_fallback_steps(self, template: IncidentRunbookTemplate) -> tuple[IncidentStep, ...]:
        steps: list[IncidentStep] = []
        for index, step in enumerate(template.steps, start=1):
            safe_command, requires_sudo = self._validate_template_step(
                command_text=step.command_text,
                requires_sudo=step.requires_sudo,
            )
            steps.append(
                IncidentStep(
                    step_order=index,
                    title=step.title,
                    command_text=safe_command,
                    target_scope="all",
                    risk_level=step.risk_level,
                    requires_sudo=requires_sudo,
                    requires_tty=step.requires_tty or requires_sudo,
                )
            )
        return tuple(steps)

    def _validate_template_step(self, *, command_text: str, requires_sudo: bool) -> tuple[str, bool]:
        normalized_command = " ".join(command_text.strip().split())
        if not normalized_command:
            raise ValidationError("Incident Mode step command cannot be empty.")
        if normalized_command.lower().startswith("sudo "):
            normalized_command = normalized_command[5:].strip()
            requires_sudo = True
        self._ai_service.validate_action_command(normalized_command)
        for token in self._FORBIDDEN_SHELL_TOKENS:
            if token in normalized_command:
                raise ValidationError(
                    "Incident Mode auto-run commands must be single-shot commands without shell chaining, pipes, or redirects."
                )
        if not any(pattern.search(normalized_command) for pattern, _label in self._ALLOWED_INCIDENT_PATTERNS):
            raise ValidationError(
                "Incident Mode auto-run only allows finite read-only diagnostic commands from the diagnostic allowlist."
            )
        return normalized_command, requires_sudo

    def _validate_incident_step(self, step: ProviderFixStepResponse) -> tuple[str, bool]:
        normalized_scope = step.target_scope.strip().lower()
        if normalized_scope not in {"all", "all hosts", "all servers", "all targets", "*"}:
            raise ValidationError("Incident Mode auto-run steps must target all selected hosts.")

        normalized_command = " ".join(step.command_text.strip().split())
        if not normalized_command:
            raise ValidationError("Incident Mode step command cannot be empty.")

        requires_sudo = step.requires_sudo
        if normalized_command.lower().startswith("sudo "):
            normalized_command = normalized_command[5:].strip()
            requires_sudo = True

        self._ai_service.validate_action_command(normalized_command)
        for token in self._FORBIDDEN_SHELL_TOKENS:
            if token in normalized_command:
                raise ValidationError(
                    "Incident Mode auto-run commands must be single-shot commands without shell chaining, pipes, or redirects."
                )
        if not any(pattern.search(normalized_command) for pattern, _label in self._ALLOWED_INCIDENT_PATTERNS):
            raise ValidationError(
                "Incident Mode auto-run only allows finite read-only diagnostic commands from the diagnostic allowlist."
            )
        return normalized_command, requires_sudo

    def _build_combined_command(
        self,
        *,
        title: str,
        symptom: str,
        steps: tuple[IncidentStep, ...],
    ) -> str:
        lines = [
            "incident_step_failed=0",
            self._printf_line(f"[INCIDENT] {title}"),
            self._printf_line(f"[SYMPTOM] {symptom}"),
            self._printf_line(""),
        ]
        for step in steps:
            lines.append(self._printf_line(f"[STEP {step.step_order}] {step.title}"))
            lines.append(self._printf_line(f"[COMMAND] {step.command_text}"))
            lines.append(f"{step.command_text} || incident_step_failed=1")
            lines.append(self._printf_line(""))
        lines.append("exit $incident_step_failed")
        return "\n".join(lines)

    def _printf_line(self, text: str) -> str:
        return f"printf '%s\\n' {shlex.quote(text)}"
