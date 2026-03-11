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
from admin_assistant.core.errors import ValidationError
from admin_assistant.core.time import utc_now
from admin_assistant.modules.ai.dto import (
    AIProviderAnalysisResponse,
    AnalysisQuery,
    AnalysisRequest,
    ExecuteSuggestedActionRequest,
    ProviderFixStepResponse,
    ProviderSuggestedActionResponse,
    SuggestedActionApprovalRequest,
    SuggestedActionRejectionRequest,
)
from admin_assistant.modules.ai.models import AIAnalysis, AISuggestedAction
from admin_assistant.modules.ai.prompt_builder import DefaultPromptBuilder
from admin_assistant.modules.ai.service import DefaultAIAnalysisService
from admin_assistant.modules.execution.dto import OutputChunkDTO
from admin_assistant.modules.execution.models import RunTargetResult, ScriptRun
from admin_assistant.modules.settings.models import AIProviderConfig, AppSettings


class InMemoryAIRepository:
    def __init__(self) -> None:
        self.analyses: dict[str, AIAnalysis] = {}
        self.actions_by_analysis: dict[str, tuple[AISuggestedAction, ...]] = {}

    def create_analysis(self, analysis: AIAnalysis) -> AIAnalysis:
        self.analyses[analysis.id] = analysis
        return analysis

    def create_suggested_actions(
        self,
        actions: tuple[AISuggestedAction, ...],
    ) -> tuple[AISuggestedAction, ...]:
        if actions:
            self.actions_by_analysis[actions[0].analysis_id] = actions
        return actions

    def get_analysis(self, analysis_id: str) -> AIAnalysis | None:
        return self.analyses.get(analysis_id)

    def get_suggested_action(self, action_id: str) -> AISuggestedAction | None:
        for actions in self.actions_by_analysis.values():
            for action in actions:
                if action.id == action_id:
                    return action
        return None

    def list_suggested_actions(self, analysis_id: str) -> tuple[AISuggestedAction, ...]:
        return self.actions_by_analysis.get(analysis_id, ())

    def update_suggested_action(self, action: AISuggestedAction) -> AISuggestedAction:
        actions = list(self.actions_by_analysis.get(action.analysis_id, ()))
        for index, existing in enumerate(actions):
            if existing.id == action.id:
                actions[index] = action
                self.actions_by_analysis[action.analysis_id] = tuple(actions)
                return action
        raise KeyError(action.id)


class FakeRunReader:
    def __init__(
        self,
        script_run: ScriptRun,
        targets: tuple[RunTargetResult, ...],
        chunks: tuple[OutputChunkDTO, ...],
    ) -> None:
        self.script_run = script_run
        self.targets = targets
        self.chunks = chunks

    def get_run(self, run_id: str) -> ScriptRun | None:
        return self.script_run if self.script_run.id == run_id else None

    def list_target_results(self, run_id: str) -> tuple[RunTargetResult, ...]:
        return self.targets if self.script_run.id == run_id else ()

    def list_output_chunks(self, run_id: str) -> tuple[OutputChunkDTO, ...]:
        return self.chunks if self.script_run.id == run_id else ()


class FakeSettingsRepository:
    def __init__(
        self,
        provider_config: AIProviderConfig,
        analysis_language: AnalysisLanguage = AnalysisLanguage.EN,
    ) -> None:
        self.provider_config = provider_config
        self.app_settings = AppSettings(id="app-settings", analysis_language=analysis_language)

    def get_provider_config(self, provider_config_id: str) -> AIProviderConfig | None:
        return self.provider_config if self.provider_config.id == provider_config_id else None

    def get_app_settings(self) -> AppSettings:
        return self.app_settings


class MemorySecretStore:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def read_secret(self, key: str) -> str | None:
        return self.values.get(key)

    def save_secret(self, key: str, value: str) -> str:
        self.values[key] = value
        return key

    def delete_secret(self, key: str) -> None:
        self.values.pop(key, None)


class FakeProviderClient:
    def __init__(self, response: AIProviderAnalysisResponse) -> None:
        self.response = response
        self.last_prompt: str | None = None
        self.last_api_key: str | None = None
        self.last_model: str | None = None

    def analyze(
        self,
        prompt: str,
        provider_config: AIProviderConfig,
        api_key: str | None = None,
    ) -> AIProviderAnalysisResponse:
        self.last_prompt = prompt
        self.last_api_key = api_key
        self.last_model = provider_config.model_name
        return self.response


class NullRunLauncher:
    def start_run(self, request):
        raise NotImplementedError


class FakeRunLauncher:
    def __init__(self) -> None:
        self.last_request = None

    def start_run(self, request):
        from admin_assistant.modules.execution.dto import RunLaunchResult

        self.last_request = request
        return RunLaunchResult(run_id="run-executed-1", status=RunStatus.SUCCEEDED)


