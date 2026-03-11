from __future__ import annotations

from pydantic import SecretStr

from admin_assistant.core.enums import (
    AIAnalysisStatus,
    ApprovalStatus,
    AuthType,
    HostKeyPolicy,
    RiskLevel,
    RunKind,
    RunStatus,
    ShellType,
)
from admin_assistant.core.time import utc_now
from admin_assistant.infrastructure.db.repositories.ai_repository_sqlalchemy import SqlAlchemyAIRepository
from admin_assistant.infrastructure.db.repositories.execution_repository_sqlalchemy import (
    SqlAlchemyExecutionRepository,
)
from admin_assistant.infrastructure.db.repositories.history_query_sqlalchemy import SqlAlchemyHistoryReadStore
from admin_assistant.infrastructure.db.repositories.script_repository_sqlalchemy import SqlAlchemyScriptRepository
from admin_assistant.infrastructure.db.repositories.server_repository_sqlalchemy import SqlAlchemyServerRepository
from admin_assistant.infrastructure.db.session import create_session_factory
from admin_assistant.modules.ai.models import AIAnalysis, AISuggestedAction
from admin_assistant.modules.execution.dto import CommandExecutionResult, RunRequest
from admin_assistant.modules.execution.service import DefaultExecutionService
from admin_assistant.modules.history.dto import AnalysisDetailsQuery, ConsoleReplayQuery, RunDetailsQuery, RunHistoryQuery
from admin_assistant.modules.history.service import DefaultHistoryQueryService
from admin_assistant.modules.servers.dto import ServerCreateRequest
from admin_assistant.modules.servers.models import Server
from admin_assistant.modules.servers.service import DefaultServerService


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def save_secret(self, key: str, value: str) -> str:
        self.values[key] = value
        return key

    def read_secret(self, key: str) -> str | None:
        return self.values.get(key)

    def delete_secret(self, key: str) -> None:
        self.values.pop(key, None)


class StubConnectivityProbe:
    def test_connection(self, server: Server, password: str | None = None, key_passphrase: str | None = None):
        raise NotImplementedError


class FakeExecutionGateway:
    def execute_manual_command(
        self,
        server: Server,
        command_text: str,
        shell_type: ShellType,
        requires_sudo: bool = False,
        requires_tty: bool = False,
        timeout_sec: int | None = None,
        password: str | None = None,
        key_passphrase: str | None = None,
    ) -> CommandExecutionResult:
        del server, shell_type, requires_sudo, requires_tty, timeout_sec, password, key_passphrase
        if "status sshd" in command_text:
            return CommandExecutionResult(
                stdout="checking sshd\n",
                stderr="sshd inactive\n",
                exit_code=3,
                completed_at=utc_now(),
                error_message="sshd inactive",
            )
        return CommandExecutionResult(
            stdout="sshd restarted\n",
            stderr="",
            exit_code=0,
            completed_at=utc_now(),
        )

    def execute_script(self, server: Server, script, password: str | None = None, key_passphrase: str | None = None):
        raise NotImplementedError


def test_history_queries_return_runs_output_and_ai_links(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'history.db').as_posix()}"
    session_factory = create_session_factory(database_url=database_url, create_schema=True)

    server_repository = SqlAlchemyServerRepository(session_factory=session_factory)
    script_repository = SqlAlchemyScriptRepository(session_factory=session_factory)
    execution_repository = SqlAlchemyExecutionRepository(session_factory=session_factory)
    ai_repository = SqlAlchemyAIRepository(session_factory=session_factory)
    history_store = SqlAlchemyHistoryReadStore(session_factory=session_factory)
    secret_store = MemorySecretStore()

    server_service = DefaultServerService(
        repository=server_repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )
    execution_service = DefaultExecutionService(
        repository=execution_repository,
        output_repository=execution_repository,
        server_reader=server_repository,
        script_reader=script_repository,
        secret_store=secret_store,
        ssh_gateway=FakeExecutionGateway(),
        publish_event=lambda event: None,
        task_runner=None,  # type: ignore[arg-type]
    )
    history_service = DefaultHistoryQueryService(read_store=history_store)

    created_server = server_service.create_server(
        ServerCreateRequest(
            name="web-01",
            host="192.0.2.10",
            username="root",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("pw-123"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )

    source_run = execution_service.start_run(
        RunRequest(
            run_kind=RunKind.COMMAND,
            server_ids=(created_server.id,),
            command_text="systemctl status sshd",
            shell_type=ShellType.BASH,
        )
    )
    executed_run = execution_service.start_run(
        RunRequest(
            run_kind=RunKind.AI_ACTION,
            server_ids=(created_server.id,),
            command_text="systemctl restart sshd",
            shell_type=ShellType.BASH,
            source_analysis_id="analysis-1",
            source_action_id="action-1",
        )
    )

    ai_repository.create_analysis(
        AIAnalysis(
            id="analysis-1",
            run_id=source_run.run_id,
            provider_config_id="provider-1",
            status=AIAnalysisStatus.COMPLETED,
            summary="SSHD is not running.",
            probable_causes=("Service stopped",),
            next_steps=("Restart the service",),
            created_at=utc_now(),
        )
    )
    ai_repository.create_suggested_actions(
        (
            AISuggestedAction(
                id="action-1",
                analysis_id="analysis-1",
                title="Restart SSHD",
                command_text="systemctl restart sshd",
                target_scope=created_server.id,
                risk_level=RiskLevel.WARNING,
                approval_status=ApprovalStatus.APPROVED,
                approved_at=utc_now(),
                execution_run_id=executed_run.run_id,
                created_at=utc_now(),
            ),
        )
    )

    run_page = history_service.list_runs(RunHistoryQuery())
    source_details = history_service.get_run_details(RunDetailsQuery(run_id=source_run.run_id))
    executed_details = history_service.get_run_details(RunDetailsQuery(run_id=executed_run.run_id))
    source_replay = history_service.get_console_replay(ConsoleReplayQuery(run_id=source_run.run_id))
    analysis_details = history_service.get_analysis_details(AnalysisDetailsQuery(analysis_id="analysis-1"))

    assert run_page.total_count >= 2
    assert {item.run_id for item in run_page.items} >= {source_run.run_id, executed_run.run_id}
    assert source_details.run_kind is RunKind.COMMAND
    assert source_details.target_count == 1
    assert len(source_details.analyses) == 1
    assert source_details.analyses[0].suggested_actions[0].execution_run_id == executed_run.run_id
    assert executed_details.run_kind is RunKind.AI_ACTION
    assert executed_details.source_analysis_id == "analysis-1"
    assert executed_details.source_action_id == "action-1"
    assert any("checking sshd" in line.chunk_text for line in source_replay.all_hosts_lines)
    assert analysis_details.id == "analysis-1"
    assert analysis_details.suggested_actions[0].execution_run_id == executed_run.run_id
