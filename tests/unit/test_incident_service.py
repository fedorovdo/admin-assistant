from __future__ import annotations

from admin_assistant.core.enums import (
    AIAnalysisStatus,
    AnalysisLanguage,
    ApprovalStatus,
    RiskLevel,
    RunKind,
    RunStatus,
    ShellType,
    StreamType,
)
from admin_assistant.core.errors import ExternalIntegrationError, ValidationError
from admin_assistant.core.time import utc_now
from admin_assistant.modules.ai.dto import (
    AIAnalysisView,
    AIProviderAnalysisResponse,
    AnalysisLaunchResult,
    ProviderFixStepResponse,
    SuggestedActionView,
)
from admin_assistant.modules.execution.dto import OutputChunkDTO
from admin_assistant.modules.incident.dto import IncidentInvestigateRequest
from admin_assistant.modules.incident.prompt_builder import DefaultIncidentPromptBuilder
from admin_assistant.modules.incident.service import DefaultIncidentService
from admin_assistant.modules.settings.models import AIProviderConfig, AppSettings


class FakeSettingsRepository:
    def __init__(self, provider_config: AIProviderConfig) -> None:
        self.provider_config = provider_config
        self.app_settings = AppSettings(
            id="app-settings",
            default_ai_provider_id=provider_config.id,
            analysis_language=AnalysisLanguage.EN,
        )

    def get_app_settings(self) -> AppSettings:
        return self.app_settings

    def get_provider_config(self, provider_config_id: str) -> AIProviderConfig | None:
        return self.provider_config if provider_config_id == self.provider_config.id else None

    def list_provider_configs(self, include_disabled: bool = True) -> tuple[AIProviderConfig, ...]:
        if not include_disabled and not self.provider_config.is_enabled:
            return ()
        return (self.provider_config,)


class MemorySecretStore:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def read_secret(self, key: str) -> str | None:
        return self.values.get(key)