def test_ai_analysis_service_creates_analysis_for_completed_run() -> None:
    completed_run = ScriptRun(
        id="run-1",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="systemctl status nginx",
        shell_type=ShellType.BASH,
        started_at=utc_now(),
        completed_at=utc_now(),
    )
    target = RunTargetResult(
        id="target-1",
        run_id="run-1",
        server_id="server-1",
        server_snapshot={"name": "web-01"},
        status=RunStatus.FAILED,
        exit_code=3,
        error_message="nginx failed",
    )
    output_chunk = OutputChunkDTO(
        target_result_id="target-1",
        seq_no=1,
        stream=StreamType.STDERR,
        chunk_text="nginx: service failed\n",
        created_at=utc_now(),
    )
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
    provider = FakeProviderClient(
        AIProviderAnalysisResponse(
            summary="Nginx is failing to start.",
            probable_causes=("Invalid nginx configuration",),
            evidence=("nginx -t reported a syntax error",),
            next_steps=("Review nginx config syntax", "Check nginx error logs"),
            suggested_actions=(
                ProviderSuggestedActionResponse(
                    title="Validate nginx config",
                    command_text="nginx -t",
                    target_scope="web-01",
                    risk_level=RiskLevel.SAFE,
                ),
            ),
        )
    )
    service = DefaultAIAnalysisService(
        repository=InMemoryAIRepository(),
        run_reader=FakeRunReader(completed_run, (target,), (output_chunk,)),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=provider,
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=NullRunLauncher(),
        publish_event=lambda event: None,
    )

    launch = service.request_analysis(
        AnalysisRequest(
            run_id="run-1",
            provider_config_id="provider-1",
        )
    )
    analysis = service.get_analysis(AnalysisQuery(analysis_id=launch.analysis_id))

    assert launch.status is AIAnalysisStatus.COMPLETED
    assert provider.last_api_key == "sk-test"
    assert provider.last_model == "gpt-4o-mini"
    assert provider.last_prompt is not None
    assert "web-01" in provider.last_prompt
    assert "nginx: service failed" in provider.last_prompt
    assert analysis.summary == "Nginx is failing to start."
    assert analysis.probable_causes == ("Invalid nginx configuration",)
    assert analysis.evidence == ("nginx -t reported a syntax error",)
    assert analysis.next_steps == ("Review nginx config syntax", "Check nginx error logs")
    assert len(analysis.suggested_actions) == 1
    assert analysis.suggested_actions[0].approval_status is ApprovalStatus.PENDING
    assert analysis.suggested_actions[0].risk_level is RiskLevel.SAFE


def test_ai_analysis_service_persists_fix_plan_steps() -> None:
    completed_run = ScriptRun(
        id="run-fix-1",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="systemctl status sshd --no-pager",
        shell_type=ShellType.BASH,
        started_at=utc_now(),
        completed_at=utc_now(),
    )
    target = RunTargetResult(
        id="target-fix-1",
        run_id="run-fix-1",
        server_id="server-1",
        server_snapshot={"name": "web-01", "host": "192.0.2.10"},
        status=RunStatus.FAILED,
        exit_code=1,
    )
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
    provider = FakeProviderClient(
        AIProviderAnalysisResponse(
            summary="SSHD is unhealthy.",
            fix_plan_title="Repair SSH access",
            fix_plan_summary="Check service health first, then restart the daemon if needed.",
            fix_steps=(
                ProviderFixStepResponse(
                    title="Inspect SSH logs",
                    command_text="journalctl -u sshd -n 50 --no-pager",
                    target_scope="web-01",
                    risk_level=RiskLevel.SAFE,
                ),
                ProviderFixStepResponse(
                    title="Restart SSH daemon",
                    command_text="sshd -t",
                    target_scope="web-01",
                    risk_level=RiskLevel.WARNING,
                    requires_sudo=True,
                    requires_tty=True,
                ),
            ),
        )
    )
    service = DefaultAIAnalysisService(
        repository=InMemoryAIRepository(),
        run_reader=FakeRunReader(completed_run, (target,), ()),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=provider,
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=NullRunLauncher(),
        publish_event=lambda event: None,
    )

    launch = service.request_analysis(
        AnalysisRequest(run_id="run-fix-1", provider_config_id="provider-1")
    )
    analysis = service.get_analysis(AnalysisQuery(analysis_id=launch.analysis_id))

    assert analysis.fix_plan_title == "Repair SSH access"
    assert analysis.fix_plan_summary == "Check service health first, then restart the daemon if needed."
    assert analysis.suggested_actions == ()
    assert len(analysis.fix_steps) == 2
    assert tuple(step.step_order for step in analysis.fix_steps) == (1, 2)
    assert analysis.fix_steps[0].title == "Inspect SSH logs"
    assert analysis.fix_steps[0].command_text == "journalctl -u sshd -n 50 --no-pager"
    assert analysis.fix_steps[0].target_scope == "server-1"
    assert analysis.fix_steps[0].requires_sudo is False
    assert analysis.fix_steps[1].title == "Restart SSH daemon"
    assert analysis.fix_steps[1].command_text == "sshd -t"
    assert analysis.fix_steps[1].requires_sudo is True
    assert analysis.fix_steps[1].requires_tty is True


def test_ai_analysis_service_builds_russian_prompt_when_language_is_ru() -> None:
    completed_run = ScriptRun(
        id="run-ru-1",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="df -h",
        shell_type=ShellType.BASH,
        started_at=utc_now(),
        completed_at=utc_now(),
    )
    target = RunTargetResult(
        id="target-ru-1",
        run_id="run-ru-1",
        server_id="server-1",
        server_snapshot={"name": "db-01"},
        status=RunStatus.FAILED,
        exit_code=1,
    )
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
    provider = FakeProviderClient(AIProviderAnalysisResponse(summary="ok"))
    service = DefaultAIAnalysisService(
        repository=InMemoryAIRepository(),
        run_reader=FakeRunReader(completed_run, (target,), ()),
        settings_repository=FakeSettingsRepository(provider_config, analysis_language=AnalysisLanguage.RU),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=provider,
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=NullRunLauncher(),
        publish_event=lambda event: None,
    )

    service.request_analysis(
        AnalysisRequest(
            run_id="run-ru-1",
            provider_config_id="provider-1",
        )
    )

    assert provider.last_prompt is not None
    assert "Respond in Russian" in provider.last_prompt
    assert "must not be translated" in provider.last_prompt
    assert "- evidence: array of concrete findings from the collected output that support the analysis" in provider.last_prompt
    assert "target_scope is a machine-readable internal field and must not be translated" in provider.last_prompt
    assert "fix_plan_title" in provider.last_prompt
    assert "requires_sudo and requires_tty are machine-readable booleans and must not be translated" in provider.last_prompt
    assert "Forbidden command patterns include: top, htop, watch, tail -f" in provider.last_prompt
    assert "Do not return nested remote-access commands such as ssh, scp, or sftp." in provider.last_prompt
    assert "Do not return executable commands that directly modify /etc/ssh/sshd_config." in provider.last_prompt
    assert "Do not return executable commands that restart or reload ssh or sshd." in provider.last_prompt
    assert "If remediation is needed for SSH configuration, describe it in next_steps as a manual human-reviewed step" in provider.last_prompt
    assert "journalctl -n 50 --no-pager" in provider.last_prompt
    assert "systemctl status <service> --no-pager" in provider.last_prompt


def test_ai_analysis_service_supports_ollama_without_api_key() -> None:
    completed_run = ScriptRun(
        id="run-ollama-1",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="journalctl -u sshd -n 50",
        shell_type=ShellType.BASH,
        started_at=utc_now(),
        completed_at=utc_now(),
    )
    target = RunTargetResult(
        id="target-ollama-1",
        run_id="run-ollama-1",
        server_id="server-1",
        server_snapshot={"name": "web-01"},
        status=RunStatus.FAILED,
        exit_code=1,
    )
    provider_config = AIProviderConfig(
        id="provider-ollama-1",
        provider_name="ollama",
        display_name="Ollama",
        base_url="http://localhost:11434",
        model_name="llama3",
        api_key_ref=None,
        is_default=True,
        is_enabled=True,
    )
    provider = FakeProviderClient(AIProviderAnalysisResponse(summary="Local analysis"))
    service = DefaultAIAnalysisService(
        repository=InMemoryAIRepository(),
        run_reader=FakeRunReader(completed_run, (target,), ()),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({}),
        provider_client=provider,
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=NullRunLauncher(),
        publish_event=lambda event: None,
    )

    launch = service.request_analysis(
        AnalysisRequest(
            run_id="run-ollama-1",
            provider_config_id="provider-ollama-1",
        )
    )

    assert launch.status is AIAnalysisStatus.COMPLETED
    assert provider.last_model == "llama3"
    assert provider.last_api_key is None