class QueuedProviderClient:
    def __init__(self, responses: list[AIProviderAnalysisResponse]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []
        self.models: list[str] = []
        self.api_keys: list[str | None] = []

    def analyze(self, prompt: str, provider_config: AIProviderConfig, api_key: str | None = None):
        self.prompts.append(prompt)
        self.models.append(provider_config.model_name)
        self.api_keys.append(api_key)
        if not self._responses:
            raise AssertionError("No queued provider response left.")
        return self._responses.pop(0)


class FakeExecutionService:
    def __init__(
        self,
        *,
        status: RunStatus = RunStatus.FAILED,
        target_statuses: tuple[RunStatus, ...] = (RunStatus.SUCCEEDED, RunStatus.FAILED),
        output_chunks: tuple[OutputChunkDTO, ...] | None = None,
    ) -> None:
        self.requests = []
        self.status = status
        self.target_statuses = target_statuses
        self.output_chunks = output_chunks or ()

    def start_run(self, request):
        from admin_assistant.modules.execution.dto import RunLaunchResult

        self.requests.append(request)
        return RunLaunchResult(run_id="incident-run-1", status=self.status)

    def get_run_status(self, query):
        from admin_assistant.modules.execution.dto import RunStatusSnapshot, TargetResultView

        return RunStatusSnapshot(
            run_id=query.run_id,
            status=self.status,
            targets=tuple(
                TargetResultView(
                    id=f"target-{index}",
                    server_id=f"server-{index}",
                    server_name=f"host-{index}",
                    status=target_status,
                    exit_code=0 if target_status is RunStatus.SUCCEEDED else 1,
                    error_message=None if target_status is RunStatus.SUCCEEDED else "command failed",
                )
                for index, target_status in enumerate(self.target_statuses, start=1)
            ),
        )

    def list_run_output(self, query):
        return self.output_chunks


class FakeAIAnalysisService:
    def __init__(self, *, evidence: tuple[str, ...] = ("df -h showed / at 98%", "journalctl reported disk pressure warnings")) -> None:
        self.validated_commands: list[str] = []
        self.requested_analyses: list[object] = []
        self.analysis = AIAnalysisView(
            id="analysis-incident-1",
            run_id="incident-run-1",
            provider_config_id="provider-1",
            status=AIAnalysisStatus.COMPLETED,
            summary="Disk pressure caused the alert.",
            probable_causes=("The root filesystem is nearly full.",),
            evidence=evidence,
            next_steps=("Review large files in /var/log",),
            suggested_actions=(
                SuggestedActionView(
                    id="action-1",
                    analysis_id="analysis-incident-1",
                    title="Check disk usage in /var/log",
                    command_text="du -sh /var/log/*",
                    target_scope="all",
                    risk_level=RiskLevel.SAFE,
                    approval_status=ApprovalStatus.PENDING,
                    created_at=utc_now(),
                ),
            ),
            fix_plan_title="Disk remediation plan",
            fix_plan_summary="Clean up large log files carefully.",
            fix_steps=(),
            created_at=utc_now(),
        )

    def validate_action_command(self, command_text: str) -> None:
        self.validated_commands.append(command_text)

    def request_analysis(self, request):
        self.requested_analyses.append(request)
        return AnalysisLaunchResult(
            analysis_id=self.analysis.id,
            status=AIAnalysisStatus.COMPLETED,
        )

    def get_analysis(self, query):
        return self.analysis


class RaisingProviderClient:
    def analyze(self, prompt: str, provider_config: AIProviderConfig, api_key: str | None = None):
        raise ExternalIntegrationError("timed out")


def test_incident_service_runs_safe_diagnostic_plan_and_returns_final_analysis() -> None:
    provider_config = AIProviderConfig(
        id="provider-1",
        provider_name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4o-mini",
        api_key_ref="openai-key",
        is_default=True,
        is_enabled=True,
    )
    provider = QueuedProviderClient(
        [
            AIProviderAnalysisResponse(
                summary="Collect quick disk evidence.",
                probable_causes=("Disk space may be low.",),
                fix_plan_title="Incident diagnostics",
                fix_plan_summary="Capture fast disk and process evidence.",
                fix_steps=(
                    ProviderFixStepResponse(
                        title="Check disk usage",
                        command_text="df -h",
                        target_scope="all",
                        risk_level=RiskLevel.SAFE,
                    ),
                    ProviderFixStepResponse(
                        title="Check memory",
                        command_text="free -h",
                        target_scope="all",
                        risk_level=RiskLevel.SAFE,
                    ),
                    ProviderFixStepResponse(
                        title="Unsafe interactive monitor",
                        command_text="top",
                        target_scope="all",
                        risk_level=RiskLevel.WARNING,
                    ),
                ),
            )
        ]
    )
    output_chunk = OutputChunkDTO(
        target_result_id="target-1",
        seq_no=1,
        stream=StreamType.STDOUT,
        chunk_text="Filesystem      Size Used Avail Use%\n/dev/sda1        40G  39G  1G  98%\n",
        created_at=utc_now(),
    )
    execution_service = FakeExecutionService(
        status=RunStatus.FAILED,
        target_statuses=(RunStatus.SUCCEEDED, RunStatus.FAILED),
        output_chunks=(output_chunk,),
    )
    ai_service = FakeAIAnalysisService()
    service = DefaultIncidentService(
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=provider,
        prompt_builder=DefaultIncidentPromptBuilder(),
        execution_service=execution_service,
        ai_service=ai_service,
    )
    progress_messages: list[str] = []

    session = service.investigate(
        IncidentInvestigateRequest(
            title="High disk usage",
            symptom="Users report disk pressure alerts on the web tier.",
            server_ids=("server-1", "server-2"),
            shell_type=ShellType.SH,
            initiated_by="operator",
        ),
        progress_messages.append,
    )

    assert session.status == "completed"
    assert session.category == "disk"
    assert session.plan_title == "Incident diagnostics"
    assert len(session.steps) == 2
    assert session.steps[0].command_text == "df -h"
    assert session.steps[1].command_text == "free -h"
    assert session.skipped_steps
    assert "Unsafe interactive monitor" in session.skipped_steps[0]
    assert execution_service.requests
    request = execution_service.requests[0]
    assert request.run_kind is RunKind.COMMAND
    assert request.server_ids == ("server-1", "server-2")
    assert request.shell_type is ShellType.SH
    assert "[INCIDENT] High disk usage" in request.command_text
    assert "[STEP 1] Check disk usage" in request.command_text
    assert "df -h || incident_step_failed=1" in request.command_text
    assert "top" not in request.command_text
    assert ai_service.requested_analyses
    assert ai_service.requested_analyses[0].run_id == "incident-run-1"
    assert ai_service.requested_analyses[0].provider_config_id == "provider-1"
    assert ai_service.requested_analyses[0].trigger_source == "incident_mode"
    assert session.analysis is not None
    assert session.analysis.summary == "Disk pressure caused the alert."
    assert session.analysis.probable_root_cause == "The root filesystem is nearly full."
    assert session.analysis.evidence == (
        "df -h showed / at 98%",
        "journalctl reported disk pressure warnings",
    )
    assert progress_messages[0] == "[incident][status] Using incident runbook template: disk."
    assert progress_messages[1] == "[incident][status] Generating investigation plan..."
    assert "[incident][status] Filtered out 1 unsafe or unsupported incident step(s)." in progress_messages
    assert "[incident][status] Running 2 safe diagnostic step(s)..." in progress_messages
    assert any("Diagnostic run completed with failures on 1/2 target(s)" in message for message in progress_messages)
    assert "[incident][status] Analyzing collected evidence..." in progress_messages
    assert progress_messages[-1] == "[incident][status] Investigation complete."
    assert provider.prompts
    assert "Likely incident category: disk" in provider.prompts[0]
    assert "Preferred baseline runbook: Disk pressure diagnostics" in provider.prompts[0]
    assert "command_text=df -h" in provider.prompts[0]


def test_incident_service_falls_back_to_runbook_template_when_ai_plan_is_unsafe() -> None:
    provider_config = AIProviderConfig(
        id="provider-1",
        provider_name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4o-mini",
        api_key_ref="openai-key",
        is_default=True,
        is_enabled=True,
    )
    provider = QueuedProviderClient(
        [
            AIProviderAnalysisResponse(
                summary="Plan",
                fix_plan_title="Unsafe plan",
                fix_plan_summary="Contains only unsafe commands.",
                fix_steps=(
                    ProviderFixStepResponse(
                        title="Restart sshd",
                        command_text="systemctl restart sshd",
                        target_scope="all",
                        risk_level=RiskLevel.WARNING,
                    ),
                ),
            )
        ]
    )
    service = DefaultIncidentService(
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=provider,
        prompt_builder=DefaultIncidentPromptBuilder(),
        execution_service=FakeExecutionService(),
        ai_service=FakeAIAnalysisService(),
    )
    progress_messages: list[str] = []

    session = service.investigate(
        IncidentInvestigateRequest(
            symptom="SSH is failing.",
            server_ids=("server-1",),
        ),
        progress_messages.append,
    )

    assert session.status == "completed"
    assert session.category == "ssh"
    assert session.steps
    assert session.steps[0].command_text == "systemctl status sshd --no-pager"
    assert progress_messages[0] == "[incident][status] Using incident runbook template: ssh."
    assert progress_messages[1] == "[incident][status] Generating investigation plan..."
    assert any("Filtered out 1 unsafe or unsupported incident step(s)." in message for message in progress_messages)
    assert "[incident][status] Falling back to the built-in ssh runbook template." in progress_messages
    assert progress_messages[-1] == "[incident][status] Investigation complete."


def test_incident_service_reports_missing_output_and_empty_evidence_cleanly() -> None:
    provider_config = AIProviderConfig(
        id="provider-1",
        provider_name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4o-mini",
        api_key_ref="openai-key",
        is_default=True,
        is_enabled=True,
    )
    provider = QueuedProviderClient(
        [
            AIProviderAnalysisResponse(
                summary="Collect SSH evidence.",
                fix_plan_title="SSH diagnostics",
                fix_plan_summary="Check service state safely.",
                fix_steps=(
                    ProviderFixStepResponse(
                        title="Check sshd status",
                        command_text="systemctl status sshd --no-pager",
                        target_scope="all",
                        risk_level=RiskLevel.SAFE,
                    ),
                ),
            )
        ]
    )
    execution_service = FakeExecutionService(
        status=RunStatus.FAILED,
        target_statuses=(RunStatus.FAILED,),
        output_chunks=(),
    )
    ai_service = FakeAIAnalysisService(evidence=())
    service = DefaultIncidentService(
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=provider,
        prompt_builder=DefaultIncidentPromptBuilder(),
        execution_service=execution_service,
        ai_service=ai_service,
    )
    progress_messages: list[str] = []

    session = service.investigate(
        IncidentInvestigateRequest(
            symptom="SSH login attempts fail.",
            server_ids=("server-1",),
        ),
        progress_messages.append,
    )

    assert session.analysis is not None
    assert session.analysis.evidence == ()
    assert "[incident][status] No command output was collected. AI analysis will use target status and errors only." in progress_messages
    assert "[incident][status] Analysis returned no explicit evidence list. Review the summary and next checks." in progress_messages


def test_incident_service_wraps_provider_timeout_during_plan_generation() -> None:
    provider_config = AIProviderConfig(
        id="provider-1",
        provider_name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4o-mini",
        api_key_ref="openai-key",
        is_default=True,
        is_enabled=True,
    )
    service = DefaultIncidentService(
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=RaisingProviderClient(),
        prompt_builder=DefaultIncidentPromptBuilder(),
        execution_service=FakeExecutionService(),
        ai_service=FakeAIAnalysisService(),
    )

    try:
        service.investigate(
            IncidentInvestigateRequest(
                symptom="Service is timing out.",
                server_ids=("server-1",),
            )
        )
    except ExternalIntegrationError as exc:
        assert str(exc).startswith("Incident plan generation failed:")
        assert "timed out" in str(exc)
    else:  # pragma: no cover - defensive failure path
        raise AssertionError("Expected ExternalIntegrationError for provider timeout.")