def test_ai_analysis_service_filters_unsafe_generated_commands() -> None:
    completed_run = ScriptRun(
        id="run-unsafe-1",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="systemctl status sshd --no-pager",
        shell_type=ShellType.BASH,
        started_at=utc_now(),
        completed_at=utc_now(),
    )
    target = RunTargetResult(
        id="target-unsafe-1",
        run_id="run-unsafe-1",
        server_id="server-1",
        server_snapshot={"name": "web-01", "host": "192.0.2.10"},
        status=RunStatus.FAILED,
        exit_code=1,
    )
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
    provider = FakeProviderClient(
        AIProviderAnalysisResponse(
            summary="Unsafe commands were suggested.",
            suggested_actions=(
                ProviderSuggestedActionResponse(
                    title="Monitor load interactively",
                    command_text="top",
                    target_scope="web-01",
                    risk_level=RiskLevel.SAFE,
                ),
                ProviderSuggestedActionResponse(
                    title="SSH to another host",
                    command_text="ssh admin@192.0.2.15",
                    target_scope="web-01",
                    risk_level=RiskLevel.WARNING,
                ),
                ProviderSuggestedActionResponse(
                    title="Check SSH logs safely",
                    command_text="journalctl -u sshd -n 50 --no-pager",
                    target_scope="web-01",
                    risk_level=RiskLevel.SAFE,
                ),
            ),
            fix_steps=(
                ProviderFixStepResponse(
                    title="Follow logs forever",
                    command_text="journalctl -u sshd -f",
                    target_scope="web-01",
                    risk_level=RiskLevel.WARNING,
                ),
            ),
        )
    )
    service = DefaultAIAnalysisService(
        repository=InMemoryAIRepository(),
        run_reader=FakeRunReader(completed_run, (target,), ()),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=provider,
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=NullRunLauncher(),
        publish_event=lambda event: None,
    )

    launch = service.request_analysis(
        AnalysisRequest(run_id="run-unsafe-1", provider_config_id="provider-1")
    )
    analysis = service.get_analysis(AnalysisQuery(analysis_id=launch.analysis_id))

    assert len(analysis.suggested_actions) == 1
    assert analysis.suggested_actions[0].command_text == "journalctl -u sshd -n 50 --no-pager"
    assert analysis.fix_steps == ()


def test_ai_analysis_service_filters_risky_ssh_remediation_commands() -> None:
    completed_run = ScriptRun(
        id="run-ssh-risk-1",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="systemctl status sshd --no-pager",
        shell_type=ShellType.BASH,
        started_at=utc_now(),
        completed_at=utc_now(),
    )
    target = RunTargetResult(
        id="target-ssh-risk-1",
        run_id="run-ssh-risk-1",
        server_id="server-1",
        server_snapshot={"name": "web-01", "host": "192.0.2.10"},
        status=RunStatus.FAILED,
        exit_code=1,
    )
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
    provider = FakeProviderClient(
        AIProviderAnalysisResponse(
            summary="SSHD likely has a configuration issue.",
            suggested_actions=(
                ProviderSuggestedActionResponse(
                    title="Inspect sshd_config safely",
                    command_text="grep -E '^(PasswordAuthentication|PermitRootLogin|PubkeyAuthentication)' /etc/ssh/sshd_config",
                    target_scope="web-01",
                    risk_level=RiskLevel.SAFE,
                ),
                ProviderSuggestedActionResponse(
                    title="Patch sshd_config directly",
                    command_text="sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config",
                    target_scope="web-01",
                    risk_level=RiskLevel.DANGER,
                ),
            ),
            fix_steps=(
                ProviderFixStepResponse(
                    title="Restart SSH daemon",
                    command_text="systemctl restart sshd",
                    target_scope="web-01",
                    risk_level=RiskLevel.WARNING,
                    requires_sudo=True,
                    requires_tty=True,
                ),
            ),
        )
    )
    service = DefaultAIAnalysisService(
        repository=InMemoryAIRepository(),
        run_reader=FakeRunReader(completed_run, (target,), ()),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=provider,
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=NullRunLauncher(),
        publish_event=lambda event: None,
    )

    launch = service.request_analysis(
        AnalysisRequest(run_id="run-ssh-risk-1", provider_config_id="provider-1")
    )
    analysis = service.get_analysis(AnalysisQuery(analysis_id=launch.analysis_id))

    assert len(analysis.suggested_actions) == 1
    assert analysis.suggested_actions[0].command_text.startswith("grep -E")
    assert analysis.fix_steps == ()


def test_ai_analysis_service_keeps_localized_titles_but_canonicalizes_target_scope() -> None:
    completed_run = ScriptRun(
        id="run-ru-2",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="systemctl status sshd",
        shell_type=ShellType.BASH,
        started_at=utc_now(),
        completed_at=utc_now(),
    )
    target = RunTargetResult(
        id="target-ru-2",
        run_id="run-ru-2",
        server_id="server-1",
        server_snapshot={"name": "web-01", "host": "192.0.2.10"},
        status=RunStatus.FAILED,
        exit_code=1,
    )
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
    provider = FakeProviderClient(
        AIProviderAnalysisResponse(
            summary="Служба SSH не запущена.",
            probable_causes=("Ошибка конфигурации",),
            next_steps=("Проверить журнал SSH",),
            suggested_actions=(
                ProviderSuggestedActionResponse(
                    title="Проверить журналы SSH",
                    command_text="journalctl -u sshd -n 50 --no-pager",
                    target_scope="сервер web-01",
                    risk_level=RiskLevel.WARNING,
                ),
            ),
        )
    )
    service = DefaultAIAnalysisService(
        repository=InMemoryAIRepository(),
        run_reader=FakeRunReader(completed_run, (target,), ()),
        settings_repository=FakeSettingsRepository(provider_config, analysis_language=AnalysisLanguage.RU),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=provider,
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=NullRunLauncher(),
        publish_event=lambda event: None,
    )

    launch = service.request_analysis(
        AnalysisRequest(
            run_id="run-ru-2",
            provider_config_id="provider-1",
        )
    )
    analysis = service.get_analysis(AnalysisQuery(analysis_id=launch.analysis_id))

    assert len(analysis.suggested_actions) == 1
    action = analysis.suggested_actions[0]
    assert action.title == "Проверить журналы SSH"
    assert action.command_text == "journalctl -u sshd -n 50 --no-pager"
    assert action.target_scope == "server-1"
    assert action.risk_level is RiskLevel.WARNING


def test_ai_analysis_service_canonicalizes_russian_all_hosts_scope() -> None:
    completed_run = ScriptRun(
        id="run-ru-3",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="df -h",
        shell_type=ShellType.BASH,
        started_at=utc_now(),
        completed_at=utc_now(),
    )
    targets = (
        RunTargetResult(
            id="target-a",
            run_id="run-ru-3",
            server_id="server-a",
            server_snapshot={"name": "web-01", "host": "192.0.2.10"},
            status=RunStatus.FAILED,
            exit_code=1,
        ),
        RunTargetResult(
            id="target-b",
            run_id="run-ru-3",
            server_id="server-b",
            server_snapshot={"name": "web-02", "host": "192.0.2.11"},
            status=RunStatus.FAILED,
            exit_code=1,
        ),
    )
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
    provider = FakeProviderClient(
        AIProviderAnalysisResponse(
            summary="Недостаточно места на диске.",
            suggested_actions=(
                ProviderSuggestedActionResponse(
                    title="Проверить использование диска",
                    command_text="df -h",
                    target_scope="все хосты",
                    risk_level=RiskLevel.SAFE,
                ),
            ),
        )
    )
    service = DefaultAIAnalysisService(
        repository=InMemoryAIRepository(),
        run_reader=FakeRunReader(completed_run, targets, ()),
        settings_repository=FakeSettingsRepository(provider_config, analysis_language=AnalysisLanguage.RU),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=provider,
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=NullRunLauncher(),
        publish_event=lambda event: None,
    )

    launch = service.request_analysis(
        AnalysisRequest(
            run_id="run-ru-3",
            provider_config_id="provider-1",
        )
    )
    analysis = service.get_analysis(AnalysisQuery(analysis_id=launch.analysis_id))

    assert len(analysis.suggested_actions) == 1
    assert analysis.suggested_actions[0].title == "Проверить использование диска"
    assert analysis.suggested_actions[0].target_scope == "all"


def test_ai_analysis_service_rejects_incomplete_run() -> None:
    running_run = ScriptRun(
        id="run-2",
        run_kind=RunKind.COMMAND,
        status=RunStatus.RUNNING,
        command_snapshot="tail -f /var/log/syslog",
        shell_type=ShellType.BASH,
        started_at=utc_now(),
    )
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
    service = DefaultAIAnalysisService(
        repository=InMemoryAIRepository(),
        run_reader=FakeRunReader(running_run, (), ()),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=FakeProviderClient(AIProviderAnalysisResponse(summary="unused")),
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=NullRunLauncher(),
        publish_event=lambda event: None,
    )

    try:
        service.request_analysis(AnalysisRequest(run_id="run-2", provider_config_id="provider-1"))
    except ValidationError as exc:
        assert "completed runs" in str(exc)
    else:  # pragma: no cover - defensive failure path
        raise AssertionError("Expected ValidationError for incomplete run analysis.")


def test_ai_analysis_service_approves_suggested_action() -> None:
    repository = InMemoryAIRepository()
    action = AISuggestedAction(
        id="action-1",
        analysis_id="analysis-1",
        title="Restart nginx",
        command_text="systemctl restart nginx",
        target_scope="web-01",
        risk_level=RiskLevel.WARNING,
        approval_status=ApprovalStatus.PENDING,
        created_at=utc_now(),
    )
    repository.actions_by_analysis["analysis-1"] = (action,)

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
    service = DefaultAIAnalysisService(
        repository=repository,
        run_reader=FakeRunReader(
            ScriptRun(id="run-1", run_kind=RunKind.COMMAND, status=RunStatus.SUCCEEDED),
            (),
            (),
        ),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=FakeProviderClient(AIProviderAnalysisResponse(summary="unused")),
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=NullRunLauncher(),
        publish_event=lambda event: None,
    )

    approved = service.approve_action(
        SuggestedActionApprovalRequest(action_id="action-1", approved_by="user")
    )

    assert approved.approval_status is ApprovalStatus.APPROVED
    assert approved.approved_at is not None
    assert approved.rejected_at is None
    stored = repository.get_suggested_action("action-1")
    assert stored is not None
    assert stored.approval_status is ApprovalStatus.APPROVED


def test_ai_analysis_service_rejects_suggested_action() -> None:
    repository = InMemoryAIRepository()
    action = AISuggestedAction(
        id="action-2",
        analysis_id="analysis-2",
        title="Delete temp files",
        command_text="rm -rf /tmp/app-cache",
        target_scope="web-02",
        risk_level=RiskLevel.DANGER,
        approval_status=ApprovalStatus.PENDING,
        created_at=utc_now(),
    )
    repository.actions_by_analysis["analysis-2"] = (action,)

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
    service = DefaultAIAnalysisService(
        repository=repository,
        run_reader=FakeRunReader(
            ScriptRun(id="run-1", run_kind=RunKind.COMMAND, status=RunStatus.SUCCEEDED),
            (),
            (),
        ),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=FakeProviderClient(AIProviderAnalysisResponse(summary="unused")),
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=NullRunLauncher(),
        publish_event=lambda event: None,
    )

    rejected = service.reject_action(
        SuggestedActionRejectionRequest(action_id="action-2", rejected_by="user")
    )

    assert rejected.approval_status is ApprovalStatus.REJECTED
    assert rejected.rejected_at is not None
    assert rejected.approved_at is None
    stored = repository.get_suggested_action("action-2")
    assert stored is not None
    assert stored.approval_status is ApprovalStatus.REJECTED


def test_ai_analysis_service_executes_approved_action_as_new_run() -> None:
    repository = InMemoryAIRepository()
    repository.analyses["analysis-3"] = AIAnalysis(
        id="analysis-3",
        run_id="run-source-1",
        provider_config_id="provider-1",
        status=AIAnalysisStatus.COMPLETED,
        summary="source analysis",
        created_at=utc_now(),
    )
    action = AISuggestedAction(
        id="action-3",
        analysis_id="analysis-3",
        title="Check SSH logs",
        command_text="journalctl -u sshd -n 50 --no-pager",
        target_scope="web-01",
        risk_level=RiskLevel.WARNING,
        approval_status=ApprovalStatus.APPROVED,
        approved_at=utc_now(),
        created_at=utc_now(),
    )
    repository.actions_by_analysis["analysis-3"] = (action,)

    source_run = ScriptRun(
        id="run-source-1",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="systemctl status sshd",
        shell_type=ShellType.SH,
        requires_tty=False,
        completed_at=utc_now(),
    )
    source_target = RunTargetResult(
        id="target-source-1",
        run_id="run-source-1",
        server_id="server-1",
        server_snapshot={"name": "web-01", "host": "192.0.2.10"},
        status=RunStatus.FAILED,
        exit_code=1,
    )
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
    launcher = FakeRunLauncher()
    service = DefaultAIAnalysisService(
        repository=repository,
        run_reader=FakeRunReader(source_run, (source_target,), ()),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=FakeProviderClient(AIProviderAnalysisResponse(summary="unused")),
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=launcher,
        publish_event=lambda event: None,
    )

    launch = service.execute_approved_action(
        ExecuteSuggestedActionRequest(action_id="action-3", initiated_by="user")
    )

    assert launch.run_id == "run-executed-1"
    assert launcher.last_request is not None
    assert launcher.last_request.run_kind is RunKind.AI_ACTION
    assert launcher.last_request.server_ids == ("server-1",)
    assert launcher.last_request.command_text == "journalctl -u sshd -n 50 --no-pager"
    assert launcher.last_request.shell_type is ShellType.SH
    assert launcher.last_request.requires_sudo is False
    assert launcher.last_request.requires_tty is False
    assert launcher.last_request.source_analysis_id == "analysis-3"
    assert launcher.last_request.source_action_id == "action-3"
    stored = repository.get_suggested_action("action-3")
    assert stored is not None
    assert stored.approval_status is ApprovalStatus.APPROVED
    assert stored.execution_run_id == "run-executed-1"


def test_ai_analysis_service_rejects_execution_of_unsafe_approved_action() -> None:
    repository = InMemoryAIRepository()
    repository.analyses["analysis-unsafe-exec"] = AIAnalysis(
        id="analysis-unsafe-exec",
        run_id="run-source-unsafe",
        provider_config_id="provider-1",
        status=AIAnalysisStatus.COMPLETED,
        summary="source analysis",
        created_at=utc_now(),
    )
    action = AISuggestedAction(
        id="action-unsafe-exec",
        analysis_id="analysis-unsafe-exec",
        title="Follow the logs",
        command_text="journalctl -u sshd -f",
        target_scope="web-01",
        risk_level=RiskLevel.WARNING,
        approval_status=ApprovalStatus.APPROVED,
        approved_at=utc_now(),
        created_at=utc_now(),
    )
    repository.actions_by_analysis["analysis-unsafe-exec"] = (action,)

    source_run = ScriptRun(
        id="run-source-unsafe",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="systemctl status sshd --no-pager",
        shell_type=ShellType.BASH,
        completed_at=utc_now(),
    )
    source_target = RunTargetResult(
        id="target-source-unsafe",
        run_id="run-source-unsafe",
        server_id="server-1",
        server_snapshot={"name": "web-01", "host": "192.0.2.10"},
        status=RunStatus.FAILED,
        exit_code=1,
    )
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
    launcher = FakeRunLauncher()
    service = DefaultAIAnalysisService(
        repository=repository,
        run_reader=FakeRunReader(source_run, (source_target,), ()),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=FakeProviderClient(AIProviderAnalysisResponse(summary="unused")),
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=launcher,
        publish_event=lambda event: None,
    )

    try:
        service.execute_approved_action(
            ExecuteSuggestedActionRequest(action_id="action-unsafe-exec", initiated_by="user")
        )
    except ValidationError as exc:
        assert "not allowed" in str(exc).lower() or "--no-pager" in str(exc)
    else:  # pragma: no cover - defensive failure path
        raise AssertionError("Expected ValidationError for unsafe approved action execution.")

    assert launcher.last_request is None


def test_ai_analysis_service_rejects_execution_of_nested_ssh_action() -> None:
    repository = InMemoryAIRepository()
    repository.analyses["analysis-nested-ssh"] = AIAnalysis(
        id="analysis-nested-ssh",
        run_id="run-source-nested-ssh",
        provider_config_id="provider-1",
        status=AIAnalysisStatus.COMPLETED,
        summary="source analysis",
        created_at=utc_now(),
    )
    action = AISuggestedAction(
        id="action-nested-ssh",
        analysis_id="analysis-nested-ssh",
        title="Connect to another host",
        command_text="ssh admin@192.0.2.15",
        target_scope="web-01",
        risk_level=RiskLevel.WARNING,
        approval_status=ApprovalStatus.APPROVED,
        approved_at=utc_now(),
        created_at=utc_now(),
    )
    repository.actions_by_analysis["analysis-nested-ssh"] = (action,)

    source_run = ScriptRun(
        id="run-source-nested-ssh",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="systemctl status sshd --no-pager",
        shell_type=ShellType.BASH,
        completed_at=utc_now(),
    )
    source_target = RunTargetResult(
        id="target-source-nested-ssh",
        run_id="run-source-nested-ssh",
        server_id="server-1",
        server_snapshot={"name": "web-01", "host": "192.0.2.10"},
        status=RunStatus.FAILED,
        exit_code=1,
    )
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
    launcher = FakeRunLauncher()
    service = DefaultAIAnalysisService(
        repository=repository,
        run_reader=FakeRunReader(source_run, (source_target,), ()),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=FakeProviderClient(AIProviderAnalysisResponse(summary="unused")),
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=launcher,
        publish_event=lambda event: None,
    )

    try:
        service.execute_approved_action(
            ExecuteSuggestedActionRequest(action_id="action-nested-ssh", initiated_by="user")
        )
    except ValidationError as exc:
        assert "nested ssh" in str(exc).lower() or "not allowed" in str(exc).lower()
    else:  # pragma: no cover - defensive failure path
        raise AssertionError("Expected ValidationError for nested SSH action execution.")

    assert launcher.last_request is None


def test_ai_analysis_service_rejects_execution_of_risky_ssh_remediation_action() -> None:
    repository = InMemoryAIRepository()
    repository.analyses["analysis-ssh-remediation"] = AIAnalysis(
        id="analysis-ssh-remediation",
        run_id="run-source-ssh-remediation",
        provider_config_id="provider-1",
        status=AIAnalysisStatus.COMPLETED,
        summary="source analysis",
        created_at=utc_now(),
    )
    action = AISuggestedAction(
        id="action-ssh-remediation",
        analysis_id="analysis-ssh-remediation",
        title="Restart SSH daemon",
        command_text="systemctl restart sshd",
        target_scope="web-01",
        risk_level=RiskLevel.WARNING,
        approval_status=ApprovalStatus.APPROVED,
        approved_at=utc_now(),
        created_at=utc_now(),
    )
    repository.actions_by_analysis["analysis-ssh-remediation"] = (action,)

    source_run = ScriptRun(
        id="run-source-ssh-remediation",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="systemctl status sshd --no-pager",
        shell_type=ShellType.BASH,
        completed_at=utc_now(),
    )
    source_target = RunTargetResult(
        id="target-source-ssh-remediation",
        run_id="run-source-ssh-remediation",
        server_id="server-1",
        server_snapshot={"name": "web-01", "host": "192.0.2.10"},
        status=RunStatus.FAILED,
        exit_code=1,
    )
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
    launcher = FakeRunLauncher()
    service = DefaultAIAnalysisService(
        repository=repository,
        run_reader=FakeRunReader(source_run, (source_target,), ()),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=FakeProviderClient(AIProviderAnalysisResponse(summary="unused")),
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=launcher,
        publish_event=lambda event: None,
    )

    try:
        service.execute_approved_action(
            ExecuteSuggestedActionRequest(action_id="action-ssh-remediation", initiated_by="user")
        )
    except ValidationError as exc:
        assert "ssh/sshd" in str(exc).lower() or "not allowed" in str(exc).lower()
    else:  # pragma: no cover - defensive failure path
        raise AssertionError("Expected ValidationError for risky SSH remediation execution.")

    assert launcher.last_request is None


def test_ai_analysis_service_executes_approved_fix_step_with_stored_privilege_flags() -> None:
    repository = InMemoryAIRepository()
    repository.analyses["analysis-5"] = AIAnalysis(
        id="analysis-5",
        run_id="run-source-5",
        provider_config_id="provider-1",
        status=AIAnalysisStatus.COMPLETED,
        summary="source analysis",
        created_at=utc_now(),
    )
    action = AISuggestedAction(
        id="action-5",
        analysis_id="analysis-5",
        title="Restart SSH daemon",
        command_text="sshd -t",
        target_scope="server-5",
        risk_level=RiskLevel.WARNING,
        requires_sudo=True,
        requires_tty=True,
        step_order=2,
        approval_status=ApprovalStatus.APPROVED,
        approved_at=utc_now(),
        created_at=utc_now(),
    )
    repository.actions_by_analysis["analysis-5"] = (action,)

    source_run = ScriptRun(
        id="run-source-5",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="systemctl status sshd --no-pager",
        shell_type=ShellType.BASH,
        requires_tty=False,
        completed_at=utc_now(),
    )
    source_target = RunTargetResult(
        id="target-source-5",
        run_id="run-source-5",
        server_id="server-5",
        server_snapshot={"name": "web-05", "host": "192.0.2.15"},
        status=RunStatus.FAILED,
        exit_code=1,
    )
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
    launcher = FakeRunLauncher()
    service = DefaultAIAnalysisService(
        repository=repository,
        run_reader=FakeRunReader(source_run, (source_target,), ()),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=FakeProviderClient(AIProviderAnalysisResponse(summary="unused")),
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=launcher,
        publish_event=lambda event: None,
    )

    service.execute_approved_action(
        ExecuteSuggestedActionRequest(action_id="action-5", initiated_by="user")
    )

    assert launcher.last_request is not None
    assert launcher.last_request.command_text == "sshd -t"
    assert launcher.last_request.requires_sudo is True
    assert launcher.last_request.requires_tty is True


def test_ai_analysis_service_infers_sudo_for_approved_action_execution() -> None:
    repository = InMemoryAIRepository()
    repository.analyses["analysis-4"] = AIAnalysis(
        id="analysis-4",
        run_id="run-source-2",
        provider_config_id="provider-1",
        status=AIAnalysisStatus.COMPLETED,
        summary="source analysis",
        created_at=utc_now(),
    )
    action = AISuggestedAction(
        id="action-4",
        analysis_id="analysis-4",
        title="Restart nginx",
        command_text="sudo systemctl restart nginx",
        target_scope="web-02",
        risk_level=RiskLevel.WARNING,
        approval_status=ApprovalStatus.APPROVED,
        approved_at=utc_now(),
        created_at=utc_now(),
    )
    repository.actions_by_analysis["analysis-4"] = (action,)

    source_run = ScriptRun(
        id="run-source-2",
        run_kind=RunKind.COMMAND,
        status=RunStatus.FAILED,
        command_snapshot="systemctl status nginx --no-pager",
        shell_type=ShellType.BASH,
        requires_tty=False,
        completed_at=utc_now(),
    )
    source_target = RunTargetResult(
        id="target-source-2",
        run_id="run-source-2",
        server_id="server-2",
        server_snapshot={"name": "web-02", "host": "192.0.2.11"},
        status=RunStatus.FAILED,
        exit_code=1,
    )
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
    launcher = FakeRunLauncher()
    service = DefaultAIAnalysisService(
        repository=repository,
        run_reader=FakeRunReader(source_run, (source_target,), ()),
        settings_repository=FakeSettingsRepository(provider_config),
        secret_store=MemorySecretStore({"openai-key": "sk-test"}),
        provider_client=FakeProviderClient(AIProviderAnalysisResponse(summary="unused")),
        prompt_builder=DefaultPromptBuilder(),
        run_launcher=launcher,
        publish_event=lambda event: None,
    )

    service.execute_approved_action(
        ExecuteSuggestedActionRequest(action_id="action-4", initiated_by="user")
    )

    assert launcher.last_request is not None
    assert launcher.last_request.requires_sudo is True
    assert launcher.last_request.requires_tty is True
